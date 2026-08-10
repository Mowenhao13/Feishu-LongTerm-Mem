"""Lightweight entity name extractor for short search queries.

Single LLM call that turns a user query into a list of entity names,
used by the 4th RRF signal in HierarchicalRetriever.
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

QUERY_ENTITY_PROMPT = """你是一个实体提取助手。从用户的搜索问题中提取出所有提到的实体名称。

要求：
- 只提取有明显实体名称的词（人名、项目名、技术名、产品名等）
- 不提取泛化的普通名词（"系统"、"问题"、"方案"等）
- 如果没有找到任何实体，返回空数组
- 返回纯 JSON 数组，不要包含多余内容

示例：
问题: "上次讨论的微服务架构方案中，张工提到的那个问题"
["微服务架构", "张工"]

问题: "数据库分表策略"
["数据库分表策略"]

问题: "今天有什么安排"
[]

问题: {query}
"""


class QueryEntityExtractor:
    """Extract entity names from a short search query via a single LLM call."""

    def __init__(self, llm_provider: Any) -> None:
        self._llm = llm_provider
        logger.info(
            "[QueryEntityExtractor] Initialized with provider=%s",
            type(llm_provider).__name__,
        )

    async def extract(self, query: str) -> List[str]:
        """Return a list of entity names mentioned in the query.

        Returns an empty list on any error — the caller should treat this
        as a graceful degradation and skip the entity signal.
        """
        if not query or not query.strip():
            return []

        prompt = QUERY_ENTITY_PROMPT.format(query=query.strip())
        logger.info("[QueryEntityExtractor] >>> Calling LLM (len=%d)", len(prompt))

        try:
            resp = await self._llm.generate(prompt)
            raw = resp.strip()

            # Strip markdown code fences if present
            if "```json" in raw:
                start = raw.index("```json") + 7
                end = raw.index("```", start) if "```" in raw[start:] else len(raw)
                raw = raw[start:end].strip()
            elif raw.startswith("```"):
                start = raw.index("\n") + 1 if "\n" in raw else 3
                end = raw.rindex("```") if "```" in raw[start:] else len(raw)
                raw = raw[start:end].strip()

            result = json.loads(raw)
            if isinstance(result, list):
                names = [str(n).strip() for n in result if n]
                logger.info(
                    "[QueryEntityExtractor] Extracted %d entities: %s",
                    len(names),
                    names[:5],
                )
                return names
            logger.warning(
                "[QueryEntityExtractor] Unexpected response shape: %s",
                type(result).__name__,
            )
            return []
        except Exception as exc:
            logger.warning("[QueryEntityExtractor] Failed: %s", exc)
            return []