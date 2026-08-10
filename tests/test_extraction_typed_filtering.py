"""Tests for decision_kind typed filtering in Stage 2 extraction.

Covers:
- decision_kind parsing from LLM response
- status/discussion deterministic filtering
- suggestion forced is_suggestion=True
- EvidenceDecision.is_confirmed per decision_kind
- extraction stats counters
- compound-decision and context-boundary prompt guidance
"""

from __future__ import annotations

import json
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# EvidenceDecision.is_confirmed by decision_kind
# ---------------------------------------------------------------------------


class TestEvidenceDecisionKind:
    """EvidenceDecision.is_confirmed respects decision_kind."""

    @pytest.mark.parametrize(
        "kind,expected",
        [
            ("choice", True),
            ("conditional_choice", True),
            ("execution_commitment", True),
            ("policy_constraint", True),
            ("suggestion", False),
            ("status", False),
            ("discussion", False),
        ],
    )
    def test_is_confirmed_by_decision_kind(self, kind: str, expected: bool):
        from src.eval.confirmed_decision_eval import EvidenceDecision

        d = EvidenceDecision(
            chat_id="c1",
            title="test",
            summary="test",
            status="decided",
            is_suggestion=False,
            decision_kind=kind,
        )
        assert d.is_confirmed is expected

    def test_is_confirmed_defaults_to_choice(self):
        from src.eval.confirmed_decision_eval import EvidenceDecision

        d = EvidenceDecision(
            chat_id="c1",
            title="test",
            summary="test",
            status="decided",
            is_suggestion=False,
        )
        assert d.decision_kind == "choice"
        assert d.is_confirmed is True

    def test_suggestion_kind_overrides_is_suggestion_false(self):
        """decision_kind='suggestion' makes is_confirmed False even if is_suggestion=False."""
        from src.eval.confirmed_decision_eval import EvidenceDecision

        d = EvidenceDecision(
            chat_id="c1",
            title="test",
            summary="test",
            status="decided",
            is_suggestion=False,
            decision_kind="suggestion",
        )
        assert d.is_confirmed is False


# ---------------------------------------------------------------------------
# Prompt contains required guidance
# ---------------------------------------------------------------------------


class TestPromptGuidance:
    """DECISION_EXTRACTION_PROMPT_SHORT contains decision_kind, compound, and context guidance."""

    def test_prompt_contains_decision_kind_enum(self):
        from src.prompts.decision_prompts import DECISION_EXTRACTION_PROMPT_SHORT

        for kind in [
            "choice",
            "conditional_choice",
            "execution_commitment",
            "policy_constraint",
            "suggestion",
            "status",
            "discussion",
        ]:
            assert kind in DECISION_EXTRACTION_PROMPT_SHORT, (
                f"decision_kind '{kind}' missing from prompt"
            )

    def test_prompt_contains_compound_decision_guidance(self):
        from src.prompts.decision_prompts import DECISION_EXTRACTION_PROMPT_SHORT

        # Must mention atomic decision splitting rule
        assert "atomic" in DECISION_EXTRACTION_PROMPT_SHORT.lower() or \
               "independently" in DECISION_EXTRACTION_PROMPT_SHORT.lower()

    def test_prompt_contains_context_boundary_guidance(self):
        from src.prompts.decision_prompts import DECISION_EXTRACTION_PROMPT_SHORT

        # Must mention that context cannot provide evidence
        assert "context" in DECISION_EXTRACTION_PROMPT_SHORT.lower()


# ---------------------------------------------------------------------------
# Typed filtering in extractor
# ---------------------------------------------------------------------------


