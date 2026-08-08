"""Frozen-output evaluator calibration harness.

Loads previously-generated chunk report outputs (not runs/**/report.json)
and re-scores them through a supplied evaluator mode to measure agreement
against human labels. No extractor, memory extractor, or engine invocation
is performed — only the evaluator over frozen decisions.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_final_outputs(reports_root: Path) -> list[dict[str, Any]]:
    """Walk for chunk_*/report.json only, ignoring nested runs/**/report.json.

    Returns a flat list of confirmed_output rows from all chunk reports,
    each augmented with chunk_source metadata.
    """
    rows: list[dict[str, Any]] = []
    pattern = "chunk_*"
    for chunk_dir in sorted(reports_root.glob(pattern)):
        if not chunk_dir.is_dir():
            continue
        report_path = chunk_dir / "report.json"
        if not report_path.exists():
            continue
        report = _read_json(report_path)
        confirmed = report.get("evaluation_audit", {}).get("confirmed_outputs", [])
        chunk_label = chunk_dir.name
        for output in confirmed:
            output["_chunk"] = chunk_label
            rows.append(output)
    return rows


def _normalize_key(output: dict[str, Any]) -> str:
    """Create a deterministic key for an output row."""
    chat_id = output.get("chat_id", "")
    title = output.get("title", "")
    return f"{chat_id}__{title}"


def score_calibration(
    labels: list[dict[str, Any]],
    assignments: dict[str, str],
) -> dict[str, Any]:
    """Per-class confusion matrix keeping valid_extra distinct from invalid.

    labels: list of human label dicts, each with output_normalized and classification.
    assignments: dict mapping normalized_key -> classifier_result classification.

    Returns confusion dict, per_class metrics, and macro_f1.
    """
    classes = ["match_gt", "valid_extra", "invalid"]
    confusion: dict[str, dict[str, int]] = {
        cls: {other: 0 for other in classes} for cls in classes
    }

    for label in labels:
        key = label.get("output_normalized", "")
        true_cls = label.get("classification", "")
        if true_cls not in classes:
            continue
        pred_cls = assignments.get(key, "invalid")
        if pred_cls not in classes:
            pred_cls = "invalid"
        confusion[true_cls][pred_cls] += 1

    per_class: dict[str, dict[str, float]] = {}
    for cls in classes:
        tp = confusion[cls][cls]
        fp = sum(confusion[other][cls] for other in classes if other != cls)
        fn = sum(confusion[cls][other] for other in classes if other != cls)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        per_class[cls] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    macro_f1 = (
        sum(per_class[cls]["f1"] for cls in classes) / len(classes)
        if classes
        else 0.0
    )

    return {
        "confusion": confusion,
        "per_class": per_class,
        "macro_f1": round(macro_f1, 4),
    }


def run_calibration(
    reports_root: Path,
    labels_path: Path,
    repeats: int = 3,
    evaluator: Callable[[list[dict[str, Any]]], dict[str, str]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Main orchestrator for evaluator calibration.

    Handles dry-run mode, unreviewed labels, and evaluator failure.
    """
    # Load labels
    labels_data = _read_json(labels_path)
    reviewed = labels_data.get("reviewed", False)
    label_rows = labels_data.get("rows", [])

    # Load final outputs
    outputs = load_final_outputs(reports_root)

    report: dict[str, Any] = {
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "reports_root": str(reports_root),
        "labels_path": str(labels_path),
        "labels_reviewed": reviewed,
        "label_count": len(label_rows),
        "output_count": len(outputs),
        "chunks_found": len(set(o.get("_chunk", "") for o in outputs)),
        "repeats": repeats,
        "dry_run": dry_run,
        "health": {
            "all_complete": True,
            "errors": [],
        },
    }

    if dry_run:
        report["dry_run_note"] = (
            "Dry-run: no evaluator execution performed."
        )
        if not reviewed:
            report["health"]["all_complete"] = False
            report["health"]["labels_not_reviewed"] = True
        return report

    if not reviewed:
        return {
            **report,
            "health": {
                "all_complete": False,
                "errors": ["labels not reviewed"],
            },
        }

    # Run evaluation for each repeat
    run_results: list[dict[str, Any]] = []
    all_complete = True

    for repeat_index in range(repeats):
        repeat_result: dict[str, Any] = {
            "repeat_index": repeat_index + 1,
            "complete": True,
            "assignments": {},
            "errors": [],
        }

        try:
            if evaluator is not None:
                assignments = evaluator(outputs)
            else:
                assignments = {}
            repeat_result["assignments"] = assignments
        except Exception as exc:
            repeat_result["complete"] = False
            repeat_result["errors"].append(str(exc))
            all_complete = False

        # Score calibration for this repeat
        if repeat_result["complete"]:
            scoring = score_calibration(label_rows, repeat_result["assignments"])
            repeat_result["scoring"] = scoring
        else:
            repeat_result["scoring"] = None

        run_results.append(repeat_result)

    report["runs"] = run_results
    report["health"] = {
        "all_complete": all_complete,
        "errors": [],
    }

    return report


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate frozen-output evaluator against human labels"
    )
    parser.add_argument(
        "--reports-root",
        type=Path,
        required=True,
        help="Root directory containing chunk_*/report.json files",
    )
    parser.add_argument(
        "--labels",
        required=True,
        type=Path,
        help="Path to calibration_labels.json",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of evaluator repeats (default: 3)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for calibration report (default: printed to stdout)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inventory outputs and check labels without running evaluator",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not args.labels.exists():
        print(f"Error: labels file not found: {args.labels}", file=sys.stderr)
        return 1

    report = run_calibration(
        reports_root=args.reports_root,
        labels_path=args.labels,
        repeats=args.repeats,
        evaluator=None,
        dry_run=args.dry_run,
    )

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        _write_json(args.output, report)
    else:
        print(output)

    return 0 if report["health"]["all_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())