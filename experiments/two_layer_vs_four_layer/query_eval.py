"""查询评估 — 基于 queries.jsonl 的检索准确率测试

从 `queries.jsonl`（717 条 query）中读取 query + gold_answer，
使用两种超图结构的检索接口进行匹配比对。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    query_id: str
    query: str
    gold_answer: str
    retrieved_answer: str
    match_score: float
    retrieval_time_ms: float
    is_match: bool


@dataclass
class QueryEvalReport:
    total_queries: int
    matched: int
    match_rate: float
    avg_retrieval_time_ms: float
    p50_retrieval_time_ms: float
    p95_retrieval_time_ms: float
    by_difficulty: Dict[str, Dict[str, Any]]
    by_type: Dict[str, Dict[str, Any]]
    details: List[Dict[str, Any]] = field(default_factory=list)


class RetrievalFunction(Protocol):
    """检索函数签名：给定 query → 返回检索结果文本"""
    def __call__(self, query: str, **kwargs) -> str: ...


class SimpleMatcher:
    """简单的检索-匹配评估器

    使用字符重叠率判断 retrieved_answer 是否匹配 gold_answer。
    如需语义匹配，可传入 embedder 使用 embedding cosine similarity。
    """

    def __init__(self, embedder: Optional[Any] = None) -> None:
        self._embedder = embedder

    @staticmethod
    def char_overlap(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        a_chars = set(a.lower())
        b_chars = set(b.lower())
        if not a_chars or not b_chars:
            return 0.0
        intersection = a_chars & b_chars
        return len(intersection) / max(len(a_chars), len(b_chars))

    def similarity(self, retrieved: str, gold: str) -> float:
        if self._embedder is not None:
            try:
                vecs = self._embedder.embed([retrieved, gold])
                import numpy as np
                v1, v2 = np.array(vecs[0]), np.array(vecs[1])
                n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if n1 > 0 and n2 > 0:
                    return float(np.dot(v1, v2) / (n1 * n2))
            except Exception:
                pass
        return self.char_overlap(retrieved, gold)


class QueryEvaluator:
    """查询评估器

    加载 queries.jsonl，对每条 query 调用 retrieval_fn，
    与 gold_answer 比较，产出结构化报告。
    """

    def __init__(
        self,
        queries_path: str,
        retrieval_fn: RetrievalFunction,
        matcher: Optional[SimpleMatcher] = None,
        threshold: float = 0.3,
    ) -> None:
        self._queries_path = Path(queries_path)
        self._retrieval_fn = retrieval_fn
        self._matcher = matcher or SimpleMatcher()
        self._threshold = threshold
        self._queries: List[Dict[str, Any]] = []

    def load_queries(self) -> List[Dict[str, Any]]:
        if not self._queries_path.exists():
            raise FileNotFoundError(f"Queries file not found: {self._queries_path}")
        queries: List[Dict[str, Any]] = []
        with open(self._queries_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    queries.append(json.loads(line))
        self._queries = queries
        logger.info("Loaded %d queries from %s", len(queries), self._queries_path)
        return queries

    async def evaluate_all(self, sample_size: int = 0) -> QueryEvalReport:
        """评估所有 query（或前 sample_size 条）

        Args:
            sample_size: 0 = 全部评估

        Returns:
            QueryEvalReport
        """
        if not self._queries:
            self.load_queries()

        queries_to_run = self._queries[:sample_size] if sample_size > 0 else self._queries
        results: List[QueryResult] = []

        for q in queries_to_run:
            query_text = q.get("query", "")
            gold_answer = q.get("gold_answer", "")
            if not query_text or not gold_answer:
                continue

            t0 = time.time()
            try:
                retrieved = self._retrieval_fn(query_text)
            except Exception as e:
                logger.warning("Retrieval failed for query %s: %s", q.get("q_id", "?"), e)
                retrieved = ""
            elapsed_ms = (time.time() - t0) * 1000

            score = self._matcher.similarity(retrieved, gold_answer)
            is_match = score >= self._threshold

            results.append(QueryResult(
                query_id=q.get("q_id", ""),
                query=query_text,
                gold_answer=gold_answer,
                retrieved_answer=retrieved[:200],
                match_score=round(score, 4),
                retrieval_time_ms=round(elapsed_ms, 1),
                is_match=is_match,
            ))

        return self._compute_report(results, queries_to_run)

    def _compute_report(
        self,
        results: List[QueryResult],
        raw_queries: List[Dict[str, Any]],
    ) -> QueryEvalReport:
        total = len(results)
        matched = sum(1 for r in results if r.is_match)
        times = [r.retrieval_time_ms for r in results]

        # 按难度分组
        by_difficulty: Dict[str, Dict] = {}
        for r, q in zip(results, raw_queries):
            diff = q.get("difficulty", "medium")
            if diff not in by_difficulty:
                by_difficulty[diff] = {"total": 0, "matched": 0}
            by_difficulty[diff]["total"] += 1
            if r.is_match:
                by_difficulty[diff]["matched"] += 1

        diff_report = {}
        for diff, counts in by_difficulty.items():
            diff_report[diff] = {
                "total": counts["total"],
                "matched": counts["matched"],
                "match_rate": round(counts["matched"] / counts["total"], 4) if counts["total"] > 0 else 0.0,
            }

        # 按查询类型分组
        by_type: Dict[str, Dict] = {}
        for r, q in zip(results, raw_queries):
            qtype = q.get("query_type", "simple")
            if qtype not in by_type:
                by_type[qtype] = {"total": 0, "matched": 0}
            by_type[qtype]["total"] += 1
            if r.is_match:
                by_type[qtype]["matched"] += 1

        type_report = {}
        for qt, counts in by_type.items():
            type_report[qt] = {
                "total": counts["total"],
                "matched": counts["matched"],
                "match_rate": round(counts["matched"] / counts["total"], 4) if counts["total"] > 0 else 0.0,
            }

        sorted_times = sorted(times)

        return QueryEvalReport(
            total_queries=total,
            matched=matched,
            match_rate=round(matched / total, 4) if total > 0 else 0.0,
            avg_retrieval_time_ms=round(sum(times) / len(times), 1) if times else 0.0,
            p50_retrieval_time_ms=round(sorted_times[len(sorted_times) // 2], 1) if sorted_times else 0.0,
            p95_retrieval_time_ms=round(sorted_times[int(len(sorted_times) * 0.95)], 1) if len(sorted_times) >= 20 else 0.0,
            by_difficulty=diff_report,
            by_type=type_report,
            details=[{
                "q_id": r.query_id,
                "query": r.query[:60],
                "match_score": r.match_score,
                "is_match": r.is_match,
                "retrieval_time_ms": r.retrieval_time_ms,
            } for r in results],
        )

    def report_to_dict(self, report: QueryEvalReport) -> Dict[str, Any]:
        return {
            "total_queries": report.total_queries,
            "matched": report.matched,
            "match_rate": report.match_rate,
            "retrieval_latency_ms": {
                "avg": report.avg_retrieval_time_ms,
                "p50": report.p50_retrieval_time_ms,
                "p95": report.p95_retrieval_time_ms,
            },
            "by_difficulty": report.by_difficulty,
            "by_type": report.by_type,
            "details": report.details,
        }