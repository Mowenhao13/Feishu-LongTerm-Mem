"""
Node types - Merged from ref/decision/relation.go + ref/decision/objection.go

Relation types, Relation edge, Objection status, and Objection entity.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== Relation Types (from relation.go) ====================


class RelationType(str, Enum):
    """Relation type between decision nodes."""
    DEPENDS_ON = "DEPENDS_ON"
    SUPERSEDES = "SUPERSEDES"
    REFINES = "REFINES"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    RELATES_TO = "RELATES_TO"
    OBJECTION = "OBJECTION"


RELATION_TYPE_DESCRIPTIONS: Dict[RelationType, str] = {
    RelationType.DEPENDS_ON: "A depends on B (A cannot proceed without B)",
    RelationType.SUPERSEDES: "A supersedes B (A replaces B as the newer decision)",
    RelationType.REFINES: "A refines B (A provides more detail or a narrower scope)",
    RelationType.CONFLICTS_WITH: "A conflicts with B (A and B cannot both be true)",
    RelationType.RELATES_TO: "A relates to B (general association, no specific semantics)",
    RelationType.OBJECTION: "A has an objection from some source (links to Objection entity)",
}


class Relation(BaseModel):
    """Relation edge connecting a decision node to a target node."""
    type: RelationType = Field(..., description="Type of relation")
    target_id: str = Field(..., description="Target decision SDRID or node ID")
    description: str = Field(default="", description="Optional description of the relation")
    hyperedge_id: str = Field(default="", description="Corresponding hyperedge ID (bi-directional link)")


# ==================== Objection Types (from objection.go) ====================


class ObjectionStatus(str, Enum):
    """Status of an objection."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    OVERRULED = "overruled"

    def is_valid(self) -> bool:
        return self in (ObjectionStatus.ACTIVE, ObjectionStatus.RESOLVED, ObjectionStatus.OVERRULED)


class Objection(BaseModel):
    """Objection record linked to a decision node."""
    oid: str = Field(..., description="Objection unique identifier")
    objection_content: str = Field(..., description="Content of the objection")
    rationale: str = Field(default="", description="Reasoning behind the objection")
    alternative: str = Field(default="", description="Proposed alternative, if any")
    objector: str = Field(default="", description="Who raised the objection")

    status: ObjectionStatus = Field(default=ObjectionStatus.ACTIVE, description="Current status")

    references_decision: str = Field(default="", description="Decision SDRID this objection targets")

    source_type: str = Field(default="", description="Source channel: comment/im/doc_content/meeting")
    source_doc_token: str = Field(default="", description="Source doc token")
    source_comment_id: str = Field(default="", description="Source comment ID")
    source_message_id: str = Field(default="", description="Source message ID")
    source_chat_id: str = Field(default="", description="Source chat ID")

    topic_id: str = Field(default="", description="Associated topic ID")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")


# ==================== Phase / Impact / Access Types (from node.go) ====================


class PhaseScope(str, Enum):
    """Phase scope of a decision."""
    POINT = "Point"
    SPAN = "Span"
    RETROACTIVE = "Retroactive"


class ImpactLevel(str, Enum):
    """Impact level of a decision."""
    ADVISORY = "advisory"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"

    def is_valid(self) -> bool:
        return self in (ImpactLevel.ADVISORY, ImpactLevel.MINOR, ImpactLevel.MAJOR, ImpactLevel.CRITICAL)


class DecisionStatus(str, Enum):
    """Decision lifecycle status. Aligned with decision_prompts.py DECISION_STATUS_DESCRIPTIONS."""
    PENDING = "pending"
    PENDING_CONFIRMATION = "pending_confirmation"
    IN_DISCUSSION = "in_discussion"
    DECIDED = "decided"
    EXECUTING = "executing"
    COMPLETED = "completed"
    SHELVED = "shelved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"

    def is_valid(self) -> bool:
        return self in (
            DecisionStatus.PENDING,
            DecisionStatus.PENDING_CONFIRMATION,
            DecisionStatus.IN_DISCUSSION,
            DecisionStatus.DECIDED,
            DecisionStatus.EXECUTING,
            DecisionStatus.COMPLETED,
            DecisionStatus.SHELVED,
            DecisionStatus.REJECTED,
            DecisionStatus.SUPERSEDED,
            DecisionStatus.DEPRECATED,
        )

    def is_active(self) -> bool:
        return self in ACTIVE_DECISION_STATUSES

    def is_inactive(self) -> bool:
        return self in INACTIVE_DECISION_STATUSES


ACTIVE_DECISION_STATUSES: List[DecisionStatus] = [
    DecisionStatus.PENDING,
    DecisionStatus.PENDING_CONFIRMATION,
    DecisionStatus.IN_DISCUSSION,
    DecisionStatus.DECIDED,
    DecisionStatus.EXECUTING,
]

INACTIVE_DECISION_STATUSES: List[DecisionStatus] = [
    DecisionStatus.COMPLETED,
    DecisionStatus.SHELVED,
    DecisionStatus.REJECTED,
    DecisionStatus.SUPERSEDED,
    DecisionStatus.DEPRECATED,
]


class VersionRange(BaseModel):
    """Version range for a decision."""
    from_version: str = Field(default="", description="Start version")
    to: Optional[str] = Field(default=None, description="End version (None = currently effective)")


class FeishuLinks(BaseModel):
    """Feishu entity links for a decision node."""
    related_chat_ids: List[str] = Field(default_factory=list)
    related_message_ids: List[str] = Field(default_factory=list)
    related_doc_tokens: List[str] = Field(default_factory=list)
    related_event_ids: List[str] = Field(default_factory=list)
    related_meeting_ids: List[str] = Field(default_factory=list)
    related_task_guids: List[str] = Field(default_factory=list)
    related_minute_tokens: List[str] = Field(default_factory=list)
    related_comment_ids: List[str] = Field(default_factory=list)


class AccessStats(BaseModel):
    """Access statistics for hotspot calculation."""
    last_accessed_at: Optional[datetime] = Field(default=None)
    access_count: int = Field(default=0)
    reference_count: int = Field(default=0)
    hot_score: float = Field(default=100.0)
    last_calculated: Optional[datetime] = Field(default=None)

    def record_access(self) -> None:
        self.last_accessed_at = datetime.now()
        self.access_count += 1

    def record_reference(self) -> None:
        self.reference_count += 1