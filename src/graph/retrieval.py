from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.node.node import DecisionNode
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """Result container for a single retrieval pass.

    Per-decision scores are stored as parallel lists in ``decision_scores``,
    keyed by channel name (e.g. "embedding", "bm25", "entity_graph") — each list
    aligns 1:1 with ``decisions``.
    """

    queries: List[str] = field(default_factory=list)
    topics: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[DecisionNode] = field(default_factory=list)
    facts: List[Dict[str, Any]] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    total_count: int = 0
    decision_scores: Dict[str, List[float]] = field(default_factory=dict)


class HierarchicalRetriever:
    """层次化检索器

    整合 ref/main stage4 的核心逻辑：
    3 层检索（Topic → Episode/Decision → Fact），支持 BM25 + 向量 + 图结构实体融合。
    """

    def __init__(
        self,
        memory_graph: Any = None,
        bm25_index: Any = None,
        embedding_provider: Any = None,
        reranker_provider: Any = None,
        neo4j_client: Any = None,
        query_entity_extractor: Any = None,
        retrieval_type: str = "rrf",
        use_reranker: bool = False,
        top_k_decisions: int = 10,
    ) -> None:
        self._memory_graph = memory_graph
        self._bm25 = bm25_index
        self._embedding = embedding_provider
        self._reranker = reranker_provider
        self._neo4j_client = neo4j_client
        self._entity_extractor = query_entity_extractor
        self._retrieval_type = retrieval_type
        self._use_reranker = use_reranker
        self._top_k_decisions = top_k_decisions

    def retrieve(
        self,
        query: str,
        top_k_topics: int = 5,
        top_k_decisions: int = 10,
        top_k_facts: int = 15,
        project: str = "feishu-mem",
        retrieval_type: Optional[str] = None,
        use_reranker: Optional[bool] = None,
    ) -> RetrievalResult:
        result = RetrievalResult(queries=[query])

        if self._memory_graph is None:
            logger.warning("MemoryGraph not available, skipping retrieval")
            return result

        rtype = retrieval_type or self._retrieval_type
        do_rerank = use_reranker if use_reranker is not None else self._use_reranker

        # ── Step 1: Graph entity signal (Neo4j entity→decision traversal) ─
        entity_list: List[Tuple[Dict, float]] = []
        if self._neo4j_client is not None and self._entity_extractor is not None and rtype in ("entity_graph", "rrf"):
            try:
                entity_list = self._entity_graph_search(query, top_k_decisions * 3)
            except Exception as e:
                logger.warning("[Retrieval] Entity graph search failed, skipping: %s", str(e)[:80])

        # ── Step 2: Dense retrieval via Embedding ──────────────────────────
        vector_list: List[Tuple[Dict, float]] = []
        if self._embedding is not None and rtype in ("vector", "rrf"):
            try:
                vector_list = self._vector_search(query, top_k_decisions * 3)
            except Exception as e:
                logger.warning("[Retrieval] Vector search failed, skipping: %s", str(e)[:80])

        # ── Step 3: Sparse retrieval via BM25 ──────────────────────────────
        bm25_list: List[Tuple[Dict, float]] = []
        if self._bm25 is not None and rtype in ("bm25", "rrf"):
            try:
                bm25_list = self._bm25_search(query, top_k_decisions * 3)
            except Exception as e:
                logger.warning("[Retrieval] BM25 search failed, skipping: %s", str(e)[:80])

        # ── Step 4: Fusion / selection ─────────────────────────────────────
        fused: List[Tuple[Dict, float]] = []
        if rtype == "rrf":
            # Build the list of non-empty signal lists for RRF
            signals = [lst for lst in [entity_list, vector_list, bm25_list] if lst]
            if len(signals) >= 2:
                fused = self.reciprocal_rank_fusion(
                    signals,
                    top_n=top_k_decisions * top_k_topics,
                    k=60,
                )
                logger.info(
                    "[Retrieval] RRF fused: entity=%d vector=%d bm25=%d → %d",
                    len(entity_list), len(vector_list), len(bm25_list), len(fused),
                )
            elif len(signals) == 1:
                fused = signals[0][: top_k_decisions * top_k_topics]
        elif rtype == "vector" and vector_list:
            fused = vector_list[:top_k_decisions * top_k_topics]
            logger.info("[Retrieval] Vector-only: %d results", len(fused))
        elif rtype == "bm25" and bm25_list:
            fused = bm25_list[:top_k_decisions * top_k_topics]
            logger.info("[Retrieval] BM25-only: %d results", len(fused))
        elif rtype == "entity_graph" and entity_list:
            fused = entity_list[:top_k_decisions * top_k_topics]
            logger.info("[Retrieval] Entity-graph-only: %d results", len(fused))
        else:
            # Fallback: keyword 兜底
            try:
                keyword_decisions = self._memory_graph.search_by_keywords(query)
                fused = [
                    ({"id": d.sid, "summary": d.summary, "full_text": d.full_text}, 0.0)
                    for d in keyword_decisions
                ][:top_k_decisions * top_k_topics]
                logger.info("[Retrieval] Fallback to keyword: %d results", len(fused))
            except Exception as e:
                logger.warning("[Retrieval] Keyword fallback failed: %s", str(e)[:80])

        # ── Step 5: Build DecisionNode list from fused results ────────────
        decisions: List[DecisionNode] = []
        seen_ids: set = set()
        # Build lookups for decision resolution — use all decisions from memory graph
        node_map: Dict[str, DecisionNode] = {}
        if self._memory_graph is not None:
            for d in self._memory_graph.get_all_decisions():
                node_map[d.sid] = d

        for doc_dict, score in fused:
            doc_id = doc_dict.get("id", "")
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            node = node_map.get(doc_id)
            if node is not None:
                decisions.append(node)

        # ── Step 6: Reranker refinement (optional) ─────────────────────────
        if do_rerank and self._reranker is not None and decisions:
            try:
                decisions = self._rerank_decisions(query, decisions, top_k_decisions * top_k_topics)
            except Exception as e:
                logger.warning("[Retrieval] Reranker failed, skipping: %s", str(e)[:80])

        # ── Step 7: Build topic groups ────────────────────────────────────
        topic_groups: Dict[str, List[DecisionNode]] = {}
        for d in decisions:
            tid = d.topic_id or "general"
            if tid not in topic_groups:
                topic_groups[tid] = []
            topic_groups[tid].append(d)

        for tid, topic_decisions in topic_groups.items():
            result.topics.append({
                "id": tid,
                "title": tid,
                "match_count": len(topic_decisions),
                "decisions": [d.sid for d in topic_decisions[:top_k_decisions]],
            })
            result.decisions.extend(topic_decisions[:top_k_decisions])

        # Deduplicate across topics
        seen: set = set()
        unique_decisions: List[DecisionNode] = []
        for d in result.decisions:
            if d.sid not in seen:
                seen.add(d.sid)
                unique_decisions.append(d)
        result.decisions = unique_decisions[:top_k_decisions * top_k_topics]
        result.total_count = len(unique_decisions)

        # Populate channel-level scores
        result.scores["retrieval_type"] = float(len(vector_list)) if rtype == "vector" else 0.0
        result.scores["entity_count"] = float(len(entity_list))
        result.scores["vector_count"] = float(len(vector_list))
        result.scores["bm25_count"] = float(len(bm25_list))
        result.scores["reranker_applied"] = 1.0 if (do_rerank and self._reranker is not None and decisions) else 0.0

        return result

    def _entity_graph_search(
        self,
        query: str,
        top_n: int,
    ) -> List[Tuple[Dict, float]]:
        """Extract entity names from the query, then find related decisions
        via the Neo4j graph (Entity→MENTIONS→Episode→REFERENCES→Decision).

        Returns scored results compatible with RRF.
        """
        if self._entity_extractor is None or self._neo4j_client is None:
            return []

        # 1. Extract entity names from the query (single light LLM call)
        entity_names = self._run_entity_extraction(query)
        if not entity_names:
            logger.debug("[Retrieval] No entities extracted from query")
            return []

        # 2. Search Neo4j for decisions related to these entities
        raw_results = self._run_neo4j_search(entity_names, top_n)
        if not raw_results:
            logger.debug("[Retrieval] No decisions found for entities: %s", entity_names)
            return []

        # 3. Score by inverse rank for RRF compatibility
        scored: List[Tuple[Dict, float]] = []
        for rank, item in enumerate(raw_results):
            score = 1.0 / (rank + 1)
            scored.append((
                {
                    "id": item.get("sid") or item.get("id", ""),
                    "summary": item.get("summary", ""),
                    "full_text": item.get("full_text", ""),
                },
                score,
            ))

        logger.info(
            "[Retrieval] Entity graph search: entities=%s → %d decisions",
            entity_names[:5], len(scored),
        )
        return scored

    def _run_entity_extraction(self, query: str) -> List[str]:
        """Run the lightweight entity extractor synchronously.

        The extractor's ``extract()`` is async.  When called from a sync
        context that may or may not have a running event loop, we use a
        fresh thread + new loop to avoid blocking.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run, self._entity_extractor.extract(query)
            )
            return future.result(timeout=10)

    def _run_neo4j_search(
        self, entity_names: List[str], limit: int
    ) -> List[Dict[str, Any]]:
        """Run the Neo4j search synchronously (same thread+loop pattern)."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                self._neo4j_client.search_decisions_by_entity_names(
                    entity_names, limit=limit
                ),
            )
            return future.result(timeout=10)

    def _vector_search(
        self,
        query: str,
        top_n: int,
    ) -> List[Tuple[Dict, float]]:
        """Embed the query and compare against all active decisions (batched)."""
        all_decisions = self._memory_graph.get_all_decisions()
        texts: List[str] = []
        idx_map: List[DecisionNode] = []
        for d in all_decisions:
            text = (d.summary or "") + " " + (d.full_text or "")
            text = text.strip()
            if text:
                texts.append(text)
                idx_map.append(d)

        if not texts:
            return []

        query_vec = np.array(self._embedding.embed([query])[0])
        doc_vecs = np.array(self._embedding.embed(texts))

        # Cosine similarity (batched)
        dot_product = np.dot(doc_vecs, query_vec)
        query_norm = np.linalg.norm(query_vec)
        doc_norms = np.linalg.norm(doc_vecs, axis=1)
        denominator = query_norm * doc_norms
        denominator[denominator == 0] = 1e-9
        scores = dot_product / denominator

        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)
        return [
            ({"id": idx_map[i].sid, "summary": idx_map[i].summary, "full_text": idx_map[i].full_text}, float(s))
            for i, s in indexed[:top_n]
        ]

    def _bm25_search(
        self,
        query: str,
        top_n: int,
    ) -> List[Tuple[Dict, float]]:
        """Run BM25 sparse retrieval and return scored results.

        BM25Indexer.search() returns dicts without native scores, so we
        derive scores inversely from rank order for RRF compatibility.
        """
        raw = self._bm25.search(query, top_n=top_n)
        scored: List[Tuple[Dict, float]] = []
        for rank, item in enumerate(raw):
            doc_id = item.get("id", "")
            # Use inverse rank as a surrogate score so RRF has signal
            score = 1.0 / (rank + 1)
            scored.append((
                {"id": doc_id, "summary": item.get("data", {}).get("summary", "")},
                score,
            ))
        return scored

    def _rerank_decisions(
        self,
        query: str,
        decisions: List[DecisionNode],
        top_n: int,
    ) -> List[DecisionNode]:
        """Re-rank decisions using the Reranker provider."""
        docs = [d.summary or d.full_text or "" for d in decisions]
        scores = self._reranker.rerank_single(query, docs)
        paired = list(zip(decisions, scores))
        paired.sort(key=lambda x: x[1], reverse=True)
        reranked = [d for d, _ in paired[:top_n]]
        return reranked

    def retrieve_from_graph(
        self,
        memory_graph: Any,
        query: str,
        top_k: int = 10,
    ) -> List[DecisionNode]:
        self._memory_graph = memory_graph
        result = self.retrieve(query, top_k_decisions=top_k)
        return result.decisions

    # ─── Hypergraph embedding retrieval ────────────────────

    def retrieve_hypergraph_embedding(
        self,
        query: str,
        hypergraph_embedding: Any,
        hypergraph: Any,
        top_k_topics: int = 5,
        top_k_episodes: int = 10,
        top_k_facts: int = 15,
    ) -> RetrievalResult:
        """Retrieve hypergraph content by embedding similarity.

        Encodes the query, then finds the nearest topics, episodes, and facts
        from the pre-computed HypergraphEmbedding object.
        """
        result = RetrievalResult(queries=[query])

        if self._embedding is None:
            logger.warning("EmbeddingProvider not set, skipping hypergraph retrieval")
            return result

        if hypergraph_embedding is None:
            logger.warning("HypergraphEmbedding not available, skipping hypergraph retrieval")
            return result

        try:
            query_vec = np.array(self._embedding.embed([query])[0])

            # Score topics by embedding similarity
            topic_scores: List[tuple] = []
            for tid, t_emb in hypergraph_embedding.topics.items():
                if t_emb.size == 0:
                    continue
                sim = float(np.dot(t_emb, query_vec) / (np.linalg.norm(t_emb) * np.linalg.norm(query_vec) + 1e-9))
                topic_scores.append((tid, sim))
            topic_scores.sort(key=lambda x: x[1], reverse=True)

            for tid, score in topic_scores[:top_k_topics]:
                topic_node = hypergraph.topics.get(tid) if hasattr(hypergraph, "topics") else None
                if topic_node is None:
                    continue
                result.topics.append({
                    "id": tid,
                    "title": getattr(topic_node, "title", ""),
                    "summary": getattr(topic_node, "summary", ""),
                    "score": round(score, 4),
                })

            # Score episodes by embedding similarity
            episode_scores: List[tuple] = []
            for eid, e_emb in hypergraph_embedding.episodes.items():
                if e_emb.size == 0:
                    continue
                sim = float(np.dot(e_emb, query_vec) / (np.linalg.norm(e_emb) * np.linalg.norm(query_vec) + 1e-9))
                episode_scores.append((eid, sim))
            episode_scores.sort(key=lambda x: x[1], reverse=True)

            for eid, score in episode_scores[:top_k_episodes]:
                result.facts.append({
                    "id": eid,
                    "type": "episode",
                    "summary": (getattr(hypergraph.episodes.get(eid), "summary", "")
                                 if hasattr(hypergraph, "episodes") else ""),
                    "score": round(score, 4),
                })
            all_count = len(result.topics) + len([f for f in result.facts if f["type"] == "episode"])
            result.total_count = all_count
            logger.info("[Retrieval] Hypergraph embedding retrieval: %d topics, %d facts+episodes",
                        len(result.topics), all_count - len(result.topics))

        except Exception as e:
            logger.warning("[Retrieval] Hypergraph embedding retrieval failed: %s", str(e)[:80])

        return result

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