"""
MCP (Model Context Protocol) 服务器 — 决策记忆查询与管理工具

通过 stdio 传输协议暴露工具给 OpenClaw、Claude Desktop 等 MCP 客户端。

入口: scripts/mcp_server.py
"""

from __future__ import annotations

import json
import logging
import os
import time as _time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.config import get_storage_path
from src.graph.memory_graph import MemoryGraph
from src.llm.client import LLMClient
from src.model.embedding_provider import EmbeddingProvider
from src.model.reranker_provider import RerankerProvider
from src.view import TaskViewSyncer, is_task_view_enabled
from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.utils.logger import get_logger

logger = get_logger("mcp_server")

PROJECT = "feishu-mem"
WORK_DIR = get_storage_path()

mcp = FastMCP(
    "Feishu Memory Agent",
    instructions="""飞书协作记忆系统的决策记忆查询服务。

提供以下工具:
1. list_decisions — 列出所有决策
2. topic — 按议题查询决策
3. search — 搜索决策
4. decision — 获取单个决策详情
5. list_topics — 列出所有议题
6. get_relations — 获取决策关系网络
7. stats — 系统统计
8. hot_decisions — 热点决策排名
9. forgotten_decisions — 被遗忘的决策
10. related_decisions — 相关决策
11. recent_decisions — 最近决策
12. git_history — Git 提交历史
13. git_search — Git 内容搜索
14. git_blame — Git 追溯
15. fulltext_search — 全文搜索
16. conflict_list — 冲突列表
17. objection_list — 异议列表
18. decision_card — 决策卡片
19. decision_history — 决策版本历史
20. decision_children — 子决策列表
21. decision_descendants — 后代决策
22. decision_ancestors — 祖先路径
23. decision_tree — 完整层级树
24. show_tree — 决策森林
25. timeline — 时间线查询（按时间、主题、状态筛选）
26. mutation_history — 决策变更审计日志
27. create_decision — 创建决策
28. update_decision — 更新决策
29. confirm_decision — 确认决策
30. reject_decision — 拒绝决策
29. revert_decision — 回滚决策
30. resolve_conflict — 解决冲突
31. resolve_conflict_action — 获取冲突解决建议
32. evaluate_dedup — 去重/冲突评估
33. extract_decision — 从文本提取决策
34. classify_topic — 议题归类
35. detect_crosstopic — 检测跨议题影响
36. check_conflict — 检测冲突
37. extract_and_create — 提取并创建决策
38. refresh — 重新加载
""",
    log_level="WARNING",
)

_mcp_llm_client: Optional[LLMClient] = None


def set_llm_client(client: LLMClient) -> None:
    global _mcp_llm_client
    _mcp_llm_client = client


def get_llm_client() -> LLMClient:
    global _mcp_llm_client
    if _mcp_llm_client is None:
        _mcp_llm_client = LLMClient()
    return _mcp_llm_client


# ==================== 数据加载 ====================


class MemoryLoader:
    def __init__(self):
        self._graph: Optional[MemoryGraph] = None
        self._storage: Optional[GitStorage] = None
        self._decisions: List[Any] = []
        self._syncer: Optional[TaskViewSyncer] = None
        self._loaded = False
        self.mutation_log: List[Dict[str, Any]] = []

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._storage = GitStorage(config=GitStorageConfig(work_dir=WORK_DIR))
        graph = MemoryGraph()
        graph.load_from_git(self._storage, PROJECT)
        self._graph = graph
        self._decisions = graph.get_all_decisions()
        self._loaded = True

        try:
            if not is_task_view_enabled():
                logger.info("[TaskView] Skipped (TASK_ENABLED=false)")
            else:
                self._syncer = TaskViewSyncer(WORK_DIR)
                self._storage.post_commit_hooks.append(self._syncer.sync_decision)
                self._syncer.full_sync()
        except Exception as e:
            logger.warning("[TaskView] Sync init failed (non-fatal): %s", e)

    @property
    def graph(self) -> MemoryGraph:
        self.ensure_loaded()
        return self._graph

    @property
    def storage(self) -> GitStorage:
        self.ensure_loaded()
        return self._storage

    def _get_storage(self) -> GitStorage:
        """Return the GitStorage instance (for test access)."""
        self.ensure_loaded()
        return self._storage

    @property
    def decisions(self) -> List[Any]:
        self.ensure_loaded()
        return self._decisions

    @decisions.setter
    def decisions(self, value: List[Any]) -> None:
        self._decisions = value

    def reload(self) -> None:
        self._loaded = False
        self._graph = None
        self._storage = None
        self._decisions = []
        self.ensure_loaded()


