"""Tests for graph module: MemoryGraph, HypergraphBuilder, SnapshotManager"""

from datetime import datetime, timedelta

import pytest

from graph.memory_graph import Conflict, MemoryGraph
from graph.builder import HypergraphBuilder
from graph.retrieval import HierarchicalRetriever, RetrievalResult
from graph.snapshot import DetectorSnapshot, SnapshotManager
from node.node import DecisionNode
from node.types import DecisionStatus, ImpactLevel, Relation, RelationType


class TestMemoryGraph:
    def test_init_empty(self):
        g = MemoryGraph()
        assert g.count() == 0
        assert g.topic_count("test") == 0

    def test_upsert_and_get_decision(self):
        g = MemoryGraph()
        node = DecisionNode(
            sid="test-001",
            topic_id="topic-a",
            summary="Test decision",
            full_text="We decided to test",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR,
        )
        g.upsert_decision(node, "test-project")

        assert g.count() == 1
        got = g.get_decision("test-001")
        assert got is not None
        assert got.sid == "test-001"
        assert got.summary == "Test decision"

    def test_delete_decision(self):
        g = MemoryGraph()
        node = DecisionNode(sid="test-002", topic_id="topic-a", summary="To be deleted")
        g.upsert_decision(node, "p")
        assert g.count() == 1
        g.delete_decision("test-002")
        assert g.count() == 0

    def test_query_by_topic(self):
        g = MemoryGraph()
        for i in range(3):
            node = DecisionNode(
                sid=f"t-00{i}",
                topic_id="topic-x",
                summary=f"Decision {i}",
                status=DecisionStatus.DECIDED,
            )
            g.upsert_decision(node, "p")
        results = g.query_by_topic("p", "topic-x")
        assert len(results) == 3

    def test_search_by_keywords(self):
        g = MemoryGraph()
        g.upsert_decision(
            DecisionNode(sid="k1", topic_id="t", summary="Alpha release", status=DecisionStatus.DECIDED), "p"
        )
        g.upsert_decision(
            DecisionNode(sid="k2", topic_id="t", summary="Beta version", status=DecisionStatus.DECIDED), "p"
        )
        g.upsert_decision(
            DecisionNode(sid="k3", topic_id="t", summary="Gamma test", status=DecisionStatus.SHELVED), "p"
        )
        results = g.search_by_keywords("alpha")
        assert len(results) == 1
        assert results[0].sid == "k1"

    def test_detect_conflicts(self):
        g = MemoryGraph()
        existing = DecisionNode(
            sid="existing-1",
            topic_id="t",
            summary="Existing decision",
            status=DecisionStatus.DECIDED,
            relations=[
                Relation(target_id="conflicting-new", type=RelationType.CONFLICTS_WITH, description="conflict")
            ],
        )
        g.upsert_decision(existing, "p")

        new_node = DecisionNode(
            sid="conflicting-new",
            topic_id="t",
            summary="New conflicting decision",
            status=DecisionStatus.DECIDED,
        )
        conflicts = g.detect_conflicts(new_node)
        assert len(conflicts) == 1
        assert conflicts[0].decision_a == "existing-1"
        assert conflicts[0].decision_b == "conflicting-new"

    def test_hot_score(self):
        g = MemoryGraph()
        node = DecisionNode(sid="hot-1", topic_id="t", summary="Hot decision", status=DecisionStatus.DECIDED)
        g.upsert_decision(node, "p")

        g.record_reference("hot-1")
        g.record_reference("hot-1")
        g.update_access_stats("hot-1")
        g.recalculate_hot_score("hot-1")

        updated = g.get_decision("hot-1")
        assert updated is not None
        assert updated.access_stats.reference_count == 2
        assert updated.access_stats.access_count == 1
        assert updated.access_stats.hot_score > 0

    def test_get_dirty_and_clean(self):
        g = MemoryGraph()
        g.upsert_decision(DecisionNode(sid="d1", topic_id="t", summary="Dirty 1"), "p")
        g.upsert_decision(DecisionNode(sid="d2", topic_id="t", summary="Dirty 2"), "p")
        dirty = g.get_dirty_and_clean()
        assert len(dirty) == 2
        assert g.get_dirty_and_clean() == []


