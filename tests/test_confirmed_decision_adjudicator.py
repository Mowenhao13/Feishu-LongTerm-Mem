import pytest

from src.eval.confirmed_decision_adjudicator import LLMDecisionAdjudicator
from src.eval.confirmed_decision_eval import (
    Adjudication,
    ChatAssignment,
    EvidenceDecision,
    GlobalAdjudicationGroup,
)


class FakeProvider:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def generate(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return self.response


def _group(outputs=None, candidates=None, messages=None) -> GlobalAdjudicationGroup:
    return GlobalAdjudicationGroup(
        chat_id="chat-a",
        outputs=tuple(
            outputs
            or (
                EvidenceDecision(
                    chat_id="chat-a",
                    title="采用 PostgreSQL",
                    summary="采用 PostgreSQL",
                    status="decided",
                    is_suggestion=False,
                    source_message_ids=("m1",),
                    evidence_quote="确认采用 PostgreSQL",
                ),
                EvidenceDecision(
                    chat_id="chat-a",
                    title="下周开始编码",
                    summary="下周开始编码",
                    status="decided",
                    is_suggestion=False,
                    source_message_ids=("m2",),
                    evidence_quote="确认下周开始编码",
                ),
            )
        ),
        candidates=tuple(
            candidates
            or (
                {"msg_id": "g1", "expected_summary": "采用 PostgreSQL", "chat_id": "chat-a"},
                {"msg_id": "g2", "expected_summary": "下周开始编码", "chat_id": "chat-a"},
            )
        ),
        messages=tuple(
            messages
            or (
                {"msg_id": "m1", "msg": "确认采用 PostgreSQL"},
                {"msg_id": "m2", "msg": "确认下周开始编码"},
            )
        ),
    )


@pytest.mark.asyncio
async def test_adjudicate_chat_parses_one_to_one_global_assignment():
    provider = FakeProvider(
        '{"assignments":[{"output_index":0,"classification":"match_gt","matched_gt_index":0,"decision_kind":"execution_commitment","core_equivalent":true,"polarity_compatible":true,"commitment_compatible":true,"material_qualifier_conflict":false,"reason":"同一决策"},{"output_index":1,"classification":"valid_extra","matched_gt_index":null,"decision_kind":"execution_commitment","core_equivalent":false,"polarity_compatible":true,"commitment_compatible":true,"material_qualifier_conflict":false,"reason":"GT 未覆盖"}]}'
    )

    assignment = await LLMDecisionAdjudicator(provider).adjudicate_chat(_group())

    assert isinstance(assignment, ChatAssignment)
    assert assignment.chat_id == "chat-a"
    assert assignment.rows[0].matched_msg_id == "g1"
    assert assignment.rows[0].outcome is Adjudication.MATCH_GT
    assert assignment.rows[1].outcome is Adjudication.VALID_EXTRA
    assert provider.calls[0][1] == {"temperature": 0, "response_format": {"type": "json_object"}}


@pytest.mark.asyncio
async def test_adjudicate_chat_normalizes_input_for_cache_key():
    provider = FakeProvider('{"assignments":[]}')
    adjudicator = LLMDecisionAdjudicator(provider)
    first = _group()
    second = _group(outputs=tuple(reversed(first.outputs)), candidates=tuple(reversed(first.candidates)), messages=tuple(reversed(first.messages)))

    assert adjudicator.cache_key(first) == adjudicator.cache_key(second)
    assert adjudicator.normalized_input_hash(first) == adjudicator.normalized_input_hash(second)


@pytest.mark.asyncio
async def test_adjudicate_chat_rejects_unknown_gt_index():
    provider = FakeProvider(
        '{"assignments":[{"output_index":0,"classification":"match_gt","matched_gt_index":9,"decision_kind":"execution_commitment","core_equivalent":true,"polarity_compatible":true,"commitment_compatible":true,"material_qualifier_conflict":false,"reason":"bad"},{"output_index":1,"classification":"valid_extra","matched_gt_index":null,"decision_kind":"execution_commitment","core_equivalent":false,"polarity_compatible":true,"commitment_compatible":true,"material_qualifier_conflict":false,"reason":"GT 未覆盖"}]}'
    )

    with pytest.raises(ValueError, match="unknown GT index"):
        await LLMDecisionAdjudicator(provider).adjudicate_chat(_group())


def test_legacy_adjudicate_does_not_use_lexical_overlap():
    adjudicator = LLMDecisionAdjudicator(FakeProvider('{"assignments":[]}'))
    assert "lexical overlap" not in adjudicator.PROMPT.lower()
