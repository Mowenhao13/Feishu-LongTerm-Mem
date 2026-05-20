"""
Decision Node - Translated from ref/decision/node.go

DecisionNode model with topic association (via topic_prompts), 
decision status lifecycle (via decision_prompts), and role-based 
attribution (aligned with structure.py DecisionRole).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from node.types import (
    AccessStats,
    DecisionStatus,
    FeishuLinks,
    ImpactLevel,
    Objection,
    PhaseScope,
    Relation,
    VersionRange,
)


SDRID = str
"""SDRID (Structured Decision Record ID) type alias - unique decision identifier."""


# ==================== Decision Role (aligned with structure.py DecisionNode) ====================


class DecisionRole(str):
    """Decision role aligned with structure.DecisionNode decision_role field."""
    ROLE_DECISION = "decision"
    ROLE_PLAN = "plan"
    ROLE_CONSIDERATION = "consideration"
    ROLE_ACTION = "action"


DECISION_ROLE_OPTIONS: List[str] = [
    DecisionRole.ROLE_DECISION,
    DecisionRole.ROLE_PLAN,
    DecisionRole.ROLE_CONSIDERATION,
    DecisionRole.ROLE_ACTION,
]


# ==================== Decision Node ====================


class DecisionNode(BaseModel):
    """Decision node in the memory graph.

    Translated from ref/decision/node.go DecisionNode struct.
    Aligned with structure.py DecisionNode fields (decision_role, confidence, impact_level).
    """
    sid: SDRID = Field(..., description="Unique decision SDRID")

    topic_id: str = Field(default="", description="Associated topic ID from the topic memory layer")
    tags: List[str] = Field(default_factory=list, description="Tags/categories")

    summary: str = Field(default="", description="Decision summary (short)")
    full_text: str = Field(default="", description="Full decision text/content")

    status: DecisionStatus = Field(default=DecisionStatus.PENDING, description="Lifecycle status")
    decision_role: str = Field(
        default=DecisionRole.ROLE_DECISION,
        description="Role of this node: decision/plan/consideration/action",
    )
    phase_scope: PhaseScope = Field(default=PhaseScope.POINT, description="Phase scope")
    impact_level: ImpactLevel = Field(default=ImpactLevel.MINOR, description="Impact level")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    authority: str = Field(default="", description="Decision authority (who decided)")
    assignee: str = Field(default="", description="Person responsible for execution")

    depends_on: List[str] = Field(default_factory=list, description="SDRIDs this decision depends on")

    version: str = Field(default="v1.0", description="Semantic version (e.g. v1.0, v1.1)")
    version_range: VersionRange = Field(default_factory=VersionRange)

    relations: List[Relation] = Field(default_factory=list, description="Outgoing relations")
    objections: List[Objection] = Field(default_factory=list, description="Associated objections")

    source_type: str = Field(default="", description="Source: im/doc/meeting/comment")
    source_doc_token: str = Field(default="", description="Source doc token")
    source_message_id: str = Field(default="", description="Source message ID")
    source_chat_id: str = Field(default="", description="Source chat ID")
    source_minute_token: str = Field(default="", description="Source minute token")
    source_event_id: str = Field(default="", description="Source event ID")

    feishu_links: FeishuLinks = Field(default_factory=FeishuLinks)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    decided_at: Optional[datetime] = Field(default=None)

    extra: Dict[str, Any] = Field(default_factory=dict, description="Extensible extra metadata")
    access_stats: AccessStats = Field(default_factory=AccessStats)

    # ==================== Status helpers ====================

    def is_active(self) -> bool:
        return self.status.is_active()

    def is_inactive(self) -> bool:
        return self.status.is_inactive()

    def is_decided(self) -> bool:
        return self.status in (
            DecisionStatus.DECIDED,
            DecisionStatus.EXECUTING,
            DecisionStatus.COMPLETED,
        )

    # ==================== Branch version helpers (from node.go) ====================

    def branch_version(self) -> str:
        if not self.version:
            return "v1.0"
        return self.version

    def next_version(self, base: str = "v1.0") -> str:
        if not self.version:
            return base
        parts = self.version.lstrip("v").split(".")
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            return f"v{major}.{minor + 1}"
        except (ValueError, IndexError):
            return base

    def next_major_version(self) -> str:
        if not self.version:
            return "v1.0"
        parts = self.version.lstrip("v").split(".")
        try:
            major = int(parts[0])
            return f"v{major + 1}.0"
        except (ValueError, IndexError):
            return "v1.0"

    # ==================== Conflict helpers (from node.go) ====================

    @staticmethod
    def conflict_status(a_status: DecisionStatus, b_status: DecisionStatus) -> str:
        if a_status == DecisionStatus.COMPLETED or b_status == DecisionStatus.COMPLETED:
            return "resolved"
        if a_status == DecisionStatus.SUPERSEDED or b_status == DecisionStatus.SUPERSEDED:
            return "superseded"
        if a_status == DecisionStatus.DEPRECATED or b_status == DecisionStatus.DEPRECATED:
            return "deprecated"
        if a_status == DecisionStatus.SHELVED or b_status == DecisionStatus.SHELVED:
            return "shelved"
        if a_status == DecisionStatus.DECIDED and b_status == DecisionStatus.DECIDED:
            return "conflict_active"
        return "unknown"

    # ==================== Objection helpers ====================

    def add_objection(self, objection: Objection) -> None:
        objection.created_at = datetime.now()
        self.objections.append(objection)
        self.updated_at = datetime.now()

    def active_objections(self) -> List[Objection]:
        return [o for o in self.objections if o.status.value == "active"]

    def has_active_objections(self) -> bool:
        return len(self.active_objections()) > 0

    # ==================== Relation helpers ====================

    def add_relation(self, relation: Relation) -> None:
        self.relations.append(relation)
        self.updated_at = datetime.now()

    # ==================== Topic association ====================

    def set_topic(self, topic_id: str) -> None:
        self.topic_id = topic_id
        self.updated_at = datetime.now()

    # ==================== State change ====================

    def change_status(self, new_status: DecisionStatus) -> None:
        self.status = new_status
        self.updated_at = datetime.now()
        if new_status == DecisionStatus.DECIDED:
            self.decided_at = datetime.now()


# ==================== Inline decision creation (from node.go) ====================


def new_decision_node(
    sid: SDRID,
    topic_id: str = "",
    summary: str = "",
    full_text: str = "",
    decision_role: str = DecisionRole.ROLE_DECISION,
    status: DecisionStatus = DecisionStatus.PENDING,
    impact_level: ImpactLevel = ImpactLevel.MINOR,
    confidence: float = 1.0,
    authority: str = "",
    assignee: str = "",
    source_type: str = "",
    source_message_id: str = "",
    source_chat_id: str = "",
    **extra: Any,
) -> DecisionNode:
    return DecisionNode(
        sid=sid,
        topic_id=topic_id,
        summary=summary,
        full_text=full_text,
        decision_role=decision_role,
        status=status,
        impact_level=impact_level,
        confidence=confidence,
        authority=authority,
        assignee=assignee,
        source_type=source_type,
        source_message_id=source_message_id,
        source_chat_id=source_chat_id,
        extra=extra,
    )