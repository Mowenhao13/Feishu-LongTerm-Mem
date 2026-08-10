"""两层超图构建器 — 简化的 Episode → Topic 结构（无 Hyperedge）

对应 LAB-52 的设计简化：
- 输入 Episode dict → 输出 TwoLayerHypergraph
- 不创建任何 Hyperedge
- Episode 通过 subject/topic 字段直接关联到 Topic
- 增量合并逻辑：按 chat_id 查找已有 topic
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.node.types import DecisionStatus
from src.structure import EpisodeNode, TopicNode

from .two_layer_hypergraph import TwoLayerHypergraph

logger = logging.getLogger(__name__)


def _short_hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:8]


class TwoLayerBuilder:
    """两层超图构建器 — 简化版

    从 Episode dict 列表构建 TwoLayerHypergraph。
    每个 episode dict 应包含:
      id / chat_id / participants / full_text / start_time / end_time / messages / topic / ...
    """

    def __init__(self, llm_provider: Optional[Any] = None) -> None:
        self._llm = llm_provider

    def build_from_episodes(
        self,
        episodes: List[Dict[str, Any]],
        llm_provider: Optional[Any] = None,
        existing_hypergraph: Optional[TwoLayerHypergraph] = None,
    ) -> TwoLayerHypergraph:
        """从 episode 列表构建两层超图

        Args:
            episodes: Episode.to_dict() 的列表
            llm_provider: 用于 LLM 增强的可选 provider
            existing_hypergraph: 已有超图（增量合并用）

        Returns:
            TwoLayerHypergraph
        """
        if existing_hypergraph is not None:
            hg = existing_hypergraph
        else:
            hg = TwoLayerHypergraph()

        chat_groups: Dict[str, List[Dict[str, Any]]] = {}
        for ep in episodes:
            chat_id = ep.get("chat_id", "default")
            ep_id = ep.get("id", "")
            if ep_id and ep_id in hg.episodes:
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
                    hyperedge={},
                    fact_hyperedge_id="",
                )
                hg.episodes[ep_id] = episode_node
                episode_ids.append(ep_id)

            if not episode_ids:
                continue

            # 按 chat_id 查找已有 topic（无 Hyperedge 版本）
            existing_topic_id = self._find_topic_by_chat(hg, chat_id, episode_ids)

            if existing_topic_id is not None:
                topic_node = hg.topics[existing_topic_id]
                for ep_id in episode_ids:
                    if ep_id not in topic_node.episode_ids:
                        topic_node.episode_ids.append(ep_id)
                    # 两层结构中 episode 通过 subject 关联 topic
                    if ep_id in hg.episodes:
                        hg.episodes[ep_id].subject = topic_node.title

                if llm_provider or self._llm:
                    self._enrich_topic_with_llm(hg, existing_topic_id, topic_node.episode_ids,
                                                llm_provider or self._llm)

                logger.debug("Merged %d episode(s) into existing topic %s",
                             len(episode_ids), existing_topic_id[:12])
                continue

            # 无匹配 → 创建新 topic
            topic_id = f"topic_{_short_hash(chat_id)}_{int(time.time())}"
            topic_node = TopicNode(
                id=topic_id,
                title=f"Chat {_short_hash(chat_id)} Discussion",
                summary=f"Discussion with {len(episode_ids)} episodes from chat {_short_hash(chat_id)}",
                episode_ids=episode_ids,
                timestamp=datetime.now(),
                user_id_list=[],
                episode_hyperedge_id="",  # 两层结构中不使用
            )
            hg.topics[topic_id] = topic_node

            # 将 episode 的 subject 设为 topic title
            for ep_id in episode_ids:
                if ep_id in hg.episodes:
                    hg.episodes[ep_id].subject = topic_node.title

            if llm_provider or self._llm:
                self._enrich_topic_with_llm(hg, topic_id, episode_ids,
                                            llm_provider or self._llm)

        return hg

    @staticmethod
    def _find_topic_by_chat(
        hg: TwoLayerHypergraph,
        chat_id: str,
        new_episode_ids: List[str],
    ) -> Optional[str]:
        """按 chat_id 查找已有 topic（基于 participant 重叠）"""
        new_participants: set = set()
        for ep_id in new_episode_ids:
            ep = hg.episodes.get(ep_id)
            if ep:
                new_participants.update(ep.user_id_list)

        for ep_id, ep_node in hg.episodes.items():
            if ep_id in new_episode_ids:
                continue
            chat_participants = set(ep_node.user_id_list)
            if not chat_participants:
                continue
            if new_participants and chat_participants & new_participants:
                # 找到该 episode 所属的 topic（两层结构中通过 subject 关联）
                topic_title = ep_node.subject
                if topic_title:
                    for tid, t in hg.topics.items():
                        if t.title == topic_title:
                            return tid
        return None

    def _enrich_topic_with_llm(
        self,
        hg: TwoLayerHypergraph,
        topic_id: str,
        episode_ids: List[str],
        llm: Any,
    ) -> None:
        """用 LLM 丰富 topic 的标题和关键词"""
        try:
            episode_texts = []
            for ep_id in episode_ids:
                ep_node = hg.episodes.get(ep_id)
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

            topic_node = hg.topics.get(topic_id)
            if topic_node:
                topic_node.title = result.get("title", topic_node.title)
                topic_node.summary = result.get("summary", topic_node.summary)
                topic_node.keywords = result.get("keywords", [])

        except Exception as e:
            logger.warning("[TwoLayer] LLM topic enrichment failed: %s", str(e)[:60])