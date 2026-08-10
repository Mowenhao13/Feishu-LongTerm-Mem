"""
实验框架 — 统一入口 (run_ablation.py)

三种模式:
    --mode ablation              消融实验
    --mode threshold-scan        阈值扫描
    --mode claude_code           Claude Code 基线

用法:
    # 全消融
    uv run python experiments/ablation/run_ablation.py --mode ablation

    # 只跑特定变体
    uv run python experiments/ablation/run_ablation.py --mode ablation --variant no_memory_extractor

    # 阈值扫描
    uv run python experiments/ablation/run_ablation.py --mode threshold-scan \
        --param embedding_similarity --range "0.3,0.8,0.05"

    # Claude Code 基线（快速）
    uv run python experiments/ablation/run_ablation.py --mode claude_code --sample 3

    # 快速验证（--sample 限制 chat 数）
    uv run python experiments/ablation/run_ablation.py --mode ablation --sample 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import dotenv

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

dotenv.load_dotenv(_REPO / ".env")

# Disable Langfuse to avoid trace() errors in eval mode
os.environ.setdefault("LANGFUSE_ENABLE", "false")
os.environ.setdefault("LANGFUSE_ENABLED", "false")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ablation")

from src.extractors.memory_extractor import MemoryExtractor
from src.extractors.simple_llm_extractor import SimpleLLMExtractor
from src.extractors.project_types import ProjectDevelopmentContext, ProjectFileChange
from src.storage.entity_store import EntityStore
from src.model.llm_provider import LLMProvider

from experiments.ablation.variants import (
    VARIANT_REGISTRY,
    ALL_VARIANTS,
    VariantResult,
    PipelineDiagnostics,
)

# ── Paths ────────────────────────────────────────────────────────

ARGUSBOT_V3_DIR = str(_REPO / "eval_dataset" / "argusbot_v3")
EXPERIMENTS_DIR = _REPO / "experiments" / "ablation_experiments"
EXPERIMENTS_MD = _REPO / "EXPERIMENTS.md"
REPORT_PATH = EXPERIMENTS_DIR / "ablation_report.json"

LLM_EVAL_PROMPT = """你是一个决策提取评估助手。判断一条"提取决策"是否与对应的"期望决策"语义等价。

期望决策: {expected}
提取决策: {extracted}

请判断：
- 如果提取决策与期望决策表达了**相同或等价的技术决策**（只是表述不同可以接受），返回 true
- 如果提取决策与期望决策**不同**，返回 false
- 如果提取决策是期望决策的**细化或子决策**，返回 true
- 如果提取决策与期望决策**部分重叠**（有交叉但不是完全一样），返回 true，因为说明系统捕捉到了相关信号

