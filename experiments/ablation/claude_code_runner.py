"""
实验框架 — Claude Code 基线运行器 (claude_code_runner.py)

对每个 chat 的完整对话，启动一个独立的 Claude Code 进程，
输入该 chat 的全量消息 + 项目上下文，要求输出结构化决策 JSON。

使用与 ablations/run_ablation.py 相同的 LLM 评估流水线做对比。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("claude_code_runner")

from src.model.llm_provider import LLMProvider
from experiments.ablation.run_ablation import evaluate_variant

# ── Prompt templates ─────────────────────────────────────────────


SYSTEM_PROMPT = """你是一个技术决策提取助手。你的任务是从群聊对话中提取所有已做出的技术决策和具体建议。

请严格按以下 JSON 格式输出，不要包含无关文字：

{
  "decisions": [
    {
      "title": "决策标题（一句话概括，15-40字）",
      "summary": "决策摘要（引用原文措辞风格）",
      "topic": "所属主题",
      "status": "decided/pending",
      "impact_level": "major/minor",
      "is_suggestion": false,
      "proposer": "提议人姓名",
      "executor": "执行人姓名（如果有）"
    }
  ],
  "entities": [
    {"name": "实体名", "entity_type": "Person/Technology/Project/Service/Concept", "confidence": 0.9}
  ],
  "facts": [
    {"content": "事实陈述", "confidence": 0.8}
  ]
}

注意：
- 只输出 JSON，不要任何额外文字、markdown 标记、代码块包装
- 每条 decision 必须包含 topic 字段（不要默认 "general"）
- 如果没有任何决策，输出 {"decisions": [], "entities": [], "facts": []}
- 决策的定义：明确拍板、达成共识的事项。建议（is_suggestion=true）是尚未确认的具体方案
"""


def _build_input_data(messages: List[dict]) -> dict:
    """Build input JSON for Claude Code from a list of raw messages."""
    conversation = []
    for m in messages:
        speaker = m.get("speaker", m.get("sender", "?"))
        role = m.get("role", "")
        msg = m.get("msg", m.get("content", ""))
        timestamp = m.get("timestamp", "")
        line = f"[{timestamp}] {speaker}"
        if role:
            line += f" ({role})"
        line += f": {msg}"
        conversation.append(line)

    return {
        "task": "从以下群聊对话中提取所有技术决策和建议。",
        "format_instructions": "输出 JSON，只包含 decisions、entities、facts 三个数组。不要代码块包装。",
        "conversation": "\n".join(conversation[-200:]),  # Limit to last 200 lines
    }


def _parse_claude_output(output_path: str) -> Optional[Dict[str, Any]]:
    """Parse Claude Code's output JSON from the output file.

    Handles:
    - Pure JSON
    - Markdown code block wrapping
    - Claude "thinking" or "summary" text before/after JSON
    """
    if not os.path.exists(output_path):
        logger.warning("Claude output file not found: %s", output_path)
        return None

    with open(output_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    if not raw:
        return None

    # Try direct JSON parse first
    for attempt in [raw, _extract_json_block(raw), _extract_braces(raw)]:
        if attempt:
            try:
                data = json.loads(attempt)
                if isinstance(data, dict) and ("decisions" in data or "has_decisions" in data):
                    return data
                # Wrap non-standard formats
                if isinstance(data, dict):
                    return _normalize_decision_format(data)
            except json.JSONDecodeError:
                continue

    # Last resort: search for list/array in raw text
    import re
    array_match = re.search(r'\[\s*\{.*"title".*\}\s*\]', raw, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group())
            return {"decisions": data}
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse Claude output: %.200s...", raw[:200])
    return None


def _extract_json_block(text: str) -> Optional[str]:
    """Extract JSON from markdown code block."""
    import re
    # ```json ... ``` or ``` ... ```
    for pattern in [r'```(?:json)?\s*\n?(.*?)\n?```', r'```(?:json)?\s*(.*?)\s*```']:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


def _extract_braces(text: str) -> Optional[str]:
    """Extract top-level JSON object from text (find outermost { ... })."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _normalize_decision_format(data: dict) -> Dict[str, Any]:
    """Normalize various Claude output formats to our standard."""
    decisions = data.get("decisions", [])
    if not decisions and "decision" in data:
        decisions = [data["decision"]]
    if not decisions and "decisions_identified" in data:
        decisions = data["decisions_identified"]

    # Ensure each decision has required fields
    normalized = []
    for d in decisions:
        if isinstance(d, str):
            normalized.append({
                "title": d,
                "summary": d,
                "topic": "general",
                "status": "decided",
                "impact_level": "minor",
                "is_suggestion": False,
            })
        else:
            normalized.append({
                "title": d.get("title", d.get("summary", "")),
                "summary": d.get("summary", d.get("title", "")),
                "topic": (d.get("topic") or d.get("topic_id", "") or "general"),
                "status": d.get("status", "decided"),
                "impact_level": d.get("impact_level", "minor"),
                "is_suggestion": d.get("is_suggestion", False),
                "proposer": d.get("proposer", ""),
                "executor": d.get("executor", ""),
            })

    return {
        "decisions": normalized,
        "entities": data.get("entities", []),
        "facts": data.get("facts", []),
    }


