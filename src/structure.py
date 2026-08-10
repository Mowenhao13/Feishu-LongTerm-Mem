"""
Two-Layer Structure Definition

The simplified architecture after removing 4-layer hypergraph:

Raw Data Layer:
  EpisodeNode — conversation episodes from IM messages
  Document   — from local MD files (future)

Knowledge Layer:
  DecisionNode — prescriptive knowledge (decisions made)
  Objection   — objections to decisions (kept in node/types.py)
  TopicNode   — topics that group related episodes and decisions
  Person      — person entity (future, currently string references)

Relations are now direct between entities:
  Decision -[:DECIDES]-> Requirement (future)
  Person -[:RAISES_OBJECTION]-> Objection
  Decision -[:REFERENCES]-> Episode
  Decision -[:DEPENDS_ON|OVERRULES]-> Decision
  Decision|Objection -[:BELONGS_TO]-> Topic
"""

import numpy as np
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from .types import Episode, Topic, Decision, DecisionStatus, RawDataType


# ==================== Role Type Enumerations ====================

class FactRole(str, Enum):
    """Fact role types in an episode."""
    CORE = "core"
    CONTEXT = "context"
    DETAIL = "detail"
    TEMPORAL = "temporal"
    CAUSAL = "causal"


class EpisodeRole(str, Enum):
    """Episode role types in a topic."""
    INITIATING = "initiating"
    DEVELOPING = "developing"
    CLIMAX = "climax"
    CONCLUDING = "concluding"
    RECURRING = "recurring"
    BACKGROUND = "background"
    KEY_MOMENT = "key_moment"
    TRANSITION = "transition"


class DecisionRole(str, Enum):
    """Decision role types in an episode or topic."""
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    ALTERNATIVE = "alternative"
    AMENDMENT = "amendment"
    SUPERSEDING = "superseding"


# ==================== Node Types ====================

class EpisodeNode(BaseModel):
    """
    Episode node — raw data layer.

    Stores complete episode information from conversation aggregation.
    """
    id: str = Field(..., description="Node unique identifier, corresponds to event_id")
    user_id_list: List[str] = Field(default_factory=list, description="Involved user ID list")
    original_data: List[Dict[str, Any]] = Field(default_factory=list, description="Original data")
    timestamp: Optional[datetime] = Field(default=None, description="Event timestamp")
    summary: Optional[str] = Field(default=None, description="Episode summary")
    participants: Optional[List[str]] = Field(default=None, description="Participant list")
    type: Optional[RawDataType] = Field(default=None, description="Raw data type")
    keywords: Optional[List[str]] = Field(default=None, description="Keywords extracted from episode")
    subject: Optional[str] = Field(default=None, description="Episode subject")
    episode_description: Optional[str] = Field(default=None, description="Episode memory description")

    # Direct topic reference (replaces hyperedge indirection)
    topic_id: str = Field(default="", description="Associated topic ID")

    @classmethod
    def from_episode(cls, episode: Episode, topic_id: str = "") -> 'EpisodeNode':
        """Create EpisodeNode from Episode data class"""
        return cls(
            id=episode.event_id,
            user_id_list=episode.user_id_list,
            original_data=episode.original_data,
            timestamp=episode.timestamp,
            summary=episode.summary,
            participants=episode.participants,
            type=episode.type,
            keywords=episode.keywords,
            subject=episode.subject,
            episode_description=episode.episode_description,
            topic_id=topic_id,
        )

    def to_episode(self) -> Episode:
        """Convert to Episode data class"""
        return Episode(
            event_id=self.id,
            user_id_list=self.user_id_list,
            original_data=self.original_data,
            timestamp=self.timestamp if self.timestamp else datetime.now(),
            summary=self.summary if self.summary else "",
            participants=self.participants,
            type=self.type,
            keywords=self.keywords,
            subject=self.subject,
            episode_description=self.episode_description,
        )


class TopicNode(BaseModel):
    """
    Topic node — knowledge layer.

    Stores generalized topic information that groups related episodes and decisions.
    """
    id: str = Field(..., description="Node unique identifier, corresponds to topic_id")
    title: str = Field(..., description="Topic title/theme")
    summary: str = Field(..., description="Topic summary")
    episode_ids: List[str] = Field(default_factory=list, description="List of episode IDs that compose this topic")
    timestamp: Optional[datetime] = Field(default=None, description="Topic creation time")
    user_id_list: List[str] = Field(default_factory=list, description="Involved user ID list")
    participants: Optional[List[str]] = Field(default=None, description="Participant list")
    keywords: Optional[List[str]] = Field(default=None, description="Keywords describing this topic")

    @classmethod
    def from_topic(cls, topic: Topic) -> 'TopicNode':
        """Create TopicNode from Topic data class"""
        return cls(
            id=topic.topic_id,
            title=topic.title,
            summary=topic.summary,
            episode_ids=topic.episode_ids,
            timestamp=topic.timestamp,
            user_id_list=topic.user_id_list,
            participants=topic.participants,
            keywords=topic.keywords,
        )

    def to_topic(self) -> Topic:
        """Convert to Topic data class"""
        return Topic(
            topic_id=self.id,
            title=self.title,
            summary=self.summary,
            episode_ids=self.episode_ids,
            timestamp=self.timestamp if self.timestamp else datetime.now(),
            user_id_list=self.user_id_list,
            participants=self.participants,
            keywords=self.keywords,
        )


