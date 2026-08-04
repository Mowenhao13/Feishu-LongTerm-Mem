"""Simple in-memory entity store for extracted entities, relationships, and facts.

Provides:
- Thread-safe (single-threaded async) storage for the lifetime of a MemoryEngine
- Entity dedup by name
- Context-building for prompt injection (avoid duplicate entity extraction)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.extractors.memory_types import ExtractedEntity, ExtractedFact, ExtractedRelationship

logger = logging.getLogger(__name__)


class EntityStore:
    """Simple in-memory store for extracted entities, relationships, and facts."""

    def __init__(self) -> None:
        self._entities: Dict[str, ExtractedEntity] = {}  # name → entity
        self._relationships: List[ExtractedRelationship] = []
        self._facts: List[ExtractedFact] = []

    # ─────────────────────────────────────────────
    # Add operations
    # ─────────────────────────────────────────────

    def add_entities(self, entities: List[ExtractedEntity]) -> int:
        """Add entities, deduplicating by name (higher confidence wins).

        Returns:
            Number of new entities added (not counting overwrites).
        """
        count = 0
        for ent in entities:
            existing = self._entities.get(ent.name)
            if existing is None:
                self._entities[ent.name] = ent
                count += 1
            elif ent.confidence > existing.confidence:
                self._entities[ent.name] = ent
                # Overwrite counts as "new" since better data arrived
                count += 1
        if count:
            logger.debug("[EntityStore] Added/updated %d entities (total=%d)",
                         count, len(self._entities))
        return count

    def add_relationships(self, rels: List[ExtractedRelationship]) -> int:
        """Add relationships (append-only, no dedup).

        Returns:
            Number of relationships added.
        """
        self._relationships.extend(rels)
        if rels:
            logger.debug("[EntityStore] Added %d relationships (total=%d)",
                         len(rels), len(self._relationships))
        return len(rels)

    def add_facts(self, facts: List[ExtractedFact]) -> int:
        """Add facts (append-only, no dedup).

        Returns:
            Number of facts added.
        """
        self._facts.extend(facts)
        if facts:
            logger.debug("[EntityStore] Added %d facts (total=%d)",
                         len(facts), len(self._facts))
        return len(facts)

    # ─────────────────────────────────────────────
    # Query operations
    # ─────────────────────────────────────────────

    def get_entity(self, name: str) -> Optional[ExtractedEntity]:
        """Get a single entity by canonical name."""
        return self._entities.get(name)

    def get_all_entities(self) -> List[ExtractedEntity]:
        """Get all stored entities."""
        return list(self._entities.values())

    def get_entities_by_type(self, type_name: str) -> List[ExtractedEntity]:
        """Get all entities matching a specific entity type (e.g. 'Technology')."""
        return [e for e in self._entities.values() if e.entity_type == type_name]

    def get_all_relationships(self) -> List[ExtractedRelationship]:
        """Get all stored relationships."""
        return list(self._relationships)

    def get_all_facts(self) -> List[ExtractedFact]:
        """Get all stored facts."""
        return list(self._facts)

    def count(self) -> Dict[str, int]:
        """Return counts of stored items."""
        return {
            "entities": len(self._entities),
            "relationships": len(self._relationships),
            "facts": len(self._facts),
        }

    # ─────────────────────────────────────────────
    # Context building
    # ─────────────────────────────────────────────

    def build_extraction_context(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Build a list of entity dicts for prompt injection context.

        Args:
            names: Optional subset of entity names to include.
                   If None, returns all entities.

        Returns:
            List of dicts: [{"name": "...", "entity_type": "..."}, ...]
        """
        if names is not None:
            entities = [self._entities[n] for n in names if n in self._entities]
        else:
            entities = list(self._entities.values())

        return [
            {"name": e.name, "entity_type": e.entity_type}
            for e in entities
        ]

    # ─────────────────────────────────────────────
    # Neo4j sync helpers
    # ─────────────────────────────────────────────

    def get_dirty_entities(self) -> List[ExtractedEntity]:
        """获取所有待同步实体（兼容 Neo4jSyncEngine 接口）"""
        return list(self._entities.values())

    def get_dirty_relationships(self) -> List[ExtractedRelationship]:
        """获取所有待同步关系（兼容 Neo4jSyncEngine 接口）"""
        return list(self._relationships)

    # ─────────────────────────────────────────────
    # Maintenance
    # ─────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all stored data."""
        self._entities.clear()
        self._relationships.clear()
        self._facts.clear()
        logger.info("[EntityStore] Cleared all data")