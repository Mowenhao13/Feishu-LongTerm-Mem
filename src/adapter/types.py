"""
Core data types for Lark adapter.
Mirrors internal/lark-adapter/types.go + MessageRecord from context_message.go
"""

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class MessageRecord:
    message_id: str = ""
    chat_id: str = ""
    thread_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    content: str = ""
    msg_type: str = ""
    create_time: int = 0
    mentions: List[str] = field(default_factory=list)


@dataclass
class Change:
    type: str = ""                          # "new" | "updated" | "deleted"
    entity_type: str = ""                   # "message", "pin", "event", "doc", "task"
    entity_id: str = ""
    summary: str = ""
    timestamp: int = 0

    chat_id: str = ""
    thread_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    mention_ids: List[str] = field(default_factory=list)
    raw_content: str = ""
    context_text: str = ""
    comment_id: str = ""
    meta: Dict[str, str] = field(default_factory=dict)


@dataclass
class DetectResult:
    has_changes: bool = False
    source: str = ""
    detected_at: Optional[datetime] = None
    last_check: Optional[datetime] = None
    changes: List[Change] = field(default_factory=list)


@dataclass
class ExtractionResult:
    source: str = ""
    extracted_at: Optional[datetime] = None
    raw_data: Any = None
    formatted: Any = None


@dataclass
class SourceState:
    last_check: Optional[datetime] = None
    last_detected: Optional[datetime] = None
    version: int = 0


class Detector(Protocol):
    def detect(self, last_check: datetime):
        ...

    def name(self) -> str:
        ...


class Extractor(Protocol):
    def extract(self):
        ...

    def name(self) -> str:
        ...


class StateManager:
    def __init__(self, file_path: str):
        self._lock = threading.Lock()
        self.file_path = file_path
        self.state: Dict[str, SourceState] = {}
        self._load()

    def get_last_check(self, source: str) -> Optional[datetime]:
        with self._lock:
            s = self.state.get(source)
            if s is None:
                return None
            return s.last_check

    def get_last_detected(self, source: str) -> Optional[datetime]:
        with self._lock:
            s = self.state.get(source)
            if s is None:
                return None
            return s.last_detected

    def update_last_check(self, source: str, t: datetime) -> None:
        with self._lock:
            s = self.state.get(source)
            if s is None:
                s = SourceState(version=1)
            s.last_check = t
            s.version += 1
            self.state[source] = s
            self._save()

    def update_last_detected(self, source: str, t: datetime) -> None:
        with self._lock:
            s = self.state.get(source)
            if s is None:
                s = SourceState(version=1)
            s.last_detected = t
            s.version += 1
            self.state[source] = s
            self._save()

    def _load(self) -> None:
        if not os.path.exists(self.file_path):
            self.state = {}
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.state = {}
            for k, v in raw.items():
                last_check = _parse_time(v.get("last_check"))
                last_detected = _parse_time(v.get("last_detected"))
                self.state[k] = SourceState(
                    last_check=last_check,
                    last_detected=last_detected,
                    version=v.get("version", 0),
                )
        except (json.JSONDecodeError, IOError):
            self.state = {}

    def _save(self) -> None:
        raw = {}
        for k, v in self.state.items():
            raw[k] = {
                "last_check": v.last_check.isoformat() if v.last_check else None,
                "last_detected": v.last_detected.isoformat() if v.last_detected else None,
                "version": v.version,
            }
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)


def _parse_time(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    return None


def state_dir() -> str:
    d = "outputs"
    os.makedirs(d, exist_ok=True)
    return d


def save_to_json(source_name: str, result: ExtractionResult) -> None:
    d = state_dir()
    filename = os.path.join(d, f"{source_name}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2, default=str)


def save_detect_result(result: DetectResult) -> None:
    d = state_dir()
    filename = os.path.join(d, f"{result.source}_detect.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2, default=str)


def extract_detect(d: Detector) -> DetectResult:
    sm = StateManager(os.path.join(state_dir(), "detect_state.json"))
    last_check = sm.get_last_check(d.name())
    if last_check is None:
        last_check = datetime.fromtimestamp(0)

    result = d.detect(last_check)
    sm.update_last_check(d.name(), datetime.now())
    return result