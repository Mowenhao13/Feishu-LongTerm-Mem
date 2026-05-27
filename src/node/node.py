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

from src.node.types import (
    AccessStats,
    DecisionStatus,
    FeishuLinks,
    ImpactLevel,
    Objection,
    PhaseScope,
    Relation,
    RelationType,
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
    """Decision node — a structured representation of a team decision.

    Translates ref/decision/node.go DecisionNode.
    """

    sid: str = Field(default="", description="Unique SDRID (hash-based)")
    sdr_type: Optional[str] = Field(default="", description="Type hint for the node")
    project_id: str = Field(default="", description="Project this decision belongs to")
    topic_id: str = Field(default="", description="Topic/category within the project")

    title: str = Field(default="", description="Short title")
    summary: str = Field(default="", description="Human-readable summary")
    full_text: str = Field(default="", description="Full decision prose")
    rationale: str = Field(default="", description="Reasoning/justification")
    alternatives: List[str] = Field(default_factory=list, description="Alternatives considered")
    scope: Optional[str] = Field(default=None, description="Scope of the decision (team-wide, project-wide, etc.)")

    proposer: str = Field(default="", description="Who proposed the decision")
    authority: str = Field(default="", description="Authority/role who made the decision")
    assignee: str = Field(default="", description="Who is responsible for execution")

    status: DecisionStatus = Field(default=DecisionStatus.PENDING)
    impact_level: ImpactLevel = Field(default=ImpactLevel.MINOR)

    version: int = Field(default=1, description="Decision version (incrementing integer)")
    branch: str = Field(default="", description="Git branch name: decision/{sid}")
    parent_id: str = Field(default="", description="Parent decision SDRID, empty = root node")
    conflict_status: str = Field(default="", description="Conflict status: ''|active|resolved")
    conflict_with: str = Field(default="", description="SDRID of the conflicting decision")

    tags: List[str] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    objections: List[Objection] = Field(default_factory=list)
    feishu_links: FeishuLinks = Field(default_factory=FeishuLinks)
    access_stats: AccessStats = Field(default_factory=AccessStats)
    version_chain: List[VersionRange] = Field(default_factory=list)

    source: str = Field(default="", description="Source channel: lark_im / doc / meeting / manual")
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)

    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Extraction confidence from LLM")
    git_commit_hash: str = Field(default="", description="Last git commit hash")

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

    # ==================== Branch version helpers ====================

    def branch_version(self) -> str:
        return f"v{self.version}"

    def next_version(self) -> int:
        return self.version + 1

    def next_major_version(self) -> int:
        return self.version + 1

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

    # ==================== Tree helpers ====================

    def add_child(self, child_sid: str) -> None:
        self.add_relation(Relation(
            type=RelationType.PARENT_OF,
            target_id=child_sid,
            description=f"Parent of {child_sid}",
        ))

    def get_children(self, graph: Any = None) -> List[str]:
        """从 relations 中获取子决策 SDRID 列表"""
        return [r.target_id for r in self.relations if r.type == RelationType.PARENT_OF]

    def has_parent(self) -> bool:
        return bool(self.parent_id)

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