只返回 JSON: {{"match": true/false, "reason": "简短理由"}}"""


# ── Dataset Loading ──────────────────────────────────────────────


def load_messages() -> List[dict]:
    """Load all messages from messages.jsonl."""
    path = Path(ARGUSBOT_V3_DIR) / "messages.jsonl"
    all_msgs: List[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msg = json.loads(line)
                from datetime import datetime as _dt
                ts = msg.get("timestamp", "")
                try:
                    msg["_ts"] = _dt.fromisoformat(ts).timestamp() if isinstance(ts, str) else float(ts)
                except (ValueError, TypeError):
                    msg["_ts"] = 0.0
                all_msgs.append(msg)
    all_msgs.sort(key=lambda m: m["_ts"])
    return all_msgs


def load_expected() -> List[dict]:
    """Load all ground truth decisions from expected.jsonl."""
    path = Path(ARGUSBOT_V3_DIR) / "expected.jsonl"
    entries: List[dict] = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


def build_episodes(messages: List[dict]) -> List[dict]:
    """Group messages by chat_id into episodes (simplified — no ChatEpisodeManager).

    Returns list of dicts: [{chat_id, id, full_text, message_count, n_expected}]
    """
    chat_groups: Dict[str, List[dict]] = defaultdict(list)
    for msg in messages:
        chat_groups[msg["chat_id"]].append(msg)

    episodes = []
    for chat_id, msgs in sorted(chat_groups.items()):
        full_lines = []
        for m in msgs:
            speaker = m.get("speaker", m.get("sender", "?"))
            text = m.get("msg", m.get("content", ""))
            full_lines.append(f"{speaker}: {text}")

        n_expected = sum(
            1 for m in msgs
            if m.get("expected_decision") is True
            or str(m.get("expected_decision", "")).lower() == "true"
        )

        episodes.append({
            "chat_id": chat_id,
            "id": f"ep_{chat_id}",
            "full_text": "\n".join(full_lines),
            "message_count": len(msgs),
            "n_expected": n_expected,
        })
    return episodes


# ── LLM / Extractor Init ─────────────────────────────────────────


def init_extractors() -> Tuple[LLMProvider, SimpleLLMExtractor, MemoryExtractor, EntityStore]:
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
    model = os.getenv("MODEL_NAME", "deepseek-chat")
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
        confidence_threshold=0.5,
    )
    entity_store = EntityStore()
    return provider, decision_extractor, memory_extractor, entity_store


def build_fake_project_context() -> ProjectDevelopmentContext:
    """Build a minimal project context (simulating files from ArgusBot)."""
    recent_py = ["src/adapter/lark_im.py", "src/core/engine.py",
                 "src/extractors/memory_extractor.py", "src/model/llm_provider.py"]
    ctx = ProjectDevelopmentContext(
        recent_changes=[
            ProjectFileChange(
                file_path=f, change_type="modified",
                content_hash=f"h{i}", extension=".py",
                language="Python",
                diff_summary="+50 lines; -15 lines",
                timestamp=time.time(), size_bytes=3000,
            ) for i, f in enumerate(recent_py)
        ],
        detected_at=time.time(),
    )
    ctx.linked_conversation_snippets = [
        "Related keywords: decision, extraction, memory, entity, lark"
    ]
    return ctx


# ── LLM Judge Evaluation ─────────────────────────────────────────


async def llm_judge_match(
    llm_provider: LLMProvider, expected: str, extracted: str,
) -> Tuple[bool, str]:
    """Use LLM to judge semantic equivalence."""
    if not expected or not extracted:
        return False, "empty text"
    prompt = LLM_EVAL_PROMPT.format(expected=expected, extracted=extracted)
    try:
        resp = await llm_provider.generate(
            prompt,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.strip())
        return bool(data.get("match", False)), data.get("reason", "")
    except Exception as e:
        logger.warning("[LLM Judge] Error: %s", e)
        return False, f"LLM error: {e}"


async def evaluate_variant(
    llm_provider: LLMProvider,
    episode_results: List[dict],
    gt_entries: List[dict],
    eval_cache: Dict[str, bool],
) -> Dict[str, Any]:
    """Evaluate variant results against ground truth using LLM judge.

    Returns:
        {precision, recall, f1, true_positives, false_positives, false_negatives, ...}
    """
    gt_by_chat = defaultdict(list)
    for gt in gt_entries:
        gt_by_chat[gt["chat_id"]].append(gt)

    total_tp = 0
    total_fp = 0
    total_fn = 0

    for cid, gts in gt_by_chat.items():
        gt_texts = [g.get("expected_summary", "") for g in gts if g.get("expected_summary")]

        ext_titles = []
        for r in episode_results:
            if r.get("chat_id") == cid and r.get("ok"):
                ext_titles.extend(r.get("decision_titles", []))

        gt_matched = [False] * len(gt_texts)
        ext_matched = [False] * len(ext_titles)

        for ei, ext_title in enumerate(ext_titles):
            if not ext_title:
                continue
            for gi, gt_text in enumerate(gt_texts):
                if gt_matched[gi]:
                    continue
                cache_key = f"{cid}:{gi}:{ei}"
                if cache_key in eval_cache:
                    match = eval_cache[cache_key]
                else:
                    match, _ = await llm_judge_match(llm_provider, gt_text, ext_title)
                    eval_cache[cache_key] = match
                if match:
                    ext_matched[ei] = True
                    gt_matched[gi] = True
                    break

        total_tp += sum(gt_matched)
        total_fp += sum(1 for m in ext_matched if not m)
        total_fn += sum(1 for m in gt_matched if not m)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)

    return {
        "true_positives": total_tp,
        "false_positives": total_fp,
        "false_negatives": total_fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


# ── EXPERIMENTS.md Writer ────────────────────────────────────────


def write_experiments_md(
    experiment_type: str,
    command: str,
    results: Any,
    notes: str = "",
) -> None:
    """Append a new experiment record to EXPERIMENTS.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"\n## {datetime.now().strftime('%Y-%m-%d')} — {experiment_type}",
        "",
        f"**命令**: `{command}`",
        f"**时间**: {now}",
        f"**环境**: {os.getenv('MODEL_NAME', 'deepseek-chat')}",
        "",
    ]

    if experiment_type == "消融实验":
        lines.append("### 结果")
        lines.append("")
        lines.append("| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |")
        lines.append("|------|-----------|--------|----|---------|-----------|")
        for variant_name, r in results.get("variants", {}).items():
            lines.append(
                f"| {variant_name} | {r.get('precision', 0):.2%} | "
                f"{r.get('recall', 0):.2%} | {r.get('f1', 0):.2%} | "
                f"{r.get('llm_calls', 0)} | {r.get('total_time', 0):.0f} |"
            )

    elif experiment_type == "阈值扫描":
        lines.append("### 结果")
        lines.append("")
        param = results.get("param", "?")
        scans = results.get("scans", [])
        lines.append(f"| {param} | P | R | F1 |")
        lines.append("|------|---|---|----|")
        for s in scans:
            lines.append(
                f"| {s['value']:.2f} | {s.get('precision', 0):.2%} | "
                f"{s.get('recall', 0):.2%} | {s.get('f1', 0):.2%} |"
            )
        lines.append("")
        if results.get("optimal"):
            opt = results["optimal"]
            lines.append(f"**最优**: {param}={opt['value']:.2f} 时 F1={opt['f1']:.2%}")
            lines.append(f"**当前设置**: {opt.get('current_value', '?')}")

    elif experiment_type == "Claude Code 基线":
        lines.append("### 结果")
        lines.append("")
        for k, v in results.items():
            lines.append(f"| {k} | {v} |")

    if notes:
        lines.append("")
        lines.append(f"**备注**: {notes}")

    lines.append("")
    lines.append("---")

    # Append to file
    if Path(EXPERIMENTS_MD).exists():
        with open(EXPERIMENTS_MD, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        with open(EXPERIMENTS_MD, "w", encoding="utf-8") as f:
            f.write("# 实验记录\n\n")
            f.write("\n".join(lines) + "\n")

    logger.info("[EXPERIMENTS.md] Record appended")


# ── Ablation Mode ────────────────────────────────────────────────


async def run_ablation_mode(
    variants: List[str],
    episodes: List[dict],
    gt_entries: List[dict],
    llm_provider: LLMProvider,
    sample: int = 0,
) -> Dict[str, Any]:
    """Run all specified variants and collect results."""
    _, decision_extractor, memory_extractor, entity_store = init_extractors()
    project_ctx = build_fake_project_context()

    if sample > 0:
        episodes = episodes[:sample]

    results: Dict[str, Any] = {
        "method": "llm_judge",
        "dataset": {
            "episodes": len(episodes),
            "expected_decisions": len(gt_entries),
        },
        "variants": {},
        "diagnostics": {},
    }

    for variant_name in variants:
        logger.info("=" * 60)
        logger.info("[Variant] %s — %s", variant_name,
                     VARIANT_REGISTRY[variant_name]["description"])
        logger.info("=" * 60)

        # Fresh entity store per variant
        fresh_entity_store = EntityStore()
        ev_fn = VARIANT_REGISTRY[variant_name]["fn"]

        all_diags: List[Dict] = []
        all_episode_results = []
        t_start = time.time()

        for ep in episodes:
            content = ep["full_text"]
            if not content or len(content) < 50:
                continue

            result, diag = await ev_fn(
                content,
                episode_id=ep["id"],
                chat_id=ep["chat_id"],
                memory_extractor=memory_extractor,
                decision_extractor=decision_extractor,
                entity_store=fresh_entity_store,
                project_ctx=project_ctx,
            )

            episode_result = {
                "chat_id": ep["chat_id"],
                "episode_id": ep["id"],
                "message_count": ep["message_count"],
                "n_expected": ep["n_expected"],
                "ok": result is not None,
                "decision_count": len(result) if result else 0,
                "decision_titles": [
                    d.get("title", d.get("summary", ""))
                    for d in (result or [])
                ],
                "diagnostics": diag.to_dict(),
            }
            all_episode_results.append(episode_result)
            all_diags.append(diag.to_dict())

        total_time = time.time() - t_start

        # Evaluate
        eval_cache: Dict[str, bool] = {}
        metrics = await evaluate_variant(
            llm_provider, all_episode_results, gt_entries, eval_cache,
        )

        variant_config = VARIANT_REGISTRY[variant_name]
        llm_calls = variant_config["llm_calls"] * len(episodes)

        results["variants"][variant_name] = {
            **metrics,
            "llm_calls": llm_calls,
            "total_time": round(total_time, 1),
            "config": variant_config["description"],
        }
        results["diagnostics"][variant_name] = {
            "n_episodes": len([d for d in all_diags if d.get("total_latency_sec", 0) > 0]),
            "avg_stage1_latency": _avg_diag(all_diags, "stage1", "latency_sec"),
            "avg_stage2_latency": _avg_diag(all_diags, "stage2", "latency_sec"),
            "avg_total_latency": _avg_diag(all_diags, "total_latency_sec"),
            "avg_entities_extracted": _avg_diag(all_diags, "stage1", "extracted_entities"),
        }

        # Print variant result
        logger.info("")
        logger.info("Variant %s result:", variant_name)
        logger.info("  Precision=%.2f%%  Recall=%.2f%%  F1=%.2f%%",
                     metrics["precision"] * 100, metrics["recall"] * 100,
                     metrics["f1"] * 100)
        logger.info("  TP=%d  FP=%d  FN=%d  LLM_calls=%d  time=%.0fs",
                     metrics["true_positives"], metrics["false_positives"],
                     metrics["false_negatives"], llm_calls, total_time)
        logger.info("")

    # Compute contribution scores (diff vs full)
    if "full" in results["variants"]:
        baseline = results["variants"]["full"]
        contributions: Dict[str, Dict[str, float]] = {}
        for vn in variants:
            if vn == "full":
                continue
            v = results["variants"].get(vn, {})
            contributions[vn] = {
                "f1_delta": round(baseline["f1"] - v.get("f1", 0), 4),
                "recall_delta": round(baseline["recall"] - v.get("recall", 0), 4),
                "precision_delta": round(baseline["precision"] - v.get("precision", 0), 4),
            }
        results["contributions"] = contributions

    return results


def _avg_diag(diags: List[Dict], *keys: str) -> float:
    vals = []
    for d in diags:
        v = d
        for k in keys:
            v = v.get(k, {}) if isinstance(v, dict) else 0
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return round(sum(vals) / len(vals), 2) if vals else 0.0


# ── Threshold Scan Mode ──────────────────────────────────────────


async def run_threshold_scan(
    param: str,
    param_range: Tuple[float, float, float],
    episodes: List[dict],
    gt_entries: List[dict],
    llm_provider: LLMProvider,
    sample: int = 0,
) -> Dict[str, Any]:
    """Run ablation across a parameter range and track F1."""
    from experiments.ablation import threshold_scanner
    return await threshold_scanner.run_scan(
        param=param,
        param_range=param_range,
        episodes=episodes,
        gt_entries=gt_entries,
        llm_provider=llm_provider,
        sample=sample,
    )


# ── Claude Code Mode ─────────────────────────────────────────────


async def run_claude_code_mode(
    episodes: List[dict],
    gt_entries: List[dict],
    claude_dir: str,
    llm_provider: LLMProvider,
    sample: int = 0,
) -> Dict[str, Any]:
    """Run Claude Code baseline."""
    from experiments.ablation.claude_code_runner import run_claude_code_baseline
    return await run_claude_code_baseline(
        episodes=episodes,
        gt_entries=gt_entries,
        claude_dir=claude_dir,
        llm_provider=llm_provider,
        sample=sample,
    )


# ── CLI ──────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ablation / threshold-scan / Claude-Code 实验框架",
    )
    parser.add_argument(
        "--mode", choices=["ablation", "threshold-scan", "claude_code", "agentic_baseline"],
        required=True,
        help="实验模式",
    )

    # Common
    parser.add_argument(
        "--sample", type=int, default=0,
        help="只处理前 N 个 episode (默认全部)",
    )

    # Ablation mode
    parser.add_argument(
        "--variant", choices=ALL_VARIANTS, default=None,
        help="仅跑单个变体",
    )

    # Threshold-scan mode
    parser.add_argument(
        "--param",
        choices=["embedding_similarity", "initial_candidates",
                 "confidence_threshold", "episode_semantic_threshold"],
        default="embedding_similarity",
        help="扫描参数",
    )
    parser.add_argument(
        "--range", type=str, default="0.3,0.8,0.05",
        help="start,end,step (e.g. 0.3,0.8,0.05)",
    )

    # Claude Code mode
    parser.add_argument(
        "--claude-dir", type=str, default="",
        help="ArgusBot 项目目录 (Claude Code 用)",
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    api_key = os.getenv("API_KEY", "")
    if not api_key:
        logger.error("API_KEY not set. Aborting.")
        sys.exit(1)

    # Load data
    messages = load_messages()
    episodes = build_episodes(messages)
    gt_entries = load_expected()

    logger.info("Loaded %d messages → %d episodes, %d expected decisions",
                 len(messages), len(episodes), len(gt_entries))

    provider, _, _, _ = init_extractors()

    report: Dict[str, Any] = {}

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode == "ablation":
        variants = ALL_VARIANTS if args.variant is None else [args.variant]
        report = await run_ablation_mode(
            variants, episodes, gt_entries, provider,
            sample=args.sample,
        )
        write_experiments_md(
            "消融实验",
            " ".join(sys.argv),
            report,
            notes="",
        )

    elif args.mode == "threshold-scan":
        start, end, step = [float(x) for x in args.range.split(",")]
        report = await run_threshold_scan(
            args.param, (start, end, step),
            episodes, gt_entries, provider,
            sample=args.sample,
        )
        write_experiments_md(
            "阈值扫描",
            " ".join(sys.argv),
            report,
            notes="",
        )

    elif args.mode == "claude_code":
        claude_dir = args.claude_dir or str(_REPO / "ref" / "ArgusBot")
        report = await run_claude_code_mode(
            episodes, gt_entries, claude_dir, provider,
            sample=args.sample,
        )
        write_experiments_md(
            "Claude Code 基线",
            " ".join(sys.argv),
            report,
            notes="",
        )

    elif args.mode == "agentic_baseline":
        from experiments.ablation.agentic_baseline import run_agentic_baseline
        report = await run_agentic_baseline(
            provider, episodes, gt_entries, messages,
            sample=args.sample,
        )
        write_experiments_md(
            "Agentic Baseline (3-tier)",
            " ".join(sys.argv),
            report,
            notes="Tier1=single-shot, Tier2=structured-4step, Tier3=agentic-tool-loop",
        )

    # Save report
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("Report saved: %s", REPORT_PATH)


if __name__ == "__main__":
    asyncio.run(main())