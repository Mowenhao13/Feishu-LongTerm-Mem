"""LLM-backed global semantic adjudication for evidence-valid decisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

from src.eval.confirmed_decision_eval import (
    Adjudication,
    AdjudicationResult,
    AssignmentRow,
    ChatAssignment,
    EvidenceDecision,
    GlobalAdjudicationGroup,
)


class LLMDecisionAdjudicator:
    PROMPT_VERSION = "global-assignment-v1"
    SCHEMA_VERSION = "global-assignment-v1"

    PROMPT = """你是全局语义判定器。你的任务是对同一个 chat 中的多个已确认决策，做一对一分配。

输入中每条输出都必须且只能得到一个分类；每条 GT 最多只能匹配一次。

判定规则：
1. match_gt：输出和某条 GT 是同一个决策或语义等价决策，且只能选择一条 GT。
2. valid_extra：输出是真实、明确的决策或执行承诺，但 GT 中没有覆盖它。
3. invalid：输出不是决策，只是讨论、状态、建议、噪声，或证据不成立。
4. 仅主题相同不算 match_gt。
5. 比较核心命题、正负极性、承诺强度和关键限定条件。
6. 可以忽略非关键细节缺失，但不能忽略会改变决策含义的条件、范围、时间、阈值、是否分批、是否试点、是否回滚等限定。
7. 如果输出和 GT 在核心内容上冲突，必须判为 invalid 或 valid_extra，不能判 match_gt。
8. 如果一个输出对应多个 GT，选择最贴近的那一个，但每条 GT 仍然最多只能被匹配一次。
9. 不要使用词面重合、字面相似度或 embedding 阈值来覆盖语义判断。

输出必须严格是 JSON，格式如下：
{"assignments":[{"output_index":0,"classification":"match_gt|valid_extra|invalid","matched_gt_index":0|null,"decision_kind":"...","core_equivalent":true|false,"polarity_compatible":true|false,"commitment_compatible":true|false,"material_qualifier_conflict":true|false,"reason":"..."}]}

当前 chat_id: {chat_id}

待判定输出：
{outputs}

GT 候选：
{candidates}

