"""CLI for evidence-aware production-path ablation smoke runs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.eval.confirmed_decision_adjudicator import LLMDecisionAdjudicator
from src.eval.confirmed_decision_eval import (
    build_global_adjudication_groups,
    ChatAssignment,
    ConfirmedDecisionEvaluator,
    DatasetSelection,
    GlobalAdjudicationGroup,
)

DATASET = REPO / "eval_dataset" / "argusbot_v3"


def _run_metadata(options: object, selection: DatasetSelection) -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False,
    ).stdout.strip()
    return {
        "run_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "dataset_hash": selection.dataset_hash,
        "model": os.getenv("MODEL_NAME", "deepseek-chat"),
        "options": options.__dict__,
    }


async def _adjudicate_decisions(
    judge: LLMDecisionAdjudicator,
    decisions: tuple,
    selection: DatasetSelection,
    evaluator: ConfirmedDecisionEvaluator,
    cache: dict[str, ChatAssignment] | None = None,
) -> tuple[dict, Callable[[GlobalAdjudicationGroup], ChatAssignment]]:
    """Build global per-chat adjudication assignments and return report metadata + closure.

    Optionally accepts an existing *cache* dict to reuse across invocations.
    """
    adjudicator_calls = 0
    adjudicator_cache_hits = 0
    adjudication_errors: list[str] = []
    adjudication_cache: dict[str, ChatAssignment] = {} if cache is None else cache

    for group in build_global_adjudication_groups(decisions, selection):
        key = judge.cache_key(group)
        if key in adjudication_cache:
            adjudicator_cache_hits += 1
            continue
        try:
            adjudication_cache[key] = await judge.adjudicate_chat(group)
            adjudicator_calls += 1
        except Exception as exc:
            adjudication_errors.append(f"{group.chat_id}: {exc}")

    def global_adjudicator(group: GlobalAdjudicationGroup) -> ChatAssignment:
        key = judge.cache_key(group)
        if key not in adjudication_cache:
            raise RuntimeError(f"missing adjudication result for {group.chat_id}")
        return adjudication_cache[key]

    return {
        "enabled": True,
        "mode": "global_assignment_v1",
        "calls": adjudicator_calls,
        "cache_hits": adjudicator_cache_hits,
        "errors": list(adjudication_errors),
        "prompt_version": judge.PROMPT_VERSION,
        "schema_version": judge.SCHEMA_VERSION,
        "cache_keys": sorted(adjudication_cache),
    }, global_adjudicator


async def main() -> int:
    # Heavy imports deferred to avoid circular/chain imports at module level
    from experiments.production_ablation.runner import run_variant
    from experiments.production_ablation.variants import build_variants
    from src.extractors.memory_extractor import MemoryExtractor
    from src.extractors.simple_llm_extractor import SimpleLLMExtractor
    from src.model.llm_provider import LLMProvider

    def _provider() -> LLMProvider:
        return LLMProvider(
            provider_type="openai",
            base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("API_KEY", ""),
            model=os.getenv("MODEL_NAME", "deepseek-chat"),
            max_tokens=int(os.getenv("MAX_TOKENS", "8192")),
            enable_stats=False,
        )

    parser = argparse.ArgumentParser(description="Production-path ablation smoke runner")
    parser.add_argument("--variant", default="full", choices=sorted(build_variants()))
    parser.add_argument("--sample", type=int, default=3)
    parser.add_argument("--chat-id", action="append", default=[])
    parser.add_argument("--run-root", type=Path, default=REPO / "experiments" / "production_ablation" / "runs")
    parser.add_argument("--adjudicate", action="store_true", help="Use LLM three-state adjudication for evidence-valid GT extras")
    args = parser.parse_args()

    selection = DatasetSelection.from_jsonl(
        DATASET, chat_ids=args.chat_id or None, sample=None if args.chat_id else args.sample,
    )
    variants = build_variants()
    variant = variants[args.variant]
    metadata = _run_metadata(variant.options, selection)
    run_dir = args.run_root / metadata["run_id"]

    provider = _provider()
    extractor = SimpleLLMExtractor(provider)
    memory_extractor = MemoryExtractor(provider)
    result = await run_variant(
        dict(selection.messages_by_chat), variant, run_dir, extractor, memory_extractor,
    )

    adjudicator_report: dict = {
        "enabled": False,
        "mode": "disabled",
        "calls": 0,
        "cache_hits": 0,
        "errors": [],
        "prompt_version": "",
        "schema_version": "",
        "cache_keys": [],
    }
    evaluator = ConfirmedDecisionEvaluator()

    if args.adjudicate:
        judge = LLMDecisionAdjudicator(provider)
        adjudicator_report, global_adjudicator = await _adjudicate_decisions(
            judge, result.decisions, selection, evaluator,
        )
        evaluator = ConfirmedDecisionEvaluator(global_adjudicator=global_adjudicator)

    outcome = evaluator.evaluate(result.decisions, selection)
    chat_metrics = {}
    for chat_id in selection.chat_ids:
        rows = [row for row in outcome.details if row.get("chat_id") == chat_id]
        chat_tp = sum(row.get("adjudication") == "match_gt" for row in rows)
        chat_fp = sum(row.get("adjudication") == "invalid" for row in rows)
        chat_fn = max(len(selection.expected_by_chat.get(chat_id, ())) - chat_tp, 0)
        chat_precision = chat_tp / (chat_tp + chat_fp) if chat_tp + chat_fp else 0.0
        chat_recall = chat_tp / (chat_tp + chat_fn) if chat_tp + chat_fn else 0.0
        chat_f1 = 2 * chat_precision * chat_recall / (chat_precision + chat_recall) if chat_precision + chat_recall else 0.0
        chat_metrics[chat_id] = {"expected": len(selection.expected_by_chat.get(chat_id, ())), "tp": chat_tp, "fp": chat_fp, "fn": chat_fn, "precision": chat_precision, "recall": chat_recall, "f1": chat_f1}
    incomplete_reason = (
        "runner_error" if result.errors
        else "evaluation_error" if outcome.incomplete
        else "missing_or_invalid_evidence" if outcome.evidence_invalid > 0
        else ""
    )
    report = {
        "metadata": metadata,
        "selection": {"chat_ids": selection.chat_ids, "expected_count": selection.expected_count, "expected_by_chat": {chat_id: len(rows) for chat_id, rows in selection.expected_by_chat.items()}},
        "trace": result.trace.__dict__,
        "output_count": len(result.decisions),
        "chat_metrics": chat_metrics,
        "metrics": {
            "strict_tp": outcome.strict_tp,
            "strict_fp": outcome.strict_fp,
            "strict_fn": outcome.strict_fn,
            "valid_extra": outcome.valid_extra,
            "invalid": outcome.invalid,
            "evidence_valid": outcome.evidence_valid,
            "evidence_invalid": outcome.evidence_invalid,
            "errors": outcome.errors,
            "precision": outcome.precision,
            "recall": outcome.recall,
            "f1": outcome.f1,
            "incomplete": outcome.incomplete or outcome.evidence_invalid > 0 or bool(result.errors),
            "incomplete_reason": incomplete_reason,
        },
        "evaluation_audit": {
            "confirmed_outputs": outcome.details,
            "unmatched_expected": outcome.unmatched_expected,
        },
        "runner_errors": result.errors,
        "adjudicator": adjudicator_report,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    temp_path = run_dir / "report.json.tmp"
    temp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
    temp_path.replace(run_dir / "report.json")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=list))
    return 0 if not report["metrics"]["incomplete"] and not result.errors else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))