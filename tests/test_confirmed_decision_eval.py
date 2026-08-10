from pathlib import Path

import pytest

from src.eval.confirmed_decision_eval import (
    Adjudication,
    AdjudicationResult,
    AssignmentRow,
    ChatAssignment,
    ConfirmedDecisionEvaluator,
    DatasetSelection,
    EvidenceDecision,
    GlobalAdjudicationGroup,
    build_global_adjudication_groups,
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


def _decision(chat_id: str, msg_id: str, evidence_quote: str, title: str) -> EvidenceDecision:
    return EvidenceDecision(
        chat_id=chat_id,
        title=title,
        summary=evidence_quote,
        status="decided",
        is_suggestion=False,
        source_message_ids=(msg_id,),
        evidence_quote=evidence_quote,
    )


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


def test_global_assignment_matches_outputs_independent_of_input_order(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    outputs = [
        _decision("a", "m3", "确认每周执行备份演练。", "备份演练"),
        _decision("a", "m3", "确认每周执行备份演练。", "备份计划"),
    ]
    assignment = ChatAssignment(
        chat_id="a",
        input_hash="fixture",
        rows=(
            AssignmentRow(0, Adjudication.VALID_EXTRA, reason="独立真实决定"),
            AssignmentRow(1, Adjudication.MATCH_GT, "m1", "execution_commitment", True),
        ),
    )
    evaluator = ConfirmedDecisionEvaluator(global_adjudicator=lambda *_: assignment)
    forward = evaluator.evaluate(outputs, selection)
    reverse = evaluator.evaluate(list(reversed(outputs)), selection)
    assert (forward.strict_tp, forward.strict_fp, forward.valid_extra) == (1, 0, 1)
    assert (reverse.strict_tp, reverse.strict_fp, reverse.valid_extra) == (1, 0, 1)


def test_global_assignment_builder_groups_outputs_by_chat_and_order(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    outputs = [
        _decision("a", "m3", "确认每周执行备份演练。", "备份演练"),
        _decision("a", "m3", "确认每周执行备份演练。", "备份计划"),
    ]
    groups = build_global_adjudication_groups(outputs, selection)
    assert len(groups) == 1
    assert groups[0].chat_id == "a"
    assert [output.title for output in groups[0].outputs] == ["备份演练", "备份计划"]


@pytest.mark.parametrize("rows", [
    (AssignmentRow(0, Adjudication.MATCH_GT, "unknown", "choice", True),),
    (AssignmentRow(0, Adjudication.MATCH_GT, "m1", "choice", False),),
    (
        AssignmentRow(0, Adjudication.MATCH_GT, "m1", "choice", True),
        AssignmentRow(1, Adjudication.MATCH_GT, "m1", "choice", True),
    ),
])
def test_invalid_global_assignment_marks_evaluation_incomplete_without_fp(tmp_path: Path, rows):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    outputs = [
        EvidenceDecision("a", "备份演练", "每周执行备份演练", "decided", False, ("m3",), "确认每周执行备份演练。"),
        EvidenceDecision("a", "备份计划", "制定备份计划", "decided", False, ("m3",), "确认每周执行备份演练。"),
    ]
    assignment = ChatAssignment("a", "fixture", rows)
    evaluator = ConfirmedDecisionEvaluator(global_adjudicator=lambda received: assignment)
    outcome = evaluator.evaluate(outputs, selection)
    assert outcome.incomplete
    assert outcome.strict_fp == 0
    assert outcome.invalid == 0


def test_valid_extra_row_is_not_counted_as_strict_false_positive(tmp_path: Path):
    selection = DatasetSelection.from_jsonl(_write_dataset(tmp_path), chat_ids=["a"])
    outputs = [
        EvidenceDecision("a", "备份演练", "每周执行备份演练", "decided", False, ("m3",), "确认每周执行备份演练。"),
        EvidenceDecision("a", "备份计划", "制定备份计划", "decided", False, ("m3",), "确认每周执行备份演练。"),
    ]
    assignment = ChatAssignment(
        chat_id="a",
        input_hash="fixture",
        rows=(
            AssignmentRow(0, Adjudication.VALID_EXTRA, reason="保留为真实补充"),
            AssignmentRow(1, Adjudication.MATCH_GT, "m1", "execution_commitment", True),
        ),
    )
    outcome = ConfirmedDecisionEvaluator(global_adjudicator=lambda *_: assignment).evaluate(outputs, selection)
    assert outcome.valid_extra == 1
    assert outcome.strict_fp == 0
    assert outcome.strict_tp == 1


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


def test_argusbot_model_version_acknowledgement_regression():
    dataset = Path(__file__).resolve().parents[1] / "eval_dataset" / "argusbot_v3"
    selection = DatasetSelection.from_jsonl(dataset, chat_ids=["ai_ml_platform_channel_1"])

    feast_output = EvidenceDecision(
        chat_id="ai_ml_platform_channel_1",
        title="特征存储选Feast，进入implementation",
        summary="特征存储选Feast，进入implementation",
        status="decided",
        is_suggestion=False,
        source_message_ids=("m017",),
        evidence_quote="好，特征存储选Feast，进入implementation。",
    )
    outcome_without_ack = ConfirmedDecisionEvaluator().evaluate([feast_output], selection)
    assert outcome_without_ack.strict_fn == 1
    assert outcome_without_ack.unmatched_expected[0]["msg_id"] == "m033"
    assert outcome_without_ack.unmatched_expected[0]["expected_topic"] == "模型版本管理"

    mlflow_decision_with_wrong_quote = EvidenceDecision(
        chat_id="ai_ml_platform_channel_1",
        title="先定MLflow，PoC后决定",
        summary="先定MLflow，PoC后决定",
        status="decided",
        is_suggestion=False,
        source_message_ids=("m032", "m033"),
        evidence_quote="那就先定MLflow，PoC后决定。",
    )
    outcome_with_wrong_quote = ConfirmedDecisionEvaluator().evaluate(
        [feast_output, mlflow_decision_with_wrong_quote], selection
    )
    assert outcome_with_wrong_quote.strict_tp == 1
    assert outcome_with_wrong_quote.strict_fn == 1
    assert outcome_with_wrong_quote.unmatched_expected[0]["msg_id"] == "m033"

    model_version_ack = EvidenceDecision(
        chat_id="ai_ml_platform_channel_1",
        title="好，我明天开始搭建。",
        summary="好，我明天开始搭建。",
        status="decided",
        is_suggestion=False,
        source_message_ids=("m033",),
        evidence_quote="好，我明天开始搭建。",
    )
    outcome_with_ack = ConfirmedDecisionEvaluator().evaluate([feast_output, model_version_ack], selection)
    assert outcome_with_ack.strict_tp == 2
    assert outcome_with_ack.strict_fn == 0
    assert outcome_with_ack.unmatched_expected == ()
