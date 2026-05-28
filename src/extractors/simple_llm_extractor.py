"""简单的 LLM 决策提取器 — 适配 MemoryEngine._extract_decision 接口"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM_PROMPT = """你是一个决策提取助手。从群聊对话中提取决策信息。

一段对话可能包含多个决策，请提取最重要的一个。

返回 JSON 格式，不要包含无关内容：
{
    "has_decision": true/false,
    "title": "决策标题（简短概括）",
    "content": "决策的完整描述",
    "topic": "所属主题（如技术选型、项目排期、团队管理等）",
    "status": "decided",
    "impact_level": "major/minor",
    "parent_id": "如果本决策是某个已有决策的子决策/细化，填写该决策的 sid；否则留空"
}

如果没有决策，返回 {"has_decision": false}"""


class SimpleLLMExtractor:
    """简单的 LLM 决策提取器"""

    def __init__(self, llm_provider: Any) -> None:
        self._llm = llm_provider
        logger.info("[LLM Extractor] Initialized with provider=%s", type(llm_provider).__name__)

    async def extract_decision(self, content: str,
                                existing_decisions: Optional[list] = None) -> Optional[dict]:
        """从消息内容中提取决策"""
        if not content or not content.strip():
            logger.info("[LLM Extractor] Empty content, skipping")
            return None

        context_prompt = EXTRACT_SYSTEM_PROMPT
        if existing_decisions:
            context_lines = []
            for d in existing_decisions:
                sid = d.get("sid", "")[:8]
                summary = d.get("summary", "")[:60]
                topic = d.get("topic", "")
                context_lines.append(f"  sid={sid} | 主题={topic} | {summary}")
            context_prompt += (
                "\n\n以下是系统中已有的决策（供参考，判断新决策是否为子决策）：\n"
                + "\n".join(context_lines)
            )

        prompt = f"{context_prompt}\n\n群聊对话：{content}"
        logger.info("[LLM Extractor] >>> Calling LLM (len=%d)", len(prompt))

        try:
            resp = await self._llm.generate(
                prompt,
                response_format={"type": "json_object"},
            )
            logger.info("[LLM Extractor] <<< LLM response len=%d", len(resp))

            result = json.loads(resp)
            if not result.get("has_decision", False):
                logger.info("[LLM Extractor] No decision found in content")
                return None

            return {
                "title": result.get("title", ""),
                "content": result.get("content", content),
                "summary": result.get("title", ""),
                "topic": result.get("topic", "general"),
                "status": result.get("status", "decided"),
                "impact_level": result.get("impact_level", "minor"),
                "parent_id": result.get("parent_id", ""),
            }
        except json.JSONDecodeError as e:
            logger.error("[LLM Extractor] Failed to parse LLM response: %s", e)
            return None
        except Exception as e:
            logger.error("[LLM Extractor] LLM call failed: %s", e)
            return None