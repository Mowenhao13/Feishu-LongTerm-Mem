import pytest

from src.extractors.simple_llm_extractor import SimpleLLMExtractor


def test_evidence_linker_attaches_best_message_when_model_omits_evidence():
    content = "[m1] Alice: 我们确认采用PostgreSQL作为主数据库。\n[m2] Bob: 下周开始迁移。"
    decision = {"title": "采用PostgreSQL作为主数据库", "summary": "采用PostgreSQL作为主数据库"}

    SimpleLLMExtractor._attach_evidence(decision, content)

    assert decision["source_message_ids"] == ["m1"]
    assert decision["evidence_quote"] == "我们确认采用PostgreSQL作为主数据库。"
    assert decision["evidence_source"] == "heuristic"


def test_evidence_linker_does_not_fabricate_unrelated_evidence():
    content = "[m1] Alice: 今天天气很好。\n[m2] Bob: 下午一起喝咖啡。"
    decision = {"title": "采用PostgreSQL作为主数据库", "summary": "采用PostgreSQL作为主数据库"}

    SimpleLLMExtractor._attach_evidence(decision, content)

    assert decision.get("source_message_ids", []) == []
    assert decision.get("evidence_quote", "") == ""