_loader = MemoryLoader()


def _record_mutation(t: str, sid: str, old_status: str = "", new_status: str = "") -> None:
    """Record a mutation event for audit trail (in-memory, MCP-scoped)."""
    _loader.mutation_log.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": t,
        "sid": sid,
        "old_status": old_status,
        "new_status": new_status,
    })


def _get_storage() -> GitStorage:
    """Return the GitStorage instance (for test access)."""
    return _loader._get_storage()


# ==================== 工具函数 ====================


def _node_to_dict(node: Any) -> Dict[str, Any]:
    return {
        "sid": node.sid,
        "parent_id": node.parent_id or "",
        "summary": node.summary or "",
        "full_text": node.full_text or "",
        "topic": node.topic_id or "",
        "status": node.status.value if hasattr(node.status, "value") else str(node.status),
        "impact_level": node.impact_level.value if hasattr(node.impact_level, "value") else str(node.impact_level),
        "authority": node.authority or "",
        "assignee": node.assignee or "",
        "tags": list(node.tags) if node.tags else [],
        "version": getattr(node, "version", 1),
        "hot_score": round(getattr(node.access_stats, "hot_score", 0.0), 1),
        "created_at": node.created_at.strftime("%Y-%m-%d %H:%M") if node.created_at else "",
        "updated_at": node.updated_at.strftime("%Y-%m-%d %H:%M") if hasattr(node, "updated_at") and node.updated_at else "",
        # Lifecycle timestamps
        "proposed_at": node.proposed_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "proposed_at", None) else "",
        "discussed_at": node.discussed_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "discussed_at", None) else "",
        "decided_at": node.decided_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "decided_at", None) else "",
        "executing_at": node.executing_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "executing_at", None) else "",
        "completed_at": node.completed_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "completed_at", None) else "",
        "shelved_at": node.shelved_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "shelved_at", None) else "",
        "rejected_at": node.rejected_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "rejected_at", None) else "",
        "superseded_at": node.superseded_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "superseded_at", None) else "",
        "deprecated_at": node.deprecated_at.strftime("%Y-%m-%d %H:%M") if getattr(node, "deprecated_at", None) else "",
    }


def _relation_to_dict(rel: Any) -> Dict[str, str]:
    return {
        "type": rel.type.value if hasattr(rel.type, "value") else str(rel.type),
        "target_id": rel.target_id,
        "description": rel.description,
    }


def _commit_log_to_dict(entry: Any) -> Dict[str, str]:
    return {
        "hash": getattr(entry, "hash", "") or getattr(entry, "commit_hash", ""),
        "author": getattr(entry, "author", ""),
        "date": getattr(entry, "date", ""),
        "message": getattr(entry, "message", ""),
    }


def _gen_sid() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


# ==================== Query Tools ====================


@mcp.tool(
    name="search",
    description="搜索决策记忆。优先使用 Embedding + Reranker 语义检索，模型不可用时自动降级为关键词检索。",
)
def search(query: str, topic: str = "", top_k: int = 10) -> str:
    _loader.ensure_loaded()
    graph = _loader.graph
    if not _loader.decisions:
        return json.dumps({"results": [], "total": 0}, ensure_ascii=False)

    top_k = min(max(top_k, 1), 30)

    try:
        embedder = EmbeddingProvider()
        reranker = RerankerProvider()
        candidates = _loader.decisions

        query_vec = np.array(embedder.embed([query])[0])
        texts = [d.full_text or d.summary for d in candidates]
        doc_vectors = np.array(embedder.embed(texts))
        scores = embedder.cosine_similarity(query_vec, doc_vectors)

        top_indices = np.argsort(scores)[::-1][:min(top_k * 2, 30)]
        scored = [(candidates[int(i)], float(scores[int(i)])) for i in top_indices]
        docs = [d.full_text or d.summary for d, _ in scored]
        rerank_scores = reranker.rerank_single(query, docs)

        combined = sorted(
            [(_node_to_dict(n), es, float(rerank_scores[i])) for i, (n, es) in enumerate(scored)],
            key=lambda x: x[2], reverse=True,
        )[:top_k]

        results = [
            {**item[0], "score_embedding": item[1], "score_reranker": item[2]}
            for item in combined
        ]
        return json.dumps({"results": results, "total": len(results), "method": "semantic"}, ensure_ascii=False)

    except Exception:
        logger.info("[search] Model unavailable, fallback to keyword")
        kw = graph.search_by_keywords(query, topic)
        results = [_node_to_dict(d) for d in kw[:top_k]]
        return json.dumps({"results": results, "total": len(results), "method": "keyword"}, ensure_ascii=False)


