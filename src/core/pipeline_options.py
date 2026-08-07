"""Runtime switches for production decision-pipeline experiments.

`PipelineOptions` is intentionally small and immutable: it lets the production
engine change one component boundary at a time without creating a separate
experiment-only pipeline implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class PipelineOptions:
    """Feature gates for the production decision-processing path."""

    enable_memory_extraction: bool = True
    inject_entity_context: bool = True
    inject_project_context: bool = True
    enable_neo4j_history: bool = True
    enable_embedding_dedup: bool = True
    enable_llm_dedup: bool = True

    def changed_fields_from(self, other: "PipelineOptions") -> set[str]:
        """Return option names whose values differ from another configuration."""
        return {
            field.name
            for field in fields(self)
            if getattr(self, field.name) != getattr(other, field.name)
        }
