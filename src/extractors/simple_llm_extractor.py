"""简单的 LLM 决策提取器 — 适配 MemoryEngine._extract_decision 接口"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from src.prompts.decision_prompts import DECISION_EXTRACTION_PROMPT_SHORT

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
        logger.info("[LLM Extractor] Initialized with provider=%s", type(llm_provider).__name__)

    async def extract_decision(self, content: str,
                                existing_decisions: Optional[list] = None) -> Optional[List[dict]]:
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
                extracted.append({
                    "title": d.get("title", ""),
                    "content": d.get("content", content),
                    "summary": d.get("title", ""),
                    "topic": d.get("topic", "general"),
                    "status": d.get("status", "decided"),
                    "impact_level": d.get("impact_level", "minor"),
                    "is_suggestion": bool(d.get("is_suggestion", False)),
                    "parent_id": d.get("parent_id", ""),
                    "confidence": d.get("confidence", 0.85),
                    "rationale": d.get("rationale", ""),
                    "proposer": d.get("proposer"),
                    "executor": d.get("executor"),
                })

            logger.info("[LLM Extractor] Extracted %d decisions from episode", len(extracted))
            return extracted

        except json.JSONDecodeError as e:
            logger.error("[LLM Extractor] Failed to parse LLM response: %s", e)
            logger.error("[LLM Extractor] Raw response: %.300s", resp[:300] if resp else "(empty)")
            return None
        except Exception as e:
            import traceback
            logger.error("[LLM Extractor] LLM call failed: %s", e)
            logger.error("[LLM Extractor] Traceback: %s", traceback.format_exc())
            return None