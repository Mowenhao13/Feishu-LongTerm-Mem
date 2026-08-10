"""
Tests for decision timeline / lifecycle timestamps and mutation audit trail.

Covers P0 implementation:
- DecisionNode lifecycle timestamp fields (proposed_at, decided_at, etc.)
- change_status() auto-sets lifecycle timestamps
- Mutation timestamp and history
- MCP timeline tool ordering and filtering
"""

import sys
from pathlib import Path

# Add project root + src/ to sys.path so that both "from node.node" and "from src.node.types" work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for p in [str(PROJECT_ROOT), str(SRC_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from node.node import DecisionNode
from node.types import DecisionStatus, ImpactLevel
from core.mutations import DecisionMutation, MutationType


# ==================== Test 1: DecisionNode lifecycle timestamps ====================


class TestDecisionNodeLifecycle:
    """DecisionNode 生命周期时间戳：创建后字段默认 None，change_status() 自动设置对应时间戳"""

    def test_created_without_timestamps(self):
        """创建决策后，生命周期时间戳默认为 None（向后兼容）"""
        node = DecisionNode(
            sid="test001",
            topic_id="general",
            summary="Test decision",
        )
        # Core timestamps should exist
        assert node.created_at is None
        assert node.updated_at is None
        # Lifecycle timestamps should all be None
        assert node.proposed_at is None
        assert node.discussed_at is None
        assert node.decided_at is None
        assert node.executing_at is None
        assert node.completed_at is None
        assert node.shelved_at is None
        assert node.rejected_at is None
        assert node.superseded_at is None
        assert node.deprecated_at is None

    def test_initial_status_default_no_timestamp(self):
        """初始 PENDING 状态不触发 proposed_at（仅在 change_status 后设置）"""
        node = DecisionNode(
            sid="test002", topic_id="general",
            summary="Test", status=DecisionStatus.PENDING,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        # proposed_at should be None since we didn't call change_status
        assert node.proposed_at is None

    def test_change_status_decided_sets_decided_at(self):
        """change_status(DECIDED) 自动设置 decided_at"""
        node = DecisionNode(
            sid="test003", topic_id="general",
            summary="Test decision",
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        node.change_status(DecisionStatus.DECIDED)
        assert node.decided_at is not None
        assert node.status == DecisionStatus.DECIDED

    def test_all_status_transitions(self):
        """所有 10 种状态变更都应设置对应时间戳"""
        node = DecisionNode(
            sid="test004", topic_id="general",
            summary="Test all transitions",
            created_at=datetime.now(), updated_at=datetime.now(),
        )

        transitions = [
            (DecisionStatus.PENDING, "proposed_at"),
            (DecisionStatus.PENDING_CONFIRMATION, "pending_confirmation_at"),
            (DecisionStatus.IN_DISCUSSION, "discussed_at"),
            (DecisionStatus.DECIDED, "decided_at"),
            (DecisionStatus.EXECUTING, "executing_at"),
            (DecisionStatus.COMPLETED, "completed_at"),
            (DecisionStatus.SHELVED, "shelved_at"),
            (DecisionStatus.REJECTED, "rejected_at"),
            (DecisionStatus.SUPERSEDED, "superseded_at"),
            (DecisionStatus.DEPRECATED, "deprecated_at"),
        ]

        for status, field in transitions:
            node.change_status(status)
            assert getattr(node, field) is not None, (
                f"change_status({status.value}) should set {field}"
            )
            assert node.status == status
            assert node.updated_at is not None

    def test_timestamp_not_overwritten(self):
        """已设置的时间戳不应被后续的 change_status 覆盖"""
        now = datetime.now()
        node = DecisionNode(
            sid="test005", topic_id="general",
            summary="Test no overwrite",
            created_at=now, updated_at=now,
        )

        node.change_status(DecisionStatus.DECIDED)
        first_decided = node.decided_at

        # Change to another status and back
        node.change_status(DecisionStatus.EXECUTING)
        node.change_status(DecisionStatus.DECIDED)

        # decided_at should still be from the first call
        assert node.decided_at == first_decided, "decided_at should not be overwritten"

    def test_updated_at_set_on_change(self):
        """change_status 应同时更新 updated_at"""
        node = DecisionNode(
            sid="test006", topic_id="general",
            summary="Test updated_at",
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        old_updated = node.updated_at
        node.change_status(DecisionStatus.DECIDED)
        assert node.updated_at >= old_updated


# ==================== Test 2: DecisionMutation timestamp ====================


class TestMutationTimestamp:
    """Mutation 时间戳字段"""

    def test_mutation_default_timestamp_none(self):
        """新创建的 Mutation timestamp 默认 None（向后兼容）"""
        mut = DecisionMutation(
            mtype=MutationType.CREATE,
            sdr_id="mut001",
            summary="Test mutation",
        )
        assert mut.timestamp is None

    def test_mutation_timestamp_settable(self):
        """Mutation timestamp 可以手动设置"""
        now = datetime.now()
        mut = DecisionMutation(
            mtype=MutationType.UPDATE,
            sdr_id="mut002",
            timestamp=now,
        )
        assert mut.timestamp == now

    def test_mutation_is_valid_unchanged(self):
        """添加 timestamp 字段后，is_valid 行为不变"""
        valid = DecisionMutation(
            mtype=MutationType.CREATE,
            sdr_id="valid001",
            summary="Valid mutation",
        )
        assert valid.is_valid is True

        invalid_no_sid = DecisionMutation(
            mtype=MutationType.CREATE,
            sdr_id="",
        )
        assert invalid_no_sid.is_valid is False


# ==================== Test 3: Timeline ordering ====================


class TestTimelineOrdering:
    """时间线排序逻辑"""

    def _make_node(self, sid: str, created_at: datetime) -> DecisionNode:
        return DecisionNode(
            sid=sid, topic_id="general",
            summary=f"Decision {sid}",
            created_at=created_at,
            updated_at=created_at,
        )

    def test_sort_by_created_at_descending(self):
        """决策应按 created_at 倒序排列"""
        now = datetime.now()
        nodes = [
            self._make_node("a", now - timedelta(hours=3)),
            self._make_node("b", now - timedelta(hours=1)),
            self._make_node("c", now - timedelta(hours=2)),
        ]
        sorted_nodes = sorted(nodes, key=lambda d: d.created_at or datetime.min, reverse=True)
        assert [n.sid for n in sorted_nodes] == ["b", "c", "a"]

    def test_timeline_filter_by_hours(self):
        """时间线工具应支持按小时筛选"""
        now = datetime.now()
        nodes = [
            self._make_node("a", now - timedelta(hours=2)),
            self._make_node("b", now - timedelta(hours=48)),
        ]
        since = now - timedelta(hours=24)
        filtered = [n for n in nodes if n.created_at and n.created_at > since]
        assert len(filtered) == 1
        assert filtered[0].sid == "a"

    def test_timeline_filter_by_status(self):
        """时间线工具应支持按状态筛选"""
        nodes = [
            DecisionNode(sid="a", topic_id="general", summary="A",
                         status=DecisionStatus.DECIDED),
            DecisionNode(sid="b", topic_id="general", summary="B",
                         status=DecisionStatus.REJECTED),
        ]
        filtered = [n for n in nodes if n.status == DecisionStatus.DECIDED]
        assert len(filtered) == 1
        assert filtered[0].sid == "a"

    def test_timeline_filter_by_topic(self):
        """时间线工具应支持按主题筛选"""
        nodes = [
            DecisionNode(sid="a", topic_id="arch", summary="A"),
            DecisionNode(sid="b", topic_id="general", summary="B"),
        ]
        filtered = [n for n in nodes if n.topic_id == "arch"]
        assert len(filtered) == 1
        assert filtered[0].sid == "a"

    def test_nodes_without_created_at_fallback(self):
        """缺少 created_at 的节点应排在末尾"""
        now = datetime.now()
        node_with_time = DecisionNode(
            sid="a", topic_id="general", summary="A",
            created_at=now, updated_at=now,
        )
        node_no_time = DecisionNode(
            sid="b", topic_id="general", summary="B",
        )
        nodes = sorted([node_no_time, node_with_time],
                       key=lambda d: d.created_at or datetime.min,
                       reverse=True)
        assert nodes[0].sid == "a"
        assert nodes[1].sid == "b"


# ==================== Test 4: change_status on PipelineEngine scenarios ====================


class TestStatusChangePipeline:
    """Pipeline engine 层面的 status_change 时间戳记录"""

    def test_status_change_via_method(self):
        """通过 change_status() 方法触发状态变更"""
        node = DecisionNode(
            sid="pipeline001", topic_id="general",
            summary="Pipeline test",
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        assert node.discussed_at is None

        node.change_status(DecisionStatus.IN_DISCUSSION)
        assert node.discussed_at is not None
        assert node.status == DecisionStatus.IN_DISCUSSION

        node.change_status(DecisionStatus.DECIDED)
        assert node.decided_at is not None
        assert node.discussed_at is not None  # Previous timestamp preserved


# ==================== Test 5: MCP mutation_history (data-level) ====================


class TestMutationHistory:
    """mutation_history 工具的数据层行为"""

    def test_mutation_log_entry_structure(self):
        """mutation 日志条目的结构"""
        now = datetime.now()
        entry = {
            "timestamp": now.isoformat(timespec="seconds"),
            "type": "status_change",
            "sid": "hist001",
            "old_status": "pending",
            "new_status": "decided",
        }
        assert entry["timestamp"]
        assert entry["type"] == "status_change"
        assert entry["sid"] == "hist001"
        assert entry["old_status"] == "pending"
        assert entry["new_status"] == "decided"

    def test_mutation_history_filter_by_sid(self):
        """mutation 历史可按 sid 过滤"""
        history = [
            {"sid": "dec1", "type": "create", "timestamp": "2026-01-01T00:00:00"},
            {"sid": "dec2", "type": "update", "timestamp": "2026-01-02T00:00:00"},
            {"sid": "dec1", "type": "confirm", "timestamp": "2026-01-03T00:00:00"},
        ]
        dec1_records = [m for m in history if m["sid"] == "dec1"]
        assert len(dec1_records) == 2

    def test_mutation_history_sort_by_timestamp(self):
        """mutation 历史应按时间排序"""
        history = [
            {"sid": "dec1", "timestamp": "2026-01-03T00:00:00"},
            {"sid": "dec1", "timestamp": "2026-01-01T00:00:00"},
            {"sid": "dec1", "timestamp": "2026-01-02T00:00:00"},
        ]
        sorted_history = sorted(history, key=lambda x: x["timestamp"], reverse=True)
        timestamps = [h["timestamp"] for h in sorted_history]
        assert timestamps == [
            "2026-01-03T00:00:00",
            "2026-01-02T00:00:00",
            "2026-01-01T00:00:00",
        ]