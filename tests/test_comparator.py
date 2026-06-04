"""单元测试 EvalComparator"""

import json
import tempfile
from pathlib import Path
from src.eval.comparator import EvalComparator


def _write_jsonl(path: Path, data: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


class TestEvalComparator:
    def test_basic_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected_path = Path(tmp) / "expected.jsonl"
            _write_jsonl(expected_path, [
                {"expected_topic": "用PG还是MySQL", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "用PG还是MySQL", "summary": "采用PostgreSQL作为主数据库",
                 "status": "decided", "sid": "abc"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            m = comparator.compute_metrics()
            assert m["true_positives"] == 1
            assert m["false_positives"] == 0
            assert m["false_negatives"] == 0
            assert m["precision"] == 1.0
            assert m["recall"] == 1.0
            assert m["f1"] == 1.0

    def test_partial_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected_path = Path(tmp) / "expected.jsonl"
            _write_jsonl(expected_path, [
                {"expected_topic": "用PG还是MySQL", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
                {"expected_topic": "Next.js App Router迁移", "expected_summary": "使用App Router",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "用PG还是MySQL", "summary": "采用PostgreSQL作为主数据库",
                 "status": "decided", "sid": "abc"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            m = comparator.compute_metrics()
            assert m["true_positives"] == 1
            assert m["false_positives"] == 0
            assert m["false_negatives"] == 1
            assert m["recall"] == 0.5

    def test_false_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected_path = Path(tmp) / "expected.jsonl"
            _write_jsonl(expected_path, [
                {"expected_topic": "用PG还是MySQL", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "用PG还是MySQL", "summary": "采用PostgreSQL",
                 "status": "decided", "sid": "abc"},
                {"topic_id": "K8s版本升级策略", "summary": "升级到1.28",
                 "status": "decided", "sid": "def"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            m = comparator.compute_metrics()
            assert m["true_positives"] == 1
            assert m["false_positives"] == 1
            assert m["precision"] == 0.5

    def test_topic_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected_path = Path(tmp) / "expected.jsonl"
            _write_jsonl(expected_path, [
                {"expected_topic": "用PG还是MySQL", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "K8s版本升级策略", "summary": "采用PostgreSQL",
                 "status": "decided", "sid": "abc"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            m = comparator.compute_metrics()
            # Topic mismatch means no match → FN for expected, FP for actual
            assert m["true_positives"] == 0
            assert m["false_positives"] == 1
            assert m["false_negatives"] == 1

    def test_report_by_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected_path = Path(tmp) / "expected.jsonl"
            _write_jsonl(expected_path, [
                {"expected_topic": "用PG还是MySQL", "expected_summary": "PG",
                 "expected_status": "decided", "chat_id": "chat_0"},
                {"expected_topic": "Next.js App Router迁移", "expected_summary": "App Router",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "用PG还是MySQL", "summary": "使用PG", "status": "decided", "sid": "a"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            by_topic = comparator.report_by_topic()
            assert "用PG还是MySQL" in by_topic
            assert "Next.js App Router迁移" in by_topic
            assert by_topic["用PG还是MySQL"]["precision"] == 1.0
            assert by_topic["Next.js App Router迁移"]["recall"] == 0.0

    def test_report_by_chat_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected_path = Path(tmp) / "expected.jsonl"
            _write_jsonl(expected_path, [
                {"expected_topic": "用PG还是MySQL", "expected_summary": "PG",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "用PG还是MySQL", "summary": "使用PG", "status": "decided", "sid": "a", "chat_id": "chat_0"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            by_chat = comparator.report_by_chat()
            iso = by_chat["_isolation"]
            assert iso["score"] == 1.0
            assert iso["issues"] == 0