# ── Single chat runner ───────────────────────────────────────────


def run_claude_code_chat(
    messages: List[dict],
    chat_id: str,
    claude_dir: str,
) -> Optional[Dict[str, Any]]:
    """Run Claude Code on a single chat's messages.

    Args:
        messages: List of raw message dicts for one chat
        chat_id: Chat identifier (for logging)
        claude_dir: ArgusBot project directory

    Returns:
        Parsed output dict, or None on failure
    """
    input_data = _build_input_data(messages)
    conversation_text = input_data.get("conversation", "")

    prompt = (
        "从以下群聊对话中提取所有技术决策和建议。\n"
        "输出 JSON 格式：\n"
        '{"decisions":[{"title":"...","summary":"...","topic":"...",'
        '"status":"decided/pending","impact_level":"major/minor",'
        '"is_suggestion":false,"proposer":"...","executor":"..."}],'
        '"entities":[{"name":"...","entity_type":"Person|Technology|Project|Service|Concept","confidence":0.9}],'
        '"facts":[{"content":"...","confidence":0.8}]}\n'
        "只输出 JSON，不要任何额外文字，不要代码块标记。\n"
        "如果没有决策，输出 {\"decisions\":[],\"entities\":[],\"facts\":[]}\n\n"
        "对话内容:\n" + conversation_text
    )

    try:
        logger.info("[Claude] Chat=%s msgs=%d running...", chat_id[:12], len(messages))

        model = os.getenv("CLAUDE_MODEL", os.getenv("MODEL_NAME", "sonnet"))
        claude_cmd = os.getenv("CLAUDE_CMD", "claude.cmd")

        result = subprocess.run(
            [claude_cmd, "--print", "--model", model],
            input=prompt,
            capture_output=True, text=True, timeout=600,
            cwd=claude_dir,
        )

        if result.returncode != 0:
            logger.warning("[Claude] Chat=%s stderr: %.200s",
                           chat_id[:12], result.stderr[:200])

        # Parse output from stdout
        stdout = result.stdout.strip()
        if not stdout:
            logger.warning("[Claude] Chat=%s → empty output", chat_id[:12])
            return None

        # Try JSON extraction
        json_str = (
            _extract_json_block(stdout)
            or _extract_braces(stdout)
            or stdout
        )
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("[Claude] Chat=%s → unparseable output: %.200s",
                           chat_id[:12], stdout[:200])
            return None

        claude_output = _normalize_decision_format(data)
        n_decisions = len(claude_output.get("decisions", []))
        logger.info("[Claude] Chat=%s → %d decisions, %d entities",
                     chat_id[:12], n_decisions, len(claude_output.get("entities", [])))
        return claude_output

    except subprocess.TimeoutExpired:
        logger.warning("[Claude] Chat=%s timed out (10m)", chat_id[:12])
        return None
    except Exception as e:
        logger.error("[Claude] Chat=%s error: %s", chat_id[:12], e)
        return None


