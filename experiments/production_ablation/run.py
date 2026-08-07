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
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.production_ablation.runner import run_variant
from experiments.production_ablation.variants import build_variants
from src.eval.confirmed_decision_eval import ConfirmedDecisionEvaluator, DatasetSelection
from src.extractors.memory_extractor import MemoryExtractor
from src.extractors.simple_llm_extractor import SimpleLLMExtractor
from src.model.llm_provider import LLMProvider

DATASET = REPO / "eval_dataset" / "argusbot_v3"


def _provider() -> LLMProvider:
    return LLMProvider(
        provider_type="openai",
        base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
        api_key=os.getenv("API_KEY", ""),
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        max_tokens=4096,
        enable_stats=False,
    )


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


async def main() -> int:
    parser = argparse.ArgumentParser(description="Production-path ablation smoke runner")
    parser.add_argument("--variant", default="full", choices=sorted(build_variants()))
    parser.add_argument("--sample", type=int, default=3)
    parser.add_argument("--chat-id", action="append", default=[])
    parser.add_argument("--run-root", type=Path, default=REPO / "experiments" / "production_ablation" / "runs")
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
    outcome = ConfirmedDecisionEvaluator().evaluate(result.decisions, selection)
    incomplete_reason = (
        "runner_error" if result.errors
        else "evaluation_error" if outcome.incomplete
        else "missing_or_invalid_evidence" if outcome.evidence_invalid > 0
        else ""
    )
    report = {
        "metadata": metadata,
        "selection": {"chat_ids": selection.chat_ids, "expected_count": selection.expected_count},
        "trace": result.trace.__dict__,
        "output_count": len(result.decisions),
        "metrics": outcome.__dict__ | {
            "precision": outcome.precision,
            "recall": outcome.recall,
            "f1": outcome.f1,
            "incomplete": outcome.incomplete or outcome.evidence_invalid > 0 or bool(result.errors),
            "incomplete_reason": incomplete_reason,
        },
        "runner_errors": result.errors,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    temp_path = run_dir / "report.json.tmp"
    temp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
    temp_path.replace(run_dir / "report.json")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=list))
    return 0 if not report["metrics"]["incomplete"] and not result.errors else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
