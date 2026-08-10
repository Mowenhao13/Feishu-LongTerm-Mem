"""
argusbot_v3 + ArgusBot 仓库 — 完整 MemoryEngine pipeline 端到端测试

全量消息一次性通过 ChatEpisodeManager 自动发现 episode 边界，
再逐个处理（MemoryExtractor Stage 1 → EntityStore → DecisionExtractor Stage 2），
同时注入 project context 和 Neo4j 历史记忆。

缓存机制:
  cache/01_episodes.json       — ChatEpisodeManager 自动发现的 episode
  cache/02_stage1/             — MemoryExtractor 的实体/关系/事实输出
  cache/02_stage2/             — DecisionExtractor 的决策输出
  cache/03_eval_cache.json     — LLM 评估结果缓存

用法:
    LANGFUSE_ENABLE=false uv run python scripts/run_e2e_pipeline_test.py
    LANGFUSE_ENABLE=false uv run python scripts/run_e2e_pipeline_test.py --no-neo4j  # 跳过 Neo4j
    LANGFUSE_ENABLE=false uv run python scripts/run_e2e_pipeline_test.py --re-eval  # 重跑评估
    LANGFUSE_ENABLE=false uv run python scripts/run_e2e_pipeline_test.py --force    # 强制重跑所有

输出:
    eval_results/e2e_pipeline_test_report.json
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
import pickle
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logger = logging.getLogger(__name__)

from src.model.llm_provider import LLMProvider
from src.extractors.simple_llm_extractor import SimpleLLMExtractor
from src.extractors.memory_extractor import MemoryExtractor
from src.extractors.project_types import (
    ProjectDevelopmentContext,
    ProjectFileChange,
)
from src.extractors.project_context_prompt import (
    PROJECT_CONTEXT_PROMPT,
    format_file_changes_for_prompt,
)
from src.storage.entity_store import EntityStore
from src.detect.project_watcher import ProjectWatcher
from src.detect.episode import ChatEpisodeManager, ChatMessage
from src.detect.suspend_pool import SuspendPool

ARGUSBOT_DIR = str(_REPO / "ref" / "ArgusBot")
ARGUSBOT_V3_DIR = str(_REPO / "eval_dataset" / "argusbot_v3")
REPORT_PATH = str(_REPO / "eval_results" / "e2e_pipeline_test_report.json")

CACHE_DIR = _REPO / "cache"
EPISODES_CACHE = CACHE_DIR / "01_episodes.json"
STAGE1_CACHE = CACHE_DIR / "stage1"
STAGE2_CACHE = CACHE_DIR / "stage2"
EVAL_CACHE_PATH = CACHE_DIR / "eval" / "03_eval_cache.json"

MAX_EPISODE_LENGTH = 20000

# 命令行参数
FORCE_RELOAD = "--force" in sys.argv
RE_EVAL = "--re-eval" in sys.argv or FORCE_RELOAD
SKIP_NEO4J = "--no-neo4j" in sys.argv
SAMPLE_LIMIT: Optional[int] = None


def _parse_args() -> None:
    global SAMPLE_LIMIT, FORCE_RELOAD, RE_EVAL, SKIP_NEO4J
    import argparse
    parser = argparse.ArgumentParser(description="argusbot_v3 E2E pipeline test")
    parser.add_argument("--sample", type=int, default=0, help="只处理前 N 个 chat (默认全部)")
    parser.add_argument("--force", action="store_true", help="强制重跑所有阶段")
    parser.add_argument("--re-eval", action="store_true", help="只重跑评估")
    parser.add_argument("--no-neo4j", action="store_true", help="跳过 Neo4j")
    args = parser.parse_args()
    if args.sample > 0:
        SAMPLE_LIMIT = args.sample
    if args.force:
        FORCE_RELOAD = True
        RE_EVAL = True
    if args.re_eval:
        RE_EVAL = True
    if args.no_neo4j:
        SKIP_NEO4J = True
    SKIP_NEO4J = SKIP_NEO4J or FORCE_RELOAD  # force 模式等同于 no-neo4j


_parse_args()


def _iso_to_ts(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return time.time()


# ==================== 数据集加载 ====================

def load_all_messages() -> Tuple[List[dict], dict, int]:
    messages_path = Path(ARGUSBOT_V3_DIR) / "messages.jsonl"
    all_msgs = []
    chat_topic_map = {}
    expected_count = 0
    with open(messages_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msg = json.loads(line)
                ts = msg.get("timestamp", "")
                msg["_ts"] = _iso_to_ts(ts) if isinstance(ts, str) else float(ts)
                all_msgs.append(msg)
                chat_topic_map[msg["chat_id"]] = msg.get("topic", "")
                if msg.get("expected_decision") is True or str(msg.get("expected_decision", "")).lower() == "true":
                    expected_count += 1
    all_msgs.sort(key=lambda m: m["_ts"])
    return all_msgs, chat_topic_map, expected_count


# ==================== LLM / Extractor 初始化 ====================

def init_llm_and_extractors() -> Tuple[LLMProvider, SimpleLLMExtractor, MemoryExtractor, EntityStore]:
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
    model = os.getenv("MODEL_NAME", "deepseek-chat")
    provider = LLMProvider(
        provider_type="openai",
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_tokens=4096,
        enable_stats=False,
    )
    decision_extractor = SimpleLLMExtractor(provider)
    memory_extractor = MemoryExtractor(
        llm_provider=provider,
        confidence_threshold=0.5,
    )
    entity_store = EntityStore()
    return provider, decision_extractor, memory_extractor, entity_store


async def build_project_context() -> ProjectDevelopmentContext:
    pw = ProjectWatcher(ARGUSBOT_DIR)
    snapshot = await pw.take_snapshot()
    recent_py = [f for f in snapshot.recent_files if f.endswith(".py")][:5]
    ctx = ProjectDevelopmentContext(
        recent_changes=[
            ProjectFileChange(
                file_path=f, change_type="modified",
                content_hash=f"h{i}", extension=".py",
                language="Python",
                diff_summary="+50 lines; -15 lines",
                timestamp=time.time(), size_bytes=3000,
            ) for i, f in enumerate(recent_py)
        ],
        detected_at=time.time(),
    )
    ctx.linked_conversation_snippets = ["Related keywords: codex, loop, agent, feishu, adapter, test"]
    return ctx


# ==================== Pipeline 处理 ====================

def _episode_cache_key(episode_id: str, suffix: str = "with") -> Path:
    return STAGE2_CACHE / f"{episode_id}_{suffix}.json"


def _stage1_cache_key(episode_id: str) -> Path:
    return STAGE1_CACHE / f"{episode_id}.json"


async def run_v2_pipeline(
    episode: Any,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    trace_id: str = "",
    neo4j_sync: Optional[Any] = None,
    force: bool = False,
) -> dict:
    content = getattr(episode, "full_text", "") or getattr(episode, "content", "")
    episode_id = getattr(episode, "id", "") or getattr(episode, "episode_id", "")
    chat_id = getattr(episode, "chat_id", "")

    if not content:
        return {"episode_id": episode_id, "chat_id": chat_id, "ok": False, "reason": "empty"}
    if len(content) > MAX_EPISODE_LENGTH:
        content = content[:MAX_EPISODE_LENGTH]

    n_expected = getattr(episode, "n_expected", 0)
    message_count = getattr(episode, "message_count", 0)

    # ── 瓶颈检测：初始化诊断字段 ──
    historical_entity_ctx: List = []
    history_decisions: List = []
    stage0_time: float = 0.0
    stage2_entities: List = []

    # ── 检查 Stage 1 缓存 ──
    stage1_cache_path = _stage1_cache_key(episode_id)
    mem_result = None
    if not force and stage1_cache_path.exists():
        try:
            with open(stage1_cache_path, "r", encoding="utf-8") as f:
                stage1_data = json.load(f)
            mem_result = _load_stage1_from_cache(stage1_data)
            logger.info("[E2E] Cache HIT: stage1 for %s", episode_id[:12])
        except Exception:
            pass

    if mem_result is None:
        if trace_id and hasattr(memory_extractor, "set_trace_id"):
            memory_extractor.set_trace_id(trace_id)

        # ── Stage 0: 从 Neo4j 获取全局历史上下文 ──
        historical_entity_ctx = []
        history_decisions = []
        stage0_time = 0.0
        if neo4j_sync is not None:
            t0_stage0 = time.time()
            try:
                historical_entity_ctx = await neo4j_sync.get_all_entity_context(limit=200)
                history_decisions = await neo4j_sync.get_all_decisions_context(limit=50)
            except Exception:
                pass
            stage0_time = time.time() - t0_stage0

        # ── Stage 1 ──
        t0 = time.time()
        local_ctx = entity_store.build_extraction_context()
        seen_names = {e["name"] for e in local_ctx}
        merged_ctx = list(local_ctx)
        for he in historical_entity_ctx:
            if he.get("name") and he["name"] not in seen_names:
                seen_names.add(he["name"])
                merged_ctx.append(he)

        mem_result = await memory_extractor.extract(
            content, episode_id=episode_id, existing_entities=merged_ctx,
        )
        stage1_time = time.time() - t0

        entity_store.add_entities(mem_result.entities)
        entity_store.add_relationships(mem_result.relationships)
        entity_store.add_facts(mem_result.facts)

        # 缓存 Stage 1
        STAGE1_CACHE.mkdir(parents=True, exist_ok=True)
        with open(stage1_cache_path, "w", encoding="utf-8") as f:
            json.dump(_dump_stage1(mem_result), f, ensure_ascii=False)

        if neo4j_sync is not None:
            asyncio.create_task(
                neo4j_sync.sync_all(entity_store=entity_store),
                name=f"neo4j-sync-{episode_id[:12] if episode_id else '?'}",
            )

        n_entities = len(mem_result.entities)
        n_rels = len(mem_result.relationships)
        n_facts = len(mem_result.facts)
    else:
        stage1_time = 0
        n_entities = len(mem_result.entities)
        n_rels = len(mem_result.relationships)
        n_facts = len(mem_result.facts)
        entity_store.add_entities(mem_result.entities)
        entity_store.add_relationships(mem_result.relationships)
        entity_store.add_facts(mem_result.facts)

    # ── Stage 2: 检查缓存 ──
    def _try_cache(suffix: str) -> Optional[List[dict]]:
        p = _episode_cache_key(episode_id, suffix)
        if not force and p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    # ── Stage 2: with project context ──
    stage2_entities = [{"name": e.name, "entity_type": e.entity_type} for e in mem_result.entities]
    cached_with = _try_cache("with")
    if cached_with is not None:
        decisions_with = cached_with
        stage2_time_with = 0
        logger.info("[E2E] Cache HIT: stage2 with for %s", episode_id[:12])
    else:
        t0 = time.time()
        if trace_id and hasattr(decision_extractor, "set_trace_id"):
            decision_extractor.set_trace_id(trace_id)
        decisions_with = await decision_extractor.extract_with_context(
            content, entity_context=stage2_entities, project_context=project_ctx,
        )
        stage2_time_with = time.time() - t0
        STAGE2_CACHE.mkdir(parents=True, exist_ok=True)
        with open(_episode_cache_key(episode_id, "with"), "w", encoding="utf-8") as f:
            json.dump(decisions_with or [], f, ensure_ascii=False)

    # ── Stage 2: without project context ──
    cached_without = _try_cache("without")
    if cached_without is not None:
        decisions_without = cached_without
        stage2_time_without = 0
        logger.info("[E2E] Cache HIT: stage2 without for %s", episode_id[:12])
    else:
        t0 = time.time()
        decisions_without = await decision_extractor.extract_with_context(
            content, entity_context=stage2_entities,
        )
        stage2_time_without = time.time() - t0
        STAGE2_CACHE.mkdir(parents=True, exist_ok=True)
        with open(_episode_cache_key(episode_id, "without"), "w", encoding="utf-8") as f:
            json.dump(decisions_without or [], f, ensure_ascii=False)

    return {
        "chat_id": chat_id,
        "episode_id": episode_id,
        "message_count": message_count,
        "n_expected": n_expected,
        "stage1": {
            "entities": n_entities, "relationships": n_rels, "facts": n_facts,
            "time_sec": round(stage1_time, 1),
        },
        "stage2": {
            "with_project": {
                "decisions": len(decisions_with) if decisions_with else 0,
                "decision_titles": [d.get("title", d.get("summary", "")) for d in (decisions_with or [])],
                "time_sec": round(stage2_time_with, 1),
            },
            "without_project": {
                "decisions": len(decisions_without) if decisions_without else 0,
                "decision_titles": [d.get("title", d.get("summary", "")) for d in (decisions_without or [])],
                "time_sec": round(stage2_time_without, 1),
            },
        },
        "entities_detail": [
            {"name": e.name, "type": e.entity_type, "confidence": round(e.confidence, 2)}
            for e in mem_result.entities
        ],
        # ── 瓶颈检测诊断 ──
        "diagnostics": {
            "stage0": {
                "neo4j_entities": len(historical_entity_ctx) if not force else 0,
                "neo4j_decisions": len(history_decisions) if not force else 0,
                "latency_sec": round(stage0_time, 2) if not force else 0.0,
            },
            "stage1": {
                "entities": n_entities,
                "entity_names": [e.name for e in mem_result.entities],
                "relationships": n_rels,
                "facts": n_facts,
                "avg_entity_confidence": round(
                    sum(e.confidence for e in mem_result.entities) / n_entities, 3
                ) if n_entities > 0 else 0.0,
                "latency_sec": round(stage1_time, 2),
            },
            "stage2": {
                "entities_in_context": len(stage2_entities),
                "has_project_context": project_ctx is not None and hasattr(project_ctx, "significant_changes") and len(project_ctx.significant_changes) > 0,
                "project_file_changes": len(getattr(project_ctx, "recent_changes", [])) if project_ctx else 0,
                "decisions_with_project": len(decisions_with) if decisions_with else 0,
                "decisions_without_project": len(decisions_without) if decisions_without else 0,
                "latency_sec_with": round(stage2_time_with, 2),
                "latency_sec_without": round(stage2_time_without, 2),
            },
        },
        "ok": True,
    }


def _dump_stage1(mem_result: Any) -> dict:
    return {
        "entities": [{"name": e.name, "entity_type": e.entity_type, "confidence": e.confidence} for e in mem_result.entities],
        "relationships": [{"source_name": r.source_name, "relationship_type": r.relationship_type, "target_name": r.target_name, "confidence": r.confidence} for r in mem_result.relationships],
        "facts": [{"content": f.content, "confidence": f.confidence, "related_entity_names": f.related_entity_names} for f in mem_result.facts],
    }


def _load_stage1_from_cache(data: dict) -> Any:
    from src.extractors.memory_types import MemoryExtractionResult, ExtractedEntity, ExtractedRelationship, ExtractedFact
    result = MemoryExtractionResult()
    for e in data.get("entities", []):
        result.entities.append(ExtractedEntity(name=e["name"], entity_type=e["entity_type"], confidence=e.get("confidence", 0)))
    for r in data.get("relationships", []):
        result.relationships.append(ExtractedRelationship(source_name=r["source_name"], relationship_type=r["relationship_type"], target_name=r["target_name"], confidence=r.get("confidence", 0)))
    for f in data.get("facts", []):
        result.facts.append(ExtractedFact(content=f["content"], confidence=f.get("confidence", 0), related_entity_names=f.get("related_entity_names", [])))
    return result


# ==================== Watcher ====================

async def test_watcher_and_snapshot() -> dict:
    from src.detect.project_detector import ProjectDetector
    from src.detect.conv_file_bridge import ConversationFileBridge, ConvFileBridgeLevel
    bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD)
    detector = ProjectDetector(ARGUSBOT_DIR, bridge=bridge, watcher_debounce=0.5)
    await detector.start()
    await asyncio.sleep(0.3)
    snapshot = await detector._watcher.take_snapshot()
    await detector.stop()
    return {"snapshot_files": snapshot.total_files, "snapshot_py_files": snapshot.file_type_counts.get(".py", 0), "watcher_available": True}


# ==================== LLM 评估 ====================

LLM_EVAL_PROMPT = """你是一个决策提取评估助手。判断一条"提取决策"是否与对应的"期望决策"语义等价。

