"""简单的 LLM 决策提取器 — 适配 MemoryEngine._extract_decision 接口"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.prompts.decision_prompts import DECISION_EXTRACTION_PROMPT_SHORT
from src.extractors.project_context_prompt import (
    PROJECT_CONTEXT_PROMPT,
    format_file_changes_for_prompt,
)

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM_PROMPT = """你是一个决策提取助手。从群聊对话中提取决策和建议。

一段对话可能包含多个决策或建议，请提取最重要的一个。

返回 JSON 格式，不要包含无关内容：
{
    "has_decision": true/false,
    "title": "决策/建议标题（简短概括）",
    "content": "决策/建议的完整描述",
    "topic": "所属主题（如技术选型、项目排期、团队管理等）",
    "status": "decided",
    "impact_level": "major/minor",
    "is_suggestion": true/false,
    "parent_id": "如果本决策是某个已有决策的子决策/细化，填写该决策的 sid；否则留空"
}

如果没有决策或建议，返回 {"has_decision": false}

注意：建议（is_suggestion=true）是指对话中有人提出具体的技术方案、参数配置或改进方向，但还没有被大家拍板确认的内容。决策（is_suggestion=false）是指已经达成共识或明确拍板的内容。"""


class SimpleLLMExtractor:
    """简单的 LLM 决策提取器"""

    def __init__(self, llm_provider: Any) -> None:
        self._llm = llm_provider
        self._trace_id: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_extraction_stats: Optional[dict] = None
        self._confidence_threshold = 0.70  # 提高置信度阈值，只保留高置信度决策
        logger.info("[LLM Extractor] Initialized with provider=%s, confidence_threshold=%.2f", 
                    type(llm_provider).__name__, self._confidence_threshold)

    def set_trace_id(self, trace_id: Optional[str]) -> None:
        """设置当前 trace_id，用于 Langfuse 溯源"""
        self._trace_id = trace_id

    @staticmethod
    def _attach_evidence(decision: Dict[str, Any], content: str) -> bool:
        """Attach auditable evidence when an extractor omitted it.

        The fallback only links an output to an explicit ``[msg_id]`` source
        line when its title/summary has substantial character overlap with the
        message. It deliberately leaves unrelated decisions unlinked so the
        evaluator can reject them instead of fabricating provenance.
        """
        import re

        messages_by_id = {}
        for line in content.splitlines():
            match = re.match(r"^\[([^\]]+)\]\s*[^:：]+[:：]\s*(.+)$", line.strip())
            if match:
                msg_id, message = match.groups()
                messages_by_id[msg_id] = message

        source_ids = [str(item) for item in decision.get("source_message_ids", []) if item]
        evidence_quote = str(decision.get("evidence_quote", "") or "")
        if source_ids and evidence_quote and any(
            evidence_quote in messages_by_id.get(message_id, "") for message_id in source_ids
        ):
            decision["evidence_source"] = "model"
            if not decision.get("source_message_id"):
                decision["source_message_id"] = source_ids[0]
            return True

        decision["source_message_ids"] = []
        decision["source_message_id"] = ""
        decision["evidence_quote"] = ""

        query = decision.get("summary", "") or decision.get("title", "")
        query_chars = set(re.sub(r"\s+", "", query.lower()))
        if len(query_chars) < 3:
            return False

        best_id = ""
        best_text = ""
        best_score = 0.0
        for msg_id, message in messages_by_id.items():
            message_chars = set(re.sub(r"\s+", "", message.lower()))
            if not message_chars:
                continue
            score = len(query_chars & message_chars) / len(query_chars)
            if score > best_score:
                best_id, best_text, best_score = msg_id, message, score

        if best_score >= 0.6:
            decision["source_message_ids"] = [best_id]
            decision["source_message_id"] = best_id
            decision["evidence_quote"] = best_text
            decision["evidence_source"] = "heuristic"
            return True
        return False

    @staticmethod
    def _add_execution_acknowledgements(decisions: List[dict], content: str) -> List[dict]:
        import re
        messages_by_id: Dict[str, str] = {}
        for line in content.splitlines():
            match = re.match(r"^\[([^\]]+)\]\s*[^:]+:\s*(.+)$", line.strip())
            if match:
                messages_by_id[match.group(1)] = match.group(2)
        acknowledgement = re.compile(r"^(?:\u597d|\u597d\u7684|\u6ca1\u95ee\u9898|\u884c|\u53ef\u4ee5|\u6536\u5230|\u660e\u767d)[，,、 ]*(?:\u6211|\u6211\u4eec|\u8fd9\u8fb9)?(?:\u4eca\u5929|\u4eca\u665a|\u660e\u5929|\u4e0b\u5468|\u672c\u5468|\u9a6c\u4e0a|\u7a0d\u540e)?(?:\u5f00\u59cb|\u642d\u5efa|\u5b9e\u73b0|\u914d\u7f6e|\u63d0\u4ea4|\u66f4\u65b0|\u5199|\u8d1f\u8d23|\u8dd1|\u6267\u884c|\u51c6\u5907|\u5b89\u6392|\u5b8c\u6210)")
        existing_sources = {str(decision.get("source_message_id")) for decision in decisions if decision.get("source_message_id")}
        derived: List[dict] = []
        for decision in decisions:
            source_ids = [str(item) for item in decision.get("source_message_ids", []) if item]
            quote = str(decision.get("evidence_quote", "") or "")
            if len(source_ids) < 2 or not quote: continue
            evidence_index = next((index for index, source_id in enumerate(source_ids) if quote in messages_by_id.get(source_id, "")), None)
            if evidence_index is None: continue
            for source_id in source_ids[evidence_index + 1:]:
                message = messages_by_id.get(source_id, "")
                if not message or source_id in existing_sources or not acknowledgement.search(message): continue
                derived.append({"title": message, "content": message, "summary": message, "topic": decision.get("topic", "general"), "status": "decided", "impact_level": decision.get("impact_level", "major"), "is_suggestion": False, "parent_id": decision.get("parent_id", ""), "confidence": max(float(decision.get("confidence", 0.80)), 0.80), "rationale": "Execution acknowledgement following a cited decision", "proposer": decision.get("proposer"), "executor": decision.get("executor"), "source_message_id": source_id, "source_message_ids": [source_id], "evidence_quote": message, "source_chat_id": decision.get("source_chat_id", ""), "evidence_source": "derived_execution_ack"})
                existing_sources.add(source_id)
        return decisions + derived


    async def extract_decision(self, content: str,
                                 existing_decisions: Optional[List] = None) -> Optional[List[dict]]:
        """从消息内容中提取所有决策（支持批量返回）"""
        if not content or not content.strip():
            logger.info("[LLM Extractor] Empty content, skipping")
            return None
        self.last_error = None

        # Escape braces in content so .format() doesn't treat {foo} as placeholders
        safe_content = content.replace("{", "{{").replace("}", "}}")
        prompt = DECISION_EXTRACTION_PROMPT_SHORT.format(conversation_text=safe_content)
        logger.info("[LLM Extractor] >>> Calling LLM (len=%d)", len(prompt))

        try:
            resp = await self._llm.generate(
                prompt,
                response_format={"type": "json_object"},
            )
            logger.info("[LLM Extractor] <<< LLM response len=%d preview=%.200s", len(resp), resp[:200])

            # Try to extract JSON from markdown code block if present
            raw_resp = resp.strip()
            if "```json" in raw_resp:
                start = raw_resp.index("```json") + 7
                end = raw_resp.index("```", start) if "```" in raw_resp[start:] else len(raw_resp)
                raw_resp = raw_resp[start:end].strip()

            result = json.loads(raw_resp)
            logger.info("[LLM Extractor] Parsed result keys: %s", list(result.keys()))

            # Handle both "has_decisions" and "has_decision" key names
            has_any = result.get("has_decisions", result.get("has_decision", False))
            if not has_any:
                logger.info("[LLM Extractor] No decision found in content")
                return None

            decisions = result.get("decisions", [])
            if not decisions:
                logger.info("[LLM Extractor] Decisions array is empty")
                return None

            extracted = []
            for d in decisions:
                # Calculate confidence from decision features
                base_conf = d.get("confidence", 0.80)
                is_sug = bool(d.get("is_suggestion", False))
                impact = d.get("impact_level", "minor")
                has_executor = bool(d.get("executor"))
                title = d.get("title", "")
                
                # Vary confidence based on decision attributes
                conf = base_conf
                if is_sug:
                    conf = min(conf, 0.75)  # Suggestions are inherently less certain
                if impact == "advisory" or impact == "minor":
                    conf -= 0.05
                if not has_executor:
                    conf -= 0.05  # No executor means less definitive
                if any(w in title for w in ["考虑", "建议", "可以", "看看", "确认", "准备"]):
                    conf -= 0.10  # Tentative language
                if any(w in title for w in ["决定", "确认", "通过", "采用", "切换", "升级"]):
                    conf += 0.05  # Definitive language
                conf = max(0.50, min(0.95, round(conf, 2)))
                
                # 只有高于置信度阈值的决策才被保留
                if conf >= self._confidence_threshold:
                    item = {
                        "title": d.get("title", ""),
                        "content": d.get("content", content),
                        "summary": d.get("title", ""),
                        "topic": "general",
                        "status": d.get("status", "decided"),
                        "impact_level": impact,
                        "is_suggestion": is_sug,
                        "parent_id": d.get("parent_id", ""),
                        "confidence": conf,
                        "rationale": d.get("rationale", ""),
                        "proposer": d.get("proposer"),
                        "executor": d.get("executor"),
                        "source_message_id": d.get("source_message_id", ""),
                        "source_message_ids": d.get("source_message_ids", []),
                        "evidence_quote": d.get("evidence_quote", ""),
                        "source_chat_id": d.get("source_chat_id", ""),
                    }
                    if self._attach_evidence(item, content):
                        extracted.append(item)
                    else:
                        logger.info("[LLM Extractor] Skipping decision without exact evidence: %s", title)
                else:
                    logger.info("[LLM Extractor] Skipping decision (confidence=%.2f < threshold=%.2f): %s", 
                               conf, self._confidence_threshold, title)

            extracted = self._add_execution_acknowledgements(extracted, content)
            logger.info("[LLM Extractor] Extracted %d decisions (filtered from %d total)",
                        len(extracted), len(decisions))
            return extracted if extracted else None

        except json.JSONDecodeError as e:
            self.last_error = f"json_parse_error: {e}"
            logger.error("[LLM Extractor] Failed to parse LLM response: %s", e)
            logger.error("[LLM Extractor] Raw response: %.300s", resp[:300] if resp else "(empty)")
            return None
        except Exception as e:
            self.last_error = f"llm_call_error: {e}"
            import traceback
            logger.error("[LLM Extractor] LLM call failed: %s", e)
            logger.error("[LLM Extractor] Traceback: %s", traceback.format_exc())
            return None

    async def extract_with_context(
        self,
        content: str,
        entity_context: Optional[List[Dict[str, Any]]] = None,
        existing_decisions: Optional[List[Dict[str, Any]]] = None,
        project_context: Optional[Any] = None,
    ) -> Optional[List[dict]]:
        """提取决策 — 支持实体上下文 + 项目文件变更上下文注入

        Same as extract_decision but injects entity names and/or
        project file changes into the prompt as preamble sections.

        Args:
            content: 对话内容
            entity_context: Stage 1 提取的实体列表
            existing_decisions: 已有决策列表（去重用）
            project_context: ProjectDevelopmentContext 包含最近的文件变更
                当 ConversationFileBridge 判断需要合并时传入

        Returns:
            Optional[List[dict]]: 同 extract_decision
        """
        if not content or not content.strip():
            logger.info("[LLM Extractor] extract_with_context: Empty content, skipping")
            return None
        self.last_error = None

        # Inject entity context as a preamble
        if entity_context:
            entity_lines = ["\n## 本段对话中已知的实体"]
            for ent in entity_context:
                name = ent.get("name", "?")
                etype = ent.get("entity_type", "?")
                entity_lines.append(f"- {name} ({etype})")
            entity_lines.append("\n提取决策时，请尽量引用上述实体的具体名称。\n")
            entity_preamble = "\n".join(entity_lines)
        else:
            entity_preamble = ""

        # Inject project file changes as a preamble (via ConversationFileBridge)
        project_preamble = ""
        if project_context:
            changes = getattr(project_context, "recent_changes", None) or getattr(project_context, "changes", None) or []
            if changes:
                file_changes_text = format_file_changes_for_prompt(changes)
                project_preamble = PROJECT_CONTEXT_PROMPT.format(file_changes_text=file_changes_text)
                logger.info(
                    "[LLM Extractor] Injected project context: %d file changes",
                    len(changes),
                )

        if existing_decisions:
            decision_lines = ["\n## 系统中已有决策（仅作参考）"]
            for d in existing_decisions:
                decision_lines.append(f"- {d.get('title', '') or d.get('summary', '')}")
            decision_preamble = "\n".join(decision_lines)
        else:
            decision_preamble = ""

        safe_content = content.replace("{", "{{").replace("}", "}}")
        enriched_parts = []
        if entity_preamble:
            enriched_parts.append(entity_preamble.replace("{", "{{").replace("}", "}}"))
        if project_preamble:
            enriched_parts.append(project_preamble.replace("{", "{{").replace("}", "}}"))
        if existing_decisions and decision_preamble:
            enriched_parts.append(decision_preamble.replace("{", "{{").replace("}", "}}"))
        enriched_parts.append(f"\n## 对话内容\n\n{safe_content}")
        enriched_content = "\n".join(enriched_parts)

        prompt = DECISION_EXTRACTION_PROMPT_SHORT.format(conversation_text=enriched_content)
        logger.info(
            "[LLM Extractor] extract_with_context: >>> Calling LLM (len=%d, entities=%d, project_changes=%d)",
            len(prompt),
            len(entity_context) if entity_context else 0,
            len(project_context.recent_changes) if project_context and getattr(project_context, "recent_changes", None) else 0,
        )

        try:
            resp = await self._llm.generate(
                prompt,
                response_format={"type": "json_object"},
                trace_id=self._trace_id,
            )
            logger.info("[LLM Extractor] extract_with_context: <<< LLM resp len=%d preview=%.200s",
                        len(resp), resp[:200])

            raw_resp = resp.strip()
            if "```json" in raw_resp:
                start = raw_resp.index("```json") + 7
                end = raw_resp.index("```", start) if "```" in raw_resp[start:] else len(raw_resp)
                raw_resp = raw_resp[start:end].strip()

            result = json.loads(raw_resp)
            has_any = result.get("has_decisions", result.get("has_decision", False))
            if not has_any:
                logger.info("[LLM Extractor] extract_with_context: No decision found")
                return None

            decisions = result.get("decisions", [])
            if not decisions:
                logger.info("[LLM Extractor] extract_with_context: Decisions array empty")
                return None

            # Apply same confidence calculation as extract_decision
            extracted = []
            stats = {
                "total_candidates": len(decisions),
                "confidence_filtered": 0,
                "status_discussion_filtered": 0,
                "evidence_attachment_dropped": 0,
                "confirmed_output": 0,
            }
            for d in decisions:
                kind = str(d.get("decision_kind", "choice"))
                title = d.get("title", "")

                # Typed filtering: status and discussion are never decisions
                if kind in ("status", "discussion"):
                    stats["status_discussion_filtered"] += 1
                    logger.info("[LLM Extractor] extract_with_context: Filtered %s decision: %s",
                                kind, title)
                    continue

                # Suggestion kind forces is_suggestion=True
                is_sug = bool(d.get("is_suggestion", False))
                if kind == "suggestion":
                    is_sug = True

                base_conf = d.get("confidence", 0.80)
                impact = d.get("impact_level", "minor")
                has_executor = bool(d.get("executor"))

                conf = base_conf
                if is_sug:
                    conf = min(conf, 0.75)
                if impact in ("advisory", "minor"):
                    conf -= 0.05
                if not has_executor:
                    conf -= 0.05
                if any(w in title for w in ["考虑", "建议", "可以", "看看", "确认", "准备"]):
                    conf -= 0.10
                if any(w in title for w in ["决定", "确认", "通过", "采用", "切换", "升级"]):
                    conf += 0.05
                conf = max(0.50, min(0.95, round(conf, 2)))

                if conf >= self._confidence_threshold:
                    item = {
                        "title": d.get("title", ""),
                        "content": d.get("content", content),
                        "summary": d.get("title", ""),
                        "topic": "general",
                        "status": d.get("status", "decided"),
                        "impact_level": impact,
                        "is_suggestion": is_sug,
                        "decision_kind": kind,
                        "parent_id": d.get("parent_id", ""),
                        "confidence": conf,
                        "rationale": d.get("rationale", ""),
                        "proposer": d.get("proposer"),
                        "executor": d.get("executor"),
                        "source_message_id": d.get("source_message_id", ""),
                        "source_message_ids": d.get("source_message_ids", []),
                        "evidence_quote": d.get("evidence_quote", ""),
                        "source_chat_id": d.get("source_chat_id", ""),
                    }
                    if self._attach_evidence(item, content):
                        extracted.append(item)
                        stats["confirmed_output"] += 1
                    else:
                        stats["evidence_attachment_dropped"] += 1
                        logger.info(
                            "[LLM Extractor] extract_with_context: Skipping decision without exact evidence: %s",
                            title,
                        )
                else:
                    stats["confidence_filtered"] += 1
                    logger.info("[LLM Extractor] extract_with_context: Skipping decision "
                                "(confidence=%.2f): %s", conf, title)

            extracted = self._add_execution_acknowledgements(extracted, content)
            stats["confirmed_output"] = len(extracted)
            self.last_extraction_stats = stats
            logger.info("[LLM Extractor] extract_with_context: Extracted %d decisions "
                        "(stats: %s)", len(extracted), stats)
            return extracted if extracted else None

        except json.JSONDecodeError as e:
            self.last_error = f"json_parse_error: {e}"
            logger.error("[LLM Extractor] extract_with_context: Parse error: %s", e)
            logger.error("[LLM Extractor] Raw: %.300s", resp[:300] if resp else "(empty)")
            return None
        except Exception as e:
            self.last_error = f"llm_call_error: {e}"
            import traceback
            logger.error("[LLM Extractor] extract_with_context: Failed: %s", e)
            logger.error("[LLM Extractor] Traceback: %s", traceback.format_exc())
            return None
