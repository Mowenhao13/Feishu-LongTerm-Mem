"""
query_memory.py — 语义检索记忆中的决策

通过 Embedding 余弦相似度 + Reranker 重排序 + 决策去重，对存储的决策进行语义检索。

用法:
    uv run python scripts/query_memory.py --query "技术选型相关"
    uv run python scripts/query_memory.py --query "前端技术选型" --top-k 5
    uv run python scripts/query_memory.py --query "微服务" --keyword-only
    uv run python scripts/query_memory.py --query "数据库" --dedup-threshold 0.9
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

import signal as _builtin_signal

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

import numpy as np

from src.graph.memory_graph import MemoryGraph
from src.model.embedding_provider import EmbeddingProvider
from src.model.reranker_provider import RerankerProvider
from src.node.node import DecisionNode
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.utils.logger import get_logger

logger = get_logger("query_memory")

PROJECT = "feishu-mem"


# ==================== 数据加载 ====================

def load_decisions(work_dir: str = "data") -> Tuple[MemoryGraph, List[DecisionNode]]:
    print(f"\n  Loading decisions from {work_dir}/decisions/{PROJECT}/ ...")

    storage = GitStorage(config=GitStorageConfig(work_dir=work_dir))
    graph = MemoryGraph()

    topics = storage.list_topics(PROJECT)
    print(f"     Found {len(topics)} topic(s): {', '.join(topics) if topics else '(none)'}")

    count = 0
    for topic in topics:
        decisions = storage.list_decisions(PROJECT, topic)
        for dec in decisions:
            node = MemoryGraph._dict_to_node(dec)
            graph.upsert_decision(node, PROJECT)
            count += 1
        print(f"     [{topic}] {len(decisions)} decision(s)")

    all_decisions = graph.get_all_decisions()
    print(f"     Total: {len(all_decisions)} decision(s) loaded")
    return graph, all_decisions


# ==================== 检索策略 ====================

def keyword_search(graph: MemoryGraph, query: str) -> List[DecisionNode]:
    return graph.search_by_keywords(query)


def embedding_search(
    embedder: EmbeddingProvider,
    query: str,
    decisions: List[DecisionNode],
    top_k: int = 30,
) -> List[Tuple[DecisionNode, float]]:
    if not decisions:
        return []

    t0 = time.time()

    query_vec = np.array(embedder.embed([query])[0])
    texts = [d.full_text or d.summary for d in decisions]
    doc_vectors = np.array(embedder.embed(texts))

    scores = embedder.cosine_similarity(query_vec, doc_vectors)

    top_indices = np.argsort(scores)[::-1][:top_k]

    results = [(decisions[int(i)], float(scores[int(i)])) for i in top_indices]
    elapsed = time.time() - t0
    print(f"     Embedding search: {len(decisions)} docs -> {len(results)} candidates ({elapsed:.2f}s)")
    return results


def rerank_results(
    reranker: RerankerProvider,
    query: str,
    candidates: List[Tuple[DecisionNode, float]],
) -> List[Tuple[DecisionNode, float, float]]:
    if not candidates:
        return []

    t0 = time.time()
    docs = [d.full_text or d.summary for d, _ in candidates]
    rerank_scores = reranker.rerank_single(query, docs)
    elapsed = time.time() - t0
    print(f"     Reranker re-rank: {len(docs)} docs ({elapsed:.2f}s)")

    combined = []
    for i, (node, embed_score) in enumerate(candidates):
        combined.append((node, embed_score, rerank_scores[i]))

    combined.sort(key=lambda x: x[2], reverse=True)
    return combined


# ==================== 决策去重 ====================

def deduplicate_results(
    embedder: EmbeddingProvider,
    results: List[Tuple[DecisionNode, float, float]],
    threshold: float = 0.85,
) -> List[Tuple[DecisionNode, float, float]]:
    """基于 Embedding 相似度去重，保留排序靠前的决策"""
    if len(results) <= 1:
        return results

    t0 = time.time()
    texts = [d.full_text or d.summary for d, _, _ in results]
    doc_vectors = np.array(embedder.embed(texts))

    keep = [True] * len(results)

    for i in range(len(results)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(results)):
            if not keep[j]:
                continue
            sim = embedder.cosine_similarity(doc_vectors[i], doc_vectors[j:j+1])[0]
            if sim > threshold:
                keep[j] = False

    deduped = [r for i, r in enumerate(results) if keep[i]]
    removed = len(results) - len(deduped)
    elapsed = time.time() - t0

    if removed > 0:
        print(f"     Dedup removed {removed} similar decisions (threshold={threshold}, {elapsed:.2f}s)")

    return deduped


# ==================== 展示 ====================

def format_impact(level: str) -> str:
    colors = {"critical": "critical", "major": "major", "minor": "minor", "advisory": "advisory"}
    return f"{colors.get(level, 'unknown')}"

def format_status(status: str) -> str:
    icons = {
        "decided": "decided", "pending": "pending", "in_discussion": "in_discussion",
        "executing": "executing", "completed": "completed", "rejected": "rejected",
        "superseded": "superseded", "deprecated": "deprecated", "shelved": "shelved",
    }
    return icons.get(status, "unknown")

def display_results(combined: List[Tuple[DecisionNode, float, float]]) -> None:
    if not combined:
        print("\n  No matching decisions found.")
        return

    print(f"\n  {'='*64}")
    print(f"  Top {len(combined)} Results (Reranker score)")
    print(f"  {'='*64}")

    for i, (node, embed_score, rerank_score) in enumerate(combined, 1):
        summary = node.summary or "(no summary)"
        content = (node.full_text or summary)[:140]

        print(f"  [{i:2d}] {summary}")
        print(f"        SID:      {node.sid}")
        print(f"        Topic:    {node.topic_id}")
        print(f"        Status:   {format_status(node.status.value)}")
        print(f"        Impact:   {format_impact(node.impact_level.value)}")
        print(f"        Embed:    {embed_score:.4f}  |  Rerank:  {rerank_score:.4f}")
        if node.authority:
            print(f"        Proposer: {node.authority}")
        if node.created_at:
            print(f"        Time:     {node.created_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"        Content:  {content}")
        if node.tags:
            print(f"        Tags:     {', '.join(node.tags)}")

    print()


# ==================== 主流程 ====================

def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search in decision memory")
    parser.add_argument("--query", type=str, required=True, help="Search query text")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results (default: 10)")
    parser.add_argument("--candidate-k", type=int, default=30, help="Candidates for re-ranking (default: 30)")
    parser.add_argument("--work-dir", type=str, default="data", help="Data directory (default: data)")
    parser.add_argument("--keyword-only", action="store_true", help="Keyword search only, no model needed")
    parser.add_argument("--dedup-threshold", type=float, default=0.85, help="Dedup similarity threshold (default: 0.85, 0=off)")
    parser.add_argument("--no-dedup", action="store_true", help="Disable deduplication")
    args = parser.parse_args()

    dedup_threshold = 0.0 if args.no_dedup else args.dedup_threshold

    print(f"{'='*64}")
    print(f"  Decision Memory Query")
    print(f"  Query: \"{args.query}\"")
    print(f"  Top-K: {args.top_k}")
    print(f"  Dedup: {'off' if dedup_threshold == 0 else f'on (>{dedup_threshold})'}")
    print(f"{'='*64}")

    # Step 1: Load data
    graph, all_decisions = load_decisions(args.work_dir)
    if not all_decisions:
        print("\n  No decisions found. Run main.py first to collect decisions.")
        return

    # Step 2: Keyword search (baseline hint)
    kw_results = keyword_search(graph, args.query)
    if kw_results:
        print(f"\n  Keyword matches: {len(kw_results)}")
        for d in kw_results[:3]:
            print(f"     {d.summary[:60]}")
    else:
        print(f"\n  No keyword matches")

    if args.keyword_only:
        display_results([(d, 1.0, 1.0) for d in kw_results])
        return

    # Step 3: Semantic search
    print(f"\n  Semantic search pipeline...")

    embedder = EmbeddingProvider()
    reranker = RerankerProvider()

    pipeline_start = time.time()

    candidates = embedding_search(embedder, args.query, all_decisions, top_k=args.candidate_k)

    if not candidates:
        print("  No semantic matches found.")
        return

    combined = rerank_results(reranker, args.query, candidates)

    # Step 4: Deduplication
    if dedup_threshold > 0:
        combined = deduplicate_results(embedder, combined, threshold=dedup_threshold)

    total_elapsed = time.time() - pipeline_start
    print(f"\n  Total retrieval: {total_elapsed:.2f}s")

    display_results(combined[:args.top_k])


if __name__ == "__main__":
    main()