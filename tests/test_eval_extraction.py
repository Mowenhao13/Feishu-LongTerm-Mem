from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

from src.eval import list_extraction_scenarios, load_extraction_dialogue, load_extraction_qa
from src.eval.evaluator import (
    EXTRACTION_SYSTEM_PROMPT,
    EvalResult,
    SummaryReport,
    evaluate_extraction,
    extract_all_conversations,
    format_dialogue,
    run_extraction_eval,
    select_sub_dialogue,
)
from src.llm.client import LLMClient


class TestEvalExtractionData:
    def test_all_scenarios_loadable(self):
        scenarios = list_extraction_scenarios()
        assert len(scenarios) >= 12
        for s in scenarios:
            assert load_extraction_dialogue(s) is not None
            assert load_extraction_qa(s) is not None

    def test_each_scenario_has_qars(self):
        scenarios = list_extraction_scenarios()
        for s in scenarios:
            qa = load_extraction_qa(s)
            assert qa is not None
            assert "qars" in qa
            assert len(qa["qars"]) > 0

    def test_each_scenario_has_dialogues(self):
        scenarios = list_extraction_scenarios()
        for s in scenarios:
            dialogue = load_extraction_dialogue(s)
            assert dialogue is not None
            assert "dialogues" in dialogue

    def test_format_dialogue_produces_text(self):
        dialogue = load_extraction_dialogue("01-technical-selection")
        assert dialogue is not None
        text = format_dialogue(dialogue)
        assert len(text) > 0
        assert "张三" in text or "陈七" in text

    def test_select_sub_dialogue(self):
        dialogue = load_extraction_dialogue("01-technical-selection")
        assert dialogue is not None
        convs = extract_all_conversations(dialogue)
        assert len(convs) > 0
        text = select_sub_dialogue(convs[0][3])
        assert len(text) > 0
        assert "张三" in text

    def test_extract_all_conversations_count(self):
        dialogue = load_extraction_dialogue("01-technical-selection")
        assert dialogue is not None
        convs = extract_all_conversations(dialogue)
        assert len(convs) >= 10  # 01 场景有 20 个对话


class TestEvalExtractionQA:
    def test_qa_items_have_required_fields(self):
        scenarios = list_extraction_scenarios()
        for s in scenarios:
            qa = load_extraction_qa(s)
            assert qa is not None
            for item in qa["qars"]:
                assert "id" in item
                assert "Q" in item
                assert "A" in item
                assert "options" in item
                assert "dimension" in item

    def test_qa_dimensions_are_valid(self):
        scenarios = list_extraction_scenarios()
        valid_dims = {"detection", "content", "proposer", "executor", "impact_level", "status", "conflict"}
        for s in scenarios:
            qa = load_extraction_qa(s)
            assert qa is not None
            for item in qa["qars"]:
                assert item["dimension"] in valid_dims, f"{s}: invalid dimension {item['dimension']}"

    def test_qa_expected_answers_in_options(self):
        scenarios = list_extraction_scenarios()
        for s in scenarios:
            qa = load_extraction_qa(s)
            assert qa is not None
            for item in qa["qars"]:
                assert item["A"] in item["options"], f"{s}: {item['id']} expected answer {item['A']} not in options"


class TestEvalExtractionIntegration:
    @pytest.fixture
    def llm_client(self) -> LLMClient:
        return LLMClient()

    @pytest.mark.skip(reason="需要真实 API 调用")
    def test_basic_evaluate_extraction_structure(self, llm_client: LLMClient):
        result = evaluate_extraction(llm_client, "07-pure-discussion", max_tokens=10)
        assert isinstance(result, EvalResult)
        assert result.scenario == "07-pure-discussion"

    @pytest.mark.skip(reason="需要真实 API 调用")
    def test_run_extraction_eval_structure(self, llm_client: LLMClient):
        report = run_extraction_eval(llm_client, scenarios=["07-pure-discussion"], max_tokens=10)
        assert isinstance(report, SummaryReport)
        assert len(report.scenario_results) == 1

    @pytest.mark.skip(reason="需要真实 API 调用")
    def test_eval_scenario_counts(self, llm_client: LLMClient):
        scenarios = list_extraction_scenarios()
        report = run_extraction_eval(llm_client, scenarios=scenarios[:3], max_tokens=10)
        assert len(report.scenario_results) == 3


class TestLazyEvalSingleScenario:
    @pytest.mark.skip(reason="需要真实 API key 才能运行，设置 .env API_KEY 后可取消跳过")
    def test_technical_selection_extraction(self):
        from dotenv import load_dotenv
        load_dotenv()
        config = LLMConfig(
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-db793c5d56cb416cae6605698c47b04d",
            max_new_tokens=10,
            temperature=0.0,
        )
        client = LLMClient(config=config)
        result = evaluate_extraction(client, "01-technical-selection", max_tokens=10)
        print(f"\n=== 01-technical-selection ===")
        print(f"Accuracy: {result.accuracy:.2%} ({result.correct}/{result.total})")
        for dim, acc in result.dim_accuracies.items():
            print(f"  {dim}: {acc:.2%}")
        print(f"Token usage: {client.token_tracker.summary()}")


class TestEvalQuickCheck:
    def test_prompt_contains_correct_instruction(self):
        assert "只输出选项字母" in EXTRACTION_SYSTEM_PROMPT
        assert "A/B/C/D" in EXTRACTION_SYSTEM_PROMPT

    def test_eval_result_to_dict(self):
        result = EvalResult(
            scenario="test",
            dim_results={"detection": [True, False]},
            dim_accuracies={"detection": 0.5},
            total=2,
            correct=1,
            accuracy=0.5,
            token_summary={"total_tokens": 100},
        )
        d = result.to_dict()
        assert d["scenario"] == "test"
        assert d["accuracy"] == 0.5

    def test_summary_report_to_dict(self):
        report = SummaryReport(
            scenario_results=[EvalResult(scenario="s1")],
            overall_accuracy=0.8,
            overall_dim_accuracies={"detection": 0.8},
            total_calls=10,
            total_tokens=500,
        )
        d = report.to_dict()
        assert d["overall_accuracy"] == 0.8
        assert d["total_tokens"] == 500
        assert len(d["scenarios"]) == 1


class TestEvalReportGeneration:
    def test_report_path(self):
        path = Path(__file__).resolve().parent.parent / "eval_reports"
        assert path.exists()

    def test_generate_report_from_result(self):
        result = EvalResult(
            scenario="01-technical-selection",
            dim_accuracies={"detection": 0.95, "content": 0.85},
            total=20,
            correct=18,
            accuracy=0.9,
            token_summary={"total_tokens": 5000, "call_count": 20, "prompt_tokens": 4000, "completion_tokens": 1000},
        )
        report_dir = Path(__file__).resolve().parent.parent / "eval_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"eval_{result.scenario}.json"
        with open(report_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        assert report_path.exists()
        report_path.unlink()


class TestTokenTrackerWithEval:
    def test_tracker_reset_between_scenarios(self):
        from src.llm.token_tracker import TokenTracker
        tracker = TokenTracker()
        tracker.track("hello", "world")
        assert tracker.call_count == 1
        tracker.reset()
        assert tracker.call_count == 0
        assert tracker.usage.total_tokens == 0

    def test_local_token_counting(self):
        from src.llm.token_tracker import TokenTracker
        tracker = TokenTracker(model="deepseek-chat")
        text = "你是一个决策提取评估助手。根据对话内容回答问题。"
        tokens = tracker.count_tokens(text)
        assert tokens > 0