@mcp.tool(
    name="topic",
    description="按议题查询决策列表。不传 topic_id 则返回所有决策（按时间倒序）。",
)
def topic(topic_id: str = "", top_k: int = 50) -> str:
    _loader.ensure_loaded()
    if topic_id:
        nodes = _loader.graph.query_by_topic(PROJECT, topic_id)
    else:
        nodes = sorted(_loader.decisions, key=lambda d: d.created_at or datetime.min, reverse=True)
    results = [_node_to_dict(d) for d in nodes[:top_k]]
    return json.dumps({"results": results, "total": len(results), "topic": topic_id or "all"}, ensure_ascii=False)


@mcp.tool(
    name="list_decisions",
    description="列出所有存储的决策（按创建时间倒序）。不需要 topic 参数，返回完整列表。",
)
def list_decisions(top_k: int = 50) -> str:
    return topic(topic_id="", top_k=top_k)


@mcp.tool(
    name="timeline",
    description="获取决策时间线。按创建时间排序，支持按主题、状态、时间段筛选。返回每个决策的完整生命周期时间戳。",
)
def timeline(topic_id: str = "", status: str = "", hours: int = 0, top_k: int = 50) -> str:
    """统一的时间线查询：按 created_at 排序，返回完整生命周期时间戳"""
    _loader.ensure_loaded()
    nodes = _loader.decisions

    # Filter by topic
    if topic_id:
        nodes = [d for d in nodes if d.topic_id == topic_id]

    # Filter by status
    if status:
        nodes = [d for d in nodes if (hasattr(d.status, "value") and d.status.value == status) or str(d.status) == status]

    # Filter by recency
    if hours > 0:
        since = datetime.now() - timedelta(hours=hours)
        nodes = [d for d in nodes if d.created_at and d.created_at > since]

    # Sort by created_at descending
    nodes.sort(key=lambda d: d.created_at or datetime.min, reverse=True)

    results = [_node_to_dict(d) for d in nodes[:top_k]]
    return json.dumps({
        "results": results,
        "total": len(results),
        "filters": {"topic_id": topic_id, "status": status, "hours": hours},
    }, ensure_ascii=False)


@mcp.tool(
    name="decision",
    description="通过 SDR ID 获取单个决策的详细信息。",
)
def decision(sid: str) -> str:
    _loader.ensure_loaded()
    d = _loader.graph.get_decision(sid)
    if d is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    return json.dumps({"result": _node_to_dict(d)}, ensure_ascii=False)


@mcp.tool(
    name="list_topics",
    description="列出所有议题分类。",
)
def list_topics() -> str:
    _loader.ensure_loaded()
    topics = _loader.graph.list_all_topics(PROJECT)
    return json.dumps({"topics": topics, "total": len(topics)}, ensure_ascii=False)


@mcp.tool(
    name="get_relations",
    description="获取指定决策的关系网络。",
)
def get_relations(sid: str) -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    relations = _loader.graph.get_relations(sid)
    related = _loader.graph.get_related_decisions(sid)
    return json.dumps({
        "sid": sid,
        "summary": node.summary,
        "relations": [_relation_to_dict(r) for r in relations],
        "related_decisions": [_node_to_dict(d) for d in related],
    }, ensure_ascii=False)


@mcp.tool(
    name="stats",
    description="获取系统统计信息。",
)
def stats() -> str:
    _loader.ensure_loaded()
    graph = _loader.graph
    topics = graph.list_all_topics(PROJECT)
    decisions = graph.get_all_decisions()

    status_counts = {}
    impact_counts = {}
    for d in decisions:
        s = d.status.value if hasattr(d.status, "value") else str(d.status)
        status_counts[s] = status_counts.get(s, 0) + 1
        imp = d.impact_level.value if hasattr(d.impact_level, "value") else str(d.impact_level)
        impact_counts[imp] = impact_counts.get(imp, 0) + 1

    return json.dumps({
        "total_decisions": len(decisions),
        "total_topics": len(topics),
        "topics": topics,
        "status_distribution": status_counts,
        "impact_distribution": impact_counts,
        "active_decisions": sum(1 for d in decisions if d.status.is_active()),
    }, ensure_ascii=False)


