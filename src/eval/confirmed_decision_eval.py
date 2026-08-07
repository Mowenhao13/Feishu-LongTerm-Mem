"""Evidence-aware evaluation for confirmed-decision extraction.

The evaluator keeps benchmark selection, deterministic evidence matching, and
optional three-state adjudication separate from extraction so experiment
failures cannot silently become false negatives.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


class Adjudication(str, Enum):
    MATCH_GT = "match_gt"
    VALID_EXTRA = "valid_extra"
    INVALID = "invalid"
    EVALUATION_ERROR = "evaluation_error"


@dataclass(frozen=True)
class DatasetSelection:
    chat_ids: tuple[str, ...]
    messages_by_chat: Mapping[str, tuple[dict, ...]]
    expected_by_chat: Mapping[str, tuple[dict, ...]]
    dataset_hash: str

    @classmethod
    def from_jsonl(
        cls,
        dataset_dir: str | Path,
        chat_ids: Iterable[str] | None = None,
        sample: int | None = None,
    ) -> "DatasetSelection":
        root = Path(dataset_dir)
        messages = [
            json.loads(line) for line in (root / "messages.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        expected = [
            json.loads(line) for line in (root / "expected.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        available = sorted({message["chat_id"] for message in messages})
        selected = sorted(set(chat_ids)) if chat_ids is not None else available
        if sample is not None and sample > 0:
            selected = selected[:sample]
        selected_set = set(selected)
        by_chat: dict[str, list[dict]] = {chat_id: [] for chat_id in selected}
        expected_by_chat: dict[str, list[dict]] = {chat_id: [] for chat_id in selected}
        for message in messages:
            if message["chat_id"] in selected_set:
                by_chat[message["chat_id"]].append(message)
        for row in expected:
            if row["chat_id"] in selected_set:
                expected_by_chat[row["chat_id"]].append(row)
        payload = json.dumps(
            {"chat_ids": selected, "messages": by_chat, "expected": expected_by_chat},
            ensure_ascii=False, sort_keys=True,
        )
        return cls(
            chat_ids=tuple(selected),
            messages_by_chat={key: tuple(value) for key, value in by_chat.items()},
            expected_by_chat={key: tuple(value) for key, value in expected_by_chat.items()},
            dataset_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    @property
    def expected_count(self) -> int:
        return sum(len(rows) for rows in self.expected_by_chat.values())


@dataclass(frozen=True)
class EvidenceDecision:
    chat_id: str
    title: str
    summary: str
    status: str
    is_suggestion: bool
    source_message_ids: tuple[str, ...] = ()
    evidence_quote: str = ""

    @property
    def is_confirmed(self) -> bool:
        return not self.is_suggestion and self.status == "decided"


@dataclass(frozen=True)
class EvaluationOutcome:
    strict_tp: int
    strict_fp: int
    strict_fn: int
    valid_extra: int
    invalid: int
    evidence_valid: int
    evidence_invalid: int
    errors: tuple[str, ...] = ()
    details: tuple[dict[str, object], ...] = ()
    unmatched_expected: tuple[dict[str, object], ...] = ()

    @property
    def incomplete(self) -> bool:
        return bool(self.errors)

    @property
    def precision(self) -> float:
        denominator = self.strict_tp + self.strict_fp
        return self.strict_tp / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.strict_tp + self.strict_fn
        return self.strict_tp / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        return 2 * self.precision * self.recall / (self.precision + self.recall) if self.precision + self.recall else 0.0


@dataclass(frozen=True)
class AdjudicationResult:
    outcome: Adjudication
    matched_msg_id: str = ""


Adjudicator = Callable[[EvidenceDecision, Sequence[dict], Sequence[dict]], AdjudicationResult]


class ConfirmedDecisionEvaluator:
    """Deterministic evidence-first scorer for confirmed decisions."""

    def __init__(self, adjudicator: Adjudicator | None = None) -> None:
        self._adjudicator = adjudicator

    @staticmethod
    def _evidence_valid(decision: EvidenceDecision, messages: Sequence[dict]) -> bool:
        by_id = {message["msg_id"]: message for message in messages}
        if not decision.source_message_ids or any(message_id not in by_id for message_id in decision.source_message_ids):
            return False
        if not decision.evidence_quote:
            return False
        return any(decision.evidence_quote in by_id[message_id].get("msg", "") for message_id in decision.source_message_ids)

    @staticmethod
    def _expected_source_ids(expected: dict) -> set[str]:
        return {expected["msg_id"]} if expected.get("msg_id") else set()

    def evaluate(self, outputs: Sequence[EvidenceDecision], selection: DatasetSelection) -> EvaluationOutcome:
        confirmed = [output for output in outputs if output.is_confirmed]
        evidence_valid = 0
        evidence_invalid = 0
        invalid = 0
        valid_extra = 0
        matched_expected: set[tuple[str, str]] = set()
        strict_tp = 0
        errors: list[str] = []
        details: list[dict[str, object]] = []

        def record_detail(
            output: EvidenceDecision,
            evidence_ok: bool,
            adjudication: Adjudication,
            reason: str,
            matched_msg_id: str = "",
        ) -> None:
            details.append({
                "chat_id": output.chat_id,
                "title": output.title,
                "summary": output.summary,
                "source_message_ids": output.source_message_ids,
                "evidence_quote": output.evidence_quote,
                "evidence_valid": evidence_ok,
                "adjudication": adjudication.value,
                "matched_msg_id": matched_msg_id,
                "reason": reason,
            })

        for output in confirmed:
            messages = selection.messages_by_chat.get(output.chat_id)
            if messages is None or not self._evidence_valid(output, messages):
                evidence_invalid += 1
                invalid += 1
                reason = "unknown_chat" if messages is None else "missing_or_invalid_evidence"
                record_detail(output, False, Adjudication.INVALID, reason)
                continue
            evidence_valid += 1
            candidates = selection.expected_by_chat.get(output.chat_id, ())
            exact = next(
                (expected for expected in candidates
                 if self._expected_source_ids(expected).intersection(output.source_message_ids)
                 and (output.chat_id, expected.get("msg_id", "")) not in matched_expected),
                None,
            )
            if exact is not None:
                matched_expected.add((output.chat_id, exact["msg_id"]))
                strict_tp += 1
                record_detail(output, True, Adjudication.MATCH_GT, "exact_source_match", exact["msg_id"])
                continue
            if self._adjudicator is None:
                invalid += 1
                record_detail(output, True, Adjudication.INVALID, "no_adjudicator_for_gt_extra")
                continue
            try:
                result = self._adjudicator(output, candidates, messages)
            except Exception as exc:  # adjudication errors make the full run incomplete
                errors.append(f"{output.chat_id}:{output.title}: {exc}")
                record_detail(output, True, Adjudication.EVALUATION_ERROR, str(exc))
                continue
            if result.outcome is Adjudication.MATCH_GT:
                key = (output.chat_id, result.matched_msg_id)
                if not result.matched_msg_id or key in matched_expected or not any(
                    expected.get("msg_id") == result.matched_msg_id for expected in candidates
                ):
                    errors.append(f"{output.chat_id}:{output.title}: invalid semantic GT identity")
                    record_detail(
                        output,
                        True,
                        Adjudication.EVALUATION_ERROR,
                        "invalid_semantic_gt_identity",
                        result.matched_msg_id,
                    )
                else:
                    matched_expected.add(key)
                    strict_tp += 1
                    record_detail(output, True, Adjudication.MATCH_GT, "semantic_match", result.matched_msg_id)
            elif result.outcome is Adjudication.VALID_EXTRA:
                valid_extra += 1
                record_detail(output, True, Adjudication.VALID_EXTRA, "adjudicated_valid_extra")
            elif result.outcome is Adjudication.INVALID:
                invalid += 1
                record_detail(output, True, Adjudication.INVALID, "adjudicated_invalid")
            else:
                errors.append(f"{output.chat_id}:{output.title}: evaluation error")
                record_detail(output, True, Adjudication.EVALUATION_ERROR, "adjudicator_returned_error")

        strict_fn = selection.expected_count - strict_tp
        strict_fp = invalid
        unmatched_expected = tuple(
            expected | {"chat_id": chat_id}
            for chat_id, rows in selection.expected_by_chat.items()
            for expected in rows
            if (chat_id, expected.get("msg_id", "")) not in matched_expected
        )
        return EvaluationOutcome(
            strict_tp=strict_tp,
            strict_fp=strict_fp,
            strict_fn=strict_fn,
            valid_extra=valid_extra,
            invalid=invalid,
            evidence_valid=evidence_valid,
            evidence_invalid=evidence_invalid,
            errors=tuple(errors),
            details=tuple(details),
            unmatched_expected=unmatched_expected,
        )
