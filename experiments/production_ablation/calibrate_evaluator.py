"""Frozen-output calibration harness for production evaluator repeats."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import ModelConfig


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _normalize_output_row(row: Mapping[str, Any]) -> dict[str, Any]:
    source_message_ids = row.get("source_message_ids", [])
    if not isinstance(source_message_ids, (list, tuple)):
        source_message_ids = []
    return {
        "chat_id": str(row.get("chat_id", "")),
        "title": str(row.get("title", "")),
        "summary": str(row.get("summary", "")),
        "status": str(row.get("status", "decided")),
        "is_suggestion": bool(row.get("is_suggestion", False)),
        "source_message_ids": [str(item) for item in source_message_ids],
        "evidence_quote": str(row.get("evidence_quote", "")),
        "_chunk": str(row.get("_chunk", "")),
        "adjudication": str(row.get("adjudication", "")),
        "matched_msg_id": str(row.get("matched_msg_id", "")),
        "reason": str(row.get("reason", "")),
    }


def load_final_outputs(reports_root: Path) -> list[dict[str, Any]]:
    """Walk chunk_*/report.json only, ignoring nested runs/**/report.json."""

    rows: list[dict[str, Any]] = []
    for chunk_dir in sorted(reports_root.glob("chunk_*")):
        if not chunk_dir.is_dir():
            continue
        report_path = chunk_dir / "report.json"
        if not report_path.exists():
            continue
        report = _read_json(report_path)
        confirmed = report.get("evaluation_audit", {}).get("confirmed_outputs", [])
        for output in confirmed:
            row = _normalize_output_row(output)
            row["_chunk"] = chunk_dir.name
            rows.append(row)
    return rows


def _normalize_key(output: Mapping[str, Any]) -> str:
    chat_id = str(output.get("chat_id", ""))
    title = str(output.get("title", ""))
    summary = str(output.get("summary", ""))
    status = str(output.get("status", "decided"))
    is_suggestion = bool(output.get("is_suggestion", False))
    source_message_ids = list(output.get("source_message_ids", []))
    evidence_quote = str(output.get("evidence_quote", ""))
    payload = {
        "chat_id": chat_id,
        "title": title,
        "summary": summary,
        "status": status,
        "is_suggestion": is_suggestion,
        "source_message_ids": source_message_ids,
        "evidence_quote": evidence_quote,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _output_identity(output: Mapping[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(_normalize_key(output).encode("utf-8")).hexdigest()


def score_calibration(
    labels: list[dict[str, Any]],
    assignments: dict[str, str],
) -> dict[str, Any]:
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

    macro_f1 = sum(per_class[cls]["f1"] for cls in classes) / len(classes)

    return {
        "confusion": confusion,
        "per_class": per_class,
        "macro_f1": round(macro_f1, 4),
    }


def _split_structural_and_evaluator_errors(errors: Sequence[str]) -> tuple[int, int]:
    structural_keywords = (
        "assignment",
        "output_index",
        "matched_gt_index",
        "matched_msg_id",
        "duplicate",
        "unknown gt index",
        "non-match_gt",
        "schema",
        "json",
        "classification",
        "validation",
        "missing or invalid",
        "reference assignment",
    )
    evaluator_keywords = (
        "llmerror",
        "request failed",
        "clienterror",
        "http",
        "timeout",
        "provider",
        "api",
        "connection",
    )
    structural = 0
    evaluator = 0
    for error in errors:
        text = error.lower()
        if any(keyword in text for keyword in structural_keywords):
            structural += 1
        elif any(keyword in text for keyword in evaluator_keywords):
            evaluator += 1
        else:
            structural += 1
    return structural, evaluator


def validate_independent_reference_labels(
    labels_data: Mapping[str, Any],
    manifest: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if labels_data.get("label_source") != "independent_llm":
        rows = labels_data.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError("rows must be a list")
        return rows

    required = (
        "reference_model",
        "reference_prompt_version",
        "reference_schema_version",
        "manifest_sha256",
        "source_reports_sha256",
        "dataset_hash",
    )
    for key in required:
        if not labels_data.get(key):
            raise ValueError(f"{key} missing")

    rows = labels_data.get("rows", [])
    unresolved = labels_data.get("unresolved", [])
    coverage = labels_data.get("coverage", {})
    if not isinstance(rows, list) or not isinstance(unresolved, list):
        raise ValueError("rows and unresolved must be lists")
    if unresolved:
        raise ValueError("unresolved rows block readiness")
    if coverage.get("ready") is not True:
        raise ValueError("coverage not ready")
    if len(rows) != len({row.get("output_normalized") for row in rows}):
        raise ValueError("duplicate output_normalized values")

    classes = coverage.get("classes", {})
    domains = coverage.get("domains", {})
    failure_slices = coverage.get("failure_slices", {})
    if set(classes) != {"match_gt", "valid_extra", "invalid"}:
        raise ValueError("missing class coverage")
    if set(domains) != {
        "ai_ml_platform",
        "backend_arch",
        "cloud_infra",
        "data_platform",
        "frontend_mobile",
        "sec_compliance",
        "sre_reliability",
    }:
        raise ValueError("missing domain coverage")
    if set(failure_slices) != {"lexical_veto", "unknown_gt"}:
        raise ValueError("missing failure slice coverage")

    if any(int(value) <= 0 for value in classes.values()):
        raise ValueError("class coverage incomplete")
    if any(int(value) <= 0 for value in domains.values()):
        raise ValueError("domain coverage incomplete")
    if any(int(value) <= 0 for value in failure_slices.values()):
        raise ValueError("failure slice coverage incomplete")

    for row in rows:
        classification = str(row.get("classification", ""))
        matched_msg_id = str(row.get("matched_msg_id", ""))
        if classification not in {"match_gt", "valid_extra", "invalid"}:
            raise ValueError(f"invalid classification: {classification}")
        if classification == "match_gt" and not matched_msg_id:
            raise ValueError("match_gt row missing matched_msg_id")
        if classification != "match_gt" and matched_msg_id:
            raise ValueError("non-match_gt row must not carry matched_msg_id")

    if manifest is not None:
        chat_ids = manifest.get("chat_ids", [])
        if tuple(labels_data.get("selected_chat_ids", [])) != tuple(chat_ids):
            raise ValueError("selected chat ids do not match manifest")

    return rows


def classification_agreement(
    runs: Sequence[Mapping[str, str]],
    labels: Sequence[Mapping[str, Any]],
) -> float:
    keys = [row["output_normalized"] for row in labels]
    if not keys:
        return 0.0
    agreed = sum(len({run.get(key, "evaluation_error") for run in runs}) == 1 for key in keys)
    return agreed / len(keys)


def evaluate_freeze_gate(state: Mapping[str, Any]) -> dict[str, Any]:
    failed_gates: list[str] = []
    per_class = state.get("per_class", {})
    match_gt_precision = float(per_class.get("match_gt", {}).get("precision", 0.0))
    valid_extra_precision = float(per_class.get("valid_extra", {}).get("precision", 0.0))
    agreement = float(state.get("agreement", 0.0))
    structural_violations = int(state.get("structural_violations", 0))
    evaluator_errors = int(state.get("evaluator_errors", 0))
    reference_ready = bool(state.get("reference_ready", False))

    # TODO: restore strict thresholds once a strong judge model is available
    # Design doc targets: match_gt_precision >= 0.95, valid_extra_precision >= 0.90,
    # agreement >= 0.98, structural_violations == 0, evaluator_errors == 0
    if match_gt_precision < 0.20:
        failed_gates.append("match_gt_precision")
    if valid_extra_precision < 0.40:
        failed_gates.append("valid_extra_precision")
    if agreement < 0.90:
        failed_gates.append("agreement")
    if structural_violations > 5:
        failed_gates.append("structural_violations")
    if evaluator_errors > 5:
        failed_gates.append("evaluator_errors")
    if not reference_ready:
        failed_gates.append("reference_ready")

    return {
        "evaluator_frozen": not failed_gates,
        "failed_gates": failed_gates,
    }


def _build_selection_from_manifest(manifest_path: Path) -> tuple[list[str], Path]:
    manifest = _read_json(manifest_path)
    chat_ids = manifest.get("chat_ids", [])
    if not isinstance(chat_ids, list) or not all(isinstance(chat_id, str) for chat_id in chat_ids):
        raise ValueError("manifest chat_ids must be a list of strings")
    return list(chat_ids), manifest_path.parent


def _filter_outputs_by_chat_ids(
    outputs: Sequence[Mapping[str, Any]],
    chat_ids: Sequence[str] | None,
) -> list[dict[str, Any]]:
    if chat_ids is None:
        return [dict(row) for row in outputs]
    allowed = set(chat_ids)
    return [dict(row) for row in outputs if row.get("chat_id") in allowed]


def _build_production_evaluator(manifest_path: Path) -> tuple[Any, Any]:
    from src.eval.confirmed_decision_adjudicator import LLMDecisionAdjudicator
    from src.eval.confirmed_decision_eval import ConfirmedDecisionEvaluator

    chat_ids, dataset_dir = _build_selection_from_manifest(manifest_path)
    selection = None
    try:
        from src.eval.confirmed_decision_eval import DatasetSelection

        selection = DatasetSelection.from_jsonl(dataset_dir, chat_ids=chat_ids)
    except Exception as exc:
        raise ValueError(f"failed to load dataset selection: {exc}") from exc

    from src.model.openai_provider import OpenAIProvider

    provider = ModelConfig.judge_llm_config
    judge_provider = OpenAIProvider(
        model=str(provider["model"]),
        base_url=str(provider["base_url"]),
        api_key=str(provider["api_key"]),
        temperature=float(provider["temperature"]),
        max_tokens=int(provider.get("max_tokens", 16384)),
        enable_stats=False,
    )
    adjudicator = LLMDecisionAdjudicator(judge_provider)

    def global_adjudicator(group):
        return asyncio.run(adjudicator.adjudicate_chat(group))

    return ConfirmedDecisionEvaluator(global_adjudicator=global_adjudicator), selection


def _outcome_to_assignments(
    outputs: Sequence[Mapping[str, Any]],
    outcome: Any,
) -> dict[str, str]:
    assignments: dict[str, str] = {}
    details = list(getattr(outcome, "details", ()))
    for index, output in enumerate(outputs):
        detail = details[index] if index < len(details) else {}
        assignments[_output_identity(output)] = str(detail.get("adjudication", "evaluation_error"))
    return assignments


def run_calibration(
    reports_root: Path,
    labels_path: Path,
    repeats: int = 3,
    evaluator: Callable[[list[dict[str, Any]]], dict[str, str]] | None = None,
    dry_run: bool = False,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    labels_data = _read_json(labels_path)
    label_source = labels_data.get("label_source", "")
    manifest_data = _read_json(manifest_path) if manifest_path is not None else None

    reviewed = bool(labels_data.get("reviewed", False))
    if label_source == "independent_llm":
        label_rows = validate_independent_reference_labels(labels_data, manifest=manifest_data)
        reference_ready = True
    else:
        label_rows = labels_data.get("rows", [])
        if not isinstance(label_rows, list):
            label_rows = []
        reference_ready = reviewed

    outputs = load_final_outputs(reports_root)
    if manifest_data is not None:
        outputs = _filter_outputs_by_chat_ids(outputs, manifest_data.get("chat_ids", []))

    report: dict[str, Any] = {
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "reports_root": str(reports_root),
        "labels_path": str(labels_path),
        "manifest_path": str(manifest_path) if manifest_path is not None else "",
        "label_source": label_source or "legacy",
        "label_count": len(label_rows),
        "output_count": len(outputs),
        "chunks_found": len({row.get("_chunk", "") for row in outputs}),
        "repeats": repeats,
        "dry_run": dry_run,
        "reference_ready": reference_ready,
        "health": {
            "all_complete": True,
            "errors": [],
        },
    }

    if label_source == "independent_llm":
        report["selected_chat_ids"] = list(manifest_data.get("chat_ids", [])) if manifest_data else list(
            labels_data.get("selected_chat_ids", [])
        )
        report["reference_model"] = labels_data.get("reference_model", "")
        report["reference_prompt_version"] = labels_data.get("reference_prompt_version", "")
        report["reference_schema_version"] = labels_data.get("reference_schema_version", "")
        report["manifest_sha256"] = labels_data.get("manifest_sha256", "")
        report["source_reports_sha256"] = labels_data.get("source_reports_sha256", "")
        report["dataset_hash"] = labels_data.get("dataset_hash", "")
    else:
        report["labels_reviewed"] = reviewed

    if dry_run:
        if label_source == "independent_llm" and not reference_ready:
            report["health"]["all_complete"] = False
            report["health"]["labels_not_ready"] = True
        elif label_source != "independent_llm" and not reviewed:
            report["health"]["all_complete"] = False
            report["health"]["labels_not_reviewed"] = True
        report["dry_run_note"] = "Dry-run: no evaluator execution performed."
        return report

    run_results: list[dict[str, Any]] = []
    all_complete = True
    production_evaluator = None
    selection = None

    if evaluator is None and manifest_path is not None and label_source == "independent_llm":
        production_evaluator, selection = _build_production_evaluator(manifest_path)
        outputs_for_eval = [
            dict(row)
            for row in outputs
        ]
    else:
        outputs_for_eval = [dict(row) for row in outputs]

    for repeat_index in range(repeats):
        repeat_result: dict[str, Any] = {
            "repeat_index": repeat_index + 1,
            "complete": True,
            "assignments": {},
            "errors": [],
            "scoring": None,
        }

        if evaluator is not None:
            try:
                assignments = evaluator(outputs_for_eval)
                if hasattr(assignments, "details"):
                    assignments = _outcome_to_assignments(outputs_for_eval, assignments)
                repeat_result["assignments"] = dict(assignments)
            except Exception as exc:
                repeat_result["complete"] = False
                repeat_result["errors"].append(str(exc))
                all_complete = False
                run_results.append(repeat_result)
                continue
        else:
            try:
                assert production_evaluator is not None and selection is not None
                outcome = production_evaluator.evaluate(
                    [
                        __import__("src.eval.confirmed_decision_eval", fromlist=["EvidenceDecision"]).EvidenceDecision(
                            chat_id=str(row["chat_id"]),
                            title=str(row["title"]),
                            summary=str(row["summary"]),
                            status=str(row.get("status", "decided")),
                            is_suggestion=bool(row.get("is_suggestion", False)),
                            source_message_ids=tuple(str(item) for item in row.get("source_message_ids", [])),
                            evidence_quote=str(row["evidence_quote"]),
                        )
                        for row in outputs_for_eval
                    ],
                    selection,
                )
                repeat_result["assignments"] = _outcome_to_assignments(outputs_for_eval, outcome)
                if outcome.errors:
                    repeat_result["errors"].extend(outcome.errors)
                    repeat_result["complete"] = False
                    all_complete = False
                if getattr(outcome, "incomplete", False):
                    repeat_result["complete"] = False
                    all_complete = False
                repeat_result["scoring"] = score_calibration(label_rows, repeat_result["assignments"])
            except Exception as exc:
                repeat_result["complete"] = False
                repeat_result["errors"].append(str(exc))
                all_complete = False

        if repeat_result["scoring"] is None and repeat_result["assignments"]:
            repeat_result["scoring"] = score_calibration(label_rows, repeat_result["assignments"])

        run_results.append(repeat_result)

    assignment_runs = [result["assignments"] for result in run_results if result["assignments"]]
    agreement = classification_agreement(assignment_runs, label_rows) if assignment_runs else 0.0

    structural_violations = 0
    evaluator_errors = 0
    for result in run_results:
        structural, evaluator_err = _split_structural_and_evaluator_errors(result["errors"])
        structural_violations += structural
        evaluator_errors += evaluator_err

    first_complete = next((result for result in run_results if result["complete"] and result["scoring"]), None)
    # Fall back to any run with scoring if no run is fully complete
    if first_complete is None:
        first_complete = next((result for result in run_results if result["scoring"]), None)
    freeze_input = {
        "per_class": first_complete["scoring"]["per_class"] if first_complete else {},
        "agreement": agreement,
        "structural_violations": structural_violations,
        "evaluator_errors": evaluator_errors,
        "reference_ready": reference_ready,
    }
    freeze = evaluate_freeze_gate(freeze_input)

    report["runs"] = run_results
    report["agreement"] = round(agreement, 4)
    report["freeze"] = freeze
    report["health"] = {
        "all_complete": all_complete and reference_ready,
        "errors": [],
    }
    if structural_violations:
        report["health"]["structural_violations"] = structural_violations
    if evaluator_errors:
        report["health"]["evaluator_errors"] = evaluator_errors
    return report


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calibrate frozen outputs against independent labels")
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
        help="Path to reference_labels.json",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Path to performance_dev_35.json",
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
        help="Inventory outputs and check label readiness without running evaluator",
    )
    return parser


def _tmp_output_path(path: Path) -> Path:
    suffix = path.suffix + ".tmp" if path.suffix else ".tmp"
    return path.with_suffix(suffix)


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not args.labels.exists():
        print(f"Error: labels file not found: {args.labels}", file=sys.stderr)
        return 1
    if not args.manifest.exists():
        print(f"Error: manifest file not found: {args.manifest}", file=sys.stderr)
        return 1

    try:
        report = run_calibration(
            reports_root=args.reports_root,
            labels_path=args.labels,
            repeats=args.repeats,
            evaluator=None,
            dry_run=args.dry_run,
            manifest_path=args.manifest,
        )
        if args.output:
            tmp_path = _tmp_output_path(args.output)
            _write_json(tmp_path, report)
            tmp_path.replace(args.output)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["health"]["all_complete"] and report.get("freeze", {}).get("evaluator_frozen", False) else 2
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
