"""LLM-backed three-state adjudication for evidence-valid decisions."""
from __future__ import annotations

import json
from typing import Any, Sequence

from src.eval.confirmed_decision_eval import Adjudication, AdjudicationResult, EvidenceDecision

class LLMDecisionAdjudicator:
    PROMPT = """你是生产决策评估器。对一条已经通过 evidence contract 的提取结果进行三态判定。

输出决策：
{output_title}
摘要：{output_summary}
证据原文：{evidence_quote}
证据消息：{evidence_messages}

本 chat 的 GT 候选：
{expected_candidates}

只返回 JSON：
{{"adjudication":"match_gt|valid_extra|invalid", "matched_msg_id":"GT消息id或空字符串", "reason":"简短理由"}}

规则：
1. match_gt：提取结果与某一条 GT 是同一个或等价决策；matched_msg_id 必须是候选 GT 的 msg_id。
2. valid_extra：提取结果有明确决策/执行承诺，证据真实，但不被任何候选 GT 覆盖。
3. invalid：不是决策、只是讨论/状态/建议噪声，或内容不被证据支持。
4. 不要因为主题相同就判 match_gt；必须有事实或执行结果等价。
"""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def adjudicate(self, output: EvidenceDecision, expected: Sequence[dict], messages: Sequence[dict]) -> AdjudicationResult:
        by_id = {message.get("msg_id", ""): message.get("msg", "") for message in messages}
        evidence_messages = "\n".join("[{}] {}".format(msg_id, by_id.get(msg_id, "")) for msg_id in output.source_message_ids)
        candidates = "\n".join("- msg_id={}: {}".format(row.get("msg_id", ""), row.get("expected_summary", "")) for row in expected) or "(none)"
        prompt = self.PROMPT.format(output_title=output.title, output_summary=output.summary, evidence_quote=output.evidence_quote, evidence_messages=evidence_messages, expected_candidates=candidates)
        raw = await self._provider.generate(prompt, response_format={"type": "json_object"})
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        data = json.loads(text)
        value = str(data.get("adjudication", "")).strip().lower()
        aliases = {"match": "match_gt", "matched": "match_gt", "extra": "valid_extra", "neutral": "valid_extra", "false": "invalid"}
        value = aliases.get(value, value)
        try:
            outcome = Adjudication(value)
        except ValueError as exc:
            raise ValueError(f"invalid adjudication: {value!r}") from exc
        matched = str(data.get("matched_msg_id", "") or "")
        expected_ids = {str(row.get("msg_id", "")) for row in expected if row.get("msg_id") }
        if outcome is Adjudication.MATCH_GT and matched not in expected_ids:
            return AdjudicationResult(Adjudication.INVALID, "", f"judge returned unknown GT msg_id: {matched}")
        if outcome is Adjudication.MATCH_GT:
            candidate = next(row for row in expected if str(row.get("msg_id", "")) == matched)
            output_chars = set("".join(str(output.title or output.summary).split()))
            expected_chars = set("".join(str(candidate.get("expected_summary", "")).split()))
            overlap = len(output_chars & expected_chars) / min(len(output_chars), len(expected_chars)) if output_chars and expected_chars else 0.0
            if overlap < 0.35:
                return AdjudicationResult(Adjudication.INVALID, "", f"judge match_gt lexical overlap too low: {overlap:.2f}")
        if outcome is not Adjudication.MATCH_GT:
            matched = ""
        return AdjudicationResult(outcome, matched, str(data.get("reason", "")))
