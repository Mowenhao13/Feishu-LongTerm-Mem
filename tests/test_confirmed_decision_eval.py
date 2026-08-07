from pathlib import Path

from src.eval.confirmed_decision_eval import (
    Adjudication,
    AdjudicationResult,
    ConfirmedDecisionEvaluator,
    DatasetSelection,
    EvidenceDecision,
)


def _write_dataset(tmp_path: Path) -> Path:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "messages.jsonl").write_text(
        '\n'.join([
            '{"chat_id":"a","msg_id":"m1","msg":"确认采用PostgreSQL。"}',
            '{"chat_id":"a","msg_id":"m3","msg":"确认每周执行备份演练。"}',
            '{"chat_id":"b","msg_id":"m2","msg":"确认采用Redis。"}',
        ]),
        encoding="utf-8",
    )
    (dataset / "expected.jsonl").write_text(
        '\n'.join([
            '{"chat_id":"a","msg_id":"m1","expected_summary":"确认采用PostgreSQL。","expected_status":"decided"}',
            '{"chat_id":"b","msg_id":"m2","expected_summary":"确认采用Redis。","expected_status":"decided"}',
        ]),
        encoding="utf-8",
    )
    return dataset


def test_sample_filters_ground_truth_with_selected_chats(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), sample=1)
    assert selection.chat_ids == ("a",)
    assert selection.expected_count == 1
    assert set(selection.messages_by_chat) == {"a"}
    assert set(selection.expected_by_chat) == {"a"}


def test_exact_source_evidence_matches_ground_truth(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    output = EvidenceDecision(
        chat_id="a", title="使用 PostgreSQL", summary="确认采用PostgreSQL。",
        status="decided", is_suggestion=False,
        source_message_ids=("m1",), evidence_quote="确认采用PostgreSQL。",
    )
    outcome = ConfirmedDecisionEvaluator().evaluate([output], selection)
    assert outcome.strict_tp == 1
    assert outcome.strict_fp == 0
    assert outcome.strict_fn == 0
    assert outcome.evidence_valid == 1
    assert not outcome.incomplete
    assert outcome.details[0]["adjudication"] == "match_gt"
    assert outcome.details[0]["matched_msg_id"] == "m1"
    assert outcome.unmatched_expected == ()


def test_cross_chat_or_fabricated_evidence_is_invalid(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    output = EvidenceDecision(
        chat_id="a", title="bad", summary="bad", status="decided", is_suggestion=False,
        source_message_ids=("m2",), evidence_quote="确认采用Redis。",
    )
    outcome = ConfirmedDecisionEvaluator().evaluate([output], selection)
    assert outcome.strict_tp == 0
    assert outcome.strict_fp == 1
    assert outcome.evidence_invalid == 1


def test_valid_extra_is_not_a_strict_false_positive(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    output = EvidenceDecision(
        chat_id="a", title="extra", summary="extra", status="decided", is_suggestion=False,
        source_message_ids=("m3",), evidence_quote="确认每周执行备份演练。",
    )
    evaluator = ConfirmedDecisionEvaluator(
        adjudicator=lambda output, expected, messages: AdjudicationResult(Adjudication.VALID_EXTRA),
    )
    outcome = evaluator.evaluate([output], selection)
    assert outcome.valid_extra == 1
    assert outcome.strict_fp == 0
    assert outcome.strict_fn == 1
    assert outcome.details[0]["adjudication"] == "valid_extra"
    assert outcome.unmatched_expected[0]["msg_id"] == "m1"


def test_adjudicator_failure_marks_run_incomplete(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    output = EvidenceDecision(
        chat_id="a", title="extra", summary="extra", status="decided", is_suggestion=False,
        source_message_ids=("m3",), evidence_quote="确认每周执行备份演练。",
    )

    def broken(*_args):
        raise RuntimeError("judge unavailable")

    outcome = ConfirmedDecisionEvaluator(adjudicator=broken).evaluate([output], selection)
    assert outcome.incomplete
    assert "judge unavailable" in outcome.errors[0]


def test_semantic_adjudication_requires_a_valid_unmatched_gt_identity(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    output = EvidenceDecision(
        chat_id="a", title="主数据库选型", summary="主数据库选型", status="decided", is_suggestion=False,
        source_message_ids=("m3",), evidence_quote="确认每周执行备份演练。",
    )
    evaluator = ConfirmedDecisionEvaluator(
        adjudicator=lambda output, expected, messages: AdjudicationResult(Adjudication.MATCH_GT, "m1"),
    )
    outcome = evaluator.evaluate([output], selection)
    assert outcome.strict_tp == 1
    assert outcome.strict_fn == 0
    assert not outcome.incomplete
