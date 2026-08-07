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


def test_evidence_linker_repairs_model_quote_spanning_multiple_messages():
    content = (
        "[m1] Alice: 我倾向于Feast，因为可控性更好。\n"
        "[m2] Bob: 好，特征存储选Feast，进入implementation。"
    )
    decision = {
        "title": "特征存储选Feast，进入implementation",
        "summary": "特征存储选Feast，进入implementation",
        "source_message_ids": ["m1", "m2"],
        "evidence_quote": "我倾向于Feast，因为可控性更好。好，特征存储选Feast，进入implementation。",
    }

    assert SimpleLLMExtractor._attach_evidence(decision, content)
    assert decision["source_message_ids"] == ["m2"]
    assert decision["evidence_quote"] == "好，特征存储选Feast，进入implementation。"
    assert decision["evidence_source"] == "heuristic"
