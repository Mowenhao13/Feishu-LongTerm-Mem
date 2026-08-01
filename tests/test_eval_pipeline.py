"""集成测试：完整评估流水线"""

import asyncio
from pathlib import Path

from src.eval_runner import EvalRunner
from src.eval.comparator import EvalComparator


class TestEvalPipeline:
    async def test_single_chat_eval(self):
        runner = EvalRunner(
            input_path="eval_dataset/test_small/messages.jsonl",
            delay=0.01,
            max_messages=0,
            group_num=1,
            expected_path="eval_dataset/test_small/expected.jsonl",
        )
        await runner.run()

        # Verify report was generated
        report_path = Path("eval_dataset/test_small/eval_report.json")
        assert report_path.exists(), "eval_report.json should exist"
        import json
        with open(report_path) as f:
            report = json.load(f)
        assert report["total_expected"] == 3

    async def test_multi_chat_eval(self):
        runner = EvalRunner(
            input_path="eval_dataset/test_small/messages.jsonl",
            delay=0.01,
            max_messages=0,
            group_num=0,
            expected_path="eval_dataset/test_small/expected.jsonl",
        )
        await runner.run()
        report_path = Path("eval_dataset/test_small/eval_report.json")
        assert report_path.exists()