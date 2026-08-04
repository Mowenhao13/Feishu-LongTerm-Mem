"""argusbot_v3 + ArgusBot 仓库 — 完整 MemoryEngine pipeline 端到端测试

遍历 argusbot_v3 全部 chat，通过实际 MemoryEngine pipeline 处理：
1. 对每个 chat 构建 episode 对象
2. 通过 _process_episode_v2 处理（MemoryExtractor Stage 1 → EntityStore → DecisionExtractor Stage 2）
3. 跟踪实体累计和 hypergraph 构建
4. 对比有/无 project context
5. 写入详细报告到 eval_results/

用法:
    LANGFUSE_ENABLE=false uv run python scripts/run_e2e_pipeline_test.py

输出:
    eval_results/e2e_pipeline_test_report.json

需要环境变量: API_KEY, BASE_URL, MODEL_NAME
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

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
from src.graph.builder import HypergraphBuilder
from src.structure import Hypergraph

ARGUSBOT_DIR = str(_REPO / "ref" / "ArgusBot")
ARGUSBOT_V3_DIR = str(_REPO / "eval_dataset" / "argusbot_v3")
REPORT_PATH = str(_REPO / "eval_results" / "e2e_pipeline_test_report.json")

MAX_MSGS_PER_CHAT = 20
MAX_LLM_CONCURRENCY = 4  # 降低并发，因为每个 episode 需要 3 次 LLM 调用 (1 Stage 1 + 2 Stage 2)

# 通过命令行参数控制：--sample N 只跑前 N 个 chat
SAMPLE_LIMIT: Optional[int] = None


def _parse_args() -> None:
    global SAMPLE_LIMIT
    import argparse
    parser = argparse.ArgumentParser(description="argusbot_v3 E2E pipeline test")
    parser.add_argument("--sample", type=int, default=0,
                        help="只处理前 N 个 chat (默认全部)")
    args = parser.parse_args()
    if args.sample > 0:
        SAMPLE_LIMIT = args.sample


_parse_args()


# ==================== Episode wrapper (适配 _process_episode_v2 接口) ====================

class EpisodeWrapper:
    """模拟 MemoryEngine._process_episode_v2 要求的 episode 对象接口"""

    def __init__(self, chat_id: str, episode_id: str, full_text: str, message_count: int):
        self.chat_id = chat_id
        self.id = episode_id
        self.full_text = full_text
        self.content = full_text
        self.message_count = message_count


# ==================== 数据集加载 ====================

def load_dataset() -> dict:
    """加载 messages.jsonl，按 chat_id 分组并排序。"""
    chats = defaultdict(list)
    messages_path = Path(ARGUSBOT_V3_DIR) / "messages.jsonl"
    with open(messages_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msg = json.loads(line)
                chats[msg["chat_id"]].append(msg)
    for cid in chats:
        chats[cid].sort(key=lambda m: m.get("timestamp", ""))
    return {
        "chats": dict(chats),
        "total_messages": sum(len(v) for v in chats.values()),
        "total_chats": len(chats),
    }


def build_episodes(chat_id: str, messages: list) -> List[dict]:
    """从一组消息构建 episode。"""
    msgs = messages[:MAX_MSGS_PER_CHAT]
    lines = []
    n_expected = 0
    for m in msgs:
        speaker = m.get("speaker", "?")
        text = m.get("msg", "")
        lines.append(f"{speaker}: {text}")
        exp = m.get("expected_decision", "False")
        if exp is True or str(exp).lower() == "true":
            n_expected += 1
    return [{
        "chat_id": chat_id,
        "episode_id": f"argus_{chat_id[:16]}",
        "message_count": len(msgs),
        "n_expected": n_expected,
        "conversation_text": "\n".join(lines),
        "topics": list({m.get("topic", "") for m in msgs}),
    }]


# ==================== LLM / Extractor 初始化 ====================

def init_llm_and_extractors() -> Tuple[LLMProvider, SimpleLLMExtractor, MemoryExtractor, EntityStore]:
    """初始化 LLM provider 和所有 extractor。"""
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
    """用 ArgusBot 仓库真实文件构建 project context。"""
    pw = ProjectWatcher(ARGUSBOT_DIR)
    snapshot = await pw.take_snapshot()
    recent_py = [f for f in snapshot.recent_files if f.endswith(".py")][:5]

    ctx = ProjectDevelopmentContext(
        recent_changes=[
            ProjectFileChange(
                file_path=f,
                change_type="modified",
                content_hash=f"h{i}",
                extension=".py",
                language="Python",
                diff_summary="+50 lines; -15 lines",
                timestamp=time.time(),
                size_bytes=3000,
            )
            for i, f in enumerate(recent_py)
        ],
        detected_at=time.time(),
    )
    ctx.linked_conversation_snippets = [
        "Related keywords: codex, loop, agent, feishu, adapter, test"
    ]
    return ctx


# ==================== Pipeline 模拟 ====================

async def run_v2_pipeline(
    episode: dict,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    trace_id: str = "",
) -> dict:
    """模拟 MemoryEngine._process_episode_v2 的核心逻辑。

    Stage 1: MemoryExtractor — 实体/关系/事实提取
    Stage 2: DecisionExtractor — 基于实体上下文的决策提取
    """
    content = episode["conversation_text"]
    episode_id = episode["episode_id"]

    if trace_id and hasattr(memory_extractor, "set_trace_id"):
        memory_extractor.set_trace_id(trace_id)

    # ── Stage 1 ──
    t0 = time.time()
    existing_ctx = entity_store.build_extraction_context()
    mem_result = await memory_extractor.extract(
        content,
        episode_id=episode_id,
        existing_entities=existing_ctx,
    )
    stage1_time = time.time() - t0

    # 存入 EntityStore
    entity_store.add_entities(mem_result.entities)
    entity_store.add_relationships(mem_result.relationships)
    entity_store.add_facts(mem_result.facts)

    # ── Stage 2 ──
    entity_context = [
        {"name": e.name, "entity_type": e.entity_type}
        for e in mem_result.entities
    ]

    t0 = time.time()
    if trace_id and hasattr(decision_extractor, "set_trace_id"):
        decision_extractor.set_trace_id(trace_id)

    decisions_with = await decision_extractor.extract_with_context(
        content,
        entity_context=entity_context,
        project_context=project_ctx,
    )
    stage2_time_with = time.time() - t0

    t0 = time.time()
    decisions_without = await decision_extractor.extract_with_context(
        content,
        entity_context=entity_context,
    )
    stage2_time_without = time.time() - t0

    return {
        "chat_id": episode["chat_id"],
        "episode_id": episode_id,
        "message_count": episode["message_count"],
        "n_expected": episode["n_expected"],
        "topic": episode["topics"][0] if episode["topics"] else "",
        "stage1": {
            "entities": len(mem_result.entities),
            "relationships": len(mem_result.relationships),
            "facts": len(mem_result.facts),
            "time_sec": round(stage1_time, 1),
        },
        "stage2": {
            "with_project": {
                "decisions": len(decisions_with) if decisions_with else 0,
                "time_sec": round(stage2_time_with, 1),
            },
            "without_project": {
                "decisions": len(decisions_without) if decisions_without else 0,
                "time_sec": round(stage2_time_without, 1),
            },
        },
        "entities_detail": [
            {"name": e.name, "type": e.entity_type, "confidence": round(e.confidence, 2)}
            for e in mem_result.entities
        ],
        "ok": True,
    }


# ==================== Hypergraph 构建 ====================

def build_chat_hypergraph(episode_results: List[dict], all_entities: dict) -> dict:
    """为单个 chat 构建 hypergraph 并返回统计。"""
    hg = Hypergraph()

    # 收集所有 episode 数据
    for ep in episode_results:
        episode_data = {
            "id": ep["episode_id"],
            "chat_id": ep["chat_id"],
            "full_text": "",  # 文本较大，超图不需要存全文
            "participants": [],
            "start_time": 0.0,
            "messages": [],
            "topic": ep["topic"],
        }
        # 从 entities_detail 提取参与者
        entities = ep.get("entities_detail", [])
        for ent in entities:
            if ent["type"].lower() in ("person", "role"):
                episode_data["participants"].append(ent["name"])

    # 用 HypergraphBuilder 构建
    builder = HypergraphBuilder(llm_provider=None)
    hg_episodes = [
        {
            "id": ep["episode_id"],
            "chat_id": ep["chat_id"],
            "full_text": "",
            "participants": [
                e["name"] for e in ep.get("entities_detail", [])
                if e["type"].lower() in ("person", "role")
            ],
            "start_time": 0.0,
            "messages": [],
            "topic": ep.get("topic", ""),
        }
        for ep in episode_results
    ]

    hypergraph = builder.build_from_episodes(hg_episodes, llm_provider=None)

    stats = hypergraph.get_stats() if hasattr(hypergraph, "get_stats") else {}
    return {
        "stats": stats,
        "episodes_in_hg": len(hypergraph.episodes) if hasattr(hypergraph, "episodes") else 0,
        "topics_in_hg": len(hypergraph.topics) if hasattr(hypergraph, "topics") else 0,
    }


# ==================== 主测试流程 ====================

async def test_watcher_and_snapshot() -> dict:
    """验证 ProjectWatcher 监控 ArgusBot 仓库。"""
    from src.detect.project_detector import ProjectDetector
    from src.detect.conv_file_bridge import ConversationFileBridge, ConvFileBridgeLevel

    bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD)
    detector = ProjectDetector(ARGUSBOT_DIR, bridge=bridge, watcher_debounce=0.5)
    await detector.start()
    await asyncio.sleep(0.3)

    snapshot = await detector._watcher.take_snapshot()
    await detector.stop()

    return {
        "snapshot_files": snapshot.total_files,
        "snapshot_py_files": snapshot.file_type_counts.get(".py", 0),
        "watcher_available": True,
    }


async def main() -> None:
    print("=" * 60)
    print("argusbot_v3 + ArgusBot — MemoryEngine Pipeline E2E 测试")
    print("=" * 60)

    # ── Step 1: 加载数据集 ──
    data = load_dataset()
    print(f"数据集: {data['total_messages']} 条消息, {data['total_chats']} 个 chat")

    episodes = []
    for chat_id, msgs in data["chats"].items():
        eps = build_episodes(chat_id, msgs)
        episodes.extend(eps)
    episodes = [ep for ep in episodes if ep["message_count"] >= 3]

    # --sample 参数：只处理前 N 个 unique chat
    if SAMPLE_LIMIT and SAMPLE_LIMIT < len(data["chats"]):
        seen_chats: set = set()
        filtered: list = []
        for ep in episodes:
            if ep["chat_id"] not in seen_chats:
                seen_chats.add(ep["chat_id"])
                if len(seen_chats) > SAMPLE_LIMIT:
                    continue
            if ep["chat_id"] in seen_chats:
                filtered.append(ep)
        episodes = filtered

    print(f"有效 episode: {len(episodes)} 个 (>=3 条消息)")
    if SAMPLE_LIMIT:
        print(f"  (--sample={SAMPLE_LIMIT}, 实际 unique chats: {len(set(e['chat_id'] for e in episodes))})")

    # ── Step 2: Watcher 验证 ──
    print("\n[1/4] ProjectWatcher 验证 (ArgusBot 仓库)...")
    watcher_info = await test_watcher_and_snapshot()
    print(f"  快照: {watcher_info['snapshot_files']} 文件, "
          f"{watcher_info['snapshot_py_files']} 个 .py")

    # ── Step 3: LLM 初始化 ──
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        print("\n[2/4] ⚠️  无 API_KEY，跳过 LLM 提取")
        print("\n[3/4] ⚠️  跳过")
        print("\n[4/4] ⚠️  跳过")
        return

    provider, decision_extractor, memory_extractor, entity_store = init_llm_and_extractors()
    project_ctx = await build_project_context()
    print(f"\n[2/4] LLM 提取 ({len(episodes)} 个 episode, 并发={MAX_LLM_CONCURRENCY})...")
    print(f"  project context: {len(project_ctx.recent_changes)} 个文件变更")
    for c in project_ctx.recent_changes:
        print(f"    - {c.file_path}")

    # 并发处理
    sem = asyncio.Semaphore(MAX_LLM_CONCURRENCY)

    async def run_ep(ep: dict) -> dict:
        async with sem:
            trace_id = f"e2e_{ep['chat_id'][:12]}_{int(time.time())}"
            return await run_v2_pipeline(
                ep,
                memory_extractor,
                decision_extractor,
                entity_store,
                project_ctx=project_ctx,
                trace_id=trace_id,
            )

    t_start = time.time()
    episode_results = await asyncio.gather(*[run_ep(ep) for ep in episodes])
    llm_elapsed = time.time() - t_start

    # ── Step 4: Hypergraph 构建与汇总 ──
    print(f"\n[3/4] 构建超图 (per-chat)...")
    chat_hypergraphs = {}
    all_chat_ids = list(set(ep["chat_id"] for ep in episode_results if ep.get("ok")))
    for cid in all_chat_ids:
        chat_eps = [ep for ep in episode_results if ep.get("chat_id") == cid]
        hg_result = build_chat_hypergraph(chat_eps, entity_store)
        chat_hypergraphs[cid] = hg_result
        print(f"  Chat {cid[:24]}: {len(chat_eps)} episodes → "
              f"{hg_result['episodes_in_hg']} HG episodes, "
              f"{hg_result['topics_in_hg']} HG topics")

    # ── 汇总 ──
    print(f"\n[4/4] 生成报告...")
    total_with = 0
    total_without = 0
    total_expected = 0
    total_entities = 0
    total_proc = 0
    ok_count = 0
    failed_count = 0

    stats = {
        "total_episodes": 0, "ok": 0, "failed": 0,
        "decisions_with": 0, "decisions_without": 0,
        "expected_total": 0, "entities_total": 0,
        "total_time": 0.0, "details": [],
    }

    for r in episode_results:
        stats["total_episodes"] += 1
        if not r.get("ok"):
            stats["failed"] += 1
            continue
        stats["ok"] += 1
        stats["expected_total"] += r["n_expected"]
        stats["entities_total"] += r["stage1"]["entities"]
        stats["decisions_with"] += r["stage2"]["with_project"]["decisions"]
        stats["decisions_without"] += r["stage2"]["without_project"]["decisions"]
        stats["total_time"] += (
            r["stage1"]["time_sec"]
            + r["stage2"]["with_project"]["time_sec"]
            + r["stage2"]["without_project"]["time_sec"]
        )
        if r["stage2"]["with_project"]["decisions"] != r["stage2"]["without_project"]["decisions"]:
            stats["details"].append(r)

    print(f"  完成: {stats['total_episodes']} 个 episode, "
          f"{llm_elapsed:.0f}s 总耗时 (并发={MAX_LLM_CONCURRENCY})")
    print(f"  成功: {stats['ok']}, 失败: {stats['failed']}")

    # EntityStore 统计
    es_counts = entity_store.count()

    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "dataset": "argusbot_v3",
            "project_dir": ARGUSBOT_DIR,
            "model": os.getenv("MODEL_NAME", "deepseek-chat"),
            "pipeline": "v2 (MemoryExtractor → EntityStore → DecisionExtractor)",
            "max_msgs_per_chat": MAX_MSGS_PER_CHAT,
            "concurrency": MAX_LLM_CONCURRENCY,
        },
        "dataset": {
            "total_messages": data["total_messages"],
            "total_chats": data["total_chats"],
            "episodes": len(episodes),
        },
        "watcher": watcher_info,
        "entity_store": {
            "total_entities": es_counts["entities"],
            "total_relationships": es_counts["relationships"],
            "total_facts": es_counts["facts"],
        },
        "llm": stats,
        "hypergraph": {
            "chats_with_hg": len(chat_hypergraphs),
            "total_hg_episodes": sum(
                h["episodes_in_hg"] for h in chat_hypergraphs.values()
            ),
            "total_hg_topics": sum(
                h["topics_in_hg"] for h in chat_hypergraphs.values()
            ),
        },
        "per_episode": [
            {k: v for k, v in r.items() if k != "entities_detail"}
            for r in episode_results
        ],
    }

    Path(REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ── 打印摘要 ──
    print("\n" + "=" * 60)
    print("测试摘要")
    print("=" * 60)
    print(f"数据集: {data['total_messages']} 消息 / {data['total_chats']} chat / "
          f"{len(episodes)} episode")
    print(f"Watcher: {watcher_info['snapshot_files']} 文件")
    print(f"EntityStore: {es_counts['entities']} 实体, {es_counts['relationships']} 关系, "
          f"{es_counts['facts']} 事实")
    print(f"超图: {report['hypergraph']['total_hg_episodes']} episodes, "
          f"{report['hypergraph']['total_hg_topics']} topics")
    print(f"LLM: {stats['ok']}/{stats['total_episodes']} 成功")
    print(f"  期望决策 (ground truth): {stats['expected_total']}")
    print(f"  有 project context: {stats['decisions_with']} 条")
    print(f"  无 project context: {stats['decisions_without']} 条")
    print(f"  差异: {stats['decisions_with'] - stats['decisions_without']:+d}")
    print(f"  Stage 1 实体提取: {stats['entities_total']}")
    print(f"\n报告已保存: {REPORT_PATH}")
    print("=" * 60)

    # ── 关键差距提示 ──
    print("\n注意: 以下 pipeline 链路尚未实现，不在本次测试范围内:")
    print("  1. MemoryEngine.set_memory_extractor() 目前在 main.py 中未调用")
    print("  2. EntityStore → Neo4j 同步: Neo4jSyncEngine 存在但未在 pipeline 中激活")
    print("  3. 历史记忆检索: entity_context 仅来自当前 extraction, 未查询 hypergraph/Neo4j")
    print("  4. Hypergraph 虽然构建但未在 LLM extraction 中作为上下文使用")
    print("  5. 以上链路需后续增量实现后，使用本脚本验证全流程")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())