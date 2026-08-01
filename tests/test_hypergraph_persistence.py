"""Tests for Hypergraph persistence: save/load round-trip validation."""

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from graph.persistence import HypergraphPersistence
from src.structure import (
    DecisionHyperedge,
    DecisionNode,
    DecisionRole,
    DecisionStatus,
    EpisodeHyperedge,
    EpisodeNode,
    EpisodeRole,
    FactHyperedge,
    FactNode,
    FactRole,
    Hypergraph,
    TopicNode,
)


def _build_full_hypergraph() -> Hypergraph:
    """Build a Hypergraph with all 4 layers populated and valid bidirectional links."""
    hg = Hypergraph()

    # ── L0: Decision Layer ──
    hg.add_node("decision", "dec_001",
                title="Use Vite",
                content="决定使用 Vite 作为构建工具",
                confidence=0.9,
                status=DecisionStatus.CONFIRMED,
                proposer="Alice",
                impact_level="major",
                rationale="更快的 dev server")
    hg.add_node("decision", "dec_002",
                title="Use Vue",
                content="决定使用 Vue 3 框架",
                confidence=0.85,
                status=DecisionStatus.CONFIRMED,
                proposer="Alice",
                impact_level="major",
                rationale="团队熟悉度高")

    # ── L1: Fact Layer ──
    hg.add_node("fact", "fact_001",
                content="Vite 比 Webpack 快 10 倍",
                keywords=["vite", "webpack", "performance"],
                temporal="2026 Q2")
    hg.add_node("fact", "fact_002",
                content="Vue 3 使用 Composition API",
                keywords=["vue3", "composition-api"])

    # ── L2: Episode Layer ──
    hg.add_node("episode", "ep_001",
                user_id_list=["ou_alice", "ou_bob"],
                summary="讨论了前端技术栈选型",
                subject="技术选型讨论",
                episode_description="Alice 和 Bob 讨论了前端技术选型，最终决定使用 Vite + Vue 3",
                keywords=["前端", "技术选型"])
    hg.add_node("episode", "ep_002",
                user_id_list=["ou_alice", "ou_bob", "ou_carl"],
                summary="讨论了构建优化方案",
                subject="构建优化",
                episode_description="进一步讨论 Vite 的构建优化配置",
                keywords=["构建", "优化"])

    # ── L3: Topic Layer ──
    hg.add_node("topic", "topic_001",
                title="前端技术栈",
                summary="前端技术栈选型与构建优化相关的讨论",
                keywords=["前端", "技术栈", "构建"])

    # ── Hyperedges ──
    hg.add_hyperedge("episode", "eh_001",
                     relation={"ep_001": EpisodeRole.INITIATING.value,
                               "ep_002": EpisodeRole.DEVELOPING.value},
                     weights={"ep_001": 1.0, "ep_002": 0.8},
                     topic_node_id="topic_001",
                     coherence_score=0.9)

    hg.add_hyperedge("decision", "dh_001",
                     relation={"dec_001": DecisionRole.PRIMARY.value,
                               "dec_002": DecisionRole.SUPPORTING.value},
                     weights={"dec_001": 1.0, "dec_002": 0.7},
                     episode_node_id="ep_001")

    hg.add_hyperedge("fact", "fh_001",
                     relation={"fact_001": FactRole.CORE.value,
                               "fact_002": FactRole.DETAIL.value},
                     weights={"fact_001": 1.0, "fact_002": 0.6},
                     episode_node_id="ep_001")

    # ── Episode → FactHyperedge 反向链接 ──
    hg.episodes["ep_001"].fact_hyperedge_id = "fh_001"

    # ── Topic → EpisodeHyperedge 反向链接 ──
    hg.topics["topic_001"].episode_ids = ["ep_001", "ep_002"]
    hg.topics["topic_001"].episode_hyperedge_id = "eh_001"

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
        """Full 4-layer Hypergraph with bidirectional links should survive round-trip."""
        hg = _build_full_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)

            persister.save(hg)
            assert fp.exists()

            loaded = persister.load()
            self._assert_hypergraph_equal(hg, loaded)

    def test_validate_bidirectional_links_after_roundtrip(self):
        """Bidirectional links must be consistent after save/load."""
        hg = _build_full_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)
            persister.save(hg)
            loaded = persister.load()

            errors = loaded.validate_bidirectional_links()
            for key, errs in errors.items():
                assert len(errs) == 0, f"{key}: {errs}"

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
        hg = _build_full_hypergraph()
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
        hg = _build_full_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)
            persister.save(hg)
            assert persister.exists()
            persister.delete()
            assert not persister.exists()

    def test_saved_file_is_valid_json(self):
        """The saved file must be valid JSON with correct structure."""
        hg = _build_full_hypergraph()
        with TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "state.json"
            persister = HypergraphPersistence(fp)
            persister.save(hg)

            with open(fp, "r", encoding="utf-8") as f:
                raw = json.load(f)

            assert "decisions" in raw
            assert "decision_hyperedges" in raw
            assert "facts" in raw
            assert "fact_hyperedges" in raw
            assert "episodes" in raw
            assert "episode_hyperedges" in raw
            assert "topics" in raw

            assert raw["decisions"]["dec_001"]["title"] == "Use Vite"
            assert raw["episodes"]["ep_001"]["subject"] == "技术选型讨论"
            assert raw["topics"]["topic_001"]["title"] == "前端技术栈"
            assert raw["episode_hyperedges"]["eh_001"]["topic_node_id"] == "topic_001"

    # ── helpers ──

    def _assert_hypergraph_equal(self, a: Hypergraph, b: Hypergraph):
        """Assert two Hypergraphs have identical structure."""
        assert a.to_dict() == b.to_dict(), (
            f"to_dict differs:\nA={a.to_dict()}\nB={b.to_dict()}"
        )
        stats_a = a.get_stats()
        stats_b = b.get_stats()
        assert stats_a == stats_b, f"stats differ: {stats_a} != {stats_b}"