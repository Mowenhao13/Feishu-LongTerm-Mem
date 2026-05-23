"""Push engine unit tests"""
from __future__ import annotations

from src.card.config import CardConfig
from src.card.pusher import PushEngine, PushTrigger
from src.graph.memory_graph import MemoryGraph
from src.node.node import DecisionNode
from node.types import AccessStats, DecisionStatus, ImpactLevel


class TestPushEngine:
    def test_push_decision_card(self, capsys):
        graph = MemoryGraph()
        config = CardConfig(
            enable_feishu=False,
            enable_terminal=True,
            enable_osascript=False,
            trigger_on_conflict=True,
            trigger_on_update=True,
            trigger_on_hot_score_threshold=True,
            hot_score_low_threshold=20.0,
            push_hot_score_increment=10.0,
            hot_score_decay_rate=0.95,
        )
        engine = PushEngine(config=config, memory_graph=graph)

        node = DecisionNode(
            sid="test-001",
            topic_id="testing",
            summary="Test push decision",
            status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MINOR,
            access_stats=AccessStats(hot_score=50.0),
        )
        graph.upsert_decision(node, "test-project")

        result = engine.push_decision_card("test-001", PushTrigger.MANUAL_QUERY)
        assert result is True

        captured = capsys.readouterr()
        assert "test-001" in captured.out or "决策" in captured.out

    def test_push_conflict_card(self, capsys):
        graph = MemoryGraph()
        config = CardConfig(enable_feishu=False, enable_terminal=True, enable_osascript=False)
        engine = PushEngine(config=config, memory_graph=graph)

        node_a = DecisionNode(sid="a-001", topic_id="t", summary="Decision A", access_stats=AccessStats(hot_score=50.0))
        node_b = DecisionNode(sid="b-001", topic_id="t", summary="Decision B", access_stats=AccessStats(hot_score=60.0))
        graph.upsert_decision(node_a, "p")
        graph.upsert_decision(node_b, "p")

        result = engine.push_conflict_card("a-001", "b-001", "conflict reason")
        assert result is True

    def test_push_update_card(self, capsys):
        graph = MemoryGraph()
        config = CardConfig(enable_feishu=False, enable_terminal=True, enable_osascript=False)
        engine = PushEngine(config=config, memory_graph=graph)

        node = DecisionNode(sid="u-001", topic_id="t", summary="Update test", access_stats=AccessStats(hot_score=50.0))
        graph.upsert_decision(node, "p")

        result = engine.push_decision_update_card("u-001", "pending", "decided")
        assert result is True

    def test_push_low_hot_score(self, capsys):
        graph = MemoryGraph()
        config = CardConfig(
            enable_feishu=False, enable_terminal=True, enable_osascript=False,
            hot_score_low_threshold=20.0,
        )
        engine = PushEngine(config=config, memory_graph=graph)

        node = DecisionNode(sid="low-001", topic_id="t", summary="Low hot score", access_stats=AccessStats(hot_score=5.0))
        graph.upsert_decision(node, "p")

        result = engine.push_low_hot_score_decisions()
        assert result is True

    def test_push_daily_summary(self, capsys):
        graph = MemoryGraph()
        config = CardConfig(enable_feishu=False, enable_terminal=True, enable_osascript=False)
        engine = PushEngine(config=config, memory_graph=graph)

        node = DecisionNode(sid="dly-001", topic_id="t", summary="Daily test", access_stats=AccessStats(hot_score=50.0))
        graph.upsert_decision(node, "p")

        result = engine.push_daily_summary()
        assert result is True

    def test_hot_score_increment_and_decay(self):
        graph = MemoryGraph()
        config = CardConfig(
            enable_feishu=False, enable_terminal=True, enable_osascript=False,
            push_hot_score_increment=10.0, hot_score_decay_rate=0.5,
        )
        engine = PushEngine(config=config, memory_graph=graph)

        node = DecisionNode(sid="hot-001", topic_id="t", summary="Hot score test", access_stats=AccessStats(hot_score=50.0))
        graph.upsert_decision(node, "p")

        engine._increment_hot_score(node)
        assert node.access_stats.hot_score == 60.0

        engine._decay_all_hot_scores()
        assert node.access_stats.hot_score == 30.0

        node_after = graph.get_decision("hot-001")
        assert node_after.access_stats.hot_score == 30.0

    def test_push_nonexistent_decision(self, capsys):
        graph = MemoryGraph()
        config = CardConfig(enable_feishu=False, enable_terminal=True, enable_osascript=False)
        engine = PushEngine(config=config, memory_graph=graph)

        result = engine.push_decision_card("nonexistent")
        assert result is False