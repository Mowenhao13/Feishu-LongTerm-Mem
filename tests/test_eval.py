from __future__ import annotations

import pytest

from src.eval import (
    get_eval_path,
    list_eval_datasets,
    list_extraction_scenarios,
    load_extraction_dialogue,
    load_extraction_qa,
    load_jsonl,
)


class TestEvalDataDiscovery:
    def test_evaldata_directory_exists(self):
        path = get_eval_path("")
        assert path.exists()

    def test_list_datasets(self):
        datasets = list_eval_datasets()
        names = [d["name"] for d in datasets]
        assert "classification" in names
        assert "conflicts" in names
        assert "corpus" in names
        assert "crosstopic" in names

    def test_each_dataset_has_files(self):
        datasets = list_eval_datasets()
        for d in datasets:
            assert len(d["files"]) > 0

    def test_list_extraction_scenarios(self):
        scenarios = list_extraction_scenarios()
        expected = [
            "01-technical-selection",
            "02-task-assignment",
            "03-parameter-lock",
            "04-implicit-consensus",
            "05-conflict-decisions",
            "06-rejection-override",
            "07-pure-discussion",
            "08-status-update",
            "09-suggestion-only",
            "10-small-talk",
            "11-mixed-scenario",
            "12-boundary-case",
        ]
        for s in expected:
            assert s in scenarios


class TestEvalDataLoading:
    def test_load_classification_jsonl(self):
        path = get_eval_path("classification") / "classification.jsonl"
        items = load_jsonl(path)
        assert len(items) > 0
        item = items[0]
        assert isinstance(item, dict)

    def test_load_conflicts_jsonl(self):
        path = get_eval_path("conflicts") / "conflicts.jsonl"
        items = load_jsonl(path)
        assert len(items) > 0

    def test_load_crosstopic_jsonl(self):
        path = get_eval_path("crosstopic") / "crosstopic.jsonl"
        items = load_jsonl(path)
        assert len(items) > 0

    def test_load_corpus_decisions_jsonl(self):
        path = get_eval_path("corpus") / "decisions.jsonl"
        items = load_jsonl(path)
        assert len(items) > 0


class TestExtractionScenarios:
    def test_technical_selection_has_dialogue(self):
        data = load_extraction_dialogue("01-technical-selection")
        assert data is not None
        assert "dialogues" in data or "messages" in data or "turns" in data or "conversation" in data

    def test_technical_selection_has_qa(self):
        data = load_extraction_qa("01-technical-selection")
        assert data is not None

    def test_task_assignment_has_dialogue(self):
        data = load_extraction_dialogue("02-task-assignment")
        assert data is not None

    def test_task_assignment_has_qa(self):
        data = load_extraction_qa("02-task-assignment")
        assert data is not None

    def test_parameter_lock_has_dialogue(self):
        data = load_extraction_dialogue("03-parameter-lock")
        assert data is not None

    def test_all_scenarios_have_both_files(self):
        from src.eval import list_extraction_scenarios

        scenarios = list_extraction_scenarios()
        for s in scenarios:
            assert load_extraction_dialogue(s) is not None, f"{s} missing dialogue.json"
            assert load_extraction_qa(s) is not None, f"{s} missing qa.json"