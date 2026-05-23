from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel, Relation, RelationType
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HypergraphBuilder:
    """超图构建器

    整合 ref/main stage2 的核心逻辑：
    1. 从对话/文档内容中提取 Topic 层级
    2. 基于 Topic 提取 Fact 层级
    3. 构建完整的超图结构
    """

    def __init__(self, llm_provider: Optional[Any] = None) -> None:
        self._llm = llm_provider

    def build_from_content(
        self,
        content: str,
        source_id: str = "",
        source_type: str = "im",
    ) -> Dict[str, Any]:
        hypergraph = {
            "source_id": source_id,
            "source_type": source_type,
            "topics": {},
            "facts": {},
            "hyperedges": {},
            "created_at": datetime.now().isoformat(),
        }
        return hypergraph

    def build_from_episodes(
        self,
        episodes: List[Dict[str, Any]],
        llm_provider: Optional[Any] = None,
    ) -> Dict[str, Any]:
        llm = llm_provider or self._llm
        hypergraph = {
            "topics": {},
            "episodes": {},
            "facts": {},
            "fact_hyperedges": {},
            "episode_hyperedges": {},
            "created_at": datetime.now().isoformat(),
        }

        for i, episode in enumerate(episodes):
            ep_id = episode.get("event_id", f"ep_{i}")
            hypergraph["episodes"][ep_id] = episode

        return hypergraph

    def build_decision_hypergraph(
        self,
        decisions: List[DecisionNode],
    ) -> Dict[str, Any]:
        topics: Dict[str, Dict] = {}
        decision_nodes: Dict[str, Dict] = {}
        hyperedges: List[Dict] = []

        for d in decisions:
            tid = d.topic_id or "general"
            if tid not in topics:
                topics[tid] = {
                    "id": tid,
                    "title": tid,
                    "decision_count": 0,
                    "decisions": [],
                }
            topics[tid]["decision_count"] += 1
            topics[tid]["decisions"].append(d.sid)

            decision_nodes[d.sid] = {
                "sid": d.sid,
                "summary": d.summary,
                "status": d.status.value,
                "impact_level": d.impact_level.value,
                "topic_id": tid,
                "tags": d.tags,
            }

            for rel in d.relations:
                hyperedges.append({
                    "source": d.sid,
                    "target": rel.target_id,
                    "type": rel.type.value,
                    "description": rel.description,
                })

        return {
            "topics": topics,
            "decisions": decision_nodes,
            "hyperedges": hyperedges,
            "decision_count": len(decisions),
            "topic_count": len(topics),
            "built_at": datetime.now().isoformat(),
        }