# ── Full baseline run ────────────────────────────────────────────


async def run_claude_code_baseline(
    episodes: List[dict],
    gt_entries: List[dict],
    claude_dir: str,
    llm_provider: LLMProvider,
    sample: int = 0,
) -> Dict[str, Any]:
    """Run Claude Code baseline on all episodes.

    This uses our message loading to build per-chat inputs,
    spawns Claude Code subprocesses, parses outputs,
    then evaluates against ground truth.

    Returns:
        {precision, recall, f1, decision_count, total_time, ...}
    """
    claude_dir_path = Path(claude_dir)
    if not claude_dir_path.exists():
        logger.warning("Claude project dir not found: %s", claude_dir_path)
        # Fall back to repo root
        from experiments.ablation.run_ablation import _REPO
        claude_dir = str(_REPO / "ref" / "ArgusBot")

    if sample > 0:
        episodes = episodes[:sample]

    logger.info("=" * 60)
    logger.info("Claude Code Baseline")
    logger.info("Project dir: %s", claude_dir)
    logger.info("Episodes: %d | GT: %d", len(episodes), len(gt_entries))
    logger.info("=" * 60)

    # Reload raw messages per chat
    from experiments.ablation.run_ablation import load_messages
    all_msgs = load_messages()
    chat_messages: Dict[str, List[dict]] = defaultdict(list)
    for m in all_msgs:
        chat_messages[m["chat_id"]].append(m)

    results = []
    t_start = time.time()
    failed = 0

    for ep in episodes:
        chat_id = ep["chat_id"]
        msgs = chat_messages.get(chat_id, [])

        claude_output = await asyncio.to_thread(
            run_claude_code_chat, msgs, chat_id, claude_dir,
        )

        if claude_output:
            normalized = _normalize_decision_format(claude_output)
            decisions = normalized.get("decisions", [])
            results.append({
                "chat_id": chat_id,
                "ok": bool(decisions),
                "decision_count": len(decisions),
                "decision_titles": [
                    d.get("title", d.get("summary", "")) for d in decisions
                ],
            })
        else:
            failed += 1
            results.append({
                "chat_id": chat_id,
                "ok": False,
                "decision_count": 0,
                "decision_titles": [],
            })

    total_time = time.time() - t_start

    logger.info("")
    logger.info("Claude Code processing complete: %d ok, %d failed, %.0fs",
                 len(results) - failed, failed, total_time)

    # Evaluate against ground truth
    eval_cache: Dict[str, bool] = {}
    metrics = await evaluate_variant(
        llm_provider, results, gt_entries, eval_cache,
    )

    # Additional stats
    n_decisions = sum(r["decision_count"] for r in results)
    avg_time_per_chat = total_time / len(episodes) if episodes else 0

    report = {
        **metrics,
        "total_time": round(total_time, 1),
        "avg_time_per_chat": round(avg_time_per_chat, 1),
        "n_claude_calls": len(episodes),
        "all_decisions_count": n_decisions,
        "failed_chats": failed,
        "model": os.getenv("MODEL_NAME", "deepseek-chat"),
        "claude_project_dir": claude_dir,
    }

    logger.info("")
    logger.info("=" * 60)
    logger.info("Claude Code Baseline Result")
    logger.info("=" * 60)
    logger.info("Precision=%.2f%%  Recall=%.2f%%  F1=%.2f%%",
                 metrics["precision"] * 100, metrics["recall"] * 100,
                 metrics["f1"] * 100)
    logger.info("TP=%d  FP=%d  FN=%d", metrics["true_positives"],
                 metrics["false_positives"], metrics["false_negatives"])
    logger.info("Decisions=%d  Chats=%d  Time=%.0fs",
                 n_decisions, len(episodes), total_time)
    logger.info("=" * 60)

    return report