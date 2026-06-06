"""
MCP 工具函数逻辑测试

测试所有 38 个 MCP 工具函数的输入验证、返回值结构和基本逻辑。
使用 data/ 目录中的真实数据（STORAGE_PATH=data）。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["STORAGE_PATH"] = str(PROJECT_ROOT / "data")

import pytest
from src.mcp_server.server import (
    _loader,
    # Query
    search,
    topic,
    list_decisions,
    decision,
    list_topics,
    get_relations,
    stats,
    hot_decisions,
    forgotten_decisions,
    related_decisions,
    recent_decisions,
    fulltext_search,
    # Git
    git_history,
    git_search,
    git_blame,
    # Conflict/Objection
    conflict_list,
    objection_list,
    decision_card,
    decision_children,
    decision_descendants,
    decision_ancestors,
    decision_tree,
    show_tree,
    decision_history,
    # Write
    create_decision,
    update_decision,
    confirm_decision,
    reject_decision,
    revert_decision,
    resolve_conflict,
    # AI/Analysis
    extract_decision,
    classify_topic,
    detect_crosstopic,
    check_conflict,
    evaluate_dedup,
    resolve_conflict_action,
    extract_and_create,
    # Utility
    refresh,
)


def _parse_json(result: str) -> dict:
    return json.loads(result)


def _get_first_sid() -> str:
    """获取一个有效的决策 sid 用于测试"""
    _loader.ensure_loaded()
    decisions = _loader.decisions
    if decisions:
        return decisions[0].sid
    return ""


@pytest.fixture(scope="module", autouse=True)
def ensure_loaded():
    _loader.ensure_loaded()
    yield


# ==================== Query Tools ====================


class TestSearch:
    def test_search_returns_json(self):
        result = search(query="测试", top_k=5)
        data = _parse_json(result)
        assert "results" in data
        assert "total" in data

    def test_search_empty_result(self):
        result = search(query="xyznonexistent123456", top_k=5)
        data = _parse_json(result)
        assert data["total"] >= 0
        assert "results" in data

    def test_search_with_topic(self):
        result = search(query="测试", topic="general", top_k=5)
        data = _parse_json(result)
        assert "results" in data


class TestTopic:
    def test_topic_all(self):
        result = topic(topic_id="", top_k=10)
        data = _parse_json(result)
        assert "results" in data
        assert "total" in data

    def test_topic_with_id(self):
        result = topic(topic_id="general", top_k=10)
        data = _parse_json(result)
        assert "results" in data


class TestListDecisions:
    def test_list_returns_decisions(self):
        result = list_decisions(top_k=10)
        data = _parse_json(result)
        assert "results" in data
        assert "total" in data


class TestDecision:
    def test_decision_not_found(self):
        result = decision(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_decision_found(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = decision(sid=sid)
        data = _parse_json(result)
        assert "result" in data
        assert data["result"]["sid"] == sid


class TestListTopics:
    def test_list_topics_returns_json(self):
        result = list_topics()
        data = _parse_json(result)
        assert "topics" in data
        assert "total" in data


class TestGetRelations:
    def test_relations_not_found(self):
        result = get_relations(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_relations_found(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = get_relations(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "relations" in data


class TestStats:
    def test_stats_returns_json(self):
        result = stats()
        data = _parse_json(result)
        assert "total_decisions" in data
        assert "total_topics" in data
        assert "status_distribution" in data
        assert "impact_distribution" in data
        assert "active_decisions" in data


class TestHotDecisions:
    def test_hot_decisions_default(self):
        result = hot_decisions(top_k=5)
        data = _parse_json(result)
        assert "results" in data
        assert "min_score" in data

    def test_hot_decisions_low_threshold(self):
        result = hot_decisions(min_score=0.0, top_k=5)
        data = _parse_json(result)
        assert "results" in data


class TestForgottenDecisions:
    def test_forgotten_decisions_default(self):
        result = forgotten_decisions(top_k=5)
        data = _parse_json(result)
        assert "results" in data
        assert "max_score" in data

    def test_forgotten_decisions_high_threshold(self):
        result = forgotten_decisions(max_score=100.0, top_k=5)
        data = _parse_json(result)
        assert "results" in data


class TestRelatedDecisions:
    def test_related_not_found(self):
        result = related_decisions(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_related_found(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = related_decisions(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "related" in data
        assert "total" in data


class TestRecentDecisions:
    def test_recent_default(self):
        result = recent_decisions(hours=24, top_k=10)
        data = _parse_json(result)
        assert "results" in data
        assert "hours" in data

    def test_recent_wide_range(self):
        result = recent_decisions(hours=8760, top_k=10)  # 1 year
        data = _parse_json(result)
        assert "results" in data


class TestFulltextSearch:
    def test_fulltext_search(self):
        result = fulltext_search(query="测试", top_k=10)
        data = _parse_json(result)
        assert "results" in data
        assert "query" in data

    def test_fulltext_search_empty(self):
        result = fulltext_search(query="xyznonexistent123456", top_k=10)
        data = _parse_json(result)
        assert "results" in data


# ==================== Git Tools ====================


class TestGitHistory:
    def test_git_history(self):
        result = git_history(limit=5)
        data = _parse_json(result)
        assert "entries" in data
        assert "total" in data


class TestGitSearch:
    def test_git_search(self):
        result = git_search(query="test")
        data = _parse_json(result)
        assert "results" in data
        assert "query" in data


class TestGitBlame:
    def test_git_blame_not_found(self):
        result = git_blame(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_git_blame_found(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = git_blame(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "results" in data


# ==================== Conflict/Objection ====================


class TestConflictList:
    def test_conflict_list(self):
        result = conflict_list(top_k=10)
        data = _parse_json(result)
        assert "results" in data
        assert "total" in data


class TestObjectionList:
    def test_objection_list_default(self):
        result = objection_list()
        data = _parse_json(result)
        assert "results" in data
        assert "topic" in data

    def test_objection_list_topic(self):
        result = objection_list(topic_id="general")
        data = _parse_json(result)
        assert "results" in data


# ==================== Decision Card & Tree ====================


class TestDecisionCard:
    def test_card_not_found(self):
        result = decision_card(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_card_found(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = decision_card(sid=sid)
        data = _parse_json(result)
        assert "card" in data
        assert "sid" in data["card"]


class TestDecisionChildren:
    def test_children(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = decision_children(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "children" in data


class TestDecisionDescendants:
    def test_descendants(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = decision_descendants(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "descendants" in data


class TestDecisionAncestors:
    def test_ancestors(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = decision_ancestors(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "ancestors" in data


class TestDecisionTree:
    def test_tree_not_found(self):
        result = decision_tree(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_tree_found(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = decision_tree(sid=sid)
        data = _parse_json(result)
        assert "sid" in data


class TestShowTree:
    def test_show_tree(self):
        result = show_tree()
        data = _parse_json(result)
        assert "total" in data
        assert "root_count" in data
        assert "trees" in data


class TestDecisionHistory:
    def test_history_not_found(self):
        result = decision_history(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_history_found(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = decision_history(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "history" in data


# ==================== Write Tools ====================


class TestCreateDecision:
    def test_create_decision(self):
        result = create_decision(
            summary="[TEST] 测试决策",
            content="这是一个测试决策，用于验证 create_decision 工具函数。",
            topic_id="general",
            impact_level="minor",
        )
        data = _parse_json(result)
        assert "sid" in data
        assert "summary" in data
        assert "commit_hash" in data


class TestUpdateDecision:
    def test_update_not_found(self):
        result = update_decision(
            sid="nonexistent_sid_xyz",
            summary="should not update",
        )
        data = _parse_json(result)
        assert "error" in data

    def test_update_decision(self):
        # 先创建一个决策
        create_result = _parse_json(create_decision(
            summary="[TEST] 测试更新",
            content="原始内容",
            topic_id="general",
        ))
        sid = create_result["sid"]

        result = update_decision(sid=sid, summary="[TEST] 测试更新-已修改")
        data = _parse_json(result)
        assert "sid" in data
        assert data["summary"] == "[TEST] 测试更新-已修改"


class TestConfirmDecision:
    def test_confirm_not_found(self):
        result = confirm_decision(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_confirm_decision(self):
        create_result = _parse_json(create_decision(
            summary="[TEST] 确认测试",
            content="测试确认功能",
            topic_id="general",
        ))
        sid = create_result["sid"]
        result = confirm_decision(sid=sid)
        data = _parse_json(result)
        assert data["status"] == "decided"
        assert data["sid"] == sid


class TestRejectDecision:
    def test_reject_not_found(self):
        result = reject_decision(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_reject_decision(self):
        create_result = _parse_json(create_decision(
            summary="[TEST] 拒绝测试",
            content="测试拒绝功能",
            topic_id="general",
        ))
        sid = create_result["sid"]
        result = reject_decision(sid=sid, reason="测试拒绝")
        data = _parse_json(result)
        assert data["status"] == "rejected"
        assert data["sid"] == sid


class TestResolveConflict:
    def test_resolve_conflict_not_found(self):
        result = resolve_conflict(
            decision_a="nonexistent_a",
            decision_b="nonexistent_b",
            resolution="test",
        )
        data = _parse_json(result)
        assert "error" in data

    def test_resolve_conflict(self):
        r1 = _parse_json(create_decision(
            summary="[TEST] 冲突A",
            content="测试内容A",
            topic_id="general",
        ))
        r2 = _parse_json(create_decision(
            summary="[TEST] 冲突B",
            content="测试内容B",
            topic_id="general",
        ))
        result = resolve_conflict(
            decision_a=r1["sid"],
            decision_b=r2["sid"],
            resolution="已协调",
        )
        data = _parse_json(result)
        assert data["resolved"] is True


class TestClassifyTopic:
    def test_classify_not_found(self):
        result = classify_topic(sid="nonexistent_sid_xyz", topic_id="other")
        data = _parse_json(result)
        assert "error" in data

    def test_classify_topic(self):
        create_result = _parse_json(create_decision(
            summary="[TEST] 归类测试",
            content="测试归类功能",
            topic_id="general",
        ))
        sid = create_result["sid"]
        result = classify_topic(sid=sid, topic_id="test_topic")
        data = _parse_json(result)
        assert data["topic"] == "test_topic"


class TestDetectCrosstopic:
    def test_detect_not_found(self):
        result = detect_crosstopic(sid="nonexistent_sid_xyz")
        data = _parse_json(result)
        assert "error" in data

    def test_detect_crosstopic(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = detect_crosstopic(sid=sid)
        data = _parse_json(result)
        assert "sid" in data
        assert "cross_topic_impacts" in data


class TestCheckConflict:
    def test_check_conflict(self):
        result = check_conflict(
            summary="[TEST] 检查冲突",
            content="用于检查冲突的测试内容",
            topic_id="general",
        )
        data = _parse_json(result)
        assert "has_conflict" in data
        assert "conflicts" in data
        assert "total" in data


class TestEvaluateDedup:
    def test_evaluate_not_found(self):
        result = evaluate_dedup(sid_a="nonexistent_a", sid_b="nonexistent_b")
        data = _parse_json(result)
        assert "error" in data

    def test_evaluate_dedup(self):
        r1 = _parse_json(create_decision(
            summary="[TEST] 去重A",
            content="内容A",
            topic_id="general",
        ))
        r2 = _parse_json(create_decision(
            summary="[TEST] 去重B",
            content="内容B",
            topic_id="general",
        ))
        result = evaluate_dedup(sid_a=r1["sid"], sid_b=r2["sid"])
        data = _parse_json(result)
        assert "decision_a" in data
        assert "decision_b" in data
        assert "same_topic" in data


class TestResolveConflictAction:
    def test_resolve_action_not_found(self):
        result = resolve_conflict_action(
            sid_a="nonexistent_a",
            sid_b="nonexistent_b",
        )
        data = _parse_json(result)
        assert "error" in data

    def test_resolve_action(self):
        r1 = _parse_json(create_decision(
            summary="[TEST] 冲突建议A",
            content="内容A",
            topic_id="general",
        ))
        r2 = _parse_json(create_decision(
            summary="[TEST] 冲突建议B",
            content="内容B",
            topic_id="general",
        ))
        result = resolve_conflict_action(sid_a=r1["sid"], sid_b=r2["sid"])
        data = _parse_json(result)
        assert "actions" in data
        assert "note" in data


# ==================== AI Extraction (requires LLM) ====================


class TestExtractDecision:
    def test_extract_without_llm(self):
        # API_KEY 未配置时返回错误提示
        result = extract_decision(text="我们应该在周五发布新版本")
        data = _parse_json(result)
        # 无 LLM 时返回 error 或 decision 字段均可
        assert "error" in data or "decision" in data


class TestExtractAndCreate:
    def test_extract_create_without_llm(self):
        result = extract_and_create(text="我们应该在周五发布新版本", topic_id="general")
        data = _parse_json(result)
        assert "error" in data or "sid" in data


# ==================== Utility ====================


class TestRefresh:
    def test_refresh(self):
        result = refresh()
        data = _parse_json(result)
        assert data["reloaded"] is True
        assert "total" in data


# ==================== Revert (needs valid commit hash) ====================


class TestRevertDecision:
    def test_revert_invalid_hash(self):
        sid = _get_first_sid()
        if not sid:
            pytest.skip("No decisions available")
        result = revert_decision(sid=sid, commit_hash="invalid_hash")
        data = _parse_json(result)
        assert "error" in data
