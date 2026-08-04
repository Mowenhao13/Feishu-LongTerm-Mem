"""Memory extraction output types.

Data classes for the two-stage memory extraction pipeline.
Stage 1 (MemoryExtractor) produces MemoryExtractionResult,
which is consumed by Stage 2 (DecisionExtractor.with_context).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExtractedEntity:
    """A single named entity extracted from episode text."""

    name: str
    entity_type: str  # Person | Technology | Project | Service | Concept
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source_episode_id: str = ""


@dataclass
class ExtractedRelationship:
    """A directed relationship between two extracted entities."""

    source_name: str
    relationship_type: str  # USES | OWNS | DEPENDS_ON | ...
    target_name: str
    confidence: float = 0.0
    valid_at: Optional[str] = None


@dataclass
class ExtractedFact:
    """A factual assertion extracted from episode text."""

    content: str
    confidence: float = 0.0
    related_entity_names: List[str] = field(default_factory=list)
    source_episode_id: str = ""


@dataclass
class MemoryExtractionResult:
    """Aggregated result from a single memory extraction call."""

    entities: List[ExtractedEntity] = field(default_factory=list)
    relationships: List[ExtractedRelationship] = field(default_factory=list)
    facts: List[ExtractedFact] = field(default_factory=list)
    reasoning: str = ""

    def filter_by_confidence(self, threshold: float = 0.5) -> None:
        """Remove entities, relationships, and facts below the confidence threshold."""
        self.entities = [e for e in self.entities if e.confidence >= threshold]
        self.relationships = [r for r in self.relationships if r.confidence >= threshold]
        self.facts = [f for f in self.facts if f.confidence >= threshold]