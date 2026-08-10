"""Integration tests for global-per-chat adjudication in the production runner.

Tests exercise the adjudication helper extracted from main() with patched
dependencies, verifying the full adjudication+report pipeline.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.eval.confirmed_decision_eval import (
    ConfirmedDecisionEvaluator,
    DatasetSelection,
    EvidenceDecision,
    GlobalAdjudicationGroup,
)


class RecordingProvider:
    """Fake LLM that records every call and returns a canned JSON response."""

    def __init__(self, response_factory):
        self.calls: list[str] = []
        self._response_factory = response_factory

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append(prompt)
        return self._response_factory()


def _decision(
    chat_id: str,
    msg_id: str,
    evidence_quote: str,
    title: str,
) -> EvidenceDecision:
    return EvidenceDecision(
        chat_id=chat_id,
        title=title,
        summary=evidence_quote,
        status="decided",
        is_suggestion=False,
        source_message_ids=(msg_id,),
        evidence_quote=evidence_quote,
    )


def _run_result(decisions: list[EvidenceDecision]) -> SimpleNamespace:
    return SimpleNamespace(
        decisions=tuple(decisions),
        errors=(),
        trace=SimpleNamespace(
            memory_extraction_enabled=False,
            entity_context_injected=False,
            project_context_injected=False,
            neo4j_history_reads=0,
            embedding_dedup_enabled=False,
            llm_dedup_enabled=False,
        ),
    )


def _write_dataset(tmp_path: Path, decisions: list[EvidenceDecision]) -> Path:
    """Write messages.jsonl and expected.jsonl for a set of decisions."""
    messages: list[dict] = []
    expected: list[dict] = []

    for d in decisions:
        for msg_id in d.source_message_ids:
            messages.append({
                "chat_id": d.chat_id,
                "msg_id": msg_id,
                "speaker": "user",
                "msg": d.evidence_quote or f"Message {msg_id}",
            })

    chat_ids = sorted({d.chat_id for d in decisions})
    for chat_id in chat_ids:
        chat_decisions = [d for d in decisions if d.chat_id == chat_id]
        for d in chat_decisions:
            for msg_id in d.source_message_ids:
                expected.append({
                    "chat_id": chat_id,
                    "msg_id": f"gt_{msg_id}",
                    "expected_summary": d.summary,
                    "expected_status": "decided",
                })

    (tmp_path / "messages.jsonl").write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in messages),
        encoding="utf-8",
    )
    (tmp_path / "expected.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in expected),
        encoding="utf-8",
    )
    return tmp_path


def _valid_assignment() -> str:
    return json.dumps({
        "assignments": [
            {
                "output_index": 0,
                "classification": "match_gt",
                "matched_gt_index": 0,
                "decision_kind": "execution_commitment",
                "core_equivalent": True,
                "polarity_compatible": True,
                "commitment_compatible": True,
                "material_qualifier_conflict": False,
                "reason": "同一决策",
            },
        ],
    })


def _invalid_missing_output_index() -> str:
    return json.dumps({
        "assignments": [
            {
                "classification": "match_gt",
                "matched_gt_index": 0,
                "decision_kind": "execution_commitment",
                "core_equivalent": True,
                "polarity_compatible": True,
                "commitment_compatible": True,
                "material_qualifier_conflict": False,
                "reason": "missing output_index",
            },
        ],
    })


@pytest.mark.asyncio
async def test_per_chat_adjudication_uses_one_call_per_chat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Two decisions in one chat produce ONE adjudicate_chat call, not two."""
    _write_dataset(tmp_path, [_decision("chat-a", "m1", "这是 PostgreSQL 决策", "采用 PostgreSQL")])
    selection = DatasetSelection.from_jsonl(tmp_path, sample=1)
    result = _run_result([_decision("chat-a", "m1", "这是 PostgreSQL 决策", "采用 PostgreSQL")])

    provider = RecordingProvider(_valid_assignment)

    from experiments.production_ablation.run import _adjudicate_decisions
    from src.eval.confirmed_decision_adjudicator import LLMDecisionAdjudicator

    judge = LLMDecisionAdjudicator(provider)
    adjudicator_report, global_adjudicator = await _adjudicate_decisions(
        judge, result.decisions, selection,
    )

    # One call for one chat
    assert len(provider.calls) == 1
    assert adjudicator_report["calls"] == 1
    assert adjudicator_report["cache_hits"] == 0
    assert adjudicator_report["enabled"] is True


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_provider_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Second run with same normalized input produces cache hit, no second call."""
    _write_dataset(tmp_path, [_decision("chat-a", "m1", "这是 PostgreSQL 决策", "采用 PostgreSQL")])
    selection = DatasetSelection.from_jsonl(tmp_path, sample=1)
    result = _run_result([_decision("chat-a", "m1", "这是 PostgreSQL 决策", "采用 PostgreSQL")])

    provider = RecordingProvider(_valid_assignment)

    from experiments.production_ablation.run import _adjudicate_decisions
    from src.eval.confirmed_decision_adjudicator import LLMDecisionAdjudicator

    judge = LLMDecisionAdjudicator(provider)
    cache: dict = {}
    report1, global_adjudicator = await _adjudicate_decisions(
        judge, result.decisions, selection, cache=cache,
    )
    assert report1["calls"] == 1
    assert report1["cache_hits"] == 0

    # Second call with the same cache: no provider call, one cache hit
    report2, _ = await _adjudicate_decisions(
        judge, result.decisions, selection, cache=cache,
    )
    assert report2["calls"] == 0
    assert report2["cache_hits"] == 1


@pytest.mark.asyncio
async def test_invalid_assignment_marks_run_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Invalid assignment response (missing output_index) makes evaluation incomplete."""
    _write_dataset(tmp_path, [_decision("chat-a", "m1", "这是 PostgreSQL 决策", "采用 PostgreSQL")])
    selection = DatasetSelection.from_jsonl(tmp_path, sample=1)
    result = _run_result([_decision("chat-a", "m1", "这是 PostgreSQL 决策", "采用 PostgreSQL")])

    provider = RecordingProvider(_invalid_missing_output_index)

    from experiments.production_ablation.run import _adjudicate_decisions
    from src.eval.confirmed_decision_adjudicator import LLMDecisionAdjudicator

    judge = LLMDecisionAdjudicator(provider)
    adjudicator_report, global_adjudicator = await _adjudicate_decisions(
        judge, result.decisions, selection,
    )

    assert adjudicator_report["errors"]
    assert any("chat-a" in e for e in adjudicator_report["errors"])
    # Use the global_adjudicator so the evaluator can process errors
    outcome = ConfirmedDecisionEvaluator(global_adjudicator=global_adjudicator).evaluate(
        result.decisions, selection,
    )
    assert outcome.incomplete
    assert outcome.invalid == 0