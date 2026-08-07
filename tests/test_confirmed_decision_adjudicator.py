import pytest

from src.eval.confirmed_decision_adjudicator import LLMDecisionAdjudicator
from src.eval.confirmed_decision_eval import Adjudication, EvidenceDecision

class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.response

def _output():
    return EvidenceDecision(chat_id="chat-a", title="采用 PostgreSQL", summary="采用 PostgreSQL", status="decided", is_suggestion=False, source_message_ids=("m1",), evidence_quote="确认采用 PostgreSQL")

@pytest.mark.asyncio
async def test_adjudicator_returns_valid_extra():
    provider = FakeProvider('{"adjudication":"valid_extra","matched_msg_id":"","reason":"明确执行承诺，但 GT 未覆盖"}')
    result = await LLMDecisionAdjudicator(provider).adjudicate(_output(), [], [{"msg_id":"m1","msg":"确认采用 PostgreSQL"}])
    assert result.outcome is Adjudication.VALID_EXTRA
    assert result.reason == "明确执行承诺，但 GT 未覆盖"
    assert provider.prompts

@pytest.mark.asyncio
async def test_adjudicator_rejects_unknown_gt_identity():
    provider = FakeProvider('{"adjudication":"match_gt","matched_msg_id":"unknown","reason":"bad"}')
    with pytest.raises(ValueError, match="candidate msg_id"):
        await LLMDecisionAdjudicator(provider).adjudicate(_output(), [{"msg_id":"m1","expected_summary":"完全不同的决策"}], [{"msg_id":"m1","msg":"确认采用 PostgreSQL"}])

@pytest.mark.asyncio
async def test_adjudicator_downgrades_low_overlap_match():
    provider = FakeProvider('{"adjudication":"match_gt","matched_msg_id":"m1","reason":"bad"}')
    result = await LLMDecisionAdjudicator(provider).adjudicate(_output(), [{"msg_id":"m1","expected_summary":"完全不同的决策"}], [{"msg_id":"m1","msg":"另一条证据"}])
    assert result.outcome is Adjudication.INVALID
    assert "overlap too low" in result.reason
