from __future__ import annotations

from typing import Optional

from src.signal.types import (
    AdapterType,
    SignalStrength,
    StateChangeSignal,
    new_signal,
)


class StateChangeEmitter:
    """Base class for all signal emitters."""

    def adapter_type(self) -> AdapterType:
        raise NotImplementedError

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        raise NotImplementedError


class IMEmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.IM

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None

        signal = new_signal(AdapterType.IM, result.source + " has changes")
        strength = SignalStrength.WEAK
        keywords: list[str] = []
        decision_signals: list[str] = []

        for ch in result.changes:
            if ch.entity_type == "pin_message":
                strength = SignalStrength.STRONG
                decision_signals.append("pin")
            if ch.type in ("new_text", "new_post"):
                keywords.extend(self._match_keywords(ch.summary))
                decision_signals.extend(self._match_decision_words(ch.summary))

        if strength == SignalStrength.WEAK and not decision_signals:
            return None

        signal.strength = strength
        signal.context.keywords = keywords
        signal.context.decision_signals = decision_signals
        if result.changes:
            signal.context.content_snippet = result.changes[0].summary

        return signal

    def _match_keywords(self, text: str) -> list[str]:
        decision_keywords = ["决定", "确认", "结论", "通过", "定下来", "approve", "decided", "confirmed"]
        matches: list[str] = []
        lower_text = text.lower()
        for kw in decision_keywords:
            if kw.lower() in lower_text:
                matches.append(kw)
        return matches

    def _match_decision_words(self, text: str) -> list[str]:
        decision_words = ["决定", "decided", "确认", "LGTM", "lgtm", "approve", "通过", "定下来", "就这么办"]
        for w in decision_words:
            if w in text:
                return ["decision"]
        return []


class VCEmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.VC

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None
        signal = new_signal(AdapterType.VC, "VC changes detected")
        strength = SignalStrength.WEAK

        for ch in result.changes:
            if ch.type in ("meeting_minutes_available", "minutes_created", "minutes_updated", "minutes_ai_summary_ready"):
                strength = _max_strength(strength, SignalStrength.STRONG)
                signal.context.decision_signals.append("ai_summary")
            elif ch.type == "meeting_todos":
                strength = _max_strength(strength, SignalStrength.STRONG)
                signal.context.decision_signals.append("action_items")
            elif ch.type == "meeting_ended":
                strength = _max_strength(strength, SignalStrength.MEDIUM)

        if strength == SignalStrength.WEAK:
            return None

        signal.strength = strength
        if result.changes:
            signal.context.content_snippet = result.changes[0].summary
        return signal


class DocsEmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.DOCS

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None
        signal = new_signal(AdapterType.DOCS, "Doc changes detected")
        strength = SignalStrength.WEAK

        for ch in result.changes:
            if ch.type == "doc_decision":
                strength = _max_strength(strength, SignalStrength.STRONG)
                signal.context.decision_signals.append("decision_doc")
            elif ch.type == "doc_comment_added":
                strength = _max_strength(strength, SignalStrength.MEDIUM)
                signal.context.decision_signals.append("doc_comment")
            elif ch.type == "doc_comment_approval":
                strength = _max_strength(strength, SignalStrength.STRONG)
                signal.context.decision_signals.append("approval_comment")
            elif ch.type in ("doc_created", "doc_content_updated"):
                strength = _max_strength(strength, SignalStrength.MEDIUM)
                signal.context.decision_signals.append("doc_change")

        if strength == SignalStrength.WEAK:
            return None

        signal.strength = strength
        if result.changes:
            signal.context.content_snippet = result.changes[0].summary
        return signal


class CalendarEmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.CALENDAR

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None
        signal = new_signal(AdapterType.CALENDAR, "Calendar changes detected")
        strength = SignalStrength.WEAK

        for ch in result.changes:
            if ch.type == "decision_meeting":
                strength = _max_strength(strength, SignalStrength.MEDIUM)
                signal.context.decision_signals.append("review_meeting")
            else:
                strength = _max_strength(strength, SignalStrength.MEDIUM)
                signal.context.decision_signals.append("calendar_change")

        if strength == SignalStrength.WEAK:
            return None

        signal.strength = strength
        if result.changes:
            signal.context.content_snippet = result.changes[0].summary
        return signal


class TaskEmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.TASK

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None
        signal = new_signal(AdapterType.TASK, "Task changes detected")
        strength = SignalStrength.WEAK

        for ch in result.changes:
            if ch.type == "task_completed":
                strength = _max_strength(strength, SignalStrength.MEDIUM)
                signal.context.decision_signals.append("task_done")
            elif ch.type in ("task_created", "task_updated"):
                strength = _max_strength(strength, SignalStrength.WEAK)

        if strength == SignalStrength.WEAK:
            return None

        signal.strength = strength
        if result.changes:
            signal.context.content_snippet = result.changes[0].summary
        return signal


class WikiEmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.WIKI

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None
        signal = new_signal(AdapterType.WIKI, "Wiki changes detected")
        strength = SignalStrength.WEAK

        for _ in result.changes:
            strength = _max_strength(strength, SignalStrength.MEDIUM)
            signal.context.decision_signals.append("wiki_change")

        if strength == SignalStrength.WEAK:
            return None

        signal.strength = strength
        if result.changes:
            signal.context.content_snippet = result.changes[0].summary
        return signal


class OKREmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.OKR

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None
        signal = new_signal(AdapterType.OKR, "OKR changes detected")
        signal.strength = SignalStrength.MEDIUM
        return signal


class ContactEmitter(StateChangeEmitter):
    def adapter_type(self) -> AdapterType:
        return AdapterType.CONTACT

    def emit_signal(self, result: "DetectResult") -> Optional[StateChangeSignal]:
        if not result.has_changes:
            return None
        signal = new_signal(AdapterType.CONTACT, "Contact changes detected")
        signal.strength = SignalStrength.WEAK
        return signal


def new_emitters() -> dict[AdapterType, StateChangeEmitter]:
    return {
        AdapterType.IM: IMEmitter(),
        AdapterType.VC: VCEmitter(),
        AdapterType.DOCS: DocsEmitter(),
        AdapterType.CALENDAR: CalendarEmitter(),
        AdapterType.TASK: TaskEmitter(),
        AdapterType.OKR: OKREmitter(),
        AdapterType.CONTACT: ContactEmitter(),
        AdapterType.WIKI: WikiEmitter(),
    }


def _max_strength(a: SignalStrength, b: SignalStrength) -> SignalStrength:
    order = {SignalStrength.WEAK: 1, SignalStrength.MEDIUM: 2, SignalStrength.STRONG: 3}
    return a if order[a] > order[b] else b


class DetectChange:
    """Simplified Change for emitter test compatibility."""
    def __init__(self, type: str = "", summary: str = "", entity_type: str = "") -> None:
        self.type = type
        self.summary = summary
        self.entity_type = entity_type


class DetectResult:
    """Simplified DetectResult for emitter test compatibility."""
    def __init__(self, has_changes: bool = False, source: str = "", changes: Optional[list[DetectChange]] = None) -> None:
        self.has_changes = has_changes
        self.source = source
        self.changes = changes or []