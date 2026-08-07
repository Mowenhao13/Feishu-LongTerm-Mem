"""Repeat production-path ablation runs and aggregate health-aware metrics."""
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
METRIC_KEYS = ("strict_tp", "strict_fp", "strict_fn", "valid_extra", "invalid", "evidence_valid", "evidence_invalid", "precision", "recall", "f1")

def aggregate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    numeric: dict[str, dict[str, float]] = {}
    for key in METRIC_KEYS:
        values = [float(report["metrics"][key]) for report in reports if key in report.get("metrics", {})]
        if values:
            numeric[key] = {"mean": statistics.mean(values), "stddev": statistics.pstdev(values), "min": min(values), "max": max(values)}
    complete = [report for report in reports if not report.get("metrics", {}).get("incomplete") and not report.get("runner_errors")]
    return {
        "runs": len(reports),
        "complete_runs": len(complete),
        "incomplete_runs": len(reports) - len(complete),
        "numeric": numeric,
        "health": {
            "all_complete": len(complete) == len(reports),
            "evidence_contract_pass_rate": sum(report.get("metrics", {}).get("evidence_invalid", 0) == 0 for report in reports) / len(reports) if reports else 0.0,
            "runner_error_free_rate": sum(not report.get("runner_errors") for report in reports) / len(reports) if reports else 0.0,
        },
        "run_ids": [report.get("metadata", {}).get("run_id", "") for report in reports],
    }

def _latest_new_report(run_root: Path, before: set[str]) -> Path | None:
    candidates = [path for path in run_root.iterdir() if path.is_dir() and path.name not in before and (path / "report.json").exists()]
    return max(candidates, key=lambda path: path.stat().st_mtime) / "report.json" if candidates else None

def main() -> int:
    parser = argparse.ArgumentParser(description="Repeat production-path ablation runs")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--sample", type=int, default=3)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--run-root", type=Path, default=REPO / "experiments" / "production_ablation" / "runs")
    parser.add_argument("--aggregate-root", type=Path, default=REPO / "experiments" / "production_ablation" / "aggregates")
    args = parser.parse_args()
    if args.runs <= 0:
        parser.error("--runs must be positive")
    args.run_root.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index in range(args.runs):
        before = {path.name for path in args.run_root.iterdir() if path.is_dir()}
        command = [sys.executable, str(RUNNER), "--variant", args.variant, "--sample", str(args.sample), "--run-root", str(args.run_root)]
        completed = subprocess.run(command, cwd=REPO, env=os.environ.copy(), capture_output=True, text=True, check=False)
        report_path = _latest_new_report(args.run_root, before)
        if report_path is not None:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["repeat_index"] = index + 1
            reports.append(report)
        else:
            failures.append({"repeat_index": index + 1, "returncode": completed.returncode, "stderr_tail": completed.stderr[-1000:]})
    aggregate = aggregate_reports(reports)
    aggregate.update({"variant": args.variant, "sample": args.sample, "failures": failures, "created_at": datetime.now(timezone.utc).isoformat()})
    args.aggregate_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.aggregate_root / f"{args.variant}_{timestamp}.json"
    output.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    return 0 if aggregate["health"]["all_complete"] and not failures else 2

if __name__ == "__main__":
    raise SystemExit(main())
