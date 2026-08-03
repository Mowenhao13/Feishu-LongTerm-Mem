"""Tests for Hypergraph persistence: save/load round-trip validation."""
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from graph.persistence import HypergraphPersistence
from src.structure import (
    DecisionNode,
    DecisionStatus,
    EpisodeNode,
    Hypergraph,
    TopicNode,
)


def _build_simple_hypergraph() -> Hypergraph:
    """Build a Hypergraph with the simplified 2-layer structure."""
    hg = Hypergraph()

    # ── Knowledge Layer: Decisions ──
    hg.add_node("decision", "dec_001",
                title="Use Vite",
                content="决定使用 Vite 作为构建工具",
                confidence=0.9,
                status=DecisionStatus.PENDING,
                proposer="Alice",
                impact_level="major",
                rationale="更快的 dev server")
    hg.add_node("decision", "dec_002",
                title="Use Vue",
                content="决定使用 Vue 3 框架",
                confidence=0.85,
                status=DecisionStatus.PENDING,
                proposer="Alice",
                impact_level="major",
                rationale="团队熟悉度高")

    # ── Raw Data Layer: Episodes ──
    hg.add_node("episode", "ep_001",
                user_id_list=["ou_alice", "ou_bob"],
                summary="讨论了前端技术栈选型",
                subject="技术选型讨论",
                topic_id="topic_001")
    hg.add_node("episode", "ep_002",
                user_id_list=["ou_alice", "ou_bob", "ou_carl"],
                summary="讨论了构建优化方案",
                subject="构建优化",
                topic_id="topic_001")

    # ── Knowledge Layer: Topics ──
    hg.add_node("topic", "topic_001",
                title="前端技术栈",
                summary="前端技术栈选型与构建优化相关的讨论",
                episode_ids=["ep_001", "ep_002"],
                keywords=["前端", "技术栈", "构建"])

    return hg


class TestHypergraphPersistence:
    def test_save_and_load_empty(self):
        """Empty Hypergraph should survive round-trip."""
        hg = Hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)

            persister.save(hg)
            assert fp.exists()

            loaded = persister.load()
            assert loaded.get_stats() == hg.get_stats()
            assert loaded.to_dict() == hg.to_dict()

    def test_save_and_load_full(self):
        """Full 2-layer Hypergraph should survive round-trip."""
        hg = _build_simple_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)

            persister.save(hg)
            assert fp.exists()

            loaded = persister.load()
            self._assert_hypergraph_equal(hg, loaded)

    def test_save_to_nested_directory(self):
        """Should create parent directories automatically."""
        hg = Hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "nested" / "path" / "state.json"
            persister = HypergraphPersistence(fp)
            persister.save(hg)
            assert fp.exists()

            loaded = persister.load()
            assert loaded.to_dict() == hg.to_dict()

    def test_exists_method(self):
        """exists() should return correct status."""
        hg = _build_simple_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)

            assert not persister.exists()
            persister.save(hg)
            assert persister.exists()

    def test_load_nonexistent_file(self):
        """Loading a non-existent file should raise FileNotFoundError."""
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "nonexistent.json"
            persister = HypergraphPersistence(fp)
            with pytest.raises(FileNotFoundError):
                persister.load()

    def test_delete_method(self):
        """delete() should remove the file."""
        hg = _build_simple_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)
            persister.save(hg)
            assert persister.exists()
            persister.delete()
            assert not persister.exists()

    def test_saved_file_is_valid_json(self):
        """The saved file must be valid JSON with correct structure."""
        hg = _build_simple_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)
            persister.save(hg)

            with open(fp, "r", encoding="utf-8") as f:
                raw = json.load(f)

            assert "decisions" in raw
            assert "episodes" in raw
            assert "topics" in raw
            # No hyperedge dictionaries in simplified structure
            assert "decision_hyperedges" not in raw
            assert "fact_hyperedges" not in raw
            assert "episode_hyperedges" not in raw

            assert raw["decisions"]["dec_001"]["title"] == "Use Vite"
            assert raw["episodes"]["ep_001"]["subject"] == "技术选型讨论"
            assert raw["topics"]["topic_001"]["title"] == "前端技术栈"

    # ── helpers ──

    def _assert_hypergraph_equal(self, a: Hypergraph, b: Hypergraph):
        """Assert two Hypergraphs have identical structure."""
        assert a.to_dict() == b.to_dict(), (
            f"to_dict differs:\nA={a.to_dict()}\nB={b.to_dict()}"
        )
        stats_a = a.get_stats()
        stats_b = b.get_stats()
        assert stats_a == stats_b, f"stats differ: {stats_a} != {stats_b}"