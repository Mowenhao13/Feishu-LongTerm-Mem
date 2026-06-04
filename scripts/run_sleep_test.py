#!/usr/bin/env python3
"""Sleep test script: run eval, backup memory data, run sleep consolidation, report results.

Usage:
    uv run python3 scripts/run_sleep_test.py --dataset multi_chat
    uv run python3 scripts/run_sleep_test.py --dataset single_chat
    uv run python3 scripts/run_sleep_test.py --dataset multi_chat --skip-eval  # reuse existing mem-data
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.sleep import SleepManager, SleepReport

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def backup_mem_data(dataset: str) -> str:
    """备份当前 mem-data 目录"""
    src = PROJECT_ROOT / "mem-data"
    if not src.exists():
        print(f"[Sleep Test] No mem-data found at {src}")
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = PROJECT_ROOT / "mem-data_backups" / f"{dataset}_{timestamp}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    print(f"[Sleep Test] Backed up mem-data to {dst}")
    return str(dst)


async def run_eval(dataset: str) -> None:
    """运行 eval 生成决策数据（不清除 mem-data）"""
    print(f"[Sleep Test] Running eval for {dataset}...")
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python3", "scripts/run_eval_accuracy.py",
        "--dataset", dataset,
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(timeout=900)
    print(stdout.decode()[-3000:] if stdout else "")
    if proc.returncode != 0:
        print(f"[Sleep Test] Eval failed:\n{stderr.decode()[-1000:]}")
        raise RuntimeError(f"Eval failed with code {proc.returncode}")
    print(f"[Sleep Test] Eval completed for {dataset}")


def collect_decisions_from_path(path: str) -> List[Dict[str, Any]]:
    """从备份路径收集所有决策（解析 md 文件）"""
    decisions: List[Dict[str, Any]] = []
    decisions_dir = Path(path) / "decisions"
    if not decisions_dir.exists():
        return decisions

    for md_file in decisions_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            record: Dict[str, Any] = {"sid": md_file.stem}
            for line in lines:
                if ":" in line and not line.startswith("#") and not line.startswith("---"):
                    k, v = line.split(":", 1)
                    record[k.strip().lower()] = v.strip()
            decisions.append(record)
        except Exception as e:
            print(f"[Sleep Test] Error reading {md_file}: {e}")

    return decisions


def compare_decisions(before: List[Dict], after_sleep_path: str) -> Dict[str, Any]:
    """比较 sleep 前后的决策统计"""
    after = collect_decisions_from_path(after_sleep_path)
    before_ids = {d.get("sid") for d in before}
    after_ids = {d.get("sid") for d in after}

    removed = before_ids - after_ids
    added = after_ids - before_ids

    before_active = [d for d in before if d.get("status") not in ("superseded", "shelved")]
    after_active = [d for d in after if d.get("status") not in ("superseded", "shelved")]

    return {
        "before_total": len(before),
        "after_total": len(after),
        "before_active": len(before_active),
        "after_active": len(after_active),
        "removed_ids": list(removed),
        "added_ids": list(added),
        "dedup_count": len(removed) - len(added),
        "compression_rate": round((len(before_active) - len(after_active)) / max(len(before_active), 1) * 100, 2),
    }


async def main():
    parser = argparse.ArgumentParser(description="Sleep consolidation test")
    parser.add_argument("--dataset", required=True, choices=["single_chat", "multi_chat", "test_small"])
    parser.add_argument("--skip-eval", action="store_true", help="Skip eval run, use existing mem-data")
    args = parser.parse_args()

    # Step 1: Run eval if needed
    if not args.skip_eval:
        await run_eval(args.dataset)
    else:
        print(f"[Sleep Test] Skipping eval, using existing mem-data")

    # Step 2: Backup mem-data
    backup_path = backup_mem_data(args.dataset)
    if not backup_path:
        print("[Sleep Test] No mem-data to backup, aborting")
        return

    # Step 3: Collect decisions BEFORE sleep
    before = collect_decisions_from_path(backup_path)
    print(f"[Sleep Test] Before sleep: {len(before)} decisions")

    # Step 4: Run SleepManager on the backup
    print(f"[Sleep Test] Running SleepManager.sleep() on backup...")
    sm = SleepManager(source_path=backup_path)
    report = sm.sleep()
    print(f"[Sleep Test] Sleep report:")
    print(f"  duplicates_found:  {report.duplicates_found}")
    print(f"  duplicates_merged: {report.duplicates_merged}")
    print(f"  noise_pruned:      {report.noise_pruned}")
    print(f"  conflicts_found:   {report.conflicts_found}")
    print(f"  decisions_promoted:{report.decisions_promoted}")
    if report.errors:
        print(f"  errors:            {report.errors}")

    # Step 5: Compare before/after
    # Sleep writes decisions back via the _storage layer.
    # We need a mem-data snapshot after sleep for comparison.
    after_backup = backup_mem_data(f"{args.dataset}_after_sleep")
    if after_backup:
        after = collect_decisions_from_path(after_backup)
        print(f"[Sleep Test] After sleep: {len(after)} decisions")
        comparison = compare_decisions(before, after_backup)
        print(f"[Sleep Test] Comparison:")
        print(f"  Before active: {comparison['before_active']}")
        print(f"  After active:  {comparison['after_active']}")
        print(f"  Dedup count:   {comparison['dedup_count']}")
        print(f"  Compression:   {comparison['compression_rate']}%")

    # Save report
    report_path = PROJECT_ROOT / "eval_reports" / f"sleep_{args.dataset}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "dataset": args.dataset,
            "backup_path": backup_path,
            "before_count": len(before),
            "sleep_report": report.to_dict(),
        }, f, ensure_ascii=False, indent=2)
    print(f"[Sleep Test] Report saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())