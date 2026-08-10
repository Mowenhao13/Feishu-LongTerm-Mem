from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AdapterType(str, Enum):
    IM = "IM"
    VC = "VC"
    DOCS = "Docs"
    CALENDAR = "Calendar"
    TASK = "Task"
    OKR = "OKR"
    CONTACT = "Contact"
    WIKI = "Wiki"
    MINUTES = "Minutes"
    PROJECT = "Project"


class ChangeType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATUS_CHANGE = "status_change"


class SignalStrength(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class DecisionLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class DocType(str, Enum):
    UNKNOWN = "unknown"
    DESIGN = "design_doc"
    WEEKLY_REPORT = "weekly_report"
    MEETING_NOTES = "meeting_notes"
    SPEC = "spec"
    DECISION_LOG = "decision_log"
    ADMINISTRATIVE = "administrative"


class DetectorMode(str, Enum):
    IM = "im"
    DOC = "doc"


class MutationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    STATUS_CHANGE = "status_change"
    CONFLICT = "conflict"
    OBJECTION = "objection"
    DEPRECATE = "deprecate"
    REVERT = "revert"


@dataclass
class EmbeddedURL:
    raw_url: str = ""
    extracted_token: str = ""
    url_type: str = ""


@dataclass
class SignalContext:
    keywords: list[str] = field(default_factory=list)
    decision_signals: list[str] = field(default_factory=list)
    mentioned_ids: list[str] = field(default_factory=list)
    actor_id: str = ""
    participant_ids: list[str] = field(default_factory=list)
    embedded_urls: list[EmbeddedURL] = field(default_factory=list)
    content_snippet: str = ""
    event_time: Optional[datetime] = None
    score: float = 0.0
    is_decision: bool = False


@dataclass
class StateChangeSignal:
    signal_id: str = ""
    adapter: AdapterType = AdapterType.IM
    timestamp: Optional[datetime] = None
    event_type: str = ""
    change_type: ChangeType = ChangeType.CREATED
    change_summary: str = ""
    primary_id: str = ""
    related_ids: list[str] = field(default_factory=list)
    comment_id: str = ""
    context: SignalContext = field(default_factory=SignalContext)
    strength: SignalStrength = SignalStrength.MEDIUM


def new_signal(adapter: AdapterType, summary: str) -> StateChangeSignal:
    return StateChangeSignal(
        signal_id=_generate_signal_id(),
        adapter=adapter,
        timestamp=datetime.now(),
        change_summary=summary,
        strength=SignalStrength.MEDIUM,
        related_ids=[],
    )


_counter: int = 0


def _generate_signal_id() -> str:
    global _counter
    _counter += 1
    return "sig-" + datetime.now().strftime("%Y%m%d%H%M%S%f") + f"-{_counter}"


@dataclass
class SignalDetail:
    category: str = ""
    name: str = ""
    weight: float = 0.0
    matched: str = ""


@dataclass
class ScoreBreakdown:
    lexical: float = 0.0
    structural: float = 0.0
    dynamic: float = 0.0
    pattern: float = 0.0
    anti_score: float = 0.0
    final: float = 0.0


@dataclass
class DetectionResult:
    score: float = 0.0
    level: DecisionLevel = DecisionLevel.NONE
    is_decision: bool = False
    signal_details: list[SignalDetail] = field(default_factory=list)
    anti_signals: list[str] = field(default_factory=list)
    factors: Optional[ScoreBreakdown] = None


@dataclass
class DetectContext:
    source: str = ""
    chat_id: str = ""
    sender_id: str = ""
    is_reply: bool = False
    has_mention: bool = False
    recent_keywords: list[str] = field(default_factory=list)
    sender_name: str = ""
    message_index: int = 0


@dataclass
class Conflict:
    conflict_id: str = ""
    decision_a: str = ""
    decision_b: str = ""
    contradiction_score: float = 0.0
    description: str = ""


class DedupAction(str, Enum):
    NEW = "new"
    SKIP = "skip"
    UPDATE = "update"
    CONFLICT = "conflict"