class DecisionNode(BaseModel):
    """
    Decision node — knowledge layer.

    Stores decision-level prescriptive knowledge:
    who decided what, why, and what came of it.
    """
    id: str = Field(..., description="Decision unique identifier (decision_id)")
    title: str = Field(..., description="Decision title")
    content: str = Field(..., description="Decision content/description")
    confidence: float = Field(default=0.8, description="Extraction confidence (0.0-1.0)")
    status: DecisionStatus = Field(default=DecisionStatus.PENDING, description="Decision lifecycle status")

    proposer: Optional[str] = Field(default=None, description="Who proposed the decision")
    executor: Optional[str] = Field(default=None, description="Who executes the decision")
    impact_level: str = Field(default="minor", description="Impact level: critical/major/advisory/minor")
    rationale: str = Field(default="", description="Rationale/reasoning behind the decision")

    episode_ids: List[str] = Field(default_factory=list, description="Source episode IDs")
    topic_id: str = Field(default="", description="Source topic ID")
    source_decision_ids: List[str] = Field(default_factory=list, description="Decisions this one supersedes/replaces")

    @classmethod
    def from_decision(cls, decision: Decision) -> 'DecisionNode':
        """Create DecisionNode from Decision data class"""
        return cls(
            id=decision.decision_id,
            title=decision.title,
            content=decision.content,
            confidence=decision.confidence,
            status=decision.status,
            proposer=decision.proposer,
            executor=decision.executor,
            impact_level=decision.impact_level,
            rationale=decision.rationale,
            episode_ids=decision.source_episode_ids or [],
            topic_id=decision.source_topic_ids[0] if decision.source_topic_ids else "",
            source_decision_ids=decision.superseded_decision_ids or [],
        )

    def to_decision(self) -> Decision:
        """Convert to Decision data class"""
        return Decision(
            decision_id=self.id,
            title=self.title,
            content=self.content,
            confidence=self.confidence,
            status=self.status,
            proposer=self.proposer,
            executor=self.executor,
            impact_level=self.impact_level,
            rationale=self.rationale,
            source_episode_ids=self.episode_ids,
            source_topic_ids=[self.topic_id] if self.topic_id else [],
            superseded_decision_ids=self.source_decision_ids,
        )

    def to_text(self) -> str:
        parts = [f"[{self.status.value}] {self.title}: {self.content}"]
        if self.proposer:
            parts.append(f"Proposer: {self.proposer}")
        if self.executor:
            parts.append(f"Executor: {self.executor}")
        if self.rationale:
            parts.append(f"Rationale: {self.rationale[:100]}")
        return " | ".join(parts)


# ==================== Graph Container ====================