@mcp.tool(
    name="hot_decisions",
    description="获取热点决策排名（按热度值从高到低）。",
)
def hot_decisions(min_score: float = 50.0, top_k: int = 10) -> str:
    _loader.ensure_loaded()
    for d in _loader.decisions:
        _loader.graph.recalculate_hot_score(d.sid)
    nodes = _loader.graph.get_decisions_by_hot_score(min_score)
    results = [_node_to_dict(d) for d in nodes[:top_k]]
    return json.dumps({"results": results, "total": len(results), "min_score": min_score}, ensure_ascii=False)


@mcp.tool(
    name="forgotten_decisions",
    description="获取被遗忘的决策（热度值低的决策）。",
)
def forgotten_decisions(max_score: float = 30.0, top_k: int = 10) -> str:
    _loader.ensure_loaded()
    for d in _loader.decisions:
        _loader.graph.recalculate_hot_score(d.sid)
    all_nodes = _loader.graph.get_all_decisions()
    filtered = [d for d in all_nodes if d.access_stats.hot_score <= max_score and d.status.is_active()]
    filtered.sort(key=lambda x: x.access_stats.hot_score)
    results = [_node_to_dict(d) for d in filtered[:top_k]]
    return json.dumps({"results": results, "total": len(results), "max_score": max_score}, ensure_ascii=False)


@mcp.tool(
    name="related_decisions",
    description="获取与指定决策相关的其他决策。",
)
def related_decisions(sid: str) -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    related = _loader.graph.get_related_decisions(sid)
    return json.dumps({
        "sid": sid,
        "summary": node.summary,
        "related": [_node_to_dict(d) for d in related],
        "total": len(related),
    }, ensure_ascii=False)


@mcp.tool(
    name="recent_decisions",
    description="获取最近创建的决策（按小时数筛选）。",
)
def recent_decisions(hours: int = 24, top_k: int = 20) -> str:
    _loader.ensure_loaded()
    since = datetime.now() - timedelta(hours=hours)
    nodes = _loader.graph.get_recent_decisions(since)
    results = [_node_to_dict(d) for d in nodes[:top_k]]
    return json.dumps({"results": results, "total": len(results), "hours": hours}, ensure_ascii=False)


@mcp.tool(
    name="fulltext_search",
    description="全文搜索决策内容（基于关键词匹配）。",
)
def fulltext_search(query: str, topic: str = "", top_k: int = 20) -> str:
    _loader.ensure_loaded()
    nodes = _loader.graph.search_by_keywords(query, topic)
    results = [_node_to_dict(d) for d in nodes[:top_k]]
    return json.dumps({"results": results, "total": len(results), "query": query}, ensure_ascii=False)


# ==================== Git Tools ====================


@mcp.tool(
    name="git_history",
    description="获取 Git 提交历史。",
)
def git_history(limit: int = 20) -> str:
    _loader.ensure_loaded()
    entries = _loader.storage.get_commit_log(limit=limit)
    results = [_commit_log_to_dict(e) for e in entries]
    return json.dumps({"entries": results, "total": len(results)}, ensure_ascii=False)


@mcp.tool(
    name="git_search",
    description="在 Git 历史中搜索决策内容。",
)
def git_search(query: str) -> str:
    _loader.ensure_loaded()
    hits = _loader.storage.search_content(PROJECT, query)
    results = [
        {
            "path": h.path if hasattr(h, "path") else getattr(h, "file_path", ""),
            "line": getattr(h, "line", 0),
            "content": getattr(h, "content", ""),
        }
        for h in hits
    ]
    return json.dumps({"results": results, "total": len(results), "query": query}, ensure_ascii=False)


@mcp.tool(
    name="git_blame",
    description="追溯决策文件的每一行最后修改人。",
)
def git_blame(sid: str, topic_id: str = "") -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    t = topic_id or node.topic_id or "general"
    entries = _loader.storage.blame_decision(PROJECT, t, sid)
    results = [
        {
            "line": getattr(e, "line", 0) or getattr(e, "line_no", 0),
            "author": getattr(e, "author", ""),
            "time": getattr(e, "time", "") or getattr(e, "date", ""),
            "content": getattr(e, "content", ""),
        }
        for e in entries
    ]
    return json.dumps({"sid": sid, "results": results, "total": len(results)}, ensure_ascii=False)


