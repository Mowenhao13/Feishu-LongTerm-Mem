#!/usr/bin/env python3
"""Sleep consolidation eval: compare Precision/Recall/F1 before and after sleep.

Usage:
    python scripts/test_sleep_consolidation.py \
        --input eval_dataset/argusbot_single/messages.jsonl \
        --expected eval_dataset/argusbot_single/expected.jsonl \
        --delay 0.3

    # multi-chat
    python scripts/test_sleep_consolidation.py \
        --input eval_dataset/argusbot_multi/messages.jsonl \
        --expected eval_dataset/argusbot_multi/expected.jsonl \
        --delay 0.3 --group-num 8
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--group-num", type=int, default=1)
    args = parser.parse_args()

    # Clean state
    store_name = "argusbot-eval" if args.group_num == 1 else "argusbot-eval-multi"
    store_path = Path(f"memory_stores/{store_name}")
    if store_path.exists():
        import shutil
        shutil.rmtree(store_path)
    store_path.mkdir(parents=True)

    Path("data/suspend_pool.json").unlink(missing_ok=True)

    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)
    os.chdir(project_root)

    # Phase 1: Run the eval (same as eval_runner)
    from src.eval_runner import EvalRunner
    runner = EvalRunner(
        input_path=args.input,
        expected_path=args.expected,
        delay=args.delay,
        group_num=args.group_num,
    )

    logger.info("=" * 60)
    logger.info("Phase 1: Processing messages")
    logger.info("=" * 60)

    import asyncio
    asyncio.run(runner.run())

    # Get pre-sleep decisions
    engine = runner._engine
    pre_sleep_decisions = engine._graph.get_all_decisions() if engine else []
    logger.info("\nPre-sleep decisions: %d", len(pre_sleep_decisions))

    # Phase 2: Run comparator BEFORE sleep
    from src.eval.comparator import EvalComparator
    actual_pre = [
        {
            "sid": d.sid,
            "topic_id": d.topic_id or "",
            "summary": d.summary or "",
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            "impact": d.impact_level.value if hasattr(d.impact_level, "value") else str(d.impact_level),
            "chat_id": getattr(d, "chat_id", ""),
            "is_suggestion": getattr(d, "is_suggestion", False),
        }
        for d in pre_sleep_decisions
    ]
    embedder = getattr(engine, "_embedder", None) if engine else None
    comp_pre = EvalComparator(args.expected, embedding_provider=embedder)
    comp_pre.match(actual_pre)
    report_pre = comp_pre.compute_metrics()

    logger.info("\n" + "=" * 60)
    logger.info("Phase 2: Precision BEFORE sleep")
    logger.info("=" * 60)
    _print_report(report_pre)

    # Phase 3: Trigger sleep
    if engine:
        logger.info("\n" + "=" * 60)
        logger.info("Phase 3: Running sleep consolidation")
        logger.info("=" * 60)
        sleep_result = engine.sleep()
        # engine.sleep() returns a dict (the report.to_dict())
        if isinstance(sleep_result, dict):
            sr = sleep_result
        else:
            sr = sleep_result.to_dict() if hasattr(sleep_result, 'to_dict') else {}
        logger.info("Sleep report: %s", json.dumps(sr, ensure_ascii=False))

        # Phase 4: Run comparator AFTER sleep
        post_sleep_decisions = engine._graph.get_all_decisions()
        active_decisions = [d for d in post_sleep_decisions if d.status.is_active()]
        logger.info("\nPost-sleep decisions: %d (active: %d)", len(post_sleep_decisions), len(active_decisions))

        actual_post = [
            {
                "sid": d.sid,
                "topic_id": d.topic_id or "",
                "summary": d.summary or "",
                "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                "impact": d.impact_level.value if hasattr(d.impact_level, "value") else str(d.impact_level),
                "chat_id": getattr(d, "chat_id", ""),
                "is_suggestion": getattr(d, "is_suggestion", False),
            }
            for d in post_sleep_decisions  # match against ALL decisions (including shelved/superseded)
        ]
        comp_post = EvalComparator(args.expected, embedding_provider=embedder)
        comp_post.match(actual_post)
        report_post = comp_post.compute_metrics()

        logger.info("\n" + "=" * 60)
        logger.info("Phase 4: Precision AFTER sleep")
        logger.info("=" * 60)
        _print_report(report_post)

        # Phase 5: Compare
        logger.info("\n" + "=" * 60)
        logger.info("BEFORE vs AFTER sleep comparison")
        logger.info("=" * 60)
        _compare_reports(report_pre, report_post, sr)
    else:
        logger.warning("Engine not available, skipping sleep")


def _print_report(report: dict) -> None:
    logger.info("Expected:     %d", report["total_expected"])
    logger.info("Actual:       %d", report["total_detected"])
    logger.info("TP:           %d  FP: %d  FN: %d", report["true_positives"], report["false_positives"], report["false_negatives"])
    logger.info("Precision:    %.1f%%  Recall: %.1f%%  F1: %.1f%%",
                report["precision"] * 100, report["recall"] * 100, report["f1"] * 100)
    dm = report["decision_metrics"]
    logger.info("Decision R:   %.1f%%  Suggestion R: %.1f%%",
                dm.get("decision_recall", 0) * 100, dm.get("suggestion_recall", 0) * 100)


def _compare_reports(pre: dict, post: dict, sleep_report: dict) -> None:
    deltas = {
        "Precision": (post["precision"] - pre["precision"]) * 100,
        "Recall": (post["recall"] - pre["recall"]) * 100,
        "F1": (post["f1"] - pre["f1"]) * 100,
    }

    logger.info("\nMetric           Before    After     Delta")
    logger.info("-" * 50)
    for name, delta in deltas.items():
        key = name.lower()
        before = pre[key] * 100
        after = post[key] * 100
        sign = "+" if delta >= 0 else ""
        logger.info("%-16s %6.1f%%  %6.1f%%  %s%.1fpp",
                    name, before, after, sign, delta)

    # Sleep actions
    sr = sleep_report if isinstance(sleep_report, dict) else {}
    logger.info("\nSleep actions:")
    logger.info("  Duplicates merged: %d", sr.get("duplicates_merged", 0))
    logger.info("  Noise pruned:      %d", sr.get("noise_pruned", 0))
    logger.info("  FPs shelved:       %d", sr.get("fp_shelved", 0))
    logger.info("  Conflicts found:   %d", sr.get("conflicts_found", 0))
    logger.info("  Decisions promoted:%d", sr.get("decisions_promoted", 0))

    # Key insight: did FP go down?
    fp_delta = post["false_positives"] - pre["false_positives"]
    sign = "+" if fp_delta >= 0 else ""
    logger.info("\nFP change: %s%d (%d → %d)", sign, fp_delta, pre["false_positives"], post["false_positives"])
    if post["false_positives"] < pre["false_positives"]:
        logger.info("✅ Sleep reduced false positives (precision improved)")
    elif post["false_positives"] == pre["false_positives"]:
        logger.info("➡️  Sleep did not change FP count")
    else:
        logger.info("⚠️  Sleep increased FP count (may have surfaced missed decisions)")


if __name__ == "__main__":
    main()
