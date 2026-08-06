"""
实验框架 — 阈值扫描引擎 (threshold_scanner.py)

对关键超参数做步进扫描，跑简化消融 (full + single_stage_direct) 并记录 F1 曲线。

用法:
    uv run python experiments/ablation/run_ablation.py --mode threshold-scan \
        --param embedding_similarity --range "0.3,0.8,0.05"
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("threshold_scanner")

from src.extractors.memory_extractor import MemoryExtractor
from src.extractors.simple_llm_extractor import SimpleLLMExtractor
from src.extractors.project_types import ProjectDevelopmentContext, ProjectFileChange
from src.storage.entity_store import EntityStore
from src.model.llm_provider import LLMProvider
from src.config import ModelConfig

from experiments.ablation.variants import (
    run_full,
    run_single_stage_direct,
    PipelineDiagnostics,
)

# ── Parameter overrides ──────────────────────────────────────────


def _apply_param(param: str, value: float) -> None:
    """Apply a parameter value to the global config/environment.

    Returns nothing; modifies global state via env vars / ModelConfig class attrs.
    """
    if param == "embedding_similarity":
        # This is used in engine._find_similar_decision as a threshold
        # We store it temporarily via env var (the eval pipeline reads it)
        os.environ["HYPERMEM_EMB_THRESHOLD"] = str(value)

    elif param == "initial_candidates":
        ModelConfig.retrieval_config["initial_candidates"] = int(value)

    elif param == "confidence_threshold":
        # MemoryExtractor's confidence_threshold
        os.environ["HYPERMEM_CONFIDENCE_THRESHOLD"] = str(value)

    elif param == "episode_semantic_threshold":
        os.environ["EPISODE_SEMANTIC_THRESHOLD"] = str(value)


def _get_param_current(param: str) -> float:
    """Get the current (default) value of a parameter."""
    defaults = {
        "embedding_similarity": 0.5,
        "initial_candidates": 100.0,
        "confidence_threshold": 0.5,
        "episode_semantic_threshold": 0.5,
    }
    return defaults.get(param, 0.5)


# ── Quick eval for a single parameter value ──────────────────────


async def _quick_eval(
    variant_fn: Any,
    episodes: List[dict],
    gt_entries: List[dict],
    llm_provider: LLMProvider,
) -> Dict[str, Any]:
    """Run variant on episodes and evaluate with LLM judge.

    Uses same LLM_EVAL_PROMPT as run_ablation.py.
    """
    from experiments.ablation.run_ablation import evaluate_variant
    from experiments.ablation.variants import VARIANT_REGISTRY
    import json

    entity_store = EntityStore()
    project_ctx = _build_minimal_project_context()

    _, decision_extractor, memory_extractor, _ = init_quick_extractors()

    all_results = []
    t_start = time.time()

    for ep in episodes:
        content = ep["full_text"]
        if not content or len(content) < 50:
            continue

        result, diag = await variant_fn(
            content,
            episode_id=ep["id"],
            chat_id=ep["chat_id"],
            memory_extractor=memory_extractor,
            decision_extractor=decision_extractor,
            entity_store=entity_store,
            project_ctx=project_ctx,
        )

        all_results.append({
            "chat_id": ep["chat_id"],
            "ok": result is not None,
            "decision_count": len(result) if result else 0,
            "decision_titles": [
                d.get("title", d.get("summary", "")) for d in (result or [])
            ],
        })

    total_time = time.time() - t_start

    eval_cache: Dict[str, bool] = {}
    metrics = await evaluate_variant(
        llm_provider, all_results, gt_entries, eval_cache,
    )

    return {
        **metrics,
        "total_time": round(total_time, 1),
        "llm_calls": VARIANT_REGISTRY.get("full", {}).get("llm_calls", 2) * len(episodes),
    }


def init_quick_extractors():
    """Initialize extractors for quick eval."""
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
    model = os.getenv("MODEL_NAME", "deepseek-chat")

    # Apply confidence threshold override
    confidence_threshold = float(os.getenv("HYPERMEM_CONFIDENCE_THRESHOLD", "0.5"))

    provider = LLMProvider(
        provider_type="openai",
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_tokens=4096,
        enable_stats=False,
    )
    decision_extractor = SimpleLLMExtractor(provider)
    memory_extractor = MemoryExtractor(
        llm_provider=provider,
        confidence_threshold=confidence_threshold,
    )
    return provider, decision_extractor, memory_extractor, EntityStore()


def _build_minimal_project_context() -> ProjectDevelopmentContext:
    return ProjectDevelopmentContext(
        recent_changes=[
            ProjectFileChange(
                file_path="src/core/engine.py", change_type="modified",
                content_hash="h0", extension=".py", language="Python",
                diff_summary="+50 lines; -15 lines",
                timestamp=time.time(), size_bytes=3000,
            ),
        ],
        detected_at=time.time(),
    )


# ── Main scan function ───────────────────────────────────────────


async def run_scan(
    param: str,
    param_range: Tuple[float, float, float],
    episodes: List[dict],
    gt_entries: List[dict],
    llm_provider: LLMProvider,
    sample: int = 0,
) -> Dict[str, Any]:
    """Run threshold scan for a single parameter.

    Args:
        param: parameter name
        param_range: (start, end, step)
        episodes: list of episode dicts
        gt_entries: ground truth list
        llm_provider: LLMProvider for evaluation
        sample: limit episodes

    Returns:
        {param, current_value, scans: [{value, precision, recall, f1, llm_calls, total_time}],
         optimal: {value, f1}}
    """
    start, end, step = param_range
    if sample > 0:
        episodes = episodes[:sample]

    current_value = _get_param_current(param)

    logger.info("=" * 60)
    logger.info("Threshold scan: %s (%.2f ~ %.2f, step=%.2f)", param, start, end, step)
    logger.info("Current value: %.2f  |  Episodes: %d  |  GT: %d",
                 current_value, len(episodes), len(gt_entries))
    logger.info("=" * 60)

    scans = []
    n_steps = int((end - start) / step) + 1

    for i in range(n_steps):
        value = round(start + i * step, 2)
        if value > end:
            break

        _apply_param(param, value)
        logger.info("[Scan %.2f/%.2f] %s = %.2f", value, end, param, value)

        try:
            metrics = await _quick_eval(
                run_full, episodes, gt_entries, llm_provider,
            )
            logger.info("  P=%.2f%%  R=%.2f%%  F1=%.2f%%  time=%.0fs",
                         metrics["precision"] * 100,
                         metrics["recall"] * 100,
                         metrics["f1"] * 100,
                         metrics["total_time"])

            scans.append({
                "value": value,
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"],
                "llm_calls": metrics["llm_calls"],
                "total_time": metrics["total_time"],
            })
        except Exception as e:
            logger.error("[Scan %.2f] FAILED: %s", value, e)
            scans.append({
                "value": value,
                "error": str(e),
            })

    # Find optimal
    valid_scans = [s for s in scans if "f1" in s]
    optimal = max(valid_scans, key=lambda s: s["f1"]) if valid_scans else {}

    result = {
        "param": param,
        "current_value": current_value,
        "scans": scans,
        "optimal": {
            "value": optimal.get("value"),
            "f1": round(optimal.get("f1", 0), 4),
            "precision": round(optimal.get("precision", 0), 4),
            "recall": round(optimal.get("recall", 0), 4),
        } if optimal else {},
    }

    # Print scan summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Scan complete: %s", param)
    logger.info("Optimal: %.2f → F1=%.2f%% (P=%.2f%% R=%.2f%%)",
                 optimal.get("value", 0),
                 optimal.get("f1", 0) * 100,
                 optimal.get("precision", 0) * 100,
                 optimal.get("recall", 0) * 100)
    logger.info("Current: %.2f → F1=%.2f%%",
                 current_value,
                 next((s["f1"] for s in valid_scans if abs(s["value"] - current_value) < 0.01),
                      0) * 100 if valid_scans else 0)
    logger.info("=" * 60)

    return result