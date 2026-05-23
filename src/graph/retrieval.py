from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.node.node import DecisionNode
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    queries: List[str] = field(default_factory=list)
    topics: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[DecisionNode] = field(default_factory=list)
    facts: List[Dict[str, Any]] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    total_count: int = 0


class HierarchicalRetriever:
    """层次化检索器

    整合 ref/main stage4 的核心逻辑：
    3 层检索（Topic → Episode/Decision → Fact），支持 BM25 + 向量融合。
    """

    def __init__(
        self,
        memory_graph: Any = None,
        bm25_index: Any = None,
        embedding_provider: Any = None,
    ) -> None:
        self._memory_graph = memory_graph
        self._bm25 = bm25_index
        self._embedding = embedding_provider

    def retrieve(
        self,
        query: str,
        top_k_topics: int = 5,
        top_k_decisions: int = 10,
        top_k_facts: int = 15,
        project: str = "feishu-mem",
    ) -> RetrievalResult:
        result = RetrievalResult(queries=[query])

        if self._memory_graph is None:
            logger.warning("MemoryGraph not available, skipping retrieval")
            return result

        matched_decisions = self._memory_graph.search_by_keywords(query)

        topic_groups: Dict[str, List[DecisionNode]] = {}
        for d in matched_decisions:
            tid = d.topic_id or "general"
            if tid not in topic_groups:
                topic_groups[tid] = []
            topic_groups[tid].append(d)

        for tid, decisions in topic_groups.items():
            result.topics.append({
                "id": tid,
                "title": tid,
                "match_count": len(decisions),
                "decisions": [d.sid for d in decisions[:top_k_decisions]],
            })
            result.decisions.extend(decisions[:top_k_decisions])

        seen: set = set()
        unique_decisions: List[DecisionNode] = []
        for d in result.decisions:
            if d.sid not in seen:
                seen.add(d.sid)
                unique_decisions.append(d)
        result.decisions = unique_decisions[:top_k_decisions * top_k_topics]
        result.total_count = len(unique_decisions)

        return result

    def retrieve_from_graph(
        self,
        memory_graph: Any,
        query: str,
        top_k: int = 10,
    ) -> List[DecisionNode]:
        self._memory_graph = memory_graph
        result = self.retrieve(query, top_k_decisions=top_k)
        return result.decisions

    def format_result(self, result: RetrievalResult) -> str:
        lines: List[str] = []
        lines.append(f"Query: {', '.join(result.queries)}")
        lines.append(f"Found {result.total_count} decisions across {len(result.topics)} topics")
        lines.append("")

        for topic in result.topics[:5]:
            lines.append(f"  Topic: {topic['title']} ({topic['match_count']} matches)")
            for d in result.decisions:
                if d.topic_id == topic["id"]:
                    lines.append(f"    [{d.status.value}] {d.summary}")

        return "\n".join(lines)

    @staticmethod
    def reciprocal_rank_fusion(
        results_list: List[List[Tuple[Dict, float]]],
        top_n: int,
        k: int = 60,
    ) -> List[Tuple[Dict, float]]:
        doc_scores: Dict[str, Dict] = {}

        for results in results_list:
            for rank, (doc, _) in enumerate(results):
                doc_id = doc.get("id") or str(hash(str(doc)))
                rrf_score = 1.0 / (k + rank + 1)
                if doc_id in doc_scores:
                    doc_scores[doc_id]["score"] += rrf_score
                else:
                    doc_scores[doc_id] = {"doc": doc, "score": rrf_score}

        sorted_results = sorted(
            [(item["doc"], item["score"]) for item in doc_scores.values()],
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_results[:top_n]