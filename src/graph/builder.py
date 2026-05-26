from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel, Relation, RelationType
from src.structure import (
    EpisodeHyperedge,
    EpisodeNode,
    EpisodeRole,
    Hypergraph,
    TopicNode,
)
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
    ) -> Hypergraph:
        """从 episode 列表构建超图

        输入是 Episode.to_dict() 的列表。
        每个 episode dict 应包含: id, chat_id, participants, full_text,
        start_time, end_time, messages, has_decision_signal, topic

        输出完整 Hypergraph（L2 Episode + L3 Topic 两层）。
        """
        hypergraph = Hypergraph()

        chat_groups: Dict[str, List[Dict[str, Any]]] = {}
        for ep in episodes:
            chat_id = ep.get("chat_id", "default")
            chat_groups.setdefault(chat_id, []).append(ep)

        for chat_id, chat_eps in chat_groups.items():
            episode_ids: List[str] = []

            for ep_data in chat_eps:
                ep_id = ep_data.get("id", f"ep_{hashlib.md5(str(ep_data).encode()).hexdigest()[:12]}")
                participants = ep_data.get("participants", [])
                full_text = ep_data.get("full_text", "")
                start_time = ep_data.get("start_time", 0.0)
                timestamp_dt = datetime.fromtimestamp(start_time) if start_time else datetime.now()
                topic_hint = ep_data.get("topic", "")

                episode_node = EpisodeNode(
                    id=ep_id,
                    user_id_list=participants,
                    original_data=ep_data.get("messages", []),
                    timestamp=timestamp_dt,
                    summary=full_text[:200] if full_text else "",
                    participants=participants,
                    keywords=[],
                    subject=topic_hint,
                    episode_description="",
                    hyperedge={},
                    fact_hyperedge_id="",
                )
                hypergraph.episodes[ep_id] = episode_node
                episode_ids.append(ep_id)

            if not episode_ids:
                continue

            topic_id = f"topic_{_short_hash(chat_id)}_{int(time.time())}"
            hyperedge_id = f"eh_{_short_hash(chat_id)}_{int(time.time())}"

            relation = {ep_id: EpisodeRole.DEVELOPING.value for ep_id in episode_ids}
            episode_hyperedge = EpisodeHyperedge(
                id=hyperedge_id,
                relation=relation,
                topic_node_id=topic_id,
                created_at=datetime.now(),
                coherence_score=0.8,
            )
            hypergraph.episode_hyperedges[hyperedge_id] = episode_hyperedge

            for ep_id in episode_ids:
                if ep_id in hypergraph.episodes:
                    hypergraph.episodes[ep_id].hyperedge[hyperedge_id] = EpisodeRole.DEVELOPING.value

            topic_node = TopicNode(
                id=topic_id,
                title=f"Chat {_short_hash(chat_id)} Discussion",
                summary=f"Discussion with {len(episode_ids)} episodes from chat {_short_hash(chat_id)}",
                episode_ids=episode_ids,
                timestamp=datetime.now(),
                user_id_list=[],
                episode_hyperedge_id=hyperedge_id,
            )
            hypergraph.topics[topic_id] = topic_node

            if llm_provider:
                self._enrich_topic_with_llm(hypergraph, topic_id, episode_ids, llm_provider)

        validation_errors = hypergraph.validate_bidirectional_links()
        if validation_errors:
            logger.warning("[Hypergraph] %d bidirectional link errors: %s",
                          sum(len(v) for v in validation_errors.values()),
                          validation_errors)

        return hypergraph

    def _enrich_topic_with_llm(
        self,
        hypergraph: Hypergraph,
        topic_id: str,
        episode_ids: List[str],
        llm: Any,
    ) -> None:
        """用 LLM 丰富 topic 的标题和关键词"""
        try:
            episode_texts = []
            for ep_id in episode_ids:
                ep_node = hypergraph.episodes.get(ep_id)
                if ep_node and ep_node.summary:
                    episode_texts.append(f"[{ep_id}]: {ep_node.summary[:100]}")

            if not episode_texts:
                return

            prompt = f"""根据以下对话片段总结讨论主题：

{chr(10).join(episode_texts)}

返回 JSON：{{"title": "简洁的主题标题（10字内）", "summary": "一句话总结讨论内容", "keywords": ["关键词1", "关键词2"]}}"""

            if hasattr(llm, "generate"):
                resp = llm.generate(prompt, response_format={"type": "json_object"})
                result = json.loads(resp) if isinstance(resp, str) else resp
            elif hasattr(llm, "chat"):
                resp = llm.chat(prompt)
                result = json.loads(resp) if isinstance(resp, str) else resp
            else:
                return

            topic_node = hypergraph.topics.get(topic_id)
            if topic_node:
                topic_node.title = result.get("title", topic_node.title)
                topic_node.summary = result.get("summary", topic_node.summary)
                topic_node.keywords = result.get("keywords", [])

        except Exception as e:
            logger.warning("[Hypergraph] LLM topic enrichment failed: %s", str(e)[:60])

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


def _short_hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:8]