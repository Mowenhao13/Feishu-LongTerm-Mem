"""
Neo4j graph database client for the memory system.

Provides async CRUD operations on the Neo4j graph model:
  - Entity nodes with type-based attributes
  - Decision nodes with lifecycle and topic association
  - Episode and Topic nodes
  - Inter-node relationships (BELONGS_TO, REFERENCES, SUPERSEDES, etc.)

Uses neo4j.AsyncGraphDatabase for connection pooling.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable, AuthError, ClientError

logger = logging.getLogger(__name__)


# ==================== Lightweight data types (aligned with memory_extractor types from Phase 3) ====================


@dataclass
class ExtractedEntity:
    """Entity extracted from conversation by the memory extractor."""
    name: str
    entity_type: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    source_id: str = ""
    created_at: Optional[datetime] = None


@dataclass
class ExtractedRelationship:
    """Relationship between two entities extracted from conversation."""
    source: str           # source entity name
    target: str           # target entity name
    rel_type: str         # e.g. "KNOWS", "WORKS_AT", "MENTIONS"
    confidence: float = 0.8
    attributes: Dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    valid_at: Optional[datetime] = None


# ==================== Helper: serialize / deserialize ====================


def _serialize_value(val: Any) -> Any:
    """Convert Python values to Neo4j-safe primitives."""
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _serialize_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_serialize_value(v) for v in val]
    if isinstance(val, Enum):
        return val.value
    return val


def _deserialize_record(record: Any) -> dict:
    """Convert a neo4j Record to a plain dict, unpacking node/rel properties."""
    data = {}
    for key in record.keys():
        value = record[key]
        if hasattr(value, "get"):
            # It's a Node or Relationship — extract .items()
            data[key] = dict(value)
        elif isinstance(value, list):
            data[key] = [_deserialize_record(v) if hasattr(v, "get") else v for v in value]
        else:
            data[key] = value
    return data


# ==================== Neo4jClient ====================


class Neo4jClient:
    """Async Neo4j client for the memory system.

    Manages connection lifecycle, schema constraints, and all CRUD
    operations against the graph data model.
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "neo4j123",
        max_connection_pool_size: int = 10,
        connection_timeout: float = 10.0,
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._max_pool_size = max_connection_pool_size
        self._connection_timeout = connection_timeout
        self._driver: Optional[AsyncDriver] = None

    # ---------- lifecycle ----------

    async def connect(self) -> None:
        """Open the connection pool."""
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
            max_connection_pool_size=self._max_pool_size,
            connection_timeout=self._connection_timeout,
        )
        logger.info("Neo4jClient connected to %s", self._uri)

    async def close(self) -> None:
        """Close the connection pool."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4jClient closed")

    async def __aenter__(self) -> "Neo4jClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def verify_connection(self) -> bool:
        """Verify the connection is alive and authenticated."""
        if self._driver is None:
            return False
        try:
            async with self._driver.session(database="neo4j") as session:
                result = await session.run("RETURN 1 AS ok")
                record = await result.single()
                return record is not None and record.get("ok") == 1
        except (ServiceUnavailable, AuthError, ClientError) as exc:
            logger.warning("Neo4j connection verification failed: %s", exc)
            return False

    # ---------- schema ----------

    async def create_constraints(self) -> None:
        """Create uniqueness constraints for the data model."""
        if self._driver is None:
            raise RuntimeError("Neo4j driver not connected")

        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Decision) REQUIRE d.sid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Topic) REQUIRE t.topic_id IS UNIQUE",
        ]
        async with self._driver.session(database="neo4j") as session:
            for cql in constraints:
                try:
                    await session.run(cql)
                except ClientError as exc:
                    logger.warning("Constraint creation skipped (%s): %s", cql, exc)
        logger.info("Neo4j constraints created / verified")

    # ---------- helpers ----------

    def _session(self) -> AsyncSession:
        if self._driver is None:
            raise RuntimeError("Neo4j driver not connected")
        return self._driver.session(database="neo4j")

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat()

    # ---------- entity CRUD ----------

    async def upsert_entity(self, entity: ExtractedEntity) -> None:
        """Create or update an Entity node.

        Uses MERGE on name for idempotent upsert. The attributes_json
        field stores the full attributes dict as a JSON string so it
        remains query-agnostic.
        """
        now = self._now()
        attrs_json = json.dumps(entity.attributes, ensure_ascii=False, default=_serialize_value)

        async with self._session() as session:
            await session.run(
                """
                MERGE (e:Entity {name: $name})
                SET e.entity_type = $entity_type,
                    e.attributes_json = $attributes_json,
                    e.confidence = $confidence,
                    e.created_at = COALESCE(e.created_at, $now)
                """,
                name=entity.name,
                entity_type=entity.entity_type,
                attributes_json=attrs_json,
                confidence=entity.confidence,
                now=now,
            )

    async def upsert_relationship(self, rel: ExtractedRelationship) -> None:
        """Create or update a RELATES_TO relationship between two entities.

        The relationship type from the extracted data is stored as a
        property rather than as the Neo4j rel-type, so we only use
        the generic :RELATES edge label.
        """
        valid_at = rel.valid_at.isoformat() if rel.valid_at else None
        attrs_json = json.dumps(rel.attributes, ensure_ascii=False, default=_serialize_value)

        async with self._session() as session:
            await session.run(
                """
                MATCH (s:Entity {name: $source})
                MATCH (t:Entity {name: $target})
                MERGE (s)-[r:RELATES {type: $rel_type}]->(t)
                SET r.confidence = $confidence,
                    r.attributes_json = $attributes_json,
                    r.valid_at = COALESCE(r.valid_at, $valid_at)
                """,
                source=rel.source,
                target=rel.target,
                rel_type=rel.rel_type,
                confidence=rel.confidence,
                attributes_json=attrs_json,
                valid_at=valid_at,
            )

    async def query_entity(self, name: str) -> Optional[dict]:
        """Lookup an entity by name, returning its properties or None."""
        async with self._session() as session:
            result = await session.run(
                "MATCH (e:Entity {name: $name}) RETURN e AS entity", name=name
            )
            record = await result.single()
            if record is None:
                return None
            return _deserialize_record(record)

    async def query_entities_by_type(self, type_name: str) -> list:
        """Return all entities matching a given entity_type."""
        async with self._session() as session:
            result = await session.run(
                "MATCH (e:Entity {entity_type: $type_name}) RETURN e AS entity ORDER BY e.name",
                type_name=type_name,
            )
            return [_deserialize_record(r) for r in await result.fetch(1000)]

    async def query_entity_relationships(
        self, name: str, max_depth: int = 2
    ) -> list:
        """Return sub-graph around an entity up to *max_depth* hops.

        Returns a list of flat dicts describing the nodes and
        relationships discovered.
        """
        # Build the path pattern with a literal number (Neo4j doesn't
        # allow parameterised length in variable-length relationship patterns).
        rel_pattern = f"[:RELATES*1..{max_depth}]"
        async with self._session() as session:
            result = await session.run(
                f"""
                MATCH path = (e:Entity {{name: $name}})-{rel_pattern}-(related)
                UNWIND nodes(path) AS n
                UNWIND relationships(path) AS r
                RETURN DISTINCT
                    n.name AS node_name,
                    labels(n) AS node_labels,
                    n.entity_type AS entity_type,
                    r.type AS rel_type,
                    r.confidence AS rel_confidence
                LIMIT 500
                """,
                name=name,
            )
            return [_deserialize_record(r) for r in await result.fetch(1000)]

    # ---------- decision CRUD ----------

    async def upsert_decision(self, decision: "DecisionNode") -> None:
        """Create or update a Decision node and its BELONGS_TO relationship to a Topic."""
        now = self._now()
        created = decision.created_at.isoformat() if decision.created_at else now
        updated = decision.updated_at.isoformat() if decision.updated_at else created

        async with self._session() as session:
            # Upsert the decision node
            await session.run(
                """
                MERGE (d:Decision {sid: $sid})
                SET d.title = $title,
                    d.summary = $summary,
                    d.status = $status,
                    d.topic_id = $topic_id,
                    d.impact_level = $impact_level,
                    d.confidence = $confidence,
                    d.created_at = COALESCE(d.created_at, $created_at),
                    d.updated_at = $updated_at,
                    d.version = $version
                """,
                sid=decision.sid,
                title=decision.title,
                summary=decision.summary,
                status=decision.status.value if hasattr(decision.status, "value") else str(decision.status),
                topic_id=decision.topic_id,
                impact_level=decision.impact_level.value if hasattr(decision.impact_level, "value") else str(decision.impact_level),
                confidence=decision.confidence,
                created_at=created,
                updated_at=updated,
                version=decision.version,
            )

            # BELONGS_TO -> Topic (if topic_id is set)
            if decision.topic_id:
                await session.run(
                    """
                    MERGE (t:Topic {topic_id: $topic_id})
                    WITH t
                    MATCH (d:Decision {sid: $sid})
                    MERGE (d)-[:BELONGS_TO]->(t)
                    """,
                    sid=decision.sid,
                    topic_id=decision.topic_id,
                )

            # REFERENCES -> Episode (if source_chat_id is set)
            if decision.source_chat_id:
                await session.run(
                    """
                    MERGE (e:Episode {id: $episode_id})
                    WITH e
                    MATCH (d:Decision {sid: $sid})
                    MERGE (d)-[:REFERENCES]->(e)
                    """,
                    sid=decision.sid,
                    episode_id=decision.source_chat_id,
                )

            # Inter-decision relationships from decision.relations
            for rel in decision.relations:
                rel_type = _neo4j_rel_type(rel.type)
                cql = f"""
                    MATCH (a:Decision {{sid: $sid}})
                    MATCH (b:Decision {{sid: $target_id}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r.description = $description
                """
                await session.run(
                    cql,
                    sid=decision.sid,
                    target_id=rel.target_id,
                    description=rel.description,
                )

    async def query_decisions_by_topic(self, topic_id: str) -> list:
        """Return all decisions BELONGS_TO the given topic_id."""
        async with self._session() as session:
            result = await session.run(
                """
                MATCH (d:Decision)-[:BELONGS_TO]->(:Topic {topic_id: $topic_id})
                RETURN d AS decision
                ORDER BY d.created_at DESC
                """,
                topic_id=topic_id,
            )
            return [_deserialize_record(r) for r in await result.fetch(1000)]

    async def query_decision_timeline(self, sid: str) -> list:
        """Return the decision timeline for a given decision SDRID.

        This traverses SUPERSEDES links backward and forward to build
        a version timeline.
        """
        async with self._session() as session:
            result = await session.run(
                """
                MATCH path = (start:Decision {sid: $sid})-[:SUPERSEDES|DEPENDS_ON|CONFLICTS_WITH*0..5]-(related)
                UNWIND nodes(path) AS n
                RETURN DISTINCT n AS decision
                ORDER BY n.created_at ASC
                """,
                sid=sid,
            )
            return [_deserialize_record(r) for r in await result.fetch(1000)]

    # ---------- episode CRUD ----------

    async def upsert_episode(self, episode: Dict[str, Any]) -> None:
        """Create or update an Episode node and link it to its topic."""
        now = self._now()
        sid = episode.get("id", "") or episode.get("event_id", "")
        summary = episode.get("summary", "")
        chat_id = episode.get("chat_id", "") or episode.get("source_chat_id", "")
        topic_id = episode.get("topic_id", "")

        if not sid:
            logger.warning("upsert_episode skipped: no id provided")
            return

        async with self._session() as session:
            await session.run(
                """
                MERGE (e:Episode {id: $id})
                SET e.summary = $summary,
                    e.chat_id = $chat_id,
                    e.created_at = COALESCE(e.created_at, $now)
                """,
                id=sid,
                summary=summary,
                chat_id=chat_id,
                now=now,
            )

            if topic_id:
                await session.run(
                    """
                    MERGE (t:Topic {topic_id: $topic_id})
                    WITH t
                    MATCH (e:Episode {id: $id})
                    MERGE (e)-[:BELONGS_TO]->(t)
                    """,
                    id=sid,
                    topic_id=topic_id,
                )

    # ---------- temporal query ----------

    async def query_as_of(
        self, entity_name: str, timestamp: str
    ) -> Optional[dict]:
        """Return the entity state as of a given ISO-8601 timestamp.

        Since Neo4j doesn't have built-in temporal versioning, this
        returns the entity if its created_at <= timestamp, or None.
        """
        async with self._session() as session:
            result = await session.run(
                """
                MATCH (e:Entity {name: $name})
                WHERE e.created_at IS NULL OR e.created_at <= $timestamp
                RETURN e AS entity
                """,
                name=entity_name,
                timestamp=timestamp,
            )
            record = await result.single()
            if record is None:
                return None
            return _deserialize_record(record)

    # ---------- cleanup / testing ----------

    async def drop_all(self) -> None:
        """Delete ALL nodes and relationships in the database.

        Warning: destructive. Intended for testing only.
        """
        async with self._session() as session:
            await session.run("MATCH (n) DETACH DELETE n")
        logger.warning("Neo4j: all nodes deleted")


# ==================== helper: map RelationType enum to Neo4j rel label ====================


def _neo4j_rel_type(rel_type: Any) -> str:
    """Convert any relation type identifier to a valid Neo4j relationship label."""
    type_map: Dict[str, str] = {
        "DEPENDS_ON": "DEPENDS_ON",
        "SUPERSEDES": "SUPERSEDES",
        "REFINES": "REFINES",
        "CONFLICTS_WITH": "CONFLICTS_WITH",
        "RELATES_TO": "RELATES_TO",
        "OBJECTION": "OBJECTION",
    }
    raw = rel_type.value if hasattr(rel_type, "value") else str(rel_type)
    return type_map.get(raw.upper(), "RELATES_TO")