"""Execute production-path ablation variants with isolated engine state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from src.core.engine import MemoryEngine, PipelineEngine
from src.core.engine_config import EngineConfig
from src.eval.confirmed_decision_eval import EvidenceDecision
from src.storage.entity_store import EntityStore

from experiments.production_ablation.fixtures import FixtureNeo4jSync
from experiments.production_ablation.variants import ProductionVariant


@dataclass(frozen=True)
class ComponentTrace:
    memory_extraction_enabled: bool
    entity_context_injected: bool
    project_context_injected: bool
    neo4j_history_reads: int
    embedding_dedup_enabled: bool
    llm_dedup_enabled: bool


@dataclass(frozen=True)
class VariantRun:
    decisions: tuple[EvidenceDecision, ...]
    trace: ComponentTrace
    errors: tuple[str, ...]


def _episode(chat_id: str, messages: Iterable[dict]) -> Any:
    rows = list(messages)
    return SimpleNamespace(
        id=f"episode_{chat_id}",
        chat_id=chat_id,
        full_text="\n".join(
            f"[{row.get('msg_id', '')}] {row.get('speaker', '?')}: {row.get('msg', '')}"
            for row in rows
        ),
        message_count=len(rows),
        messages=rows,
    )


async def run_variant(
    messages_by_chat: dict[str, tuple[dict, ...]],
    variant: ProductionVariant,
    run_dir: str | Path,
    decision_extractor: Any,
    memory_extractor: Any | None = None,
    neo4j_sync: FixtureNeo4jSync | None = None,
) -> VariantRun:
    """Run selected chats through the real engine, graph and mutation path."""
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    config = EngineConfig(storage_path=str(run_path), detector_snapshot_storage_path=str(run_path))
    engine = MemoryEngine(config=config, decision_extractor=decision_extractor, pipeline_options=variant.options)
    engine._pipeline = PipelineEngine(memory_graph=engine.graph, config=config)
    if memory_extractor is not None:
        engine.set_memory_extractor(memory_extractor, EntityStore())
    if neo4j_sync is not None:
        engine.set_neo4j_sync(neo4j_sync)

    errors: list[str] = []
    for chat_id, messages in messages_by_chat.items():
        error_count_before = engine.status.error_count
        for component in (decision_extractor, memory_extractor):
            if component is not None and hasattr(component, "last_error"):
                component.last_error = None
        try:
            await engine._process_episode_v2(_episode(chat_id, messages))
        except Exception as exc:
            errors.append(f"{chat_id}: {exc}")
            continue
        if engine.status.error_count > error_count_before:
            errors.append(f"{chat_id}: extraction or production pipeline error: {engine.status.last_error}")
        for name, component in (("decision_extractor", decision_extractor), ("memory_extractor", memory_extractor)):
            last_error = getattr(component, "last_error", None) if component is not None else None
            if last_error:
                errors.append(f"{chat_id}: {name} error: {last_error}")

    decisions = []
    for node in engine.graph.get_all_decisions():
        source_chat_id = node.source_chat_id
        source_message_ids = tuple(node.extra.get("source_message_ids", []))
        if not source_message_ids and node.source_message_id:
            source_message_ids = (node.source_message_id,)
        if not source_chat_id and len(messages_by_chat) == 1:
            source_chat_id = next(iter(messages_by_chat))
        decisions.append(EvidenceDecision(
            chat_id=source_chat_id,
            title=node.title,
            summary=node.summary,
            status=node.status.value,
            is_suggestion=bool(node.extra.get("is_suggestion", False)),
            source_message_ids=source_message_ids,
            evidence_quote=node.extra.get("evidence_quote", ""),
        ))

    trace = ComponentTrace(
        memory_extraction_enabled=variant.options.enable_memory_extraction,
        entity_context_injected=variant.options.inject_entity_context,
        project_context_injected=variant.options.inject_project_context,
        neo4j_history_reads=len(neo4j_sync.entity_reads) + len(neo4j_sync.decision_reads) if neo4j_sync else 0,
        embedding_dedup_enabled=variant.options.enable_embedding_dedup,
        llm_dedup_enabled=variant.options.enable_llm_dedup,
    )
    return VariantRun(tuple(decisions), trace, tuple(errors))
