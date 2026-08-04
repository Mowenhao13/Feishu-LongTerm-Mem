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
        self._confidence_threshold = 0.70  # 提高置信度阈值，只保留高置信度决策
        logger.info("[LLM Extractor] Initialized with provider=%s, confidence_threshold=%.2f", 
                    type(llm_provider).__name__, self._confidence_threshold)

    def set_trace_id(self, trace_id: Optional[str]) -> None:
        """设置当前 trace_id，用于 Langfuse 溯源"""
        self._trace_id = trace_id

    async def extract_decision(self, content: str,
                                 existing_decisions: Optional[List] = None) -> Optional[List[dict]]:
        """从消息内容中提取所有决策（支持批量返回）"""
        if not content or not content.strip():
            logger.info("[LLM Extractor] Empty content, skipping")
            return None

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
                    extracted.append({
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
                    })
                else:
                    logger.info("[LLM Extractor] Skipping decision (confidence=%.2f < threshold=%.2f): %s", 
                               conf, self._confidence_threshold, title)

            logger.info("[LLM Extractor] Extracted %d decisions (filtered from %d total)", 
                       len(extracted), len(decisions))
            return extracted if extracted else None

        except json.JSONDecodeError as e:
            logger.error("[LLM Extractor] Failed to parse LLM response: %s", e)
            logger.error("[LLM Extractor] Raw response: %.300s", resp[:300] if resp else "(empty)")
            return None
        except Exception as e:
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
            enriched_parts.append(entity_preamble)
        if project_preamble:
            enriched_parts.append(project_preamble)
        if existing_decisions and decision_preamble:
            enriched_parts.append(decision_preamble)
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
            for d in decisions:
                base_conf = d.get("confidence", 0.80)
                is_sug = bool(d.get("is_suggestion", False))
                impact = d.get("impact_level", "minor")
                has_executor = bool(d.get("executor"))
                title = d.get("title", "")

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
                    extracted.append({
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
                    })
                else:
                    logger.info("[LLM Extractor] extract_with_context: Skipping decision "
                                "(confidence=%.2f): %s", conf, title)

            logger.info("[LLM Extractor] extract_with_context: Extracted %d decisions",
                        len(extracted))
            return extracted if extracted else None

        except json.JSONDecodeError as e:
            logger.error("[LLM Extractor] extract_with_context: Parse error: %s", e)
            logger.error("[LLM Extractor] Raw: %.300s", resp[:300] if resp else "(empty)")
            return None
        except Exception as e:
            import traceback
            logger.error("[LLM Extractor] extract_with_context: Failed: %s", e)
            logger.error("[LLM Extractor] Traceback: %s", traceback.format_exc())
            return None