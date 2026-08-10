"""
Agentic baseline evaluation — Three-tier comparison for decision extraction.

Tier 1: Single-shot — one prompt, entire chat → JSON decisions
Tier 2: Structured — 4-step chain-of-thought (Scan → Extract → Classify → Validate)
Tier 3: Agentic — tool-use loop with search, evidence check, dedup

All tiers use the same LLM provider (deepseek-local) for fair comparison.
Evaluated by the same evaluate_variant() + LLM judge as the ablation framework.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("agentic_baseline")


# ── Tool implementations (Tier 3) ──────────────────────────────────


class ChatTools:
    """Pure-Python tools that operate on a chat's message list."""

    def __init__(self, messages: List[dict]) -> None:
        self._messages = messages
        self._by_id: Dict[str, dict] = {m.get("msg_id", ""): m for m in messages}
        self._extracted: List[dict] = []

    def search_messages(self, keyword: str) -> List[dict]:
        """Search for messages containing a keyword."""
        results = []
        for m in self._messages:
            text = m.get("msg", "")
            if keyword.lower() in text.lower():
                results.append({
                    "msg_id": m.get("msg_id", ""),
                    "speaker": m.get("speaker", ""),
                    "msg": text[:200],
                })
        return results[:20]  # cap at 20

    def get_speaker_messages(self, speaker: str) -> List[dict]:
        """Get all messages from a specific speaker."""
        results = []
        for m in self._messages:
            if m.get("speaker", "").lower() == speaker.lower():
                results.append({
                    "msg_id": m.get("msg_id", ""),
                    "msg": m.get("msg", "")[:200],
                })
        return results[:30]

    def check_evidence(self, msg_id: str, quote: str) -> dict:
        """Verify that a quote exists in the cited message."""
        msg = self._by_id.get(msg_id)
        if msg is None:
            return {"valid": False, "reason": f"msg_id '{msg_id}' not found"}
        text = msg.get("msg", "")
        if quote in text:
            return {"valid": True, "full_message": text[:300]}
        # Fuzzy: check if >60% chars overlap
        overlap = sum(1 for c in quote if c in text) / max(len(quote), 1)
        return {
            "valid": overlap > 0.6,
            "reason": "exact" if quote in text else f"fuzzy_overlap={overlap:.2f}",
            "full_message": text[:300],
        }

    def list_existing_decisions(self) -> List[dict]:
        """Return decisions already extracted in this session."""
        return [{"title": d.get("title", ""), "topic": d.get("topic", "")} for d in self._extracted]

    def submit_decisions(self, decisions: List[dict]) -> dict:
        """Submit final decisions. Terminates the loop."""
        self._extracted = decisions
        return {"submitted": len(decisions)}

    def execute(self, tool_name: str, args: dict) -> Any:
        """Dispatch a tool call."""
        dispatch = {
            "search_messages": lambda: self.search_messages(args.get("keyword", "")),
            "get_speaker_messages": lambda: self.get_speaker_messages(args.get("speaker", "")),
            "check_evidence": lambda: self.check_evidence(args.get("msg_id", ""), args.get("quote", "")),
            "list_existing_decisions": lambda: self.list_existing_decisions(),
            "submit_decisions": lambda: self.submit_decisions(args.get("decisions", [])),
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            return {"error": f"unknown tool: {tool_name}"}
        return fn()

    @property
    def decisions(self) -> List[dict]:
        return list(self._extracted)


TOOLS_SCHEMA = [
    {
        "name": "search_messages",
        "description": "搜索聊天中包含关键词的消息",
        "parameters": {"keyword": "搜索关键词"},
    },
    {
        "name": "get_speaker_messages",
        "description": "获取某个发言人的所有消息",
        "parameters": {"speaker": "发言人姓名"},
    },
    {
        "name": "check_evidence",
        "description": "验证引用是否存在于指定消息中",
        "parameters": {"msg_id": "消息ID", "quote": "引用文本"},
    },
    {
        "name": "list_existing_decisions",
        "description": "列出本轮已提取的决策（用于去重）",
        "parameters": {},
    },
    {
        "name": "submit_decisions",
        "description": "提交最终决策列表，结束提取流程",
        "parameters": {"decisions": "[{title, summary, topic, status, impact_level, is_suggestion, decision_kind, source_message_ids, evidence_quote, proposer, executor}]"},
    },
]


# ── Prompt templates ───────────────────────────────────────────────


TIER1_PROMPT = """你是一个技术决策提取助手。从以下群聊对话中提取所有已做出的技术决策和建议。

只输出 JSON，不要任何额外文字：
{{"decisions": [{{"title": "...", "summary": "...", "topic": "...", "status": "decided/pending", "impact_level": "major/minor", "is_suggestion": false, "proposer": "...", "executor": "..."}}], "reasoning": "..."}}

如果没有决策：{{"decisions": [], "reasoning": "无决策"}}

对话内容:
{conversation}"""


TIER2_PROMPT = """你是一个技术决策提取专家。请按以下 4 个步骤分析对话，逐步推理后输出结果。

## 对话内容
{conversation}

---

## 请按以下步骤分析（在 JSON 的对应字段中输出每步结果）：

### Step 1: SCAN — 识别发言人、主题和潜在决策点
扫描对话，列出参与者、讨论主题、以及可能包含决策的消息位置。

### Step 2: EXTRACT — 提取候选决策及证据
对每个候选决策，找到精确的源消息ID和证据引用。
evidence_quote 必须是源消息中的连续精确子串。

### Step 3: CLASSIFY — 分类决策类型
对每个候选应用 decision_kind 分类：
- choice: 明确的技术/方案选择
- conditional_choice: 带条件/范围/时间线的选择
- execution_commitment: 具体的执行承诺（"我来负责", "明天开始搭建"）
- policy_constraint: 团队采纳的规则/标准/合规要求
- suggestion: 尚未确认的建议 → 设置 is_suggestion=true
- status: 进度更新 → 不要提取
- discussion: 讨论/头脑风暴 → 不要提取

### Step 4: VALIDATE — 自检
检查每条决策：证据是否支持？是真正的承诺还是只是讨论？去掉不合格的。

## 输出格式（严格 JSON）
{{"scan": {{"speakers": [...], "topics": [...], "decision_points": [...]}}, "candidates": [...], "validated_decisions": [{{"title": "...", "summary": "...", "topic": "...", "status": "decided", "impact_level": "major/minor", "is_suggestion": false, "decision_kind": "choice", "proposer": "...", "executor": "...", "source_message_ids": ["m013"], "evidence_quote": "..."}}], "reasoning": "..."}}"""


TIER3_SYSTEM = """你是一个技术决策提取 Agent。你可以使用以下工具来分析群聊对话并提取决策：

可用工具：
{tools_desc}

工作流程：
1. 先用 search_messages 搜索关键词（如"决定"、"确认"、"采用"、"同意"）找到决策点
2. 用 get_speaker_messages 查看关键发言人的完整发言
3. 对每个候选决策，用 check_evidence 验证证据引用是否准确
4. 用 list_existing_decisions 检查是否有重复
5. 确认所有决策后，用 submit_decisions 提交最终结果

decision_kind 分类：choice | conditional_choice | execution_commitment | policy_constraint | suggestion

每次响应请输出 JSON：
- 如果要调用工具：{{"tool": "工具名", "args": {{...}}, "thought": "推理过程"}}
- 如果要提交结果：{{"tool": "submit_decisions", "args": {{"decisions": [...]}}}}

对话内容：
{conversation}"""


# ── Tier 1: Single-shot ────────────────────────────────────────────


async def run_tier1_single_shot(
    provider: Any,
    messages: List[dict],
    chat_id: str,
) -> dict:
    """Tier 1: Single prompt, entire chat → JSON decisions."""
    conversation = _format_conversation(messages)
    prompt = TIER1_PROMPT.format(conversation=conversation)

    t0 = time.time()
    try:
        resp = await provider.generate(prompt, response_format={"type": "json_object"})
        data = _parse_json_response(resp)
        decisions = data.get("decisions", []) if data else []
        return {
            "chat_id": chat_id,
            "ok": bool(decisions),
            "decision_count": len(decisions),
            "decision_titles": [d.get("title", d.get("summary", "")) for d in decisions],
            "llm_calls": 1,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "tier": "tier1_single_shot",
        }
    except Exception as e:
        logger.warning("[Tier1] chat=%s error: %s", chat_id[:12], e)
        return {
            "chat_id": chat_id, "ok": False, "decision_count": 0,
            "decision_titles": [], "llm_calls": 1,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "tier": "tier1_single_shot",
        }


# ── Tier 2: Structured 4-step ─────────────────────────────────────


async def run_tier2_structured(
    provider: Any,
    messages: List[dict],
    chat_id: str,
) -> dict:
    """Tier 2: Structured 4-step chain-of-thought prompt."""
    conversation = _format_conversation(messages)
    prompt = TIER2_PROMPT.format(conversation=conversation)

    t0 = time.time()
    try:
        resp = await provider.generate(prompt, response_format={"type": "json_object"})
        data = _parse_json_response(resp)
        decisions = data.get("validated_decisions", data.get("decisions", [])) if data else []
        return {
            "chat_id": chat_id,
            "ok": bool(decisions),
            "decision_count": len(decisions),
            "decision_titles": [d.get("title", d.get("summary", "")) for d in decisions],
            "llm_calls": 1,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "tier": "tier2_structured",
        }
    except Exception as e:
        logger.warning("[Tier2] chat=%s error: %s", chat_id[:12], e)
        return {
            "chat_id": chat_id, "ok": False, "decision_count": 0,
            "decision_titles": [], "llm_calls": 1,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "tier": "tier2_structured",
        }


# ── Tier 3: Agentic loop ──────────────────────────────────────────


async def run_tier3_agentic(
    provider: Any,
    messages: List[dict],
    chat_id: str,
    max_turns: int = 10,
) -> dict:
    """Tier 3: Agentic tool-use loop."""
    tools = ChatTools(messages)
    conversation = _format_conversation(messages)
    tools_desc = "\n".join(
        f"- {t['name']}: {t['description']} — 参数: {json.dumps(t['parameters'], ensure_ascii=False)}"
        for t in TOOLS_SCHEMA
    )
    system = TIER3_SYSTEM.format(tools_desc=tools_desc, conversation=conversation)

    llm_calls = 0
    t0 = time.time()
    history: List[str] = []

    for turn in range(max_turns):
        if history:
            full_prompt = system + "\n\n过往操作:\n" + "\n".join(history[-6:])  # last 6 turns
        else:
            full_prompt = system + "\n\n请开始分析。先搜索关键决策词。"

        try:
            resp = await provider.generate(full_prompt, response_format={"type": "json_object"})
            llm_calls += 1
            data = _parse_json_response(resp)
            if not data or "tool" not in data:
                # No tool call — try to extract decisions directly
                decisions = data.get("decisions", []) if data else []
                if decisions:
                    tools.submit_decisions(decisions)
                break

            tool_name = data["tool"]
            tool_args = data.get("args", {})
            thought = data.get("thought", "")

            result = tools.execute(tool_name, tool_args)
            history.append(
                f"[Turn {turn+1}] Thought: {thought}\n"
                f"Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:100]})\n"
                f"Result: {json.dumps(result, ensure_ascii=False)[:300]}"
            )

            if tool_name == "submit_decisions":
                break

        except Exception as e:
            logger.warning("[Tier3] chat=%s turn=%d error: %s", chat_id[:12], turn, e)
            history.append(f"[Turn {turn+1}] Error: {e}")

    decisions = tools.decisions
    return {
        "chat_id": chat_id,
        "ok": bool(decisions),
        "decision_count": len(decisions),
        "decision_titles": [d.get("title", d.get("summary", "")) for d in decisions],
        "llm_calls": llm_calls,
        "turns": min(turn + 1, max_turns),
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
        "tier": "tier3_agentic",
    }


# ── Full baseline run ──────────────────────────────────────────────


async def run_agentic_baseline(
    provider: Any,
    episodes: List[dict],
    gt_entries: List[dict],
    all_messages: List[dict],
    sample: int = 0,
) -> Dict[str, dict]:
    """Run all three tiers on the episode set.

    Returns dict of {tier_name: {precision, recall, f1, ...}}.
    """
    from experiments.ablation.run_ablation import evaluate_variant

    if sample > 0:
        episodes = episodes[:sample]

    chat_messages: Dict[str, List[dict]] = defaultdict(list)
    for m in all_messages:
        chat_messages[m["chat_id"]].append(m)

    results: Dict[str, List[dict]] = {
        "tier1_single_shot": [],
        "tier2_structured": [],
        "tier3_agentic": [],
    }

    tier_fns = {
        "tier1_single_shot": run_tier1_single_shot,
        "tier2_structured": run_tier2_structured,
        "tier3_agentic": run_tier3_agentic,
    }

    for tier_name, tier_fn in tier_fns.items():
        logger.info("=" * 60)
        logger.info("Running %s (%d chats)", tier_name, len(episodes))
        logger.info("=" * 60)

        t0 = time.time()
        for ep in episodes:
            chat_id = ep["chat_id"]
            msgs = chat_messages.get(chat_id, [])
            result = await tier_fn(provider, msgs, chat_id)
            results[tier_name].append(result)
            logger.info("  %s: %d decisions, %d LLM calls, %.0fms",
                        chat_id[:20], result["decision_count"],
                        result["llm_calls"], result["elapsed_ms"])

        elapsed = time.time() - t0
        logger.info("%s complete: %.0fs total", tier_name, elapsed)

    # Evaluate all tiers
    reports = {}
    eval_cache: Dict[str, bool] = {}
    for tier_name, tier_results in results.items():
        metrics = await evaluate_variant(provider, tier_results, gt_entries, eval_cache)
        total_llm = sum(r["llm_calls"] for r in tier_results)
        total_time = sum(r["elapsed_ms"] for r in tier_results) / 1000
        reports[tier_name] = {
            **metrics,
            "total_llm_calls": total_llm,
            "avg_llm_calls_per_chat": round(total_llm / len(tier_results), 1) if tier_results else 0,
            "total_time_sec": round(total_time, 1),
            "chats": len(tier_results),
        }
        logger.info("%s: P=%.1f%% R=%.1f%% F1=%.1f%% (LLM=%d, %.0fs)",
                    tier_name,
                    metrics["precision"] * 100,
                    metrics["recall"] * 100,
                    metrics["f1"] * 100,
                    total_llm, total_time)

    return reports


# ── Helpers ────────────────────────────────────────────────────────


def _format_conversation(messages: List[dict], max_lines: int = 200) -> str:
    """Format messages into [msg_id] speaker: text lines."""
    lines = []
    for m in messages[-max_lines:]:
        msg_id = m.get("msg_id", "")
        speaker = m.get("speaker", m.get("sender", "?"))
        text = m.get("msg", m.get("content", ""))
        lines.append(f"[{msg_id}] {speaker}: {text}")
    return "\n".join(lines)


def _parse_json_response(resp: str) -> Optional[dict]:
    """Parse JSON from LLM response, handling markdown wrappers."""
    if not resp:
        return None
    raw = resp.strip()

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try extracting outermost braces
    start = raw.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i + 1])
                    except json.JSONDecodeError:
                        break

    return None