# ==================== Conflict & Objection Tools ====================


@mcp.tool(
    name="conflict_list",
    description="列出所有已记录的决策冲突。",
)
def conflict_list(top_k: int = 20) -> str:
    _loader.ensure_loaded()
    conflicts = []
    for d in _loader.decisions:
        if hasattr(d, "relations") and d.relations:
            for r in d.relations:
                r_type = r.type.value if hasattr(r.type, "value") else str(r.type)
                if r_type == "CONFLICTS_WITH":
                    target = _loader.graph.get_decision(r.target_id)
                    conflicts.append({
                        "decision_a": d.sid,
                        "summary_a": d.summary,
                        "decision_b": r.target_id,
                        "summary_b": target.summary if target else "",
                        "description": r.description,
                    })
    return json.dumps({"results": conflicts[:top_k], "total": len(conflicts)}, ensure_ascii=False)


@mcp.tool(
    name="objection_list",
    description="列出指定议题下所有的异议（反对意见）。",
)
def objection_list(topic_id: str = "general") -> str:
    _loader.ensure_loaded()
    objections = _loader.storage.list_objections(PROJECT, topic_id)
    return json.dumps({"results": objections, "total": len(objections), "topic": topic_id}, ensure_ascii=False)


@mcp.tool(
    name="decision_card",
    description="获取决策的飞书卡片格式 JSON。",
)
def decision_card(sid: str) -> str:
    _loader.ensure_loaded()
    d = _loader.graph.get_decision(sid)
    if d is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    card = {
        "sid": d.sid,
        "summary": d.summary,
        "content": d.full_text,
        "status": d.status.value if hasattr(d.status, "value") else str(d.status),
        "impact_level": d.impact_level.value if hasattr(d.impact_level, "value") else str(d.impact_level),
        "topic": d.topic_id,
        "proposer": d.authority or "未知",
        "hot_score": round(getattr(d.access_stats, "hot_score", 0.0), 1),
        "tags": list(d.tags) if d.tags else [],
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "",
    }
    return json.dumps({"card": card}, ensure_ascii=False)


@mcp.tool(
    name="decision_children",
    description="获取指定决策的直接子决策列表。",
)
def decision_children(sid: str) -> str:
    _loader.ensure_loaded()
    children = _loader.graph.get_children_of(sid)
    return json.dumps({
        "sid": sid,
        "children": [_node_to_dict(c) for c in children],
        "total": len(children),
    }, ensure_ascii=False)


@mcp.tool(
    name="decision_descendants",
    description="递归获取指定决策的所有后代决策。",
)
def decision_descendants(sid: str) -> str:
    _loader.ensure_loaded()
    descendants = _loader.graph.get_descendants(sid)
    return json.dumps({
        "sid": sid,
        "descendants": [_node_to_dict(d) for d in descendants],
        "total": len(descendants),
    }, ensure_ascii=False)


@mcp.tool(
    name="decision_ancestors",
    description="获取指定决策的祖先路径（从根到自身）。",
)
def decision_ancestors(sid: str) -> str:
    _loader.ensure_loaded()
    ancestors = _loader.graph.get_ancestors(sid)
    return json.dumps({
        "sid": sid,
        "ancestors": [_node_to_dict(a) for a in ancestors],
        "total": len(ancestors),
    }, ensure_ascii=False)


@mcp.tool(
    name="decision_tree",
    description="获取指定决策的完整层级树（包含所有后代，递归嵌套结构）。",
)
def decision_tree(sid: str) -> str:
    _loader.ensure_loaded()

    def _build_subtree(node_sid: str) -> Dict[str, Any]:
        node = _loader.graph.get_decision(node_sid)
        if node is None:
            return {}
        children = _loader.graph.get_children_of(node_sid)
        return {
            **_node_to_dict(node),
            "children": [_build_subtree(c.sid) for c in children],
        }

    root = _loader.graph.get_decision(sid)
    if root is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    return json.dumps(_build_subtree(sid), ensure_ascii=False)


@mcp.tool(
    name="show_tree",
    description="展示完整的决策森林（所有根决策及其递归后代，无需参数）。",
)
def show_tree() -> str:
    _loader.ensure_loaded()

    def _build_subtree(node_sid: str) -> Dict[str, Any]:
        node = _loader.graph.get_decision(node_sid)
        if node is None:
            return {}
        children = _loader.graph.get_children_of(node_sid)
        return {
            **_node_to_dict(node),
            "children": [_build_subtree(c.sid) for c in children],
        }

    all_decisions = _loader.graph.get_all_decisions()
    roots = [d for d in all_decisions if not d.parent_id]
    trees = [_build_subtree(r.sid) for r in roots]
    return json.dumps({
        "total": len(all_decisions),
        "root_count": len(roots),
        "trees": trees,
    }, ensure_ascii=False)


