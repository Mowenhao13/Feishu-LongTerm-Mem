"""Tests for agentic baseline decision extraction tiers."""

from __future__ import annotations

import json
from typing import Any

import pytest


# ── ChatTools tests ────────────────────────────────────────────────


class TestChatTools:
    """Tests for the tool implementations used by Tier 3."""

    def _sample_messages(self) -> list[dict]:
        return [
            {"msg_id": "m001", "speaker": "张三", "msg": "我们决定采用 PostgreSQL 作为主数据库"},
            {"msg_id": "m002", "speaker": "李四", "msg": "同意，PostgreSQL 性能更好"},
            {"msg_id": "m003", "speaker": "王五", "msg": "建议加个 Redis 缓存层"},
            {"msg_id": "m004", "speaker": "张三", "msg": "进度更新：已完成 POC"},
        ]

    def test_search_messages_finds_keyword(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        results = tools.search_messages("PostgreSQL")
        assert len(results) == 2
        assert results[0]["msg_id"] == "m001"
        assert results[1]["msg_id"] == "m002"

    def test_search_messages_case_insensitive(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        results = tools.search_messages("postgresql")
        assert len(results) == 2

    def test_get_speaker_messages(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        results = tools.get_speaker_messages("张三")
        assert len(results) == 2
        assert {r["msg_id"] for r in results} == {"m001", "m004"}

    def test_check_evidence_exact_match(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        result = tools.check_evidence("m001", "决定采用 PostgreSQL")
        assert result["valid"] is True

    def test_check_evidence_missing_msg(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        result = tools.check_evidence("m999", "some quote")
        assert result["valid"] is False
        assert "not found" in result["reason"]

    def test_submit_decisions_stores_and_returns(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        decisions = [{"title": "采用 PostgreSQL", "topic": "数据库"}]
        result = tools.submit_decisions(decisions)
        assert result["submitted"] == 1
        assert tools.decisions == decisions

    def test_list_existing_decisions_empty_initially(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        assert tools.list_existing_decisions() == []

    def test_execute_dispatches_correctly(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        result = tools.execute("search_messages", {"keyword": "Redis"})
        assert len(result) == 1
        assert result[0]["msg_id"] == "m003"

    def test_execute_unknown_tool(self):
        from experiments.ablation.agentic_baseline import ChatTools
        tools = ChatTools(self._sample_messages())
        result = tools.execute("nonexistent", {})
        assert "error" in result


# ── Tier function tests ────────────────────────────────────────────


class TestTierFunctions:
    """Test that tier functions handle LLM responses correctly."""

    def _sample_messages(self) -> list[dict]:
        return [
            {"msg_id": "m001", "speaker": "张三", "msg": "我们决定采用 PostgreSQL"},
            {"msg_id": "m002", "speaker": "李四", "msg": "同意"},
        ]

    @pytest.mark.asyncio
    async def test_tier1_returns_decisions(self):
        from experiments.ablation.agentic_baseline import run_tier1_single_shot

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "decisions": [{"title": "采用 PostgreSQL", "summary": "test"}],
                    "reasoning": "test",
                })

        result = await run_tier1_single_shot(FakeProvider(), self._sample_messages(), "test-chat")
        assert result["ok"] is True
        assert result["decision_count"] == 1
        assert result["tier"] == "tier1_single_shot"
        assert result["llm_calls"] == 1

    @pytest.mark.asyncio
    async def test_tier2_extracts_validated_decisions(self):
        from experiments.ablation.agentic_baseline import run_tier2_structured

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "scan": {"speakers": ["张三"], "topics": ["数据库"], "decision_points": ["m001"]},
                    "candidates": [],
                    "validated_decisions": [{"title": "采用 PostgreSQL", "decision_kind": "choice"}],
                    "reasoning": "test",
                })

        result = await run_tier2_structured(FakeProvider(), self._sample_messages(), "test-chat")
        assert result["ok"] is True
        assert result["decision_count"] == 1
        assert result["tier"] == "tier2_structured"

    @pytest.mark.asyncio
    async def test_tier3_terminates_on_submit(self):
        from experiments.ablation.agentic_baseline import run_tier3_agentic

        call_count = 0

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return json.dumps({
                        "tool": "search_messages",
                        "args": {"keyword": "决定"},
                        "thought": "搜索决策关键词",
                    })
                return json.dumps({
                    "tool": "submit_decisions",
                    "args": {"decisions": [{"title": "采用 PostgreSQL"}]},
                    "thought": "提交结果",
                })

        result = await run_tier3_agentic(FakeProvider(), self._sample_messages(), "test-chat", max_turns=5)
        assert result["ok"] is True
        assert result["decision_count"] == 1
        assert result["llm_calls"] == 2
        assert result["tier"] == "tier3_agentic"

    @pytest.mark.asyncio
    async def test_tier3_respects_max_turns(self):
        from experiments.ablation.agentic_baseline import run_tier3_agentic

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "tool": "search_messages",
                    "args": {"keyword": "test"},
                    "thought": "keep searching",
                })

        result = await run_tier3_agentic(FakeProvider(), self._sample_messages(), "test-chat", max_turns=3)
        assert result["llm_calls"] == 3
        assert result["decision_count"] == 0


# ── JSON parsing tests ─────────────────────────────────────────────


class TestJsonParsing:
    """Test JSON response parsing with various formats."""

    def test_direct_json(self):
        from experiments.ablation.agentic_baseline import _parse_json_response
        result = _parse_json_response('{"decisions": []}')
        assert result == {"decisions": []}

    def test_markdown_wrapped(self):
        from experiments.ablation.agentic_baseline import _parse_json_response
        result = _parse_json_response('```json\n{"decisions": []}\n```')
        assert result == {"decisions": []}

    def test_text_before_json(self):
        from experiments.ablation.agentic_baseline import _parse_json_response
        result = _parse_json_response('Here is the result:\n{"decisions": [{"title": "test"}]}')
        assert result is not None
        assert len(result["decisions"]) == 1

    def test_empty_returns_none(self):
        from experiments.ablation.agentic_baseline import _parse_json_response
        assert _parse_json_response("") is None
        assert _parse_json_response(None) is None
