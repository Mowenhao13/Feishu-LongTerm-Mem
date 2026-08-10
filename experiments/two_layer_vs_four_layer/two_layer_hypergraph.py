"""两层超图变体 — 简化版 Hypergraph（无 Hyperedge）

对应 LAB-52 的设计：移除 FactHyperedge/EpisodeHyperedge/DecisionHyperedge，
只保留 Episode（Raw Data Layer）和 Decision + Topic（Knowledge Layer）。

对比 baseline 的四层结构（L0-L3），本变体：
- 移除 L0 DecisionHyperedge
- 移除 L1 FactNode + FactHyperedge
- 移除 L2 EpisodeHyperedge（但保留 EpisodeNode）
- L3 TopicNode 保留，但不再通过 EpisodeHyperedge 连接
- Episode 直接通过 topic_id 关联到 Topic
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.structure import EpisodeNode, TopicNode


class TwoLayerHypergraph(BaseModel):
    """简化两层超图

    Raw Data Layer:
      - EpisodeNode: 来自 IM 消息的对话片段

    Knowledge Layer:
      - DecisionNode: 决策节点（prescriptive knowledge），使用 dict 存储避免 forward ref
      - TopicNode: 主题节点（topic-level knowledge）

    关系：
      Episode → (topic_id) → Topic         — 直接引用，无 Hyperedge
      Decision → (topic_id) → Topic        — 直接引用
      Decision.episode_ids → Episode       — 来源关联
    """

    episodes: Dict[str, EpisodeNode] = Field(
        default_factory=dict,
        description="Episode 节点字典",
    )
    decisions: Dict[str, Any] = Field(
        default_factory=dict,
        description="决策节点字典（存 DecisionNode 的 dict 表示）",
    )
    topics: Dict[str, TopicNode] = Field(
        default_factory=dict,
        description="Topic 节点字典",
    )

    def to_dict(self) -> Dict[str, Any]:
        decisions_dict = {}
        for k, v in self.decisions.items():
            if hasattr(v, "model_dump"):
                decisions_dict[k] = v.model_dump(mode="json")
            else:
                decisions_dict[k] = v
        return {
            "episodes": {k: v.model_dump(mode="json") for k, v in self.episodes.items()},
            "decisions": decisions_dict,
            "topics": {k: v.model_dump(mode="json") for k, v in self.topics.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TwoLayerHypergraph":
        return cls(
            episodes={k: EpisodeNode(**v) for k, v in data.get("episodes", {}).items()},
            decisions=data.get("decisions", {}),
            topics={k: TopicNode(**v) for k, v in data.get("topics", {}).items()},
        )

    def get_stats(self) -> Dict[str, int]:
        return {
            "episodes": len(self.episodes),
            "decisions": len(self.decisions),
            "topics": len(self.topics),
            "total_nodes": len(self.episodes) + len(self.decisions) + len(self.topics),
        }

    def add_episode(
        self,
        episode_id: str,
        *,
        user_id_list: Optional[List[str]] = None,
        original_data: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[datetime] = None,
        summary: str = "",
        participants: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        subject: str = "",
        episode_description: str = "",
    ) -> EpisodeNode:
        node = EpisodeNode(
            id=episode_id,
            user_id_list=user_id_list or [],
            original_data=original_data or [],
            timestamp=timestamp or datetime.now(),
            summary=summary,
            participants=participants,
            keywords=keywords or [],
            subject=subject,
            episode_description=episode_description,
            hyperedge={},
            fact_hyperedge_id="",
        )
        self.episodes[episode_id] = node
        return node

    def add_decision(
        self,
        decision_id: str,
        *,
        title: str = "",
        content: str = "",
        confidence: float = 0.8,
        status=None,
        proposer: str = "",
        executor: str = "",
        impact_level: str = "minor",
        rationale: str = "",
        episode_ids: Optional[List[str]] = None,
        topic_id: str = "",
    ) -> Dict[str, Any]:
        from src.node.types import DecisionStatus
        s = (status or DecisionStatus.PENDING).value if hasattr((status or DecisionStatus.PENDING), "value") else str(status or "pending")
        node = {
            "sid": decision_id,
            "summary": title,
            "content": content,
            "confidence": confidence,
            "status": s,
            "proposer": proposer,
            "executor": executor,
            "impact_level": impact_level,
            "rationale": rationale,
            "episode_ids": episode_ids or [],
            "topic_id": topic_id,
        }
        self.decisions[decision_id] = node
        return node

    def add_topic(
        self,
        topic_id: str,
        *,
        title: str,
        summary: str = "",
        episode_ids: Optional[List[str]] = None,
        participants: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> TopicNode:
        node = TopicNode(
            id=topic_id,
            title=title,
            summary=summary,
            episode_ids=episode_ids or [],
            timestamp=datetime.now(),
            user_id_list=[],
            participants=participants,
            keywords=keywords or [],
            episode_hyperedge_id="",
        )
        self.topics[topic_id] = node
        return node

    def get_all_decisions(self) -> List[Dict[str, Any]]:
        return list(self.decisions.values())

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        return self.decisions.get(decision_id)

    def get_decisions_by_topic(self, topic_id: str) -> List[Dict[str, Any]]:
        return [d for d in self.decisions.values() if d.get("topic_id") == topic_id]

    def get_episodes_by_topic(self, topic_id: str) -> List[EpisodeNode]:
        return [ep for ep in self.episodes.values() if ep.subject == topic_id or
                any(topic_id in (ep.keywords or []))]

    def get_topic(self, topic_id: str) -> Optional[TopicNode]:
        return self.topics.get(topic_id)

    def validate(self) -> List[str]:
        """验证两层超图的一致性"""
        errors: List[str] = []
        known_topics = set(self.topics.keys())

        for ep_id, ep in self.episodes.items():
            if ep.subject and ep.subject not in known_topics:
                errors.append(f"Episode '{ep_id}' references unknown topic '{ep.subject}'")

        for dec_id, dec in self.decisions.items():
            if isinstance(dec, dict):
                tid = dec.get("topic_id", "")
                if tid and tid not in known_topics:
                    errors.append(f"Decision '{dec_id}' references unknown topic '{tid}'")

        return errors