import json
from pathlib import Path

from src.eval.confirmed_decision_eval import DatasetSelection, EvaluationOutcome


def test_real_benchmark_sample_has_aligned_ground_truth():
    root = Path(__file__).resolve().parents[1] / "eval_dataset" / "argusbot_v3"
    selection = DatasetSelection.from_jsonl(root, sample=3)
    assert len(selection.chat_ids) == 3
    assert selection.expected_count == sum(len(rows) for rows in selection.expected_by_chat.values())
    assert selection.expected_count > 0
    assert all(chat_id in selection.chat_ids for chat_id in selection.expected_by_chat)


def test_report_paths_can_be_unique(tmp_path: Path):
    first = tmp_path / "one" / "report.json"
    second = tmp_path / "two" / "report.json"
    for path, value in ((first, 1), (second, 2)):
        path.parent.mkdir(parents=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps({"value": value}), encoding="utf-8")
        temp.replace(path)
    assert json.loads(first.read_text(encoding="utf-8"))["value"] == 1
    assert json.loads(second.read_text(encoding="utf-8"))["value"] == 2


def test_missing_evidence_is_a_contract_failure():
    outcome = EvaluationOutcome(
        strict_tp=0, strict_fp=1, strict_fn=1,
        valid_extra=0, invalid=1, evidence_valid=0, evidence_invalid=1,
    )
    incomplete = outcome.incomplete or outcome.evidence_invalid > 0
    assert incomplete
