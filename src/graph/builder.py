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
    EpisodeNode,
    Hypergraph,
    TopicNode,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HypergraphBuilder:
    """Hypergraph builder

    Builds a simplified two-layer hypergraph from episodes:
    - Raw Data Layer: EpisodeNode
    - Knowledge Layer: TopicNode + DecisionNode

    No hyperedge intermediaries — episodes link directly to topics.
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
            "episodes": {},
            "decisions": {},
            "created_at": datetime.now().isoformat(),
        }
        return hypergraph

    def build_from_episodes(
        self,
        episodes: List[Dict[str, Any]],
        llm_provider: Optional[Any] = None,
        existing_hypergraph: Optional[Hypergraph] = None,
    ) -> Hypergraph:
        """Build or incrementally update hypergraph from episode dicts.

        Each episode dict should contain: id, chat_id, participants, full_text,
        start_time, end_time, messages, has_decision_signal, topic.

        Produces Hypergraph with EpisodeNode (raw data) + TopicNode (knowledge)
        linked directly (no EpisodeHyperedge intermediaries).

        When existing_hypergraph is provided, performs incremental merge:
        - Skips already-existing episode_ids
        - New episodes match existing topics by chat participant overlap
        """
        if existing_hypergraph is not None:
            hypergraph = existing_hypergraph
        else:
            hypergraph = Hypergraph()

        chat_groups: Dict[str, List[Dict[str, Any]]] = {}
        for ep in episodes:
            chat_id = ep.get("chat_id", "default")
            ep_id = ep.get("id", "")
            if ep_id and ep_id in hypergraph.episodes:
                logger.debug("Episode %s already in hypergraph, skipping", ep_id[:12])
                continue
            chat_groups.setdefault(chat_id, []).append(ep)

        for chat_id, chat_eps in chat_groups.items():
            episode_ids: List[str] = []

            for ep_data in chat_eps:
                ep_id = ep_data.get("id", f"ep_{_short_hash(str(ep_data))}_{int(time.time())}")
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
                    topic_id="",
                )
                hypergraph.episodes[ep_id] = episode_node
                episode_ids.append(ep_id)

            if not episode_ids:
                continue

            # Try to match existing topic by chat participant overlap
            existing_topic_id = self._find_topic_for_chat(hypergraph, chat_id, episode_ids)
            if existing_topic_id is not None:
                topic_node = hypergraph.topics[existing_topic_id]
                for ep_id in episode_ids:
                    if ep_id in hypergraph.episodes:
                        hypergraph.episodes[ep_id].topic_id = existing_topic_id
                    if ep_id not in topic_node.episode_ids:
                        topic_node.episode_ids.append(ep_id)

                if llm_provider:
                    self._enrich_topic_with_llm(hypergraph, existing_topic_id, topic_node.episode_ids, llm_provider)

                logger.debug("Merged %d episode(s) into existing topic %s", len(episode_ids), existing_topic_id[:12])
                continue

            # No match — create new topic
            topic_id = f"topic_{_short_hash(chat_id)}_{int(time.time())}"

            # Assign topic_id to episodes
            for ep_id in episode_ids:
                if ep_id in hypergraph.episodes:
                    hypergraph.episodes[ep_id].topic_id = topic_id

            topic_node = TopicNode(
                id=topic_id,
                title=f"Chat {_short_hash(chat_id)} Discussion",
                summary=f"Discussion with {len(episode_ids)} episodes from chat {_short_hash(chat_id)}",
                episode_ids=episode_ids,
                timestamp=datetime.now(),
                user_id_list=[],
            )
            hypergraph.topics[topic_id] = topic_node

            if llm_provider:
                self._enrich_topic_with_llm(hypergraph, topic_id, episode_ids, llm_provider)

        return hypergraph

    @staticmethod
    def _find_topic_for_chat(
        hypergraph: Hypergraph,
        chat_id: str,
        new_episode_ids: List[str],
    ) -> Optional[str]:
        """Find existing topic belonging to the same chat by participant overlap."""
        new_participants: set = set()
        for ep_id in new_episode_ids:
            ep = hypergraph.episodes.get(ep_id)
            if ep:
                new_participants.update(ep.user_id_list)

        for ep_id, ep_node in hypergraph.episodes.items():
            if ep_id in new_episode_ids:
                continue
            chat_participants = set(ep_node.user_id_list)
            if not chat_participants:
                continue
            if new_participants and chat_participants & new_participants:
                if ep_node.topic_id and ep_node.topic_id in hypergraph.topics:
                    return ep_node.topic_id

        return None

    def _enrich_topic_with_llm(
        self,
        hypergraph: Hypergraph,
        topic_id: str,
        episode_ids: List[str],
        llm: Any,
    ) -> None:
        """Enrich topic title and keywords via LLM."""
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
        relations: List[Dict] = []

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
                relations.append({
                    "source": d.sid,
                    "target": rel.target_id,
                    "type": rel.type.value,
                    "description": rel.description,
                })

        return {
            "topics": topics,
            "decisions": decision_nodes,
            "relations": relations,
            "decision_count": len(decisions),
            "topic_count": len(topics),
            "built_at": datetime.now().isoformat(),
        }


def _short_hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:8]