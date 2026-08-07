"""Checkpointed, resumable production-path evaluation by chat chunks."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "experiments" / "production_ablation" / "run.py"
DATASET = REPO / "eval_dataset" / "argusbot_v3"

def split_chunks(chat_ids: list[str], chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    return [chat_ids[index:index + chunk_size] for index in range(0, len(chat_ids), chunk_size)]

def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
    temp.replace(path)

def _latest_report(root: Path) -> Path | None:
    reports = list(root.glob("**/report.json")) if root.exists() else []
    return max(reports, key=lambda path: path.stat().st_mtime) if reports else None

def merge_chunk_reports(reports: list[dict[str, Any]], failures: list[dict[str, Any]], variant: str, job_id: str) -> dict[str, Any]:
    count_keys = ("strict_tp", "strict_fp", "strict_fn", "valid_extra", "invalid", "evidence_valid", "evidence_invalid", "output_count")
    totals = {key: sum(int(report.get("metrics", {}).get(key, report.get(key, 0))) for report in reports) for key in count_keys}
    tp, fp, fn = totals["strict_tp"], totals["strict_fp"], totals["strict_fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    per_chat = {}
    for report in reports:
        per_chat.update(report.get("chat_metrics", {}))
    macro_values = {key: [float(row[key]) for row in per_chat.values() if key in row] for key in ("precision", "recall", "f1")}
    macro = {key: {"mean": statistics.mean(values), "stddev": statistics.pstdev(values), "min": min(values), "max": max(values)} for key, values in macro_values.items() if values}
    complete = len(failures) == 0 and all(not report.get("metrics", {}).get("incomplete") and not report.get("runner_errors") for report in reports)
    return {"job_id": job_id, "variant": variant, "chunks": len(reports) + len(failures), "completed_chunks": len(reports), "failed_chunks": len(failures), "failures": failures, "totals": totals, "metrics": {"precision": precision, "recall": recall, "f1": f1, "strict_tp": tp, "strict_fp": fp, "strict_fn": fn, "valid_extra": totals["valid_extra"], "invalid": totals["invalid"], "evidence_valid": totals["evidence_valid"], "evidence_invalid": totals["evidence_invalid"], "incomplete": not complete}, "macro": macro, "per_chat": per_chat, "health": {"all_complete": complete, "evidence_contract_pass_rate": sum(report.get("metrics", {}).get("evidence_invalid", 0) == 0 for report in reports) / len(reports) if reports else 0.0, "runner_error_free_rate": sum(not report.get("runner_errors") for report in reports) / len(reports) if reports else 0.0}}

def main() -> int:
    parser = argparse.ArgumentParser(description="Checkpointed full production-path evaluation")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=1800, help="Per-chunk timeout in seconds")
    parser.add_argument("--job-root", type=Path, default=REPO / "experiments" / "production_ablation" / "chunked_runs")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--adjudicate", action="store_true")
    args = parser.parse_args()
    from src.eval.confirmed_decision_eval import DatasetSelection
    selection = DatasetSelection.from_jsonl(DATASET, sample=args.sample)
    chunks = split_chunks(list(selection.chat_ids), args.chunk_size)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_id = args.job_id or f"{args.variant}_{timestamp}"
    job_dir = args.job_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = job_dir / "manifest.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if args.resume and manifest_path.exists() else {"job_id": job_id, "variant": args.variant, "chunks": []}
    reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    completed_by_index = {item["index"]: item for item in existing.get("chunks", []) if item.get("status") == "complete"}
    for index, chat_ids in enumerate(chunks):
        chunk_dir = job_dir / f"chunk_{index:03d}"
        chunk_report = chunk_dir / "report.json"
        if args.resume and index in completed_by_index and chunk_report.exists():
            reports.append(json.loads(chunk_report.read_text(encoding="utf-8")))
            continue
        chunk_dir.mkdir(parents=True, exist_ok=True)
        run_root = chunk_dir / "runs"
        command = [sys.executable, str(RUNNER), "--variant", args.variant, "--run-root", str(run_root)]
        for chat_id in chat_ids:
            command.extend(["--chat-id", chat_id])
        if args.adjudicate:
            command.append("--adjudicate")
        status = {"index": index, "chat_ids": chat_ids, "status": "running"}
        existing["chunks"] = [item for item in existing.get("chunks", []) if item.get("index") != index] + [status]
        _write_json(manifest_path, existing)
        try:
            completed = subprocess.run(command, cwd=REPO, env=os.environ.copy(), capture_output=True, text=True, timeout=args.timeout, check=False)
            report_path = _latest_report(run_root)
            if report_path is None:
                raise RuntimeError(f"no report produced; returncode={completed.returncode}; stderr={completed.stderr[-1000:]}")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            chunk_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if completed.returncode != 0 or report.get("metrics", {}).get("incomplete") or report.get("runner_errors"):
                failures.append({"index": index, "chat_ids": chat_ids, "status": "incomplete", "returncode": completed.returncode, "run_id": report.get("metadata", {}).get("run_id", "")})
                status["status"] = "incomplete"
            else:
                reports.append(report)
                status["status"] = "complete"
        except subprocess.TimeoutExpired as exc:
            failures.append({"index": index, "chat_ids": chat_ids, "status": "timeout", "timeout_seconds": args.timeout, "stderr_tail": str(exc.stderr)[-1000:] if exc.stderr else ""})
            status["status"] = "timeout"
        except Exception as exc:
            failures.append({"index": index, "chat_ids": chat_ids, "status": "error", "error": str(exc)})
            status["status"] = "error"
        existing["chunks"] = [item for item in existing.get("chunks", []) if item.get("index") != index] + [status]
        _write_json(manifest_path, existing)
    aggregate = merge_chunk_reports(reports, failures, args.variant, job_id)
    _write_json(job_dir / "aggregate.json", aggregate)
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    return 0 if aggregate["health"]["all_complete"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