@mcp.tool(
    name="decision_history",
    description="获取决策的版本变更历史。",
)
def decision_history(sid: str, topic_id: str = "") -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    t = topic_id or node.topic_id or "general"
    entries = _loader.storage.get_decision_history(PROJECT, t, sid)
    return json.dumps({
        "sid": sid,
        "summary": node.summary,
        "history": [_commit_log_to_dict(e) for e in entries],
        "total": len(entries),
    }, ensure_ascii=False)


# ==================== Write Tools ====================


@mcp.tool(
    name="create_decision",
    description="创建一条新的决策。",
)
def create_decision(summary: str, content: str, topic_id: str = "general",
                    impact_level: str = "minor", tags: str = "") -> str:
    _loader.ensure_loaded()
    sid = _gen_sid()
    try:
        impact = ImpactLevel(impact_level)
    except ValueError:
        impact = ImpactLevel.MINOR

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    now = datetime.now()
    node = DecisionNode(
        sid=sid, topic_id=topic_id, summary=summary,
        full_text=content, status=DecisionStatus.DECIDED,
        impact_level=impact, tags=tag_list,
        created_at=now, updated_at=now,
    )
    node.change_status(DecisionStatus.DECIDED)
    _loader.graph.upsert_decision(node, PROJECT)

    dec_dict = _node_to_dict(node)
    dec_dict["project"] = PROJECT
    commit_hash = _loader.storage.write_decision(dec_dict)

    _loader.decisions = _loader.graph.get_all_decisions()
    _record_mutation("create", sid, "", "decided")
    return json.dumps({"sid": sid, "summary": summary, "commit_hash": commit_hash}, ensure_ascii=False)


@mcp.tool(
    name="update_decision",
    description="更新已有决策的内容或状态。",
)
def update_decision(sid: str, summary: str = "", content: str = "",
                    status: str = "", impact_level: str = "") -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)

    if summary:
        node.summary = summary
    if content:
        node.full_text = content
    if status:
        try:
            node.change_status(DecisionStatus(status))
        except ValueError:
            pass
    if impact_level:
        try:
            node.impact_level = ImpactLevel(impact_level)
        except ValueError:
            pass
    node.updated_at = datetime.now()

    _loader.graph.upsert_decision(node, PROJECT)
    dec_dict = _node_to_dict(node)
    dec_dict["project"] = PROJECT
    commit_hash = _loader.storage.write_decision(dec_dict)

    _loader.decisions = _loader.graph.get_all_decisions()
    _record_mutation("update", sid)
    return json.dumps({"sid": sid, "summary": node.summary, "commit_hash": commit_hash}, ensure_ascii=False)


@mcp.tool(
    name="confirm_decision",
    description="确认（批准）决策，将状态设为 decided。",
)
def confirm_decision(sid: str) -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    node.change_status(DecisionStatus.DECIDED)
    _loader.graph.upsert_decision(node, PROJECT)
    dec_dict = _node_to_dict(node)
    dec_dict["project"] = PROJECT
    _loader.storage.write_decision(dec_dict)
    _loader.decisions = _loader.graph.get_all_decisions()
    _record_mutation("confirm", sid, "", "decided")
    return json.dumps({"sid": sid, "status": "decided", "summary": node.summary}, ensure_ascii=False)


@mcp.tool(
    name="reject_decision",
    description="拒绝决策，将状态设为 rejected。",
)
def reject_decision(sid: str, reason: str = "") -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    node.change_status(DecisionStatus.REJECTED)
    _loader.graph.upsert_decision(node, PROJECT)
    dec_dict = _node_to_dict(node)
    dec_dict["project"] = PROJECT
    _loader.storage.write_decision(dec_dict)
    _loader.decisions = _loader.graph.get_all_decisions()
    _record_mutation("reject", sid, "", "rejected")
    return json.dumps({"sid": sid, "status": "rejected", "summary": node.summary}, ensure_ascii=False)


