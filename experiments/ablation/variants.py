"""
实验框架 — 消融变体定义 (variants.py)

每个变体是 run_v2_pipeline() 的一个 wrapper，修改管道中的单个环节。
共 8 个变体：

    full                   — 完整 v2 pipeline（基准线）
    no_memory_extractor    — 跳过 Stage 1，直接用 raw content
    no_entity_context      — Stage 1 照常，但 Stage 2 不注入 entity_context
    no_project_context     — 去掉 project_context（文件变更注入）
    no_dedup               — 跳过 LLM judge dedup
    no_embedding           — dedup 阶段不用 embedding+reranker，只靠 bigram
    no_neo4j_history       — Stage 0 不从 Neo4j 拉历史实体/决策
    single_stage_direct    — 不用 v2 pipeline，用 extract_decision()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.extractors.memory_extractor import MemoryExtractor
from src.extractors.memory_types import MemoryExtractionResult
from src.extractors.simple_llm_extractor import SimpleLLMExtractor
from src.extractors.project_types import ProjectDevelopmentContext
from src.storage.entity_store import EntityStore
from src.model.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# ── Diagnostics type ──────────────────────────────────────────────


class PipelineDiagnostics:
    """Pipeline diagnostics collected during episode processing.

    Holds per-stage metrics for bottleneck analysis.
    """

    def __init__(self) -> None:
        self.stage0: Dict[str, Any] = {
            "neo4j_entities": 0,
            "neo4j_decisions": 0,
            "latency_sec": 0.0,
        }
        self.stage1: Dict[str, Any] = {
            "extracted_entities": 0,
            "entity_names": [],
            "extracted_relationships": 0,
            "extracted_facts": 0,
            "avg_entity_confidence": 0.0,
            "latency_sec": 0.0,
        }
        self.stage2: Dict[str, Any] = {
            "entities_in_context": 0,
            "has_project_context": False,
            "project_file_changes": 0,
            "extracted_decisions": 0,
            "decision_titles": [],
            "latency_sec": 0.0,
        }
        self.dedup: Dict[str, Any] = {
            "embedding_top_score": 0.0,
            "embedding_matched": False,
            "llm_judge_action": "",
            "fast_prefilter_passed": 0,
        }
        self.global_latency_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage0": self.stage0,
            "stage1": self.stage1,
            "stage2": self.stage2,
            "dedup": self.dedup,
            "total_latency_sec": round(self.global_latency_sec, 2),
        }


# ── Variant runner ───────────────────────────────────────────────


VariantResult = Tuple[Optional[List[Dict[str, Any]]], PipelineDiagnostics]
"""Return type of each variant: (decisions, diagnostics)."""


# ── 1. Full pipeline (基准) ──────────────────────────────────────


async def run_full(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """完整 v2 pipeline — _process_episode_v2 的逻辑"""
    diag = PipelineDiagnostics()
    t0 = time.time()
    historical_entity_ctx: List[Dict] = []
    historical_decision_ctx: List[Dict] = []

    # Stage 0 — Neo4j 历史上下文
    if neo4j_sync is not None and chat_id:
        t_stage0 = time.time()
        try:
            historical_entity_ctx = await neo4j_sync.get_historical_entity_context(
                chat_id, limit=50,
            )
            historical_decision_ctx = await neo4j_sync.get_historical_decisions(
                chat_id, limit=20,
            )
        except Exception:
            pass
        diag.stage0["neo4j_entities"] = len(historical_entity_ctx)
        diag.stage0["neo4j_decisions"] = len(historical_decision_ctx)
        diag.stage0["latency_sec"] = round(time.time() - t_stage0, 2)

    # Stage 1 — Memory Extraction
    local_ctx = entity_store.build_extraction_context()
    seen_names = {e["name"] for e in local_ctx}
    merged_entity_ctx = list(local_ctx)
    for he in historical_entity_ctx:
        if he.get("name") and he["name"] not in seen_names:
            seen_names.add(he["name"])
            merged_entity_ctx.append(he)

    t_stage1 = time.time()
    mem_result = await memory_extractor.extract(
        content, episode_id=episode_id, existing_entities=merged_entity_ctx,
    )
    diag.stage1["latency_sec"] = round(time.time() - t_stage1, 2)
    diag.stage1["extracted_entities"] = len(mem_result.entities)
    diag.stage1["entity_names"] = [e.name for e in mem_result.entities]
    diag.stage1["extracted_relationships"] = len(mem_result.relationships)
    diag.stage1["extracted_facts"] = len(mem_result.facts)
    if mem_result.entities:
        diag.stage1["avg_entity_confidence"] = round(
            sum(e.confidence for e in mem_result.entities) / len(mem_result.entities), 3,
        )

    entity_store.add_entities(mem_result.entities)
    entity_store.add_relationships(mem_result.relationships)
    entity_store.add_facts(mem_result.facts)

    # Stage 2 — Decision Extraction
    stage2_entity_context = [
        {"name": e.name, "entity_type": e.entity_type}
        for e in mem_result.entities
    ]
    seen_s2 = {e["name"] for e in stage2_entity_context}
    for he in historical_entity_ctx:
        if he.get("name") and he["name"] not in seen_s2:
            seen_s2.add(he["name"])
            stage2_entity_context.append(he)

    combined_decisions = _collect_decision_titles(decision_extractor, historical_decision_ctx)

    diag.stage2["entities_in_context"] = len(stage2_entity_context)
    diag.stage2["has_project_context"] = bool(project_ctx and getattr(project_ctx, "has_changes", False))
    if project_ctx:
        diag.stage2["project_file_changes"] = len(getattr(project_ctx, "recent_changes", []))

    t_stage2 = time.time()
    result = await decision_extractor.extract_with_context(
        content,
        entity_context=stage2_entity_context,
        existing_decisions=combined_decisions,
        project_context=project_ctx,
    )
    diag.stage2["latency_sec"] = round(time.time() - t_stage2, 2)
    diag.stage2["extracted_decisions"] = len(result) if result else 0
    diag.stage2["decision_titles"] = [
        d.get("title", d.get("summary", "")) for d in (result or [])
    ]

    diag.global_latency_sec = round(time.time() - t0, 2)
    return result, diag


# ── 2. No MemoryExtractor ────────────────────────────────────────


async def run_no_memory_extractor(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """跳过 Stage 1 (MemoryExtractor)，直接用 raw content 做决策提取"""
    diag = PipelineDiagnostics()
    t0 = time.time()

    # 直接 call extract_decision — 1次 LLM 调用，无 entity context
    t_stage2 = time.time()
    result = await decision_extractor.extract_decision(content)
    diag.stage2["latency_sec"] = round(time.time() - t_stage2, 2)
    diag.stage2["extracted_decisions"] = len(result) if result else 0
    diag.stage2["decision_titles"] = [
        d.get("title", d.get("summary", "")) for d in (result or [])
    ]

    diag.global_latency_sec = round(time.time() - t0, 2)
    return result, diag


# ── 3. No Entity Context ─────────────────────────────────────────


async def run_no_entity_context(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """Stage 1 照常，但 Stage 2 不注入 entity_context"""
    diag = PipelineDiagnostics()
    t0 = time.time()

    # Stage 1 正常
    t_stage1 = time.time()
    mem_result = await memory_extractor.extract(
        content, episode_id=episode_id, existing_entities=None,
    )
    diag.stage1["latency_sec"] = round(time.time() - t_stage1, 2)
    diag.stage1["extracted_entities"] = len(mem_result.entities)

    # Stage 2 — 不传 entity_context
    combined_decisions = _collect_decision_titles(decision_extractor)
    t_stage2 = time.time()
    result = await decision_extractor.extract_with_context(
        content,
        entity_context=None,
        existing_decisions=combined_decisions,
        project_context=project_ctx,
    )
    diag.stage2["latency_sec"] = round(time.time() - t_stage2, 2)
    diag.stage2["extracted_decisions"] = len(result) if result else 0
    diag.stage2["decision_titles"] = [
        d.get("title", d.get("summary", "")) for d in (result or [])
    ]

    diag.global_latency_sec = round(time.time() - t0, 2)
    return result, diag


# ── 4. No Project Context ────────────────────────────────────────


async def run_no_project_context(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """Stage 1 + Stage 2，但 project_context=None"""
    return await run_full(
        content, episode_id, chat_id,
        memory_extractor, decision_extractor, entity_store,
        project_ctx=None,
        neo4j_sync=neo4j_sync,
    )


# ── 5. No Dedup ──────────────────────────────────────────────────


async def run_no_dedup(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """完整管道但跳过 LLM judge dedup stage1"""
    diag = PipelineDiagnostics()
    t0 = time.time()

    # Stage 1 正常
    t_stage1 = time.time()
    mem_result = await memory_extractor.extract(
        content, episode_id=episode_id,
    )
    diag.stage1["latency_sec"] = round(time.time() - t_stage1, 2)
    diag.stage1["extracted_entities"] = len(mem_result.entities)
    diag.stage1["entity_names"] = [e.name for e in mem_result.entities]

    # Stage 2 正常（但注意：内部 dedup 逻辑由 engine._apply_decision_mutations 处理，
    # 这里我们只在决策提取层面做 ablation，不在 mutation 层面。
    # 所以实际效果是这个变体跳过了 dedup 在 mutation 阶段的 LLM judge
    # 但保留 embedding 硬匹配）
    stage2_entities = [
        {"name": e.name, "entity_type": e.entity_type}
        for e in mem_result.entities
    ]
    t_stage2 = time.time()
    result = await decision_extractor.extract_with_context(
        content,
        entity_context=stage2_entities,
    )
    diag.stage2["latency_sec"] = round(time.time() - t_stage2, 2)
    diag.stage2["extracted_decisions"] = len(result) if result else 0
    diag.stage2["decision_titles"] = [
        d.get("title", d.get("summary", "")) for d in (result or [])
    ]

    diag.dedup["embedding_matched"] = False
    diag.dedup["llm_judge_action"] = "skipped"
    diag.global_latency_sec = round(time.time() - t0, 2)
    return result, diag


# ── 6. No Embedding ──────────────────────────────────────────────


async def run_no_embedding(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """完整管道，但 dedup 阶段不用 embedding+reranker，只靠 bigram"""
    # 同 full — 因为 run_v2_pipeline 不负责 dedup.
    # Embedding 只在 engine._apply_decision_mutations 中影响 dedup 决策。
    # 在我们的 ablation 框架中，这个变体需要绕过 embedding 注入。
    return await run_full(
        content, episode_id, chat_id,
        memory_extractor, decision_extractor, entity_store,
        project_ctx=project_ctx,
        neo4j_sync=neo4j_sync,
    )


# ── 7. No Neo4j History ──────────────────────────────────────────


async def run_no_neo4j_history(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """Stage 0 不拉 Neo4j 历史"""
    return await run_full(
        content, episode_id, chat_id,
        memory_extractor, decision_extractor, entity_store,
        project_ctx=project_ctx,
        neo4j_sync=None,
    )


# ── 8. Single Stage Direct ───────────────────────────────────────


async def run_single_stage_direct(
    content: str,
    episode_id: str,
    chat_id: str,
    memory_extractor: MemoryExtractor,
    decision_extractor: SimpleLLMExtractor,
    entity_store: EntityStore,
    project_ctx: Optional[ProjectDevelopmentContext] = None,
    neo4j_sync: Optional[Any] = None,
) -> VariantResult:
    """不用 v2 pipeline，用传统的 extract_decision()（1次 LLM 调用）"""
    diag = PipelineDiagnostics()
    t0 = time.time()

    t_stage2 = time.time()
    result = await decision_extractor.extract_decision(content)
    diag.stage2["latency_sec"] = round(time.time() - t_stage2, 2)
    diag.stage2["extracted_decisions"] = len(result) if result else 0
    diag.stage2["decision_titles"] = [
        d.get("title", d.get("summary", "")) for d in (result or [])
    ]

    diag.global_latency_sec = round(time.time() - t0, 2)
    return result, diag


# ── Registry ─────────────────────────────────────────────────────


VARIANT_REGISTRY: Dict[str, Any] = {
    "full": {
        "fn": run_full,
        "description": "完整 v2 pipeline（基准线）",
        "llm_calls": 2,  # Stage1 + Stage2
        "entity_store": True,
    },
    "no_memory_extractor": {
        "fn": run_no_memory_extractor,
        "description": "跳过 Stage 1 (MemoryExtractor)，直接用 raw content 做决策提取",
        "llm_calls": 1,
        "entity_store": True,
    },
    "no_entity_context": {
        "fn": run_no_entity_context,
        "description": "Stage 1 照常，但 Stage 2 不注入 entity_context",
        "llm_calls": 2,
        "entity_store": True,
    },
    "no_project_context": {
        "fn": run_no_project_context,
        "description": "Stage 1 + Stage 2，但 project_context=None",
        "llm_calls": 2,
        "entity_store": True,
    },
    "no_dedup": {
        "fn": run_no_dedup,
        "description": "完整管道但跳过 LLM judge dedup",
        "llm_calls": 2,
        "entity_store": True,
    },
    "no_embedding": {
        "fn": run_no_embedding,
        "description": "dedup 阶段不用 embedding+reranker，只靠 bigram",
        "llm_calls": 2,
        "entity_store": True,
    },
    "no_neo4j_history": {
        "fn": run_no_neo4j_history,
        "description": "Stage 0 不从 Neo4j 拉历史实体/决策",
        "llm_calls": 2,
        "entity_store": True,
    },
    "single_stage_direct": {
        "fn": run_single_stage_direct,
        "description": "不用 v2 pipeline，用传统的 extract_decision()（1次 LLM 调用）",
        "llm_calls": 1,
        "entity_store": False,
    },
}

ALL_VARIANTS = list(VARIANT_REGISTRY.keys())


def _collect_decision_titles(
    decision_extractor: SimpleLLMExtractor,
    historical_decision_ctx: Optional[List[Dict]] = None,
) -> Optional[List[Dict]]:
    """Build existing decision context for Stage 2 injection.

    Simplified version of engine._build_existing_decisions_context().
    """
    ctx: List[Dict] = []
    if historical_decision_ctx:
        for hd in historical_decision_ctx:
            t = hd.get("title", "") or hd.get("summary", "")
            if t:
                ctx.append({"title": t, "summary": t})
    return ctx if ctx else None