"""
Decision Node - Translated from ref/decision/node.go

DecisionNode model with topic association (via topic_prompts), 
decision status lifecycle (via decision_prompts), and role-based 
attribution (aligned with structure.py DecisionRole).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

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

    version: str = Field(default="v1.0", description="Decision version (string like v1.0)")
    branch: str = Field(default="", description="Git branch name: decision/{sid}")
    parent_id: str = Field(default="", description="Parent decision SDRID, empty = root node")

    # ==================== New fields ====================
    decision_role: str = Field(default=DecisionRole.ROLE_DECISION, description="Role: decision/plan/consideration/action")
    phase_scope: Optional[PhaseScope] = Field(default=PhaseScope.POINT, description="Phase scope of the decision")
    decided_at: Optional[datetime] = Field(default=None, description="When the decision was decided")
    source_type: str = Field(default="", description="Source channel: im/doc/meeting/manual")
    source_message_id: str = Field(default="", description="Source message ID")
    source_chat_id: str = Field(default="", description="Source chat ID")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Extra custom fields")

    # Renamed to avoid shadowing the conflict_status() static method
    conflict_state: str = Field(default="", description="Conflict status: ''|active|resolved")
    conflict_with: str = Field(default="", description="SDRID of the conflicting decision")

    tags: List[str] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    objections: List[Objection] = Field(default_factory=list)
    feishu_links: FeishuLinks = Field(default_factory=FeishuLinks)
    access_stats: Any = Field(default_factory=lambda: AccessStats())
    version_chain: List[VersionRange] = Field(default_factory=list)

    source: str = Field(default="", description="Source channel: lark_im / doc / meeting / manual")
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)

    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Extraction confidence from LLM")
    git_commit_hash: str = Field(default="", description="Last git commit hash")

    is_suggestion: bool = Field(default=False, description="True if this is a suggestion rather than a firm decision")

    @field_validator("version", mode="before")
    @classmethod
    def _coerce_version(cls, v: Any) -> str:
        if isinstance(v, int):
            return f"v{v}.0"
        if isinstance(v, str) and v:
            return v if v.startswith("v") else f"v{v}"
        return "v1.0"

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
        if not self.version or self.version == "":
            return "v1.0"
        return self.version

    def next_version(self, current: Optional[str] = None) -> str:
        if not self.version:
            if current:
                return current
            return "v1.1"
        ver = current or self.version
        parts = ver.lstrip("v").split(".")
        major = int(parts[0]) if parts[0].isdigit() else 1
        minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return f"v{major}.{minor + 1}"

    def next_major_version(self) -> str:
        if not self.version:
            return "v1.0"
        parts = self.version.lstrip("v").split(".")
        major = int(parts[0]) if parts[0].isdigit() else 1
        return f"v{major + 1}.0"

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
            type=RelationType.RELATES_TO,
            target_id=child_sid,
            description=f"Parent of {child_sid}",
        ))

    def get_children(self, graph: Any = None) -> List[str]:
        """从 relations 中获取子决策 SDRID 列表"""
        return [r.target_id for r in self.relations if r.type == RelationType.RELATES_TO and "Parent of" in r.description]

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