@mcp.tool(
    name="revert_decision",
    description="回滚决策到指定 Git 提交版本。",
)
def revert_decision(sid: str, commit_hash: str, topic_id: str = "") -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    t = topic_id or node.topic_id or "general"
    try:
        old_data = _loader.storage.read_decision_at_commit(PROJECT, t, sid, commit_hash)
        old_node = MemoryGraph._dict_to_node(old_data)
        _loader.graph.upsert_decision(old_node, PROJECT)
        dec_dict = _node_to_dict(old_node)
        dec_dict["project"] = PROJECT
        _loader.storage.write_decision(dec_dict)
        _loader.decisions = _loader.graph.get_all_decisions()
        return json.dumps({"sid": sid, "summary": old_node.summary,
                           "reverted_to": commit_hash[:12]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Revert failed: {str(e)}"}, ensure_ascii=False)


@mcp.tool(
    name="resolve_conflict",
    description="标记两个决策之间的冲突已解决。",
)
def resolve_conflict(decision_a: str, decision_b: str, resolution: str) -> str:
    _loader.ensure_loaded()
    a = _loader.graph.get_decision(decision_a)
    b = _loader.graph.get_decision(decision_b)
    if a is None or b is None:
        return json.dumps({"error": "One or both decisions not found"}, ensure_ascii=False)
    a.updated_at = datetime.now()
    b.updated_at = datetime.now()
    _loader.graph.upsert_decision(a, PROJECT)
    _loader.graph.upsert_decision(b, PROJECT)
    return json.dumps({
        "resolved": True,
        "decision_a": decision_a, "decision_b": decision_b,
        "resolution": resolution,
    }, ensure_ascii=False)


@mcp.tool(
    name="extract_decision",
    description="从文本中提取决策信息（需要 LLM 服务）。",
)
def extract_decision(text: str) -> str:
    try:
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor
        from src.model.llm_provider import LLMProvider as DirectLLMProvider
        api_key = os.getenv("API_KEY", "")
        if not api_key:
            return json.dumps({
                "error": "LLM not available: API_KEY not configured",
                "hint": "Set API_KEY in .env and restart"
            }, ensure_ascii=False)
        provider = DirectLLMProvider(
            provider_type="openai",
            base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
            api_key=api_key,
            model=os.getenv("MODEL_NAME", "deepseek-chat"),
        )
        extractor = SimpleLLMExtractor(provider)
        import asyncio
        result = asyncio.run(extractor.extract_decision(text))
        if result is None:
            return json.dumps({"decision": None, "message": "No decision pattern found"}, ensure_ascii=False)
        return json.dumps({"decision": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Extraction failed: {str(e)}"}, ensure_ascii=False)


@mcp.tool(
    name="classify_topic",
    description="给决策重新归类到指定议题。",
)
def classify_topic(sid: str, topic_id: str) -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    node.topic_id = topic_id
    node.updated_at = datetime.now()
    _loader.graph.upsert_decision(node, PROJECT)
    dec_dict = _node_to_dict(node)
    dec_dict["project"] = PROJECT
    _loader.storage.write_decision(dec_dict)
    _loader.decisions = _loader.graph.get_all_decisions()
    return json.dumps({"sid": sid, "topic": topic_id, "summary": node.summary}, ensure_ascii=False)


@mcp.tool(
    name="detect_crosstopic",
    description="检测决策对其他议题的跨议题影响。",
)
def detect_crosstopic(sid: str) -> str:
    _loader.ensure_loaded()
    node = _loader.graph.get_decision(sid)
    if node is None:
        return json.dumps({"error": f"Decision not found: {sid}"}, ensure_ascii=False)
    results = _loader.graph.query_cross_topic(PROJECT, node.topic_id)
    affected = [d for d in results if d.sid != sid]
    return json.dumps({
        "sid": sid, "summary": node.summary, "topic": node.topic_id,
        "cross_topic_impacts": [_node_to_dict(d) for d in affected],
        "total": len(affected),
    }, ensure_ascii=False)


@mcp.tool(
    name="check_conflict",
    description="检查新决策与现有决策之间的冲突。",
)
def check_conflict(summary: str, content: str, topic_id: str = "general") -> str:
    _loader.ensure_loaded()
    now = datetime.now()
    dummy = DecisionNode(
        sid="_dummy_check_", topic_id=topic_id, summary=summary,
        full_text=content, status=DecisionStatus.DECIDED,
        impact_level=ImpactLevel.MINOR, created_at=now, updated_at=now,
    )
    conflicts = _loader.graph.detect_conflicts(dummy)
    return json.dumps({
        "has_conflict": len(conflicts) > 0,
        "conflicts": [
            {
                "decision_a": c.decision_a,
                "decision_b": c.decision_b,
                "description": c.description,
                "score": c.contradiction_score,
            }
            for c in conflicts
        ],
        "total": len(conflicts),
    }, ensure_ascii=False)


@mcp.tool(
    name="evaluate_dedup",
    description="评估决策可能存在重复或冲突。需要 LLM 服务以获得准确评估。",
)
def evaluate_dedup(sid_a: str, sid_b: str) -> str:
    _loader.ensure_loaded()
    a = _loader.graph.get_decision(sid_a)
    b = _loader.graph.get_decision(sid_b)
    if a is None or b is None:
        return json.dumps({"error": "One or both decisions not found"}, ensure_ascii=False)
    return json.dumps({
        "decision_a": {"sid": a.sid, "summary": a.summary, "topic": a.topic_id},
        "decision_b": {"sid": b.sid, "summary": b.summary, "topic": b.topic_id},
        "same_topic": a.topic_id == b.topic_id,
        "note": "Use LLM extract_decision for deeper semantic comparison",
        "possible_dup": a.summary.lower() == b.summary.lower(),
    }, ensure_ascii=False)


@mcp.tool(
    name="resolve_conflict_action",
    description="获取解决两个决策之间冲突的建议。需要 LLM 服务。",
)
def resolve_conflict_action(sid_a: str, sid_b: str) -> str:
    _loader.ensure_loaded()
    a = _loader.graph.get_decision(sid_a)
    b = _loader.graph.get_decision(sid_b)
    if a is None or b is None:
        return json.dumps({"error": "One or both decisions not found"}, ensure_ascii=False)
    return json.dumps({
        "decision_a": {"sid": a.sid, "summary": a.summary},
        "decision_b": {"sid": b.sid, "summary": b.summary},
        "actions": [
            "1. Supersede: 标记其中一个决策被另一个取代",
            "2. Refine: 将两个决策合并为一个更精确的决策",
            "3. Reject: 拒绝其中一个决策并记录理由",
        ],
        "note": "Use LLM-based extract_decision for automated resolution suggestions",
    }, ensure_ascii=False)


@mcp.tool(
    name="extract_and_create",
    description="从文本提取决策信息并自动创建决策。需要 LLM 服务。",
)
def extract_and_create(text: str, topic_id: str = "general") -> str:
    try:
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor
        from src.model.llm_provider import LLMProvider as DirectLLMProvider
        api_key = os.getenv("API_KEY", "")
        if not api_key:
            return json.dumps({
                "error": "LLM not available: API_KEY not configured",
                "hint": "Set API_KEY in .env and restart"
            }, ensure_ascii=False)
        provider = DirectLLMProvider(
            provider_type="openai",
            base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
            api_key=api_key,
            model=os.getenv("MODEL_NAME", "deepseek-chat"),
        )
        extractor = SimpleLLMExtractor(provider)
        import asyncio
        result = asyncio.run(extractor.extract_decision(text))
        if result is None:
            return json.dumps({"error": "No decision pattern found in text"}, ensure_ascii=False)
        summary = result.get("title", text[:60])
        impact = result.get("impact_level", "minor")
        return create_decision(summary=summary, content=text,
                               topic_id=result.get("topic", topic_id),
                               impact_level=impact)
    except Exception as e:
        return json.dumps({"error": f"Extract and create failed: {str(e)}"}, ensure_ascii=False)


@mcp.tool(
    name="refresh",
    description="从 Git 存储重新加载所有决策。",
)
def refresh() -> str:
    _loader.reload()
    return json.dumps({"reloaded": True, "total": len(_loader.decisions)}, ensure_ascii=False)


@mcp.tool(
    name="mutation_history",
    description="获取决策的变更审计日志。列出指定决策的所有 mutation 记录，按时间排序。",
)
def mutation_history(sid: str, limit: int = 50) -> str:
    """列出指定决策的所有 mutation 变更记录"""
    _loader.ensure_loaded()
    records = [m for m in _loader.mutation_log if m["sid"] == sid]
    records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return json.dumps({
        "sid": sid,
        "history": records[:limit],
        "total": len(records),
    }, ensure_ascii=False)


# ==================== 启动 ====================


def run_server(transport: str = "stdio") -> None:
    mcp.run(transport=transport)


if __name__ == "__main__":
    run_server()