消息原文：
{messages}
"""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    @staticmethod
    def _stable_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _normalized_payload(cls, group: GlobalAdjudicationGroup) -> dict[str, Any]:
        outputs = [
            {
                "chat_id": output.chat_id,
                "title": output.title,
                "summary": output.summary,
                "status": output.status,
                "is_suggestion": output.is_suggestion,
                "source_message_ids": list(output.source_message_ids),
                "evidence_quote": output.evidence_quote,
            }
            for output in sorted(
                group.outputs,
                key=lambda item: cls._stable_json(
                    {
                        "chat_id": item.chat_id,
                        "title": item.title,
                        "summary": item.summary,
                        "status": item.status,
                        "is_suggestion": item.is_suggestion,
                        "source_message_ids": list(item.source_message_ids),
                        "evidence_quote": item.evidence_quote,
                    }
                ),
            )
        ]
        candidates = [
            {
                "msg_id": str(candidate.get("msg_id", "")),
                "chat_id": str(candidate.get("chat_id", group.chat_id)),
                "expected_summary": str(candidate.get("expected_summary", "")),
                "expected_title": str(candidate.get("expected_title", candidate.get("expected_summary", ""))),
                "status": str(candidate.get("status", "")),
                "impact": str(candidate.get("impact", "")),
            }
            for candidate in sorted(
                group.candidates,
                key=lambda item: cls._stable_json(
                    {
                        "msg_id": str(item.get("msg_id", "")),
                        "chat_id": str(item.get("chat_id", group.chat_id)),
                        "expected_summary": str(item.get("expected_summary", "")),
                        "expected_title": str(item.get("expected_title", item.get("expected_summary", ""))),
                        "status": str(item.get("status", "")),
                        "impact": str(item.get("impact", "")),
                    }
                ),
            )
        ]
        messages = [
            {
                "msg_id": str(message.get("msg_id", "")),
                "msg": str(message.get("msg", "")),
            }
            for message in sorted(group.messages, key=lambda item: str(item.get("msg_id", "")))
        ]
        return {
            "chat_id": group.chat_id,
            "outputs": outputs,
            "candidates": candidates,
            "messages": messages,
        }

    def normalized_input_hash(self, group: GlobalAdjudicationGroup) -> str:
        return hashlib.sha256(self._stable_json(self._normalized_payload(group)).encode("utf-8")).hexdigest()

    def cache_key(self, group: GlobalAdjudicationGroup) -> str:
        payload = {
            "prompt_version": self.PROMPT_VERSION,
            "schema_version": self.SCHEMA_VERSION,
            "input_hash": self.normalized_input_hash(group),
        }
        return hashlib.sha256(self._stable_json(payload).encode("utf-8")).hexdigest()

    def _render_prompt(self, group: GlobalAdjudicationGroup) -> str:
        payload = self._normalized_payload(group)
        prompt_text = self.PROMPT.replace("{chat_id}", payload["chat_id"])
        prompt_text = prompt_text.replace("{outputs}", self._stable_json(payload["outputs"]))
        prompt_text = prompt_text.replace("{candidates}", self._stable_json(payload["candidates"]))
        prompt_text = prompt_text.replace("{messages}", self._stable_json(payload["messages"]))
        return prompt_text

    @staticmethod
    def _strip_json_wrappers(text: str) -> str:
        stripped = text.strip()
        if "```json" in stripped:
            stripped = stripped.split("```json", 1)[1].split("```", 1)[0].strip()
        elif stripped.startswith("```"):
            stripped = stripped.split("```", 1)[1].split("```", 1)[0].strip()
        return stripped

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        return bool(value)

    @classmethod
    def _row_from_payload(cls, row: dict[str, Any], group: GlobalAdjudicationGroup) -> AssignmentRow:
        try:
            output_index = int(row["output_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("missing or invalid output_index") from exc

        classification = str(row.get("classification", "")).strip().lower()
        if classification not in {"match_gt", "valid_extra", "invalid"}:
            raise ValueError(f"invalid classification: {classification!r}")

        matched_msg_id = ""
        if classification == "match_gt":
            matched_index = row.get("matched_gt_index")
            if matched_index is None:
                raise ValueError("match_gt row missing matched_gt_index")
            try:
                matched_index = int(matched_index)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid matched_gt_index") from exc
            if matched_index < 0 or matched_index >= len(group.candidates):
                raise ValueError(f"unknown GT index: {matched_index}")
            matched_msg_id = str(group.candidates[matched_index].get("msg_id", ""))
            if not matched_msg_id:
                raise ValueError(f"unknown GT index: {matched_index}")

        return AssignmentRow(
            output_index=output_index,
            outcome=Adjudication(classification),
            matched_msg_id=matched_msg_id,
            decision_kind=str(row.get("decision_kind", "")),
            core_equivalent=cls._coerce_bool(row.get("core_equivalent", False)),
            polarity_compatible=cls._coerce_bool(row.get("polarity_compatible", False)),
            commitment_compatible=cls._coerce_bool(row.get("commitment_compatible", False)),
            material_qualifier_conflict=cls._coerce_bool(row.get("material_qualifier_conflict", False)),
            reason=str(row.get("reason", "")),
        )

    async def adjudicate_chat(self, group: GlobalAdjudicationGroup) -> ChatAssignment:
        prompt = self._render_prompt(group)
        raw = await self._provider.generate(
            prompt,
            temperature=0,
            response_format={"type": "json_object"},
        )
        text = self._strip_json_wrappers(str(raw))
        data = json.loads(text)
        assignments = data.get("assignments", [])
        if not isinstance(assignments, list):
            raise ValueError("assignments must be a list")
        rows = tuple(self._row_from_payload(row, group) for row in assignments)
        return ChatAssignment(chat_id=group.chat_id, input_hash=self.normalized_input_hash(group), rows=rows)

    async def adjudicate(
        self,
        output: EvidenceDecision,
        expected: Sequence[dict],
        messages: Sequence[dict],
    ) -> AdjudicationResult:
        group = GlobalAdjudicationGroup(
            chat_id=output.chat_id,
            outputs=(output,),
            candidates=tuple(expected),
            messages=tuple(messages),
        )
        assignment = await self.adjudicate_chat(group)
        row = assignment.rows[0] if assignment.rows else AssignmentRow(0, Adjudication.INVALID)
        return AdjudicationResult(row.outcome, row.matched_msg_id, row.reason)
