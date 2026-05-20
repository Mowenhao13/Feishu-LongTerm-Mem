"""
Node module: Decision nodes with hypergraph relation edges.

- types: Core type definitions (DecisionStatus, Relation, Objection, etc.)
- node: DecisionNode model aligned with structure.py and decision_prompts
- relation: Hypergraph hyperedge-based relation definitions
"""
from .node import DecisionNode, DecisionRole, new_decision_node
from .relation import (
    DecisionHyperedge,
    EpisodeHyperedge,
    FactHyperedge,
    Hyperedge,
    HyperedgeType,
    Hypergraph,
    Participant,
    RelationBuilder,
)
from .types import (
    ACTIVE_DECISION_STATUSES,
    INACTIVE_DECISION_STATUSES,
    AccessStats,
    DecisionStatus,
    FeishuLinks,
    ImpactLevel,
    Objection,
    ObjectionStatus,
    PhaseScope,
    Relation,
    RelationType,
    VersionRange,
)

__all__ = [
    "DecisionNode",
    "DecisionRole",
    "new_decision_node",
    "DecisionStatus",
    "RelationType",
    "Relation",
    "Objection",
    "ObjectionStatus",
    "ImpactLevel",
    "PhaseScope",
    "VersionRange",
    "FeishuLinks",
    "AccessStats",
    "ACTIVE_DECISION_STATUSES",
    "INACTIVE_DECISION_STATUSES",
    "Hyperedge",
    "HyperedgeType",
    "Participant",
    "DecisionHyperedge",
    "FactHyperedge",
    "EpisodeHyperedge",
    "Hypergraph",
    "RelationBuilder",
]