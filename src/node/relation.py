"""
Hypergraph relation edge definitions for decision nodes.

Based on structure.py Hyperedge / DecisionHyperedge design.
Relations are modeled as hypergraph hyperedges: an edge connects
a set of node IDs with typed roles, forming an n-ary semantic relation.

Relates to:
- src/node/types.py Relation (the outgoing link from a node to edge)
- src/node/node.py DecisionNode.relations (list of Relation)
- src/structure.py DecisionHyperedge, FactHyperedge, EpisodeHyperedge
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from src.node.types import Relation, RelationType


# ==================== Participant role (who participates in a hyperedge) ====================


class Participant(BaseModel):
    """A node participating in a hyperedge, with its role."""
    node_id: str = Field(..., description="Node SDRID")
    role: str = Field(default="member", description="Role within the hyperedge")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Participation weight")


# ==================== Hyperedge (base, from structure.py Hyperedge) ====================


class HyperedgeType(str, Enum):
    """Type of hyperedge."""
    DECISION_DEPENDENCY = "decision_dependency"
    DECISION_SUPERSEDE = "decision_supersede"
    DECISION_CONFLICT = "decision_conflict"
    DECISION_REFINEMENT = "decision_refinement"
    DECISION_OBJECTION = "decision_objection"
    DECISION_RELATED = "decision_related"
    TOPIC_GROUP = "topic_group"
    CROSS_LAYER = "cross_layer"


class Hyperedge(BaseModel):
    """A hyperedge connecting multiple nodes.

    Based on structure.py Hyperedge concept:
    - hyperedge_id: unique identifier
    - participants: list of (node_id, role, weight) tuples
    - edge_type: semantic type (aligned with RelationType)
    - properties: extensible metadata dict
    """
    hyperedge_id: str = Field(..., description="Unique hyperedge ID")
    participants: List[Participant] = Field(default_factory=list, description="Participating nodes")
    edge_type: str = Field(default="", description="Semantic type of this edge")
    relation_type: RelationType = Field(default=RelationType.RELATES_TO, description="Relation type")
    label: str = Field(default="", description="Human-readable label")
    description: str = Field(default="", description="Description of this relation")

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_directed: bool = Field(default=False, description="Whether direction matters")
    properties: Dict[str, Any] = Field(default_factory=dict)

    def add_participant(self, node_id: str, role: str = "member", weight: float = 1.0) -> None:
        self.participants.append(Participant(node_id=node_id, role=role, weight=weight))
        self.updated_at = datetime.now()

    def participant_ids(self) -> List[str]:
        return [p.node_id for p in self.participants]

    def participant_count(self) -> int:
        return len(self.participants)

    def has_node(self, node_id: str) -> bool:
        return any(p.node_id == node_id for p in self.participants)

    def remove_node(self, node_id: str) -> bool:
        before = len(self.participants)
        self.participants = [p for p in self.participants if p.node_id != node_id]
        return len(self.participants) < before


# ==================== Specialized Hyperedge Types ====================


class DecisionHyperedge(Hyperedge):
    """Hyperedge connecting decision nodes.

    Maps to structure.DecisionHyperedge concept:
    - nodes: list of decision node IDs
    - roles: maps node_id → role within this decision context
    """
    nodes: List[str] = Field(default_factory=list, description="List of decision node SDRIDs")
    roles: Dict[str, str] = Field(default_factory=dict, description="node_id → role mapping")
    decision_context: str = Field(default="", description="Context/reason for this relation")

    def sync_participants(self) -> None:
        for node_id in self.nodes:
            role = self.roles.get(node_id, "member")
            if not self.has_node(node_id):
                self.add_participant(node_id, role=role)


class FactHyperedge(Hyperedge):
    """Hyperedge connecting fact nodes.

    Maps to structure.FactHyperedge concept.
    """
    fact_ids: List[str] = Field(default_factory=list, description="List of fact node IDs")
    source_type: str = Field(default="", description="Source type: memory/extraction/inference")


class EpisodeHyperedge(Hyperedge):
    """Hyperedge connecting episode/conversation nodes.

    Maps to structure.EpisodeHyperedge concept.
    """
    episode_ids: List[str] = Field(default_factory=list, description="List of episode node IDs")
    conversation_id: str = Field(default="", description="Source conversation ID")


# ==================== Relation Builder ====================


class RelationBuilder:
    """Builds Relation (node-level link) and Hyperedge (graph-level edge) pairs."""

    @staticmethod
    def build_dependency(
        source_id: str,
        target_id: str,
        description: str = "",
        hyperedge_id: str = "",
    ) -> tuple[Relation, Hyperedge]:
        hyperedge_id = hyperedge_id or f"he_{source_id}_{target_id}_{RelationType.DEPENDS_ON.value}"

        relation = Relation(
            type=RelationType.DEPENDS_ON,
            target_id=target_id,
            description=description or f"{source_id} depends on {target_id}",
            hyperedge_id=hyperedge_id,
        )

        hyperedge = DecisionHyperedge(
            hyperedge_id=hyperedge_id,
            edge_type=HyperedgeType.DECISION_DEPENDENCY.value,
            relation_type=RelationType.DEPENDS_ON,
            nodes=[source_id, target_id],
            roles={source_id: "dependent", target_id: "prerequisite"},
            description=description,
            is_directed=True,
        )
        hyperedge.sync_participants()

        return relation, hyperedge

    @staticmethod
    def build_conflict(
        source_id: str,
        target_id: str,
        description: str = "",
        hyperedge_id: str = "",
    ) -> tuple[Relation, Hyperedge]:
        hyperedge_id = hyperedge_id or f"he_{source_id}_{target_id}_{RelationType.CONFLICTS_WITH.value}"

        relation = Relation(
            type=RelationType.CONFLICTS_WITH,
            target_id=target_id,
            description=description or f"{source_id} conflicts with {target_id}",
            hyperedge_id=hyperedge_id,
        )

        hyperedge = DecisionHyperedge(
            hyperedge_id=hyperedge_id,
            edge_type=HyperedgeType.DECISION_CONFLICT.value,
            relation_type=RelationType.CONFLICTS_WITH,
            nodes=[source_id, target_id],
            roles={source_id: "conflicting", target_id: "conflicting"},
            description=description,
            is_directed=False,
        )
        hyperedge.sync_participants()

        return relation, hyperedge

    @staticmethod
    def build_supersede(
        source_id: str,
        target_id: str,
        description: str = "",
        hyperedge_id: str = "",
    ) -> tuple[Relation, Hyperedge]:
        hyperedge_id = hyperedge_id or f"he_{source_id}_{target_id}_{RelationType.SUPERSEDES.value}"

        relation = Relation(
            type=RelationType.SUPERSEDES,
            target_id=target_id,
            description=description or f"{source_id} supersedes {target_id}",
            hyperedge_id=hyperedge_id,
        )

        hyperedge = DecisionHyperedge(
            hyperedge_id=hyperedge_id,
            edge_type=HyperedgeType.DECISION_SUPERSEDE.value,
            relation_type=RelationType.SUPERSEDES,
            nodes=[source_id, target_id],
            roles={source_id: "superseding", target_id: "superseded"},
            description=description,
            is_directed=True,
        )
        hyperedge.sync_participants()

        return relation, hyperedge

    @staticmethod
    def build_refinement(
        source_id: str,
        target_id: str,
        description: str = "",
        hyperedge_id: str = "",
    ) -> tuple[Relation, Hyperedge]:
        hyperedge_id = hyperedge_id or f"he_{source_id}_{target_id}_{RelationType.REFINES.value}"

        relation = Relation(
            type=RelationType.REFINES,
            target_id=target_id,
            description=description or f"{source_id} refines {target_id}",
            hyperedge_id=hyperedge_id,
        )

        hyperedge = DecisionHyperedge(
            hyperedge_id=hyperedge_id,
            edge_type=HyperedgeType.DECISION_REFINEMENT.value,
            relation_type=RelationType.REFINES,
            nodes=[source_id, target_id],
            roles={source_id: "specialization", target_id: "generalization"},
            description=description,
            is_directed=True,
        )
        hyperedge.sync_participants()

        return relation, hyperedge

    @staticmethod
    def build_related(
        source_id: str,
        target_id: str,
        description: str = "",
        hyperedge_id: str = "",
    ) -> tuple[Relation, Hyperedge]:
        hyperedge_id = hyperedge_id or f"he_{source_id}_{target_id}_{RelationType.RELATES_TO.value}"

        relation = Relation(
            type=RelationType.RELATES_TO,
            target_id=target_id,
            description=description or f"{source_id} relates to {target_id}",
            hyperedge_id=hyperedge_id,
        )

        hyperedge = DecisionHyperedge(
            hyperedge_id=hyperedge_id,
            edge_type=HyperedgeType.DECISION_RELATED.value,
            relation_type=RelationType.RELATES_TO,
            nodes=[source_id, target_id],
            roles={source_id: "related", target_id: "related"},
            description=description,
            is_directed=False,
        )
        hyperedge.sync_participants()

        return relation, hyperedge


# ==================== Hypergraph ====================


class Hypergraph(BaseModel):
    """A collection of hyperedges forming a relation graph.

    Maps to structure.StructuredMemory concept of hyperedges collection.
    """
    hyperedges: Dict[str, Hyperedge] = Field(default_factory=dict, description="hyperedge_id → Hyperedge")

    def add_hyperedge(self, hyperedge: Hyperedge) -> None:
        self.hyperedges[hyperedge.hyperedge_id] = hyperedge

    def get_hyperedge(self, hyperedge_id: str) -> Optional[Hyperedge]:
        return self.hyperedges.get(hyperedge_id)

    def get_edges_for_node(self, node_id: str) -> List[Hyperedge]:
        return [e for e in self.hyperedges.values() if e.has_node(node_id)]

    def get_connected_nodes(self, node_id: str) -> Set[str]:
        connected: Set[str] = set()
        for edge in self.hyperedges.values():
            if edge.has_node(node_id):
                connected.update(edge.participant_ids())
        connected.discard(node_id)
        return connected

    def remove_hyperedge(self, hyperedge_id: str) -> bool:
        return self.hyperedges.pop(hyperedge_id, None) is not None

    def size(self) -> int:
        return len(self.hyperedges)