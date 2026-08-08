from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_report(root: Path, chunk: str, confirmed_outputs: list[dict]) -> None:
    """Write a chunk report with evaluation_audit.confirmed_outputs."""
    chunk_dir = root / chunk
    chunk_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "evaluation_audit": {
            "confirmed_outputs": confirmed_outputs,
        },
        "selection": {"chat_ids": ["test_chat"], "expected_count": 1},
        "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
    }
    (chunk_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_nested_run_report(root: Path, chunk: str, run_id: str) -> None:
    """Write a nested runs/**/report.json that should be ignored."""
    run_dir = root / chunk / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "evaluation_audit": {
            "confirmed_outputs": [
                {"chat_id": "ignored_run", "title": "should be ignored"}
            ],
        },
        "selection": {"chat_ids": ["ignored_run"], "expected_count": 0},
        "metrics": {},
    }
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class TestLoadFinalOutputs:
    """Tests for load_final_outputs()."""

    def test_load_final_outputs_ignores_nested_retry_reports(self, tmp_path: Path):
        """Only chunk_*/report.json is loaded; runs/**/report.json is ignored."""
        from experiments.production_ablation.calibrate_evaluator import (
            load_final_outputs,
        )

        _write_report(
            tmp_path,
            "chunk_000",
            [
                {
                    "chat_id": "test_chat",
                    "title": "final output",
                    "summary": "test summary",
                    "adjudication": "match_gt",
                    "evidence_valid": True,
                    "source_message_ids": ["m001"],
                    "evidence_quote": "test quote",
                }
            ],
        )
        _write_nested_run_report(tmp_path, "chunk_000", "some-run-id")

        rows = load_final_outputs(tmp_path)
        assert len(rows) == 1
        assert rows[0]["title"] == "final output"
        assert rows[0]["chat_id"] == "test_chat"


class TestScoreCalibration:
    """Tests for score_calibration()."""

    def test_calibration_confusion_keeps_valid_extra_out_of_invalid(self):
        """valid_extra maps to valid_extra in confusion, not to invalid."""
        from experiments.production_ablation.calibrate_evaluator import (
            score_calibration,
        )

        labels = [
            {
                "chat_id": "ch1",
                "output_normalized": "ch1__output_1",
                "classification": "match_gt",
                "matched_msg_id": "m001",
            },
            {
                "chat_id": "ch1",
                "output_normalized": "ch1__output_2",
                "classification": "valid_extra",
                "matched_msg_id": "",
            },
            {
                "chat_id": "ch1",
                "output_normalized": "ch1__output_3",
                "classification": "invalid",
                "matched_msg_id": "",
            },
        ]
        # All assignments match labels perfectly
        assignments = {
            "ch1__output_1": "match_gt",
            "ch1__output_2": "valid_extra",
            "ch1__output_3": "invalid",
        }

        report = score_calibration(labels, assignments)
        confusion = report["confusion"]
        assert confusion["valid_extra"]["valid_extra"] == 1
        assert confusion["invalid"]["valid_extra"] == 0
        assert confusion["valid_extra"]["invalid"] == 0
        assert confusion["match_gt"]["match_gt"] == 1
        assert confusion["invalid"]["invalid"] == 1


class TestRunCalibration:
    """Tests for run_calibration()."""

    def test_failed_assignment_is_reported_as_incomplete(self, tmp_path: Path):
        """An evaluator that raises marks health.all_complete as False."""
        from experiments.production_ablation.calibrate_evaluator import (
            run_calibration,
        )

        _write_report(
            tmp_path,
            "chunk_000",
            [
                {
                    "chat_id": "test_chat",
                    "title": "some output",
                    "summary": "test",
                    "adjudication": "match_gt",
                    "evidence_valid": True,
                    "source_message_ids": ["m001"],
                    "evidence_quote": "test quote",
                }
            ],
        )

        labels_path = tmp_path / "labels.json"
        labels_path.write_text(
            json.dumps(
                {
                    "reviewed": True,
                    "metadata": {"evaluator_version": "test"},
                    "rows": [
                        {
                            "chat_id": "test_chat",
                            "output_normalized": "test_chat__some output__chunk_000",
                            "classification": "match_gt",
                            "matched_msg_id": "m001",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        def broken_evaluator(group):
            raise RuntimeError("bad assignment")

        report = run_calibration(
            reports_root=tmp_path,
            labels_path=labels_path,
            repeats=1,
            evaluator=broken_evaluator,
            dry_run=False,
        )
        assert report["health"]["all_complete"] is False

    def test_dry_run_refuses_without_reviewed_labels(self, tmp_path: Path):
        """Dry-run with unreviewed labels reports labels not reviewed."""
        from experiments.production_ablation.calibrate_evaluator import (
            run_calibration,
        )

        _write_report(
            tmp_path,
            "chunk_000",
            [
                {
                    "chat_id": "test_chat",
                    "title": "some output",
                    "summary": "test",
                    "adjudication": "match_gt",
                    "evidence_valid": True,
                    "source_message_ids": ["m001"],
                    "evidence_quote": "test quote",
                }
            ],
        )

        labels_path = tmp_path / "labels.json"
        labels_path.write_text(
            json.dumps(
                {
                    "reviewed": False,
                    "metadata": {"evaluator_version": "test"},
                    "rows": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        report = run_calibration(
            reports_root=tmp_path,
            labels_path=labels_path,
            repeats=1,
            evaluator=None,
            dry_run=True,
        )
        # In dry-run mode with unreviewed labels, the report should indicate
        # that labels are not ready.
        assert report["health"]["all_complete"] is False
        messages = str(report)
        assert (
            "reviewed" in messages.lower()
            or "not reviewed" in messages.lower()
            or "dry_run" in messages.lower()
            or "labels" in messages.lower()
        )