class Hypergraph(BaseModel):
    """
    Simplified two-layer knowledge graph container.

    Raw Data Layer: episodes
    Knowledge Layer: decisions, topics
    """
    decisions: Dict[str, DecisionNode] = Field(
        default_factory=dict,
        description="Decision node dictionary (knowledge layer)"
    )
    episodes: Dict[str, EpisodeNode] = Field(
        default_factory=dict,
        description="Episode node dictionary (raw data layer)"
    )
    topics: Dict[str, TopicNode] = Field(
        default_factory=dict,
        description="Topic node dictionary (knowledge layer)"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'decisions': {k: v.model_dump(mode='json') for k, v in self.decisions.items()},
            'episodes': {k: v.model_dump(mode='json') for k, v in self.episodes.items()},
            'topics': {k: v.model_dump(mode='json') for k, v in self.topics.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Hypergraph':
        return cls(
            decisions={k: DecisionNode(**v) for k, v in data.get('decisions', {}).items()},
            episodes={k: EpisodeNode(**v) for k, v in data.get('episodes', {}).items()},
            topics={k: TopicNode(**v) for k, v in data.get('topics', {}).items()},
        )

    def get_stats(self) -> Dict[str, int]:
        return {
            'decisions': len(self.decisions),
            'episodes': len(self.episodes),
            'topics': len(self.topics),
        }

    def add_node(self, layer: str, node_id: str, **kwargs):
        """Add node to the specified layer."""
        if layer == "decision":
            self.decisions[node_id] = DecisionNode(
                id=node_id,
                title=kwargs.get("title", ""),
                content=kwargs.get("content", ""),
                confidence=kwargs.get("confidence", 0.8),
                status=kwargs.get("status", DecisionStatus.PENDING),
                proposer=kwargs.get("proposer"),
                executor=kwargs.get("executor"),
                impact_level=kwargs.get("impact_level", "minor"),
                rationale=kwargs.get("rationale", ""),
                episode_ids=kwargs.get("episode_ids", []),
                topic_id=kwargs.get("topic_id", ""),
                source_decision_ids=kwargs.get("source_decision_ids", []),
            )
        elif layer == "episode":
            self.episodes[node_id] = EpisodeNode(
                id=node_id,
                user_id_list=kwargs.get("user_id_list", []),
                original_data=kwargs.get("original_data", []),
                timestamp=kwargs.get("timestamp"),
                summary=kwargs.get("summary", ""),
                participants=kwargs.get("participants"),
                type=kwargs.get("type"),
                keywords=kwargs.get("keywords"),
                subject=kwargs.get("subject"),
                episode_description=kwargs.get("episode_description"),
                topic_id=kwargs.get("topic_id", ""),
            )
        elif layer == "topic":
            self.topics[node_id] = TopicNode(
                id=node_id,
                title=kwargs.get("title", ""),
                summary=kwargs.get("summary", ""),
                episode_ids=kwargs.get("episode_ids", []),
                timestamp=kwargs.get("timestamp"),
                user_id_list=kwargs.get("user_id_list", []),
                participants=kwargs.get("participants"),
                keywords=kwargs.get("keywords"),
            )
        else:
            raise ValueError(f"Invalid layer: {layer}. Must be 'decision', 'episode', or 'topic'")

    def get_node(self, layer: str, node_id: str) -> Dict[str, Any]:
        if layer == "decision":
            node = self.decisions.get(node_id)
            return node.model_dump() if node else {}
        elif layer == "episode":
            node = self.episodes.get(node_id)
            return node.model_dump() if node else {}
        elif layer == "topic":
            node = self.topics.get(node_id)
            return node.model_dump() if node else {}
        else:
            raise ValueError(f"Invalid layer: {layer}. Must be 'decision', 'episode', or 'topic'")


# ==================== Embedding Container ====================

class HypergraphEmbedding(BaseModel):
    """Embedding vectors for Hypergraph nodes."""
    model_config = {"arbitrary_types_allowed": True}

    decisions: Dict[str, np.ndarray] = Field(default_factory=dict)
    episodes: Dict[str, np.ndarray] = Field(default_factory=dict)
    topics: Dict[str, np.ndarray] = Field(default_factory=dict)

    def get_stats(self) -> Dict[str, int]:
        return {
            'decisions': len(self.decisions),
            'episodes': len(self.episodes),
            'topics': len(self.topics),
        }

    def to_dict(self) -> Dict[str, Any]:
        def convert_numpy(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: convert_numpy(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(item) for item in obj]
            else:
                return obj

        return convert_numpy({
            'decisions': self.decisions,
            'episodes': self.episodes,
            'topics': self.topics,
        })

    def add_embedding(self, layer: str, node_id: str, embedding: np.ndarray):
        if layer == "decision":
            self.decisions[node_id] = embedding
        elif layer == "episode":
            self.episodes[node_id] = embedding
        elif layer == "topic":
            self.topics[node_id] = embedding
        else:
            raise ValueError(f"Invalid layer: {layer}. Must be 'decision', 'episode', or 'topic'")

    def get_embedding(self, layer: str, node_id: str) -> np.ndarray:
        if layer == "decision":
            return self.decisions.get(node_id, np.array([]))
        elif layer == "episode":
            return self.episodes.get(node_id, np.array([]))
        elif layer == "topic":
            return self.topics.get(node_id, np.array([]))
        else:
            raise ValueError(f"Invalid layer: {layer}. Must be 'decision', 'episode', or 'topic'")

    @classmethod
    def compute_from_hypergraph(
        cls,
        hypergraph: Hypergraph,
        embed_fn,
        batch_size: int = 32,
    ) -> "HypergraphEmbedding":
        """Generate embeddings for all text-bearing nodes in a Hypergraph."""
        emb = cls()
        import numpy as np

        def _batch_embed(items: Dict[str, str]) -> Dict[str, np.ndarray]:
            ids = list(items.keys())
            texts = [items[i] for i in ids]
            result: Dict[str, np.ndarray] = {}
            for start in range(0, len(texts), batch_size):
                batch_texts = texts[start:start + batch_size]
                batch_ids = ids[start:start + batch_size]
                vectors = embed_fn(batch_texts)
                for nid, vec in zip(batch_ids, vectors):
                    result[nid] = np.array(vec, dtype=np.float32)
            return result

        # decisions
        decision_texts: Dict[str, str] = {}
        for did, d in hypergraph.decisions.items():
            txt = (d.content or d.title or "").strip()
            if txt:
                decision_texts[did] = txt
        if decision_texts:
            emb.decisions = _batch_embed(decision_texts)

        # episodes
        episode_texts: Dict[str, str] = {}
        for eid, e in hypergraph.episodes.items():
            txt = (e.summary or e.episode_description or "").strip()
            if txt:
                episode_texts[eid] = txt
        if episode_texts:
            emb.episodes = _batch_embed(episode_texts)

        # topics
        topic_texts: Dict[str, str] = {}
        for tid, t in hypergraph.topics.items():
            txt = f"{t.title}: {t.summary}" if t.title and t.summary else (t.title or t.summary or "").strip()
            if txt:
                topic_texts[tid] = txt
        if topic_texts:
            emb.topics = _batch_embed(topic_texts)

        return emb