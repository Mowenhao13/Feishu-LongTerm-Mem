"""
Neo4j sync engine — synchronises in-memory graph structures to Neo4j.

Bridges the gap between the runtime memory graph / entity store and the
persistent Neo4j graph database.  The sync engine is designed to be
called periodically (e.g. from the SleepManager consolidation loop or
from the pipeline registry) and only transmits decisions / entities
that are marked as dirty.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.graph.memory_graph import MemoryGraph
    from src.storage.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class Neo4jSyncEngine:
    """Synchronises in-memory data structures to Neo4j.

    Responsibilities:
      - Flush dirty decisions from MemoryGraph into Neo4j Decision nodes
        with their BELONGS_TO and inter-decision relationships.
      - Flush entities and relationships from the entity store into
        Neo4j Entity nodes and :RELATES edges.
      - Provide summary stats of what was synced.

    The engine is resilient to transient Neo4j failures — it catches
    connection errors and logs them, continuing with the next batch
    rather than raising.
    """

    def __init__(self, client: Neo4jClient) -> None:
        self._client = client
        self._stats: Dict[str, int] = {
            "decisions_written": 0,
            "entities_written": 0,
            "relationships_written": 0,
            "episodes_written": 0,
            "errors": 0,
        }

    # ---------- public sync entry points ----------

    async def sync_all(
        self,
        memory_graph: Optional["MemoryGraph"] = None,
        entity_store: Optional[Any] = None,
    ) -> Dict[str, int]:
        """Sync both decisions and entities to Neo4j.

        Args:
            memory_graph: MemoryGraph instance (provides get_dirty_and_clean).
            entity_store: An object with ``get_dirty_entities()`` and
                          ``get_dirty_relationships()`` methods.  If the
                          entity_store has no such methods, it is skipped
                          silently.

        Returns:
            Dict with per-category write/error counts.
        """
        self._reset_stats()

        if memory_graph is not None:
            await self.sync_decisions(memory_graph)
        if entity_store is not None:
            await self.sync_entities(entity_store)

        return dict(self._stats)

    async def sync_decisions(self, memory_graph: "MemoryGraph") -> None:
        """Flush dirty decisions from MemoryGraph to Neo4j."""
        dirty = memory_graph.get_dirty_and_clean()
        if not dirty:
            logger.debug("Neo4j sync: no dirty decisions to sync")
            return

        logger.info("Neo4j sync: syncing %d dirty decisions", len(dirty))
        for decision in dirty:
            try:
                await self._client.upsert_decision(decision)
                self._stats["decisions_written"] += 1
            except Exception as exc:
                logger.error("Failed to upsert decision %s: %s", decision.sid, exc)
                self._stats["errors"] += 1

    async def sync_entities(self, entity_store: Any) -> None:
        """Flush dirty entities and relationships from the entity store."""
        # Entities
        entities: List = []
        try:
            entities = entity_store.get_dirty_entities()
        except AttributeError:
            logger.debug("Neo4j sync: entity_store has no get_dirty_entities(), skipping entities")

        if entities:
            logger.info("Neo4j sync: syncing %d dirty entities", len(entities))
            for entity in entities:
                try:
                    # 适配层：memory_types.ExtractedEntity 与 neo4j_client.ExtractedEntity 的属性名不同
                    source_type = getattr(entity, 'source_type', 'episode')
                    neo4j_entity = entity
                    if hasattr(entity, 'source_episode_id'):
                        neo4j_entity = type('Neo4jEntity', (), {
                            'name': entity.name,
                            'entity_type': entity.entity_type,
                            'attributes': getattr(entity, 'attributes', {}),
                            'confidence': getattr(entity, 'confidence', 0.8),
                            'source_id': entity.source_episode_id,
                            'created_at': getattr(entity, 'created_at', None),
                        })()
                    await self._client.upsert_entity(neo4j_entity, source_type=source_type)
                    self._stats["entities_written"] += 1
                except Exception as exc:
                    logger.error("Failed to upsert entity '%s': %s", getattr(entity, 'name', '?'), exc)
                    self._stats["errors"] += 1

        # Relationships
        relationships: List = []
        try:
            relationships = entity_store.get_dirty_relationships()
        except AttributeError:
            logger.debug("Neo4j sync: entity_store has no get_dirty_relationships(), skipping relationships")

        if relationships:
            logger.info("Neo4j sync: syncing %d dirty relationships", len(relationships))
            for rel in relationships:
                try:
                    # 适配层：memory_types.ExtractedRelationship 与 neo4j_client.ExtractedRelationship 的属性名不同
                    # memory_types 使用 source_name/target_name/relationship_type
                    # neo4j_client 使用 source/target/rel_type
                    neo4j_rel = rel
                    if hasattr(rel, 'source_name'):
                        # 来自 memory_types 的 ExtractedRelationship
                        neo4j_rel = type('Neo4jRel', (), {
                            'source': rel.source_name,
                            'target': rel.target_name,
                            'rel_type': rel.relationship_type,
                            'confidence': getattr(rel, 'confidence', 0.8),
                            'attributes': {},
                            'valid_at': getattr(rel, 'valid_at', None),
                            'source_id': getattr(rel, 'source_episode_id', ''),  # field name mismatch
                        })()
                    await self._client.upsert_relationship(neo4j_rel)
                    self._stats["relationships_written"] += 1
                except Exception as exc:
                    rel_src = getattr(rel, 'source', getattr(rel, 'source_name', '?'))
                    rel_tgt = getattr(rel, 'target', getattr(rel, 'target_name', '?'))
                    logger.error("Failed to upsert relationship %s->%s: %s", rel_src, rel_tgt, exc)
                    self._stats["errors"] += 1

    # ---------- helpers ----------

    def _reset_stats(self) -> None:
        for k in self._stats:
            self._stats[k] = 0

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)