class TestTypedFiltering:
    """SimpleLLMExtractor filters by decision_kind after LLM response."""

    def _make_llm_response(self, decisions: list[dict[str, Any]]) -> str:
        return json.dumps({
            "has_decisions": True,
            "decisions": decisions,
            "reasoning": "test",
        })

    def _make_decision(
        self,
        title: str = "采用 PostgreSQL",
        kind: str = "choice",
        confidence: float = 0.90,
        is_suggestion: bool = False,
        evidence_quote: str = "我们决定采用 PostgreSQL",
        source_message_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "decision_id": "dec_1",
            "title": title,
            "content": f"团队{title}",
            "topic": "backend",
            "confidence": confidence,
            "decision_kind": kind,
            "rationale": "test",
            "proposer": "张三",
            "executor": "李四",
            "impact_level": "major",
            "is_suggestion": is_suggestion,
            "source_message_ids": source_message_ids or ["m001"],
            "evidence_quote": evidence_quote,
        }

    @pytest.mark.asyncio
    async def test_status_decisions_are_filtered(self):
        """decision_kind='status' is dropped before evidence check."""
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor

        content = "[m001] 张三: 我们决定采用 PostgreSQL\n[m002] 李四: 进度更新"
        status_dec = self._make_decision(
            title="进度更新",
            kind="status",
            evidence_quote="进度更新",
            source_message_ids=["m002"],
        )
        choice_dec = self._make_decision(kind="choice")

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "has_decisions": True,
                    "decisions": [status_dec, choice_dec],
                    "reasoning": "test",
                })

        ext = SimpleLLMExtractor(FakeProvider())
        result = await ext.extract_with_context(content)
        # status should be filtered out; only choice survives
        assert result is not None
        titles = [d["title"] for d in result]
        assert "进度更新" not in titles
        assert "采用 PostgreSQL" in titles

    @pytest.mark.asyncio
    async def test_discussion_decisions_are_filtered(self):
        """decision_kind='discussion' is dropped."""
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor

        content = "[m001] 张三: 我们讨论了 Redis 的可行性"
        disc_dec = self._make_decision(
            title="讨论 Redis",
            kind="discussion",
            evidence_quote="讨论了 Redis",
            source_message_ids=["m001"],
        )

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "has_decisions": True,
                    "decisions": [disc_dec],
                    "reasoning": "test",
                })

        ext = SimpleLLMExtractor(FakeProvider())
        result = await ext.extract_with_context(content)
        assert result is None  # only decision was discussion → filtered → empty

    @pytest.mark.asyncio
    async def test_suggestion_kind_forces_is_suggestion_true(self):
        """decision_kind='suggestion' forces is_suggestion=True even if LLM said False."""
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor

        content = "[m001] 张三: 建议考虑用 Redis"
        sug_dec = self._make_decision(
            title="采用 Redis 缓存",
            kind="suggestion",
            is_suggestion=False,  # LLM says False
            confidence=0.90,
            evidence_quote="建议考虑用 Redis",
            source_message_ids=["m001"],
        )

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "has_decisions": True,
                    "decisions": [sug_dec],
                    "reasoning": "test",
                })

        ext = SimpleLLMExtractor(FakeProvider())
        result = await ext.extract_with_context(content)
        assert result is not None
        assert result[0]["is_suggestion"] is True

    @pytest.mark.asyncio
    async def test_decision_kind_defaults_to_choice(self):
        """Missing decision_kind in LLM response defaults to 'choice'."""
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor

        content = "[m001] 张三: 我们决定采用 PostgreSQL"
        dec = self._make_decision()
        del dec["decision_kind"]  # remove kind

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "has_decisions": True,
                    "decisions": [dec],
                    "reasoning": "test",
                })

        ext = SimpleLLMExtractor(FakeProvider())
        result = await ext.extract_with_context(content)
        assert result is not None
        assert result[0].get("decision_kind") == "choice"

    @pytest.mark.asyncio
    async def test_extraction_stats_tracking(self):
        """Extractor tracks stats for filtered decisions."""
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor

        content = "[m001] 张三: 我们决定采用 PostgreSQL\n[m002] 李四: 进度更新"
        decisions = [
            self._make_decision(kind="choice"),
            self._make_decision(title="进度更新", kind="status",
                                evidence_quote="进度更新", source_message_ids=["m002"]),
            self._make_decision(title="低信心", kind="choice", confidence=0.40),
        ]

        class FakeProvider:
            async def generate(self, prompt: str, **kw: Any) -> str:
                return json.dumps({
                    "has_decisions": True,
                    "decisions": decisions,
                    "reasoning": "test",
                })

        ext = SimpleLLMExtractor(FakeProvider())
        await ext.extract_with_context(content)
        stats = ext.last_extraction_stats
        assert stats is not None
        assert stats["total_candidates"] == 3
        assert stats["status_discussion_filtered"] >= 1
        assert stats["confidence_filtered"] >= 1
