"""Tests for Memory Consolidation (Sleep) mechanism."""

import tempfile
from pathlib import Path

import pytest

from memory.sleep import SleepManager, SleepReport, DecisionNode, DecisionStatus, ImpactLevel


def _make_decision(sid: str, summary: str, status: DecisionStatus = DecisionStatus.PENDING,
                   version: int = 1, confidence: float = 0.6, hot_score: float = 10.0) -> DecisionNode:
    """Helper to create DecisionNodes for testing."""
    d = DecisionNode(sid=sid, summary=summary, status=status, version=version,
                     confidence=confidence, impact_level=ImpactLevel.MINOR)
    if d.access_stats:
        d.access_stats.hot_score = hot_score
    return d


class TestSleepManager:
    def test_summary_similarity_exact(self):
        assert SleepManager._summary_similarity("采用K8s进行容器化", "采用K8s进行容器化") == 1.0

    def test_summary_similarity_high(self):
        sim = SleepManager._summary_similarity("采用K8s进行容器化", "采用K8s容器化部署")
        assert sim >= 0.5, f"Expected >=0.5, got {sim}"

    def test_summary_similarity_low(self):
        sim = SleepManager._summary_similarity("采用K8s进行容器化", "数据库选型为PostgreSQL")
        assert sim < 0.3, f"Expected <0.3, got {sim}"

    def test_summary_similarity_empty(self):
        assert SleepManager._summary_similarity("", "test") == 0.0
        assert SleepManager._summary_similarity("test", "") == 0.0
        assert SleepManager._summary_similarity("", "") == 0.0

    def test_decision_score_ordering(self):
        """Higher status + version + confidence should give higher score."""
        d1 = _make_decision("d1", "test", DecisionStatus.DECIDED, version=3, confidence=0.9, hot_score=50)
        d2 = _make_decision("d2", "test", DecisionStatus.PENDING, version=1, confidence=0.3, hot_score=5)
        assert SleepManager._decision_score(d1) > SleepManager._decision_score(d2)

    def test_pick_winner(self):
        mgr = SleepManager()
        d1 = _make_decision("d1", "test", DecisionStatus.DECIDED, version=2, confidence=0.8, hot_score=30)
        d2 = _make_decision("d2", "test", DecisionStatus.PENDING, version=1, confidence=0.4, hot_score=5)
        assert mgr._pick_winner(d1, d2) is True
        assert mgr._pick_winner(d2, d1) is False

    def test_deep_sleep_finds_duplicates(self):
        """Similar summaries should be flagged as duplicates."""
        decisions = [
            _make_decision("d1", "K8s容器化部署", DecisionStatus.DECIDED, version=2, confidence=0.9, hot_score=50),
            _make_decision("d2", "K8s容器化部署方案", DecisionStatus.PENDING, version=1, confidence=0.5, hot_score=5),
            _make_decision("d3", "数据库选型PG", DecisionStatus.DECIDED, version=1, confidence=0.8, hot_score=30),
        ]

        mgr = SleepManager()
        report = SleepReport()
        duplicates = mgr.deep_sleep(decisions, report)

        assert report.duplicates_found >= 1
        assert report.duplicates_found == len(duplicates)
        # d1 should be keeper (higher score)
        keep_sid, merge_sid, _ = duplicates[0]
        assert keep_sid == "d1"
        assert merge_sid == "d2"

    def test_promote_prunes_noise(self):
        """Low hot score + low confidence decisions should be pruned."""
        class FakeGraph:
            def upsert_decision(self, node, project):
                pass
        d = _make_decision("noise_1", "noise summary", confidence=0.1, hot_score=1.0)
        mgr = SleepManager(graph=FakeGraph())
        mgr._noise_hot_score_min = 5.0
        mgr._noise_confidence_min = 0.3

        report = SleepReport()
        mgr.promote([d], [], report)
        assert report.noise_pruned == 1
        assert d.status == DecisionStatus.SHELVED

    def test_promote_skips_good_decision(self):
        """Good decisions should not be pruned."""
        d = _make_decision("good", "good summary", confidence=0.8, hot_score=60.0)
        mgr = SleepManager()
        mgr._noise_hot_score_min = 5.0
        mgr._noise_confidence_min = 0.3

        report = SleepReport()
        mgr.promote([d], [], report)
        assert report.noise_pruned == 0

    def test_sleep_report_to_dict(self):
        report = SleepReport()
        report.total_decisions = 10
        report.duplicates_found = 2
        report.duplicates_merged = 2
        report.noise_pruned = 1
        report.conflicts_found = 0
        report.hot_scores_updated = 10
        report.decisions_promoted = 3

        d = report.to_dict()
        assert d["total_decisions"] == 10
        assert d["duplicates_found"] == 2
        assert d["duplicates_merged"] == 2
        assert d["noise_pruned"] == 1
        assert d["phase"] == ""
        assert "timestamp" in d

    def test_wave_without_persistence(self):
        """wave() should not crash when no persistence components are set."""
        mgr = SleepManager()
        report = SleepReport()
        mgr.wave(report)
        assert report.phase == "wave"
        assert not report.errors  # no errors, just nothing happened

    def test_light_sleep_without_graph(self):
        """light_sleep() should return empty when no graph."""
        mgr = SleepManager()
        report = SleepReport()
        result = mgr.light_sleep(report)
        assert result == []
        assert report.errors == ["No graph available"]

    def test_full_sleep_cycle_without_components(self):
        """A full sleep cycle should not crash even with no components."""
        mgr = SleepManager()
        report = mgr.sleep()
        d = report.to_dict()
        assert d["phase"] == "wave"
        assert d["total_decisions"] == 0

    def test_deep_sleep_recalculates_hot_scores(self):
        """deep_sleep should attempt to recalculate hot scores."""
        class FakeGraph:
            def recalculate_hot_score(self, sid):
                pass
            def get_all_decisions(self):
                return []

        mgr = SleepManager(graph=FakeGraph())
        report = SleepReport()
        mgr.deep_sleep([], report)
        # No decisions so no updates, but should not crash
        assert report.hot_scores_updated == 0