class TestHypergraphBuilder:
    def test_build_from_content(self):
        builder = HypergraphBuilder()
        result = builder.build_from_content("Hello world", source_id="msg-1", source_type="im")
        assert result["source_id"] == "msg-1"
        assert result["source_type"] == "im"
        assert "topics" in result
        assert "facts" in result
        assert "hyperedges" in result

    def test_build_decision_hypergraph(self):
        builder = HypergraphBuilder()
        decisions = [
            DecisionNode(sid="d1", topic_id="topic-a", summary="Dec 1", status=DecisionStatus.DECIDED),
            DecisionNode(sid="d2", topic_id="topic-a", summary="Dec 2", status=DecisionStatus.PENDING),
            DecisionNode(sid="d3", topic_id="topic-b", summary="Dec 3", status=DecisionStatus.DECIDED),
        ]
        hg = builder.build_decision_hypergraph(decisions)
        assert hg["decision_count"] == 3
        assert hg["topic_count"] == 2
        assert "topic-a" in hg["topics"]
        assert "topic-b" in hg["topics"]
        assert hg["topics"]["topic-a"]["decision_count"] == 2
        assert hg["topics"]["topic-b"]["decision_count"] == 1

    def test_build_from_episodes(self):
        builder = HypergraphBuilder()
        episodes = [
            {"event_id": "ep-1", "summary": "First episode"},
            {"event_id": "ep-2", "summary": "Second episode"},
        ]
        result = builder.build_from_episodes(episodes)
        assert "ep-1" in result["episodes"]
        assert "ep-2" in result["episodes"]


class TestSnapshot:
    def test_snapshot_create(self, tmp_path):
        from src.signal.types import DecisionLevel, DetectionResult, ScoreBreakdown
        result = DetectionResult(
            score=0.85,
            level=DecisionLevel.HIGH,
            is_decision=True,
            factors=ScoreBreakdown(lexical=1.0, structural=0.0, dynamic=0.0, pattern=0.8, anti_score=0.0, final=0.82),
        )
        snapshot = DetectorSnapshot.from_detection("We decided to launch", "im", result)
        assert snapshot.snapshot_id.startswith("snap-")
        assert snapshot.detection_result["is_decision"] is True
        assert snapshot.detection_result["score"] == 0.85

    def test_snapshot_manager_save_and_load(self, tmp_path):
        from src.signal.types import DecisionLevel, DetectionResult, ScoreBreakdown
        mgr = SnapshotManager(str(tmp_path))
        result = DetectionResult(
            score=0.9, level=DecisionLevel.HIGH, is_decision=True,
            factors=ScoreBreakdown(lexical=1.0, structural=0.5, dynamic=0.0, pattern=0.8, anti_score=0.0, final=0.82),
        )
        snapshot = DetectorSnapshot.from_detection("Test content", "im", result)
        path = mgr.save_snapshot(snapshot)
        loaded = mgr.load_snapshot(snapshot.snapshot_id)
        assert loaded is not None
        assert loaded.snapshot_id == snapshot.snapshot_id


class TestRetrieval:
    def test_retrieve_empty_graph(self):
        retriever = HierarchicalRetriever()
        result = retriever.retrieve("test query")
        assert result.total_count == 0

    def test_retrieve_with_graph(self):
        g = MemoryGraph()
        g.upsert_decision(
            DecisionNode(sid="r1", topic_id="t", summary="Foo bar decision", status=DecisionStatus.DECIDED), "p"
        )
        retriever = HierarchicalRetriever(memory_graph=g)
        result = retriever.retrieve("foo")
        assert result.total_count == 1
        assert result.decisions[0].sid == "r1"