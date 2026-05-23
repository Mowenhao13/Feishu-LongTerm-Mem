"""
文档决策提取器 — 从文档内容中提取结构化决策

TODO: 飞书 API 集成
  - 使用 LLM 提取后的决策通过 PipelineEngine.apply_mutation() 进入管道
  - 文档版本管理使用 GitStorage.write_decision()
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.llm.client import LLMClient
from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel
from src.prompts.doc_decision_prompts import (
    DOC_CONFLICT_ASSESSMENT_PROMPT,
    DOC_DECISION_DEDUP_PROMPT,
    DOC_DECISION_EXTRACTION_PROMPT,
    DOC_UPDATE_DETECTION_PROMPT,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DocDecision:
    decision_id: str
    summary: str
    status: str  # "decided" | "pending" | "rejected" | "superseded"
    impact_level: str  # "critical" | "major" | "minor" | "advisory"
    rationale: str = ""
    alternatives: List[str] = field(default_factory=list)
    scope: str = ""
    section: str = ""


@dataclass
class DocDecisionExtractResult:
    doc_token: str
    doc_title: str
    has_decisions: bool = False
    decisions: List[DocDecision] = field(default_factory=list)
    reasoning: str = ""


class DocDecisionExtractor:
    """
    文档决策提取器

    职责:
      1. 从文档内容中提取结构化决策 (LLM)
      2. 决策去重 (vs 已有决策)
      3. 冲突检测 (跨文档)
      4. 版本变更检测 (diff)

    注意: 当前使用本地文件模拟，无需飞书 API
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client or LLMClient()

    def extract(self, doc_token: str, doc_title: str, content: str, doc_type: str = "unknown") -> DocDecisionExtractResult:
        """从文档内容中提取决策

        TODO: 替换为飞书 API docs +fetch 获取内容后调用
        """
        prompt = DOC_DECISION_EXTRACTION_PROMPT.format(
            doc_token=doc_token,
            doc_title=doc_title,
            content=content,
            doc_type=doc_type,
            last_modified=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        try:
            resp = self._llm.chat(prompt, response_format={"type": "json_object"})
            # LLMClient.chat() 返回 OpenAI 格式，提取 content
            if isinstance(resp, str):
                text = resp
            elif isinstance(resp, dict):
                text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not text:
                    text = json.dumps(resp)
            else:
                text = str(resp)
        except Exception as e:
            logger.error("LLM extraction failed for doc %s: %s", doc_token, e)
            return DocDecisionExtractResult(doc_token=doc_token, doc_title=doc_title)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response for doc %s", doc_token)
            return DocDecisionExtractResult(doc_token=doc_token, doc_title=doc_title)

        decisions = []
        for item in data.get("decisions", []):
            decisions.append(DocDecision(
                decision_id=item.get("decision_id", f"doc_{doc_token}"),
                summary=item.get("summary", ""),
                status=item.get("status", "pending"),
                impact_level=item.get("impact_level", "minor"),
                rationale=item.get("rationale", ""),
                alternatives=item.get("alternatives", []),
                scope=item.get("scope", ""),
                section=item.get("section", ""),
            ))

        return DocDecisionExtractResult(
            doc_token=doc_token,
            doc_title=doc_title,
            has_decisions=data.get("has_decisions", False),
            decisions=decisions,
            reasoning=data.get("reasoning", ""),
        )

    def dedup(self, new_decision: DocDecision, existing_decisions: List[Dict]) -> Tuple[str, str, float]:
        """决策去重 — 判断新决策与已有决策的关系

        Returns: (action, matched_id, confidence)
          action: "new" | "duplicate" | "update" | "conflict"
        """
        if not existing_decisions:
            return "new", "", 0.0

        existing_text = "\n".join(
            f"- {d.get('sid', '')}: {d.get('summary', '')} (status={d.get('status', '')})"
            for d in existing_decisions
        )

        prompt = DOC_DECISION_DEDUP_PROMPT.format(
            doc_token=new_decision.decision_id,
            section=new_decision.section,
            summary=new_decision.summary,
            existing_decisions=existing_text,
        )

        try:
            resp = self._llm.chat(prompt, response_format={"type": "json_object"})
            if isinstance(resp, str):
                data = json.loads(resp)
            elif isinstance(resp, dict):
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                data = json.loads(content)
            else:
                data = json.loads(str(resp))
        except Exception as e:
            logger.warning("Dedup LLM call failed: %s", e)
            return "new", "", 0.0

        return (
            data.get("action", "new"),
            data.get("matched_decision_id", ""),
            data.get("confidence", 0.0),
        )

    def assess_conflict(
        self,
        doc_a: str, section_a: str, summary_a: str, text_a: str,
        doc_b: str, section_b: str, summary_b: str, text_b: str,
    ) -> Dict[str, Any]:
        """跨文档冲突检测

        Returns: {conflict_type, contradiction_score, description, recommended_action}
        """
        prompt = DOC_CONFLICT_ASSESSMENT_PROMPT.format(
            doc_a_token=doc_a, section_a=section_a, summary_a=summary_a, text_a=text_a,
            doc_b_token=doc_b, section_b=section_b, summary_b=summary_b, text_b=text_b,
        )

        try:
            resp = self._llm.chat(prompt, response_format={"type": "json_object"})
            if isinstance(resp, str):
                return json.loads(resp)
            elif isinstance(resp, dict):
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                return json.loads(content)
            return json.loads(str(resp))
        except Exception as e:
            logger.warning("Conflict assessment LLM call failed: %s", e)
            return {
                "conflict_type": "independent",
                "contradiction_score": 0.0,
                "description": "Assessment failed",
                "recommended_action": "nothing",
            }

    def detect_doc_update(
        self,
        doc_token: str,
        section: str,
        old_content: str,
        new_content: str,
    ) -> Dict[str, Any]:
        """文档版本变更检测 — 检测决策级别的变化

        Returns: {has_decision_change, change_type, affected_decisions, reasoning}
        """
        prompt = DOC_UPDATE_DETECTION_PROMPT.format(
            doc_token=doc_token,
            section=section,
            old_content=old_content,
            new_content=new_content,
        )

        try:
            resp = self._llm.chat(prompt, response_format={"type": "json_object"})
            if isinstance(resp, str):
                return json.loads(resp)
            elif isinstance(resp, dict):
                content = resp.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                return json.loads(content)
            return json.loads(str(resp))
        except Exception as e:
            logger.warning("Update detection LLM call failed: %s", e)
            return {"has_decision_change": False, "change_type": "no_change", "affected_decisions": [], "reasoning": ""}