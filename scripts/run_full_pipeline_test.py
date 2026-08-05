"""argusbot_v3 + ArgusBot — 全链路端到端测试

包含两大数据源的完整 pipeline：
1. 对话消息 → Episode → MemoryExtractor Stage 1 → EntityStore → DecisionExtractor Stage 2
2. 文档（ref/ArgusBot 仓库） → CocoIndex 分块 → MemoryExtractor → EntityStore → Neo4j Sync

测试以下链路完整性：
- MemoryExtractor 实体/关系/事实提取（episode + document 两种 source_type）
- EntityStore 累积
- DecisionExtractor 实体上下文注入（有/无 project context 对比）
- Neo4jSyncEngine 同步（FakeNeo4j 验证 MENTIONS 边）
- 实体→决策桥接（通过 MENTIONS 边查询决策）

用法:
    LANGFUSE_ENABLE=false uv run python scripts/run_full_pipeline_test.py
    LANGFUSE_ENABLE=false uv run python scripts/run_full_pipeline_test.py --sample 5  # 只跑前 5 个 chat
    LANGFUSE_ENABLE=false uv run python scripts/run_full_pipeline_test.py --no-docs  # 跳过文档实体提取
    LANGFUSE_ENABLE=false uv run python scripts/run_full_pipeline_test.py --dry-run  # 验证配置，不调用 LLM

输出:
    eval_results/full_pipeline_test_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ── 项目内导入 ──
from dotenv import load_dotenv
load_dotenv()  # 从 .env 加载环境变量

from src.extractors.memory_extractor import MemoryExtractor
from src.extractors.simple_llm_extractor import SimpleLLMExtractor
from src.extractors.project_types import (
    ProjectDevelopmentContext,
    ProjectFileChange,
)
from src.storage.entity_store import EntityStore
from src.storage.neo4j_sync import Neo4jSyncEngine
from src.model.llm_provider import LLMProvider
from src.utils.markdown_spliter import MarkdownSplitter
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── 常量 ──
ARGUSBOT_DIR = str(_REPO / "ref" / "ArgusBot")
ARGUSBOT_V3_DIR = str(_REPO / "eval_dataset" / "argusbot_v3")
REPORT_PATH = str(_REPO / "eval_results" / "full_pipeline_test_report.json")

MAX_MSGS_PER_CHAT = 20
MAX_LLM_CONCURRENCY = 2  # 降低并发减少学校 Proxy 断连

SAMPLE_LIMIT: Optional[int] = None
SKIP_DOCS: bool = False
DRY_RUN: bool = False


# ════════════════════════════════════════════════════════════
#  FakeNeo4j — 内存 Neo4j 模拟
# ════════════════════════════════════════════════════════════

class FakeNeo4j:
    """In-memory Neo4j mock for testing entity→decision bridging.

    Tracks entities, documents, decisions, MENTIONS edges, and REFERENCES edges.
    Supports search_decisions_by_entity_names() for entity→decision traversal.
    """

    def __init__(self):
        self.entities: Dict[str, Any] = {}
        self.documents: Dict[str, Any] = {}
        self.decisions: Dict[str, dict] = {}
        self.mentions: List[Tuple[str, str, str]] = []   # (source_id, label, entity_name)
        self.references: List[Tuple[str, str]] = []       # (decision_sid, source_chat_id)
        self.upsert_calls: Dict[str, int] = {
            "entity": 0, "decision": 0, "document": 0,
        }

    async def upsert_entity(self, entity, source_type: str = "episode"):
        self.entities[entity.name] = entity
        self.upsert_calls["entity"] += 1
        if getattr(entity, "source_id", None):
            label = "Document" if source_type == "document" else "Episode"
            self.mentions.append((entity.source_id, label, entity.name))

    async def upsert_document(self, doc_id: str, title: str = "", summary: str = ""):
        self.documents[doc_id] = {"id": doc_id, "title": title}
        self.upsert_calls["document"] += 1

    async def upsert_relationship(self, rel):
        self.upsert_calls.setdefault("relationship", 0)
        self.upsert_calls["relationship"] += 1

    async def upsert_decision(self, decision):
        sid = getattr(decision, "sid", "")
        self.decisions[sid] = {
            "sid": sid,
            "summary": getattr(decision, "summary", ""),
            "full_text": getattr(decision, "full_text", ""),
        }
        self.upsert_calls["decision"] += 1
        source_chat_id = getattr(decision, "source_chat_id", None)
        if source_chat_id:
            self.references.append((sid, source_chat_id))

    async def search_decisions_by_entity_names(self, names: List[str], limit: int = 30) -> List[Dict]:
        """Traverse: Entity←mentions—Episode/Document—references→Decision"""
        results = []
        for ent_name in names:
            for src_id, src_label, e_name in self.mentions:
                if e_name == ent_name:
                    for d_sid, ref_id in self.references:
                        if ref_id == src_id and d_sid in self.decisions:
                            results.append(self.decisions[d_sid])
        seen = set()
        deduped = [r for r in results if r["sid"] not in seen and not seen.add(r["sid"])]
        return deduped[:limit]

    async def create_constraints(self):
        pass

    async def close(self):
        pass

    def count_mentions_by_label(self, label: str) -> int:
        return sum(1 for _, lbl, _ in self.mentions if lbl == label)


# ════════════════════════════════════════════════════════════
#  数据集加载
# ════════════════════════════════════════════════════════════

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


def build_episode(chat_id: str, messages: list) -> dict:
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
    return {
        "chat_id": chat_id,
        "episode_id": f"ep_{chat_id[:16]}",
        "message_count": len(msgs),
        "n_expected": n_expected,
        "conversation_text": "\n".join(lines),
        "topics": list({m.get("topic", "") for m in msgs}),
    }


# ════════════════════════════════════════════════════════════
#  文档源 — 从 ref/ArgusBot 获取文件列表
# ════════════════════════════════════════════════════════════

def collect_project_files(project_dir: str, max_files: int = 5) -> List[Dict]:
    """收集项目中的 Python 文件用于文档实体提取。

    Returns:
        List of {"file_path": str, "content": str, "extension": str, "size": int}
    """
    files = []
    root = Path(project_dir)
    # 只搜集非巨大的 .py 文件（<50KB），最多 max_files 个
    for py_path in sorted(root.rglob("*.py")):
        # 跳过 .venv 和 .git
        rel = py_path.relative_to(root)
        parts = rel.parts
        if any(p.startswith(".") for p in parts):
            continue
        if py_path.stat().st_size > 50000:
            continue
        try:
            content = py_path.read_text(encoding="utf-8", errors="replace")
            if content.strip():
                files.append({
                    "file_path": str(rel),
                    "content": content,
                    "extension": ".py",
                    "size": len(content),
                })
        except Exception:
            continue
        if len(files) >= max_files:
            break
    return files


# ════════════════════════════════════════════════════════════
#  LLM / Extractor 初始化
# ════════════════════════════════════════════════════════════

def init_components() -> Tuple[Optional[LLMProvider], SimpleLLMExtractor, MemoryExtractor, EntityStore]:
    """初始化所有组件。"""
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
    model = os.getenv("MODEL_NAME", "deepseek-chat")

    provider = None
    if api_key and not DRY_RUN:
        provider = LLMProvider(
            provider_type="openai",
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_tokens=4096,
            enable_stats=False,
        )

    decision_extractor = SimpleLLMExtractor(provider) if provider else None

    memory_extractor = None
    if provider:
        try:
            from src.ontology.manager import OntologyManager
            memory_extractor = MemoryExtractor(
                llm_provider=provider,
                ontology=OntologyManager.get_instance(),
                confidence_threshold=0.5,
            )
        except Exception:
            memory_extractor = MemoryExtractor(
                llm_provider=provider,
                confidence_threshold=0.5,
            )

    entity_store = EntityStore()

    return provider, decision_extractor, memory_extractor, entity_store


# ════════════════════════════════════════════════════════════
#  Project context 构建
# ════════════════════════════════════════════════════════════

def build_project_context_from_files(project_dir: str) -> ProjectDevelopmentContext:
    """从 ArgusBot 仓库构建真实 project context。"""
    files = collect_project_files(project_dir, max_files=10)
    recent_changes = []
    for i, f in enumerate(files):
        recent_changes.append(ProjectFileChange(
            file_path=f["file_path"],
            change_type="modified",
            content_hash=hashlib.sha256(f["content"].encode()).hexdigest()[:16],
            extension=".py",
            language="Python",
            diff_summary="+50 lines; -15 lines",
            timestamp=time.time(),
            size_bytes=f["size"],
        ))

    ctx = ProjectDevelopmentContext(
        recent_changes=recent_changes,
        detected_at=time.time(),
    )
    ctx.linked_conversation_snippets = [
        "Related keywords: codex, loop, agent, feishu, adapter, test"
    ]
    return ctx


# ════════════════════════════════════════════════════════════
#  Episode V2 Pipeline
# ════════════════════════════════════════════════════════════

async def run_episode_v2(
    episode: dict,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
) -> dict:
    """模拟 MemoryEngine._process_episode_v2 核心逻辑。

    Stage 1: MemoryExtractor — 实体/关系/事实提取
    Stage 2: DecisionExtractor — 基于实体上下文的决策提取（有/无 project context）
    """
    content = episode["conversation_text"]
    episode_id = episode["episode_id"]

    # ── Stage 1 ──
    t0 = time.time()
    existing_ctx = entity_store.build_extraction_context()
    mem_result = await memory_extractor.extract(
        content,
        episode_id=episode_id,
        existing_entities=existing_ctx,
    )
    stage1_time = time.time() - t0

    # 存入 EntityStore（标记为 episode 来源）
    for ent in mem_result.entities:
        ent.source_type = "episode"
    entity_store.add_entities(mem_result.entities)
    entity_store.add_relationships(mem_result.relationships)
    entity_store.add_facts(mem_result.facts)

    # ── Stage 2 (with project context) ──
    entity_context = [
        {"name": e.name, "entity_type": e.entity_type}
        for e in mem_result.entities
    ]

    t0 = time.time()
    decisions_with = []
    if decision_extractor and hasattr(decision_extractor, "extract_with_context"):
        decisions_with_raw = await decision_extractor.extract_with_context(
            content,
            entity_context=entity_context,
            project_context=project_ctx,
        )
        decisions_with = decisions_with_raw if decisions_with_raw else []
    stage2_time_with = time.time() - t0

    # ── Stage 2 (without project context) ──
    t0 = time.time()
    decisions_without = []
    if decision_extractor and hasattr(decision_extractor, "extract_with_context"):
        decisions_without_raw = await decision_extractor.extract_with_context(
            content,
            entity_context=entity_context,
        )
        decisions_without = decisions_without_raw if decisions_without_raw else []
    stage2_time_without = time.time() - t0

    # Build list of decision summaries for the return dict
    with_summaries = [d.get("summary", "")[:60] for d in decisions_with]
    without_summaries = [d.get("summary", "")[:60] for d in decisions_without]

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
                "decisions": len(decisions_with),
                "decision_summaries": with_summaries,
                "time_sec": round(stage2_time_with, 1),
            },
            "without_project": {
                "decisions": len(decisions_without),
                "decision_summaries": without_summaries,
                "time_sec": round(stage2_time_without, 1),
            },
        },
        "entities_detail": [
            {"name": e.name, "type": e.entity_type, "confidence": round(e.confidence, 2)}
            for e in mem_result.entities
        ],
        "ok": True,
    }


# ════════════════════════════════════════════════════════════
#  文档实体提取 Pipeline
# ════════════════════════════════════════════════════════════

def infer_splitter_language(file_path: str) -> Optional[str]:
    """Map file extension to CocoIndex splitter language parameter."""
    ext = os.path.splitext(file_path)[1].lower()
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".java": "java", ".go": "go", ".rs": "rust",
        ".md": "markdown", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    }
    return lang_map.get(ext)


async def process_document_files(
    files: List[Dict],
    memory_extractor: MemoryExtractor,
    entity_store: EntityStore,
    splitter: Optional[MarkdownSplitter],
    neo4j_client: Any,
) -> dict:
    """对文档文件执行实体提取（分块 → MemoryExtractor → EntityStore → Neo4j sync）。

    模拟 engine._process_project_changes 中的文档实体提取逻辑。
    """
    stats = {
        "files_processed": 0,
        "total_chunks": 0,
        "entities_extracted": 0,
        "relationships_extracted": 0,
        "facts_extracted": 0,
        "sync_stats": {},
        "chunks_per_file": [],
    }

    content_chunks: List[Tuple[str, str, int]] = []  # (chunk_id, chunk_text, file_idx)
    file_map: Dict[str, Dict] = {}

    for file_idx, file_info in enumerate(files):
        content = file_info["content"]
        file_path = file_info["file_path"]

        # 分块
        chunks = []
        if splitter and len(content) >= 512:
            try:
                language = infer_splitter_language(file_path)
                raw_chunks = splitter.split(content, language=language)
                chunks = [(c.text, c.start, c.end) for c in raw_chunks]
            except Exception:
                chunks = [(content, 0, len(content))]
        else:
            chunks = [(content, 0, len(content))]

        for chunk_idx, (chunk_text, _start, _end) in enumerate(chunks):
            chunk_id = f"{file_path}#chunk-{chunk_idx}"
            content_chunks.append((chunk_id, chunk_text, file_idx))

        stats["total_chunks"] += len(chunks)
        stats["chunks_per_file"].append({
            "file_path": file_path,
            "size": file_info["size"],
            "chunks": len(chunks),
        })
        file_map[file_path] = file_info

    stats["files_processed"] = len(files)

    # 逐块提取实体
    for chunk_idx, (chunk_id, chunk_text, _) in enumerate(content_chunks):
        try:
            existing_ctx = entity_store.build_extraction_context()
            mem_result = await memory_extractor.extract(
                chunk_text,
                episode_id=chunk_id,
                existing_entities=existing_ctx,
            )
            if not mem_result or (not mem_result.entities and not mem_result.relationships):
                continue

            for ent in mem_result.entities:
                ent.source_type = "document"
            entity_store.add_entities(mem_result.entities)
            entity_store.add_relationships(mem_result.relationships)
            entity_store.add_facts(mem_result.facts)

            stats["entities_extracted"] += len(mem_result.entities)
            stats["relationships_extracted"] += len(mem_result.relationships)
            stats["facts_extracted"] += len(mem_result.facts)

        except Exception as exc:
            logger.warning("[DocumentPipeline] Chunk extraction failed for %s: %s", chunk_id, exc)

    # 同步到 Neo4j（使用 Neo4jSyncEngine 或直接调用）
    if neo4j_client is not None:
        try:
            # 先注册文档节点
            for file_info in files:
                await neo4j_client.upsert_document(
                    file_info["file_path"],
                    title=file_info["file_path"],
                )

            # 使用 Neo4jSyncEngine 同步实体
            sync_engine = Neo4jSyncEngine(client=neo4j_client)
            sync_stats = await sync_engine.sync_all(entity_store=entity_store)
            stats["sync_stats"] = sync_stats
        except Exception as exc:
            logger.warning("[DocumentPipeline] Neo4j sync failed: %s", exc)
            stats["sync_stats"] = {"error": str(exc)}

    return stats


# ════════════════════════════════════════════════════════════
#  Hypergraph 构建（仅统计）
# ════════════════════════════════════════════════════════════

def build_hypergraph_stats(episode_results: List[dict]) -> dict:
    """从 episode 结果构建 hypergraph 统计。"""
    all_episodes = []
    all_entities = set()
    for ep in episode_results:
        if not ep.get("ok"):
            continue
        all_episodes.append(ep["episode_id"])
        for ent in ep.get("entities_detail", []):
            all_entities.add(ent["name"])
    return {
        "unique_episodes_in_hg": len(set(all_episodes)),
        "unique_entities_cross_chat": len(all_entities),
        "all_entity_names": sorted(all_entities)[:50],
    }


# ════════════════════════════════════════════════════════════
#  主测试流程
# ════════════════════════════════════════════════════════════

async def main() -> None:
    global SAMPLE_LIMIT, SKIP_DOCS, DRY_RUN

    parser = argparse.ArgumentParser(description="argusbot_v3 full pipeline test")
    parser.add_argument("--sample", type=int, default=0, help="只处理前 N 个 chat")
    parser.add_argument("--no-docs", action="store_true", help="跳过文档实体提取")
    parser.add_argument("--dry-run", action="store_true", help="验证配置，不调用 LLM")
    args = parser.parse_args()

    SAMPLE_LIMIT = args.sample if args.sample > 0 else None
    SKIP_DOCS = args.no_docs
    DRY_RUN = args.dry_run

    print("=" * 60)
    print("argusbot_v3 + ArgusBot — 全链路 Pipeline 端到端测试")
    print("=" * 60)
    if DRY_RUN:
        print("  [DRY RUN — 不调用 LLM]")
    if SKIP_DOCS:
        print("  [跳过文档实体提取]")

    # ── Step 1: 加载数据集 ──
    print("\n[1/5] 加载数据集...")
    data = load_dataset()
    episodes = []
    for chat_id, msgs in data["chats"].items():
        episodes.append(build_episode(chat_id, msgs))
    episodes = [ep for ep in episodes if ep["message_count"] >= 3]
    if SAMPLE_LIMIT:
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
    print(f"  数据: {data['total_messages']} 消息, {data['total_chats']} chat")
    print(f"  有效 episode: {len(episodes)} 个 (>=3 条消息)")

    # ── Step 2: 初始化组件 ──
    print("\n[2/5] 初始化组件...")
    api_key = os.getenv("API_KEY", "")

    # 初始化 CocoIndex 分块器（可选）
    splitter = None
    try:
        splitter = MarkdownSplitter(chunk_size=4096, chunk_overlap=256)
        print("  ✓ CocoIndex MarkdownSplitter")
    except Exception as e:
        print(f"  ⚠ CocoIndex 不可用: {e}，将使用全文本作为单块")

    # 初始化 LLM/Extractors
    provider, decision_extractor, memory_extractor, entity_store = init_components()
    if provider is None and not DRY_RUN:
        print("  ✗ 无 API_KEY，且非 dry-run 模式，退出")
        return
    print(f"  ✓ LLM Provider: {os.getenv('MODEL_NAME', 'deepseek-chat') if api_key else '(dry-run, mock)'}")
    print(f"  ✓ MemoryExtractor: {'available' if memory_extractor else 'N/A'}")
    print(f"  ✓ DecisionExtractor: {'available' if decision_extractor else 'N/A'}")
    print(f"  ✓ EntityStore: initialized")

    # 初始化 FakeNeo4j
    fake_neo4j = FakeNeo4j()
    print(f"  ✓ FakeNeo4j: initialized")

    # 构建 project context
    project_ctx = build_project_context_from_files(ARGUSBOT_DIR)
    print(f"  ✓ ProjectContext: {len(project_ctx.recent_changes)} 个文件变更")

    # ── Step 3: Episode V2 Pipeline ──
    print(f"\n[3/5] Episode V2 Pipeline ({len(episodes)} 个 episode, 并发={MAX_LLM_CONCURRENCY})...")
    episode_results: List[dict] = []

    if DRY_RUN or memory_extractor is None or decision_extractor is None:
        print("  DRY RUN 或组件未就绪，跳过 LLM 提取")
        # 构建空结果
        for ep in episodes:
            episode_results.append({
                "chat_id": ep["chat_id"],
                "episode_id": ep["episode_id"],
                "message_count": ep["message_count"],
                "n_expected": ep["n_expected"],
                "topic": ep["topics"][0] if ep["topics"] else "",
                "stage1": {"entities": 0, "relationships": 0, "facts": 0, "time_sec": 0.0},
                "stage2": {
                    "with_project": {"decisions": 0, "decision_summaries": [], "time_sec": 0.0},
                    "without_project": {"decisions": 0, "decision_summaries": [], "time_sec": 0.0},
                },
                "entities_detail": [],
                "ok": True,
            })
    else:
        sem = asyncio.Semaphore(MAX_LLM_CONCURRENCY)

        async def run_ep(ep: dict) -> dict:
            async with sem:
                return await run_episode_v2(
                    ep, memory_extractor, decision_extractor, entity_store,
                    project_ctx=project_ctx,
                )

        t_start = time.time()
        episode_results = await asyncio.gather(*[run_ep(ep) for ep in episodes])
        llm_elapsed = time.time() - t_start

        # 汇总
        stats = {"ok": 0, "failed": 0, "total_expected": 0, "decisions_with": 0, "decisions_without": 0}
        for r in episode_results:
            if r.get("ok"):
                stats["ok"] += 1
                stats["total_expected"] += r["n_expected"]
                stats["decisions_with"] += r["stage2"]["with_project"]["decisions"]
                stats["decisions_without"] += r["stage2"]["without_project"]["decisions"]
            else:
                stats["failed"] += 1
        print(f"  完成: {len(episode_results)} 个 episode, {llm_elapsed:.0f}s")
        print(f"  成功: {stats['ok']}, 失败: {stats['failed']}")
        print(f"  期望决策: {stats['total_expected']}")
        print(f"  有 project context: {stats['decisions_with']} 条")
        print(f"  无 project context: {stats['decisions_without']} 条")

        # ── 保存 episode_results 到缓存（供后续快速评估） ──
        cache_path = Path("eval_results/decisions_cache.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # 只保存评估需要的字段，缩小体积
        cache_data = []
        for r in episode_results:
            cache_data.append({
                "chat_id": r.get("chat_id"),
                "episode_id": r.get("episode_id"),
                "topic": r.get("topic", ""),
                "ok": r.get("ok", False),
                "n_expected": r.get("n_expected", 0),
                "stage2": r.get("stage2", {}),
            })
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))
        print(f"  ✓ 已保存决策缓存: {cache_path} ({len(cache_data)} episodes)")

        # ── 将 episode 实体 + 决策写入 FakeNeo4j（供桥接验证） ──
        print("  同步 episode 实体与决策到 FakeNeo4j...")
        for r in episode_results:
            if not r.get("ok"):
                continue
            chat_id = r["chat_id"]
            episode_id = r["episode_id"]

            # 写入 episode 实体 → MENTIONS 边
            for ent in r.get("entities_detail", []):
                ent_obj = type("Neo4jEntity", (), {
                    "name": ent["name"],
                    "entity_type": ent["type"],
                    "attributes": {},
                    "confidence": ent.get("confidence", 0.8),
                    "source_id": episode_id,
                })()
                await fake_neo4j.upsert_entity(ent_obj, source_type="episode")

            # 写入决策（with project context）
            for d_summary in r["stage2"]["with_project"]["decision_summaries"]:
                d_sid = f"dec_{episode_id}_{hash(d_summary) % 100000:05d}"
                dec = type("DecisionNode", (), {
                    "sid": d_sid,
                    "summary": d_summary,
                    "full_text": "",
                    "source_chat_id": episode_id,  # 与实体 MENTIONS 边的 source_id 对应
                })()
                await fake_neo4j.upsert_decision(dec)

    # ── Step 4: 文档实体提取 ──
    doc_extract_stats: Dict[str, Any] = {"skipped": not SKIP_DOCS}
    if not SKIP_DOCS and memory_extractor is not None:
        print(f"\n[4/5] 文档实体提取 (ref/ArgusBot)...")
        project_files = collect_project_files(ARGUSBOT_DIR, max_files=20)
        print(f"  找到 {len(project_files)} 个 Python 文件 (<=50KB)")

        if project_files:
            doc_extract_stats = await process_document_files(
                project_files,
                memory_extractor,
                entity_store,
                splitter,
                fake_neo4j,
            )
            print(f"  处理文件: {doc_extract_stats['files_processed']}")
            print(f"  总块数: {doc_extract_stats['total_chunks']}")
            print(f"  实体: {doc_extract_stats['entities_extracted']}")
            print(f"  关系: {doc_extract_stats['relationships_extracted']}")
            print(f"  事实: {doc_extract_stats['facts_extracted']}")
            print(f"  Neo4j 同步: {doc_extract_stats['sync_stats']}")

    # ── Neo4j 验证 ──
    print(f"\n[4b/5] Neo4j MENTIONS 边验证...")
    neo4j_stats = {
        "entities_written": len(fake_neo4j.entities),
        "decisions_written": len(fake_neo4j.decisions),
        "documents_written": len(fake_neo4j.documents),
        "mentions_episode": fake_neo4j.count_mentions_by_label("Episode"),
        "mentions_document": fake_neo4j.count_mentions_by_label("Document"),
        "total_mentions": len(fake_neo4j.mentions),
        "references": len(fake_neo4j.references),
        "upsert_calls": fake_neo4j.upsert_calls,
    }
    print(f"  Entities: {neo4j_stats['entities_written']}")
    print(f"  Decisions: {neo4j_stats['decisions_written']}")
    print(f"  Documents: {neo4j_stats['documents_written']}")
    print(f"  MENTIONS (Episode): {neo4j_stats['mentions_episode']}")
    print(f"  MENTIONS (Document): {neo4j_stats['mentions_document']}")
    print(f"  Total MENTIONS: {neo4j_stats['total_mentions']}")

    # 实体→决策桥接验证
    print("\n  实体→决策桥接验证...")
    bridging_stats: Dict[str, Any] = {"entity_to_decision_lookups": 0, "bridged_decisions": 0}
    if fake_neo4j.entities:
        sample_entities = list(fake_neo4j.entities.keys())[:10]
        bridged = await fake_neo4j.search_decisions_by_entity_names(sample_entities)
        bridging_stats["entity_to_decision_lookups"] = len(sample_entities)
        bridging_stats["bridged_decisions"] = len(bridged)
        bridging_stats["sample_bridged"] = [
            {"entity": e, "decision_sid": d["sid"]}
            for e in sample_entities[:3] for d in bridged[:3]
        ]
        if bridged:
            print(f"  ✓ {len(bridged)} 条决策通过实体桥接查询到")
        else:
            print(f"  ⚠ 未查询到桥接决策（可能是实体与决策未通过 MENTIONS-REFERENCES 连通）")

    # EntityStore 统计
    es_counts = entity_store.count()
    print(f"\n  EntityStore 总量: {es_counts['entities']} 实体, "
          f"{es_counts['relationships']} 关系, {es_counts['facts']} 事实")

    # ── 评估：与 ground truth 对比 ──
    print(f"\n[4c/5] 决策提取精度评估 (vs expected.jsonl)...")
    eval_metrics: Dict[str, Any] = {"skipped": True}
    eval_metrics_without: Dict[str, Any] = {"skipped": True}
    expected_path = Path(ARGUSBOT_V3_DIR) / "expected.jsonl"
    if expected_path.exists() and episode_results:
        try:
            from src.eval.comparator import EvalComparator
            from src.model.embedding_provider import EmbeddingProvider
            _embedder = EmbeddingProvider()

            def _build_decisions(episode_results, use_with=True):
                decs = []
                for r in episode_results:
                    if not r.get("ok"):
                        continue
                    key = "with_project" if use_with else "without_project"
                    for d_summary in r["stage2"][key]["decision_summaries"]:
                        decs.append({
                            "sid": f"eval_{r['episode_id']}_{hash(d_summary) % 100000:05d}",
                            "topic_id": r.get("topic", ""),
                            "summary": d_summary,
                            "status": "decided",
                            "impact": "major",
                            "chat_id": r["chat_id"],
                            "is_suggestion": False,
                        })
                return decs

            # 有 project context
            actual_with = _build_decisions(episode_results, use_with=True)
            comp_with = EvalComparator(str(expected_path), embedding_provider=_embedder)
            comp_with.match(actual_with)
            m_with = comp_with.compute_metrics()
            eval_metrics = {
                "skipped": False,
                "precision": m_with["precision"],
                "recall": m_with["recall"],
                "f1": m_with["f1"],
                "true_positives": m_with["true_positives"],
                "false_positives": m_with["false_positives"],
                "false_negatives": m_with["false_negatives"],
                "total_expected": m_with["total_expected"],
                "total_detected": m_with["total_detected"],
                "decision_recall": m_with["decision_metrics"]["decision_recall"],
                "suggestion_recall": m_with["decision_metrics"]["suggestion_recall"],
                "by_topic": m_with.get("by_topic", {}),
                "by_chat": m_with.get("by_chat", {}),
            }

            # 无 project context
            actual_without = _build_decisions(episode_results, use_with=False)
            comp_without = EvalComparator(str(expected_path), embedding_provider=_embedder)
            comp_without.match(actual_without)
            m_without = comp_without.compute_metrics()

            eval_metrics_without = {
                "skipped": False,
                "precision": m_without["precision"],
                "recall": m_without["recall"],
                "f1": m_without["f1"],
                "true_positives": m_without["true_positives"],
                "false_positives": m_without["false_positives"],
                "false_negatives": m_without["false_negatives"],
                "total_expected": m_without["total_expected"],
                "total_detected": m_without["total_detected"],
            }

            print(f"  [有 project context]")
            print(f"    Precision: {m_with['precision']:.2%}")
            print(f"    Recall:    {m_with['recall']:.2%}")
            print(f"    F1:        {m_with['f1']:.2%}")
            print(f"    TP={m_with['true_positives']} FP={m_with['false_positives']} FN={m_with['false_negatives']}")
            print(f"    (expected={m_with['total_expected']}, detected={m_with['total_detected']})")
            print(f"  [无 project context]")
            print(f"    Precision: {m_without['precision']:.2%}")
            print(f"    Recall:    {m_without['recall']:.2%}")
            print(f"    F1:        {m_without['f1']:.2%}")
            print(f"    TP={m_without['true_positives']} FP={m_without['false_positives']} FN={m_without['false_negatives']}")
            print(f"    (expected={m_without['total_expected']}, detected={m_without['total_detected']})")
        except Exception as exc:
            import traceback as tb
            print(f"  ⚠ 评估失败: {exc}")
            print(f"     {tb.format_exc()[:200]}")
            eval_metrics = {"skipped": True, "error": str(exc)}

    # ── Hypergraph 统计 ──
    hg_stats = build_hypergraph_stats(episode_results)

    # ── Step 5: 生成报告 ──
    print(f"\n[5/5] 生成报告...")
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "dataset": "argusbot_v3",
            "project_dir": ARGUSBOT_DIR,
            "model": os.getenv("MODEL_NAME", "deepseek-chat"),
            "pipeline": "v2 (MemoryExtractor Stage 1 + Stage 2 + DocEntityExtraction + Neo4j)",
            "max_msgs_per_chat": MAX_MSGS_PER_CHAT,
            "concurrency": MAX_LLM_CONCURRENCY,
            "dry_run": DRY_RUN,
            "skip_docs": SKIP_DOCS,
        },
        "dataset": {
            "total_messages": data["total_messages"],
            "total_chats": data["total_chats"],
            "episodes": len(episodes),
        },
        "document_extraction": doc_extract_stats,
        "entity_store": {
            "total_entities": es_counts["entities"],
            "total_relationships": es_counts["relationships"],
            "total_facts": es_counts["facts"],
        },
        "neo4j": neo4j_stats,
        "entity_decision_bridge": bridging_stats,
        "eval_metrics_with_project": eval_metrics,
        "eval_metrics_without_project": eval_metrics_without,
        "hypergraph": hg_stats,
        "llm": {
            "ok": sum(1 for r in episode_results if r.get("ok")),
            "failed": sum(1 for r in episode_results if not r.get("ok")),
            "total_expected": sum(r["n_expected"] for r in episode_results if r.get("ok")),
            "decisions_with": sum(r["stage2"]["with_project"]["decisions"] for r in episode_results if r.get("ok")),
            "decisions_without": sum(r["stage2"]["without_project"]["decisions"] for r in episode_results if r.get("ok")),
            "total_entities": sum(r["stage1"]["entities"] for r in episode_results if r.get("ok")),
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
    print("全链路测试摘要")
    print("=" * 60)
    print(f"数据: {data['total_messages']} 消息 / {data['total_chats']} chat")
    print(f"Episode Pipeline: {len(episodes)} 个 episode")
    print(f"  有 project context: {report['llm']['decisions_with']} 条决策")
    print(f"  无 project context: {report['llm']['decisions_without']} 条决策")
    print(f"  Stage 1 实体: {report['llm']['total_entities']} 个")
    if not SKIP_DOCS:
        print(f"文档提取: {doc_extract_stats.get('files_processed', 0)} 文件, "
              f"{doc_extract_stats.get('entities_extracted', 0)} 实体")
    print(f"EntityStore: {es_counts['entities']} 总实体")
    print(f"Neo4j: {neo4j_stats['entities_written']} 实体写入, "
          f"{neo4j_stats['total_mentions']} 条 MENTIONS 边")
    print(f"实体→决策桥接: {bridging_stats.get('bridged_decisions', 0)} 条连通")
    print(f"超图: {hg_stats['unique_episodes_in_hg']} episodes, "
          f"{hg_stats['unique_entities_cross_chat']} 跨 chat 实体")
    # ── 评估指标 ──
    if eval_metrics.get("skipped") is False:
        em = eval_metrics
        print(f"\n评估指标 (有 project context):")
        print(f"  Precision: {em['precision']:.2%}")
        print(f"  Recall:    {em['recall']:.2%}")
        print(f"  F1:        {em['f1']:.2%}")
        print(f"  TP={em['true_positives']}  FP={em['false_positives']}  FN={em['false_negatives']}")
        print(f"  (expected={em['total_expected']}, detected={em['total_detected']})")
    if eval_metrics_without.get("skipped") is False:
        em2 = eval_metrics_without
        print(f"\n评估指标 (无 project context):")
        print(f"  Precision: {em2['precision']:.2%}")
        print(f"  Recall:    {em2['recall']:.2%}")
        print(f"  F1:        {em2['f1']:.2%}")
        print(f"  TP={em2['true_positives']}  FP={em2['false_positives']}  FN={em2['false_negatives']}")
        print(f"  (expected={em2['total_expected']}, detected={em2['total_detected']})")
    print(f"\n报告已保存: {REPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())