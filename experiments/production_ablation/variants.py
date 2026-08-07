"""Valid production-path ablation variants."""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.core.pipeline_options import PipelineOptions


@dataclass(frozen=True)
class ProductionVariant:
    name: str
    options: PipelineOptions


FULL_OPTIONS = PipelineOptions()


def build_variants() -> dict[str, ProductionVariant]:
    variants = {
        "full": ProductionVariant("full", FULL_OPTIONS),
        "no_memory_extractor": ProductionVariant(
            "no_memory_extractor", replace(FULL_OPTIONS, enable_memory_extraction=False)
        ),
        "no_entity_context": ProductionVariant(
            "no_entity_context", replace(FULL_OPTIONS, inject_entity_context=False)
        ),
        "no_project_context": ProductionVariant(
            "no_project_context", replace(FULL_OPTIONS, inject_project_context=False)
        ),
        "no_neo4j_history": ProductionVariant(
            "no_neo4j_history", replace(FULL_OPTIONS, enable_neo4j_history=False)
        ),
        "no_embedding": ProductionVariant(
            "no_embedding", replace(FULL_OPTIONS, enable_embedding_dedup=False)
        ),
        "no_llm_dedup": ProductionVariant(
            "no_llm_dedup", replace(FULL_OPTIONS, enable_llm_dedup=False)
        ),
    }
    for name, variant in variants.items():
        if name == "full":
            continue
        changed = variant.options.changed_fields_from(FULL_OPTIONS)
        if len(changed) != 1:
            raise ValueError(f"Variant {name} must differ from full by exactly one option: {changed}")
    return variants
