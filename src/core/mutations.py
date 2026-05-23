from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MutationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    STATUS_CHANGE = "status_change"
    CONFLICT_MERGE = "conflict_merge"
    CONFLICT_KEEP_BOTH = "conflict_keep_both"
    OBJECTION = "objection"
    DEPRECATE = "deprecate"
    REVERT = "revert"


@dataclass
class DecisionMutation:
    mtype: MutationType
    sdr_id: str
    project: str = "feishu-mem"
    topic: str = "general"

    summary: str = ""
    full_text: str = ""
    proposer: str = ""
    executor: str = ""
    tags: List[str] = field(default_factory=list)

    new_status: str = ""
    old_status: str = ""
    new_impact_level: str = ""
    old_impact_level: str = ""
    confidence: float = 1.0

    source_sdr_id: str = ""
    target_sdr_id: str = ""
    merge_strategy: str = "merge"

    objection_reason: str = ""
    objection_author: str = ""

    revert_to_version: int = 0
    current_version: int = 0

    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        if not self.sdr_id:
            return False
        if self.mtype == MutationType.CREATE and not self.summary:
            return False
        if self.mtype == MutationType.OBJECTION and not self.objection_reason:
            return False
        return True