期望决策: {expected}
提取决策: {extracted}

请判断：
- 如果提取决策与期望决策表达了**相同或等价的技术决策**（只是表述不同可以接受），返回 true
- 如果提取决策与期望决策**不同**，返回 false
- 如果提取决策是期望决策的**细化或子决策**，返回 true
- 如果提取决策与期望决策**部分重叠**（有交叉但不是完全一样），返回 true，因为说明系统捕捉到了相关信号

只返回 JSON: {{"match": true/false, "reason": "简短理由"}}"""


async def llm_judge_match(llm_provider: Any, expected: str, extracted: str) -> Tuple[bool, str]:
    """用 LLM 判断两条决策是否语义匹配。"""
    prompt = LLM_EVAL_PROMPT.format(expected=expected, extracted=extracted)
    try:
        resp = await llm_provider.generate(
            prompt,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.strip())
        return bool(data.get("match", False)), data.get("reason", "")
    except Exception as e:
        logger.warning("[LLM Judge] Error: %s", e)
        return False, f"LLM error: {e}"


# ==================== 主测试流程 ====================

async def main() -> None:
    print("=" * 60)
    print("argusbot_v3 + ArgusBot — MemoryEngine Pipeline E2E 测试")
    print("=" * 60)

    # ── Step 1: 加载全量消息 ──
    all_messages, chat_topic_map, total_expected = load_all_messages()
    total_chats = len(set(m["chat_id"] for m in all_messages))
    print(f"数据集: {len(all_messages)} 条消息, {total_chats} 个 chat, {total_expected} 个期望决策")

    if SAMPLE_LIMIT and SAMPLE_LIMIT < total_chats:
        seen = set()
        filtered = []
        for m in all_messages:
            if m["chat_id"] not in seen:
                seen.add(m["chat_id"])
                if len(seen) > SAMPLE_LIMIT:
                    continue
            if m["chat_id"] in seen:
                filtered.append(m)
        all_messages = filtered
        print(f"  (--sample={SAMPLE_LIMIT})")

    # ── Step 2: Watcher ──
    print("\n[1/4] ProjectWatcher 验证...")
    watcher_info = await test_watcher_and_snapshot()
    print(f"  快照: {watcher_info['snapshot_files']} 文件, {watcher_info['snapshot_py_files']} 个 .py")

    api_key = os.getenv("API_KEY", "")
    if not api_key:
        print("\n⚠️  无 API_KEY，跳过 LLM 提取")
        return

    provider, decision_extractor, memory_extractor, entity_store = init_llm_and_extractors()
    project_ctx = await build_project_context()
    print(f"\n[2/4] 全量消息注入 ChatEpisodeManager ({len(all_messages)} 条消息)...")
    for c in project_ctx.recent_changes:
        print(f"    - {c.file_path}")

    # ── Neo4j ──
    neo4j_sync = None
    if not SKIP_NEO4J:
        try:
            from src.storage.neo4j_client import Neo4jClient as _Neo4jClient
            from src.storage.neo4j_sync import Neo4jSyncEngine as _Neo4jSyncEngine
            _nc = _Neo4jClient(
                uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                user=os.getenv("NEO4J_USER", "neo4j"),
                password=os.getenv("NEO4J_PASSWORD", "password123"),
            )
            await _nc.connect()
            neo4j_sync = _Neo4jSyncEngine(client=_nc)
            print(f"  [Neo4j] Connected")
        except Exception as e:
            print(f"  [Neo4j] Not available: {e}")

    # ── 通过 ChatEpisodeManager 自动发现 episode ──
    if not FORCE_RELOAD and EPISODES_CACHE.exists():
        with open(EPISODES_CACHE, "r", encoding="utf-8") as f:
            cached = json.load(f)
        unique_eps_cache = cached.get("episodes", [])
        # 重建为 EpisodeWrapper 对象
        class EpisodeWrapper:
            def __init__(self, d):
                self.chat_id = d.get("chat_id", "")
                self.id = d.get("id", "")
                self.full_text = d.get("full_text", "")
                self.content = d.get("full_text", "")
                self.message_count = d.get("message_count", 0)
                self.n_expected = d.get("n_expected", 0)
        unique_eps = [EpisodeWrapper(d) for d in unique_eps_cache]
        msg_count = cached.get("msg_count", 0)
        print(f"  [Cache] Episodes loaded from cache ({len(unique_eps)} episodes)")
    else:
        pool = SuspendPool()
        episode_manager = ChatEpisodeManager(pool=pool)
        msg_count = 0
        for raw in all_messages:
            msg_text = raw.get("msg", raw.get("content", ""))
            if not msg_text:
                continue
            msg_obj = ChatMessage(
                chat_id=raw["chat_id"],
                sender_id=raw.get("speaker", raw.get("sender", "?")),
                content=msg_text,
                timestamp=raw["_ts"],
                message_id=f"msg_{msg_count}",
            )
            episode_manager.add_message(msg_obj)
            msg_count += 1

        await asyncio.sleep(1)
        discovered = []
        for ep in episode_manager.check_all_timeouts():
            discovered.append(ep)
        for ep in episode_manager.drain_suspended_episodes():
            discovered.append(ep)
        for ep in episode_manager.close_all():
            discovered.append(ep)

        seen_ids = set()
        unique_eps = []
        for ep in discovered:
            eid = getattr(ep, "id", "") or getattr(ep, "episode_id", "")
            if eid not in seen_ids:
                seen_ids.add(eid)
                unique_eps.append(ep)

        # 缓存 episodes
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ep_cache_data = [{
            "chat_id": getattr(ep, "chat_id", ""),
            "id": getattr(ep, "id", "") or getattr(ep, "episode_id", ""),
            "full_text": getattr(ep, "full_text", "") or getattr(ep, "content", ""),
            "message_count": getattr(ep, "message_count", 0),
            "n_expected": getattr(ep, "n_expected", 0),
        } for ep in unique_eps]
        with open(EPISODES_CACHE, "w", encoding="utf-8") as f:
            json.dump({"episodes": ep_cache_data, "msg_count": msg_count}, f, ensure_ascii=False)

        print(f"  ChatEpisodeManager 发现 {len(unique_eps)} 个 episode (已缓存)")

    for ep in unique_eps[:3]:
        print(f"    - {getattr(ep, 'id', '?')[:16]} chat={getattr(ep, 'chat_id', '?')[:20]} msgs={getattr(ep, 'message_count', '?')}")
    if len(unique_eps) > 3:
        print(f"    ... 还有 {len(unique_eps) - 3} 个")

    # ── 处理 episode ──
    print(f"\n  处理 {len(unique_eps)} 个 episode（缓存已启用）...")
    episode_results = []
    t_start = time.time()

    for i, ep in enumerate(unique_eps):
        trace_id = f"e2e_{i}_{int(time.time())}"
        result = await run_v2_pipeline(
            ep, memory_extractor, decision_extractor, entity_store,
            project_ctx=project_ctx, trace_id=trace_id,
            neo4j_sync=neo4j_sync, force=FORCE_RELOAD,
        )
        episode_results.append(result)
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(unique_eps)}] 完成")

    llm_elapsed = time.time() - t_start

    if neo4j_sync is not None:
        await asyncio.sleep(3)

    # ── 统计 ──
    stats = {"total_episodes": 0, "ok": 0, "failed": 0, "decisions_with": 0, "decisions_without": 0,
             "expected_total": 0, "entities_total": 0, "total_time": 0.0, "details": []}
    for r in episode_results:
        stats["total_episodes"] += 1
        if not r.get("ok"):
            stats["failed"] += 1; continue
        stats["ok"] += 1
        stats["expected_total"] += r.get("n_expected", 0)
        stats["entities_total"] += r["stage1"]["entities"]
        stats["decisions_with"] += r["stage2"]["with_project"]["decisions"]
        stats["decisions_without"] += r["stage2"]["without_project"]["decisions"]
        stats["total_time"] += r["stage1"]["time_sec"] + r["stage2"]["with_project"]["time_sec"] + r["stage2"]["without_project"]["time_sec"]
        if r["stage2"]["with_project"]["decisions"] != r["stage2"]["without_project"]["decisions"]:
            stats["details"].append(r)

    print(f"  完成: {stats['total_episodes']} 个 episode, {llm_elapsed:.0f}s 总耗时")
    print(f"  成功: {stats['ok']}, 失败: {stats['failed']}")

    es_counts = entity_store.count()

    # ── LLM 评估 ──
    print(f"\n[3/4] LLM 评估: 与 ground truth 对比...")
    expected_path = Path(ARGUSBOT_V3_DIR) / "expected.jsonl"
    gt_entries = []
    if expected_path.exists():
        with open(expected_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    gt_entries.append(json.loads(line))
    print(f"  加载 {len(gt_entries)} 条 ground truth")

    gt_by_chat = defaultdict(list)
    for gt in gt_entries:
        gt_by_chat[gt["chat_id"]].append(gt)

    # 检查评估缓存
    eval_cache = {}
    if EVAL_CACHE_PATH.exists() and not RE_EVAL:
        try:
            with open(EVAL_CACHE_PATH, "r", encoding="utf-8") as f:
                eval_cache = json.load(f)
            print(f"  [Cache] 加载 {len(eval_cache)} 条评估结果")
        except Exception:
            pass

    total_tp_with, total_fp_with, total_fn_with = 0, 0, 0
    total_tp_without, total_fp_without, total_fn_without = 0, 0, 0

    for cid, gts in gt_by_chat.items():
        gt_texts = [g.get("expected_summary", "") for g in gts if g.get("expected_summary")]
        ext_with = []
        ext_without = []
        for r in episode_results:
            if r.get("chat_id") == cid and r.get("ok"):
                ext_with.extend(r["stage2"]["with_project"].get("decision_titles", []))
                ext_without.extend(r["stage2"]["without_project"].get("decision_titles", []))

        # 逐条 LLM 判断 — with
        gt_matched_with = [False] * len(gt_texts)
        ext_matched_with = [False] * len(ext_with)
        for ei, ext_title in enumerate(ext_with):
            if not ext_title:
                continue
            for gi, gt_text in enumerate(gt_texts):
                if gt_matched_with[gi]:
                    continue
                cache_key = f"with:{cid}:{gi}:{ei}"
                if cache_key in eval_cache:
                    match = eval_cache[cache_key]
                else:
                    match, _ = await llm_judge_match(provider, gt_text, ext_title)
                    eval_cache[cache_key] = match
                if match:
                    ext_matched_with[ei] = True
                    gt_matched_with[gi] = True
                    break

        total_tp_with += sum(gt_matched_with)
        total_fp_with += sum(1 for m in ext_matched_with if not m)
        total_fn_with += sum(1 for m in gt_matched_with if not m)

        # 逐条 LLM 判断 — without
        gt_matched_without = [False] * len(gt_texts)
        ext_matched_without = [False] * len(ext_without)
        for ei, ext_title in enumerate(ext_without):
            if not ext_title:
                continue
            for gi, gt_text in enumerate(gt_texts):
                if gt_matched_without[gi]:
                    continue
                cache_key = f"without:{cid}:{gi}:{ei}"
                if cache_key in eval_cache:
                    match = eval_cache[cache_key]
                else:
                    match, _ = await llm_judge_match(provider, gt_text, ext_title)
                    eval_cache[cache_key] = match
                if match:
                    ext_matched_without[ei] = True
                    gt_matched_without[gi] = True
                    break

        total_tp_without += sum(gt_matched_without)
        total_fp_without += sum(1 for m in ext_matched_without if not m)
        total_fn_without += sum(1 for m in gt_matched_without if not m)

    # 保存评估缓存
    EVAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(eval_cache, f, ensure_ascii=False)
    print(f"  [Cache] 评估结果已保存 ({len(eval_cache)} 条)")

    precision_with = total_tp_with / (total_tp_with + total_fp_with) if (total_tp_with + total_fp_with) > 0 else 0
    recall_with = total_tp_with / (total_tp_with + total_fn_with) if (total_tp_with + total_fn_with) > 0 else 0
    f1_with = 2 * precision_with * recall_with / (precision_with + recall_with) if (precision_with + recall_with) > 0 else 0
    precision_without = total_tp_without / (total_tp_without + total_fp_without) if (total_tp_without + total_fp_without) > 0 else 0
    recall_without = total_tp_without / (total_tp_without + total_fn_without) if (total_tp_without + total_fn_without) > 0 else 0
    f1_without = 2 * precision_without * recall_without / (precision_without + recall_without) if (precision_without + recall_without) > 0 else 0
    fpr_with = total_fp_with / (total_fp_with + total_tp_with) * 100 if (total_fp_with + total_tp_with) > 0 else 0
    fpr_without = total_fp_without / (total_fp_without + total_tp_without) * 100 if (total_fp_without + total_tp_without) > 0 else 0

    print(f"  评估方法: LLM 语义等价判断")
    print(f"  ┌──────────────────────────────────────────────┐")
    print(f"  │  评估结果 (LLM 逐条比对)                     │")
    print(f"  ├──────────────────────┬──────────┬──────────┤")
    print(f"  │               │ 有project │ 无project │")
    print(f"  ├──────────────────┼──────────┼──────────┤")
    print(f"  │ Ground Truth     │ {len(gt_entries):>8} │ {len(gt_entries):>8} │")
    print(f"  │ 实际提取         │ {stats['decisions_with']:>8} │ {stats['decisions_without']:>8} │")
    print(f"  │ True Positive    │ {total_tp_with:>8} │ {total_tp_without:>8} │")
    print(f"  │ False Positive   │ {total_fp_with:>8} │ {total_fp_without:>8} │")
    print(f"  │ False Negative   │ {total_fn_with:>8} │ {total_fn_without:>8} │")
    print(f"  ├──────────────────┼──────────┼──────────┤")
    print(f"  │ Precision        │ {precision_with:>7.1%} │ {precision_without:>7.1%} │")
    print(f"  │ Recall           │ {recall_with:>7.1%} │ {recall_without:>7.1%} │")
    print(f"  │ F1               │ {f1_with:>7.1%} │ {f1_without:>7.1%} │")
    print(f"  │ 误检率(FPR)      │ {fpr_with:>6.1f}% │ {fpr_without:>6.1f}% │")
    print(f"  └──────────────────────┴──────────┴──────────┘")

    # ── 构建报告 ──
    print(f"\n[4/4] 构建报告...")
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {"dataset": "argusbot_v3", "project_dir": ARGUSBOT_DIR,
                    "pipeline": "v2 (ChatEpisodeManager → MemoryExtractor → EntityStore → DecisionExtractor)",
                    "total_messages_injected": msg_count},
        "dataset": {"total_messages": len(all_messages), "total_chats": total_chats,
                     "expected_decisions": total_expected, "episodes_auto_discovered": len(unique_eps)},
        "watcher": watcher_info,
        "entity_store": {"total_entities": es_counts["entities"], "total_relationships": es_counts["relationships"], "total_facts": es_counts["facts"]},
        "llm": stats,
        "evaluation": {
            "method": "llm_judge",
            "cache_size": len(eval_cache),
            "with_project": {"extracted": stats["decisions_with"], "true_positives": total_tp_with, "false_positives": total_fp_with, "false_negatives": total_fn_with,
                             "precision": round(precision_with, 4), "recall": round(recall_with, 4), "f1": round(f1_with, 4), "false_positive_rate": round(fpr_with / 100, 4)},
            "without_project": {"extracted": stats["decisions_without"], "true_positives": total_tp_without, "false_positives": total_fp_without, "false_negatives": total_fn_without,
                                "precision": round(precision_without, 4), "recall": round(recall_without, 4), "f1": round(f1_without, 4), "false_positive_rate": round(fpr_without / 100, 4)},
        },
        "per_episode": [{k: v for k, v in r.items() if k != "entities_detail"} for r in episode_results],
    }

    Path(REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("测试摘要")
    print("=" * 60)
    print(f"数据集: {len(all_messages)} 消息 / {total_chats} chat")
    print(f"Watcher: {watcher_info['snapshot_files']} 文件")
    print(f"自动发现: {len(unique_eps)} 个 episode")
    print(f"EntityStore: {es_counts['entities']} 实体, {es_counts['relationships']} 关系, {es_counts['facts']} 事实")
    print(f"LLM: {stats['ok']}/{stats['total_episodes']} 成功")
    print(f"  有 project context: {stats['decisions_with']} 条")
    print(f"  无 project context: {stats['decisions_without']} 条")
    print(f"\n报告已保存: {REPORT_PATH}")

    if neo4j_sync is not None:
        try:
            from src.storage.neo4j_client import Neo4jClient as _Neo4jClient
            _nc = _Neo4jClient(password="password123")
            await _nc.connect()
            async with _nc._session() as s:
                for q, label in [
                    ('MATCH (e:Entity) RETURN count(e) AS c', "Entity"),
                    ('MATCH ()-[:MENTIONS]->() RETURN count(*) AS c', "MENTIONS"),
                    ('MATCH ()-[:RELATES]->() RETURN count(*) AS c', "RELATES"),
                ]:
                    row = await (await s.run(q)).single()
                    print(f"  Neo4j {label}: {row['c']}")
            await _nc.close()
        except Exception as e:
            print(f"  Neo4j stats: {e}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())