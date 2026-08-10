from pathlib import Path

import pytest

from experiments.production_ablation.fixtures import FixtureNeo4jSync
from experiments.production_ablation.runner import run_variant
from experiments.production_ablation.variants import build_variants


class FakeDecisionExtractor:
    def __init__(self):
        self.context_calls = []
        self.direct_calls = 0

    async def extract_with_context(self, content, entity_context=None, existing_decisions=None, project_context=None):
        self.context_calls.append({"entities": entity_context, "project": project_context, "existing": existing_decisions})
        return [{
            "title": "采用 PostgreSQL", "summary": "确认采用PostgreSQL。", "status": "decided",
            "impact_level": "major", "is_suggestion": False,
            "source_message_id": "m1", "source_message_ids": ["m1"],
            "evidence_quote": "确认采用PostgreSQL。",
        }]

    async def extract_decision(self, content):
        self.direct_calls += 1
        return [{
            "title": "采用 PostgreSQL", "summary": "确认采用PostgreSQL。", "status": "decided",
            "impact_level": "major", "is_suggestion": False,
            "source_message_id": "m1", "source_message_ids": ["m1"],
            "evidence_quote": "确认采用PostgreSQL。",
        }]


class FakeMemoryExtractor:
    async def extract(self, content, episode_id="", existing_entities=None):
        from src.extractors.memory_types import MemoryExtractionResult
        return MemoryExtractionResult()

    def set_trace_id(self, trace_id):
        pass


def _messages():
    return {
        "chat-a": (
            {"chat_id": "chat-a", "msg_id": "m1", "speaker": "Alice", "msg": "确认采用PostgreSQL。"},
            {"chat_id": "chat-a", "msg_id": "m2", "speaker": "Bob", "msg": "团队立即开始数据库迁移。"},
        )
    }


def test_variants_each_change_exactly_one_option():
    variants = build_variants()
    full = variants["full"]
    assert len(variants) == 7
    for name, variant in variants.items():
        if name != "full":
            assert len(variant.options.changed_fields_from(full.options)) == 1


@pytest.mark.asyncio
async def test_full_production_runner_reads_history_and_uses_context(tmp_path: Path):
    extractor = FakeDecisionExtractor()
    history = FixtureNeo4jSync(entities_by_chat={"chat-a": [{"name": "PostgreSQL", "entity_type": "Technology"}]})
    run = await run_variant(_messages(), build_variants()["full"], tmp_path / "full", extractor, memory_extractor=FakeMemoryExtractor(), neo4j_sync=history)
    assert not run.errors
    assert run.trace.neo4j_history_reads == 2
    assert extractor.context_calls
    assert run.decisions[0].chat_id == "chat-a"
    assert run.decisions[0].source_message_ids == ("m1",)
    assert run.decisions[0].evidence_quote == "确认采用PostgreSQL。"
    assert run.trace.memory_extraction_enabled


@pytest.mark.asyncio
async def test_no_memory_extractor_uses_direct_engine_branch(tmp_path: Path):
    extractor = FakeDecisionExtractor()
    run = await run_variant(_messages(), build_variants()["no_memory_extractor"], tmp_path / "direct", extractor, memory_extractor=FakeMemoryExtractor(), neo4j_sync=FixtureNeo4jSync())
    assert not run.errors
    assert extractor.direct_calls == 1
    assert not extractor.context_calls
    assert not run.trace.memory_extraction_enabled


@pytest.mark.asyncio
async def test_no_neo4j_history_prevents_production_history_reads(tmp_path: Path):
    extractor = FakeDecisionExtractor()
    history = FixtureNeo4jSync(entities_by_chat={"chat-a": [{"name": "PostgreSQL", "entity_type": "Technology"}]})
    run = await run_variant(_messages(), build_variants()["no_neo4j_history"], tmp_path / "no-history", extractor, memory_extractor=FakeMemoryExtractor(), neo4j_sync=history)
    assert not run.errors
    assert run.trace.neo4j_history_reads == 0


@pytest.mark.asyncio
async def test_runner_surfaces_engine_swallowed_extraction_errors(tmp_path: Path):
    class BrokenExtractor:
        async def extract_with_context(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

        async def extract_decision(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    run = await run_variant(_messages(), build_variants()["full"], tmp_path / "broken", BrokenExtractor(), memory_extractor=FakeMemoryExtractor(), neo4j_sync=FixtureNeo4jSync())
    assert run.errors
    assert "production pipeline error" in run.errors[0]


@pytest.mark.asyncio
async def test_runner_surfaces_extractor_recorded_errors_when_output_is_empty(tmp_path: Path):
    class SwallowingExtractor:
        def __init__(self):
            self.last_error = ""

        async def extract_with_context(self, *args, **kwargs):
            self.last_error = "llm_call_error: provider unavailable"
            return None

        async def extract_decision(self, *args, **kwargs):
            self.last_error = "llm_call_error: provider unavailable"
            return None

    run = await run_variant(
        _messages(),
        build_variants()["full"],
        tmp_path / "swallowed",
        SwallowingExtractor(),
        memory_extractor=FakeMemoryExtractor(),
        neo4j_sync=FixtureNeo4jSync(),
    )

    assert run.errors
    assert "decision_extractor error" in run.errors[0]
