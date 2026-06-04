# 大规模跨群聊评估 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建大规模有真值标注的跨群聊评估流水线，量化衡量决策提取精度/召回/F1

**Architecture:** 分两阶段 — Phase 1 数据生成器通过 LLM 生产标注数据集，Phase 2 评估器通过 EvalRunner+Comparator 对比 Pipeline 输出与真值

**Tech Stack:** Python, lark_oapi, LLMClient (deepseek-chat), JSONL 数据集格式

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/eval/comparator.py` | 新增 | 决策比对器：TP/FP/FN 匹配、指标计算、按群聊/话题/难度拆解 |
| `src/eval_runner.py` | 修改 | 支持 JSONL 输入、集成 Comparator、新增 eval 模式 CLI 参数 |
| `scripts/run_eval.py` | 新增 | 评估 CLI：接收 --input/--expected/--mode 参数 |
| `src/eval/generator.py` | 新增 | LLM 数据生成器：三层 Prompt 架构、配置驱动 |
| `scripts/generate_eval_data.py` | 新增 | 数据生成 CLI |
| `eval_dataset/config.yaml` | 新增 | 默认生成配置 |
| `src/eval/__init__.py` | 修改 | 导出 Generator 和 Comparator |

### 依赖关系

```
Comparator ──→ run_eval.py ──→ eval_runner.py (增强)
                                               ↑
Generator ───→ generate_eval_data.py           ↑
                                               ↑
                                        graph.get_all_decisions()
```

执行顺序：
1. Comparator（纯逻辑，无外部依赖）
2. EvalRunner 增强（JSONL 输入）
3. run_eval.py（整合）
4. Generator（LLM 依赖）
5. generate_eval_data.py（CLI）

---

### Task 1: EvalComparator — 决策比对器

**Files:**
- Create: `src/eval/comparator.py`
- Test: (无单独测试，与 run_eval 整合测试)

- [ ] **Step 1: Create EvalComparator class**

```python
"""决策比对器：将 Pipeline 输出的实际决策与 expected.jsonl 真值对比，
计算精度/召回/F1 等指标。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class EvalComparator:
    """比较实际决策与预期真值，计算评估指标。

    Usage:
        comparator = EvalComparator("eval_dataset/single_chat/expected.jsonl")
        comparator.match(actual_decisions)
        report = comparator.compute_metrics()
    """

    def __init__(self, expected_path: str):
        self._expected_path = expected_path
        self._expected_decisions: List[Dict[str, Any]] = []
        self._actual_decisions: List[Dict[str, Any]] = []
        self._true_positives: List[Tuple[Dict, Dict]] = []  # (expected, actual)
        self._false_positives: List[Dict] = []
        self._false_negatives: List[Dict] = []
        self._load_expected()

    def _load_expected(self) -> None:
        """加载 expected.jsonl 真值"""
        path = Path(self._expected_path)
        if not path.exists():
            raise FileNotFoundError(f"Expected file not found: {self._expected_path}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._expected_decisions.append(json.loads(line))

    @staticmethod
    def _summary_similarity(s1: str, s2: str) -> float:
        """基于字符重叠率的摘要相似度"""
        if not s1 or not s2:
            return 0.0
        s1_chars = set(s1.lower())
        s2_chars = set(s2.lower())
        if not s1_chars or not s2_chars:
            return 0.0
        intersection = s1_chars & s2_chars
        return len(intersection) / max(len(s1_chars), len(s2_chars))

    def match(self, actual_decisions: List[Dict[str, Any]]) -> None:
        """将实际决策与真值进行匹配

        Args:
            actual_decisions: graph.get_all_decisions() 的决策列表，
                每条至少包含 topic_id, summary 字段。
        """
        self._actual_decisions = list(actual_decisions)
        self._true_positives = []
        self._false_positives = []
        self._false_negatives = []

        matched_actual = set()

        for expected in self._expected_decisions:
            expected_topic = (expected.get("expected_topic") or "").strip()
            expected_summary = (expected.get("expected_summary") or "").strip()
            best_match_idx = None
            best_score = 0.0

            for i, actual in enumerate(self._actual_decisions):
                if i in matched_actual:
                    continue
                actual_topic = (actual.get("topic_id") or "").strip()
                actual_summary = (actual.get("summary") or "").strip()

                # 话题必须匹配
                if expected_topic and actual_topic and expected_topic != actual_topic:
                    continue

                score = self._summary_similarity(expected_summary, actual_summary)
                if score >= 0.3 and score > best_score:
                    best_score = score
                    best_match_idx = i

            if best_match_idx is not None:
                matched_actual.add(best_match_idx)
                self._true_positives.append((
                    expected,
                    self._actual_decisions[best_match_idx],
                ))
            else:
                self._false_negatives.append(expected)

        for i, actual in enumerate(self._actual_decisions):
            if i not in matched_actual:
                self._false_positives.append(actual)

    def compute_metrics(self) -> Dict[str, Any]:
        """计算评估指标"""
        tp = len(self._true_positives)
        fp = len(self._false_positives)
        fn = len(self._false_negatives)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # 维度准确率
        topic_correct = 0
        status_correct = 0
        for exp, act in self._true_positives:
            exp_topic = exp.get("expected_topic", "")
            act_topic = act.get("topic_id", "")
            if exp_topic and act_topic and exp_topic == act_topic:
                topic_correct += 1
            exp_status = exp.get("expected_status", "")
            act_status = act.get("status", "")
            if exp_status and act_status and exp_status == act_status:
                status_correct += 1

        return {
            "total_expected": len(self._expected_decisions),
            "total_detected": len(self._actual_decisions),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "dimension_accuracy": {
                "topic": round(topic_correct / tp, 4) if tp > 0 else 0.0,
                "status": round(status_correct / tp, 4) if tp > 0 else 0.0,
            },
        }

    def report_by_topic(self) -> Dict[str, Dict[str, float]]:
        """按话题拆解指标"""
        topics: Dict[str, Dict] = {}
        for exp, act in self._true_positives:
            t = exp.get("expected_topic", "unknown")
            if t not in topics:
                topics[t] = {"tp": 0, "fp": 0, "fn": 0}
            topics[t]["tp"] += 1
        for exp in self._false_negatives:
            t = exp.get("expected_topic", "unknown")
            if t not in topics:
                topics[t] = {"tp": 0, "fp": 0, "fn": 0}
            topics[t]["fn"] += 1
        for act in self._false_positives:
            t = act.get("topic_id", "unknown")
            if t not in topics:
                topics[t] = {"tp": 0, "fp": 0, "fn": 0}
            topics[t]["fp"] += 1

        result = {}
        for t, v in topics.items():
            p = v["tp"] / (v["tp"] + v["fp"]) if (v["tp"] + v["fp"]) > 0 else 0.0
            r = v["tp"] / (v["tp"] + v["fn"]) if (v["tp"] + v["fn"]) > 0 else 0.0
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            result[t] = {
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f, 4),
            }
        return result

    def report_by_chat(self) -> Dict[str, Dict[str, Any]]:
        """按群聊拆解指标（多群模式）"""
        chats: Dict[str, Dict] = {}
        for exp in self._expected_decisions:
            cid = exp.get("chat_id", "unknown")
            if cid not in chats:
                chats[cid] = {"expected": 0, "tp": 0, "fn": 0, "fp": 0}
            chats[cid]["expected"] += 1
        for exp, act in self._true_positives:
            cid = exp.get("chat_id", "unknown")
            if cid in chats:
                chats[cid]["tp"] += 1
        for exp in self._false_negatives:
            cid = exp.get("chat_id", "unknown")
            if cid in chats:
                chats[cid]["fn"] += 1

        isolation_issues = 0
        total_chat_expected = sum(v["expected"] for v in chats.values())
        for act in self._false_positives:
            if "chat_id" not in act:
                continue
            expected_match = None
            for exp, a in self._true_positives:
                if a is act:
                    expected_match = exp
                    break
            if expected_match and expected_match.get("chat_id") != act.get("chat_id"):
                isolation_issues += 1

        result = {}
        for cid, v in chats.items():
            p = v["tp"] / (v["tp"] + v["fp"]) if (v["tp"] + v["fp"]) > 0 else 0.0
            r = v["tp"] / (v["tp"] + v["fn"]) if (v["tp"] + v["fn"]) > 0 else 0.0
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            result[cid] = {
                "expected": v["expected"],
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f, 4),
            }

        result["_isolation"] = {
            "issues": isolation_issues,
            "score": round(
                1.0 - (isolation_issues / total_chat_expected) if total_chat_expected > 0 else 1.0,
                4,
            ),
        }
        return result

    def to_dict(self) -> Dict[str, Any]:
        """输出完整报告"""
        metrics = self.compute_metrics()
        return {
            **metrics,
            "by_topic": self.report_by_topic(),
            "by_chat": self.report_by_chat(),
        }
```

- [ ] **Step 2: Write a unit test for Comparator**

Write `tests/test_comparator.py`:

```python
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
                {"expected_topic": "数据库选型", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "数据库选型", "summary": "采用PostgreSQL作为主数据库",
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
                {"expected_topic": "数据库选型", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
                {"expected_topic": "前端框架", "expected_summary": "使用React",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "数据库选型", "summary": "采用PostgreSQL作为主数据库",
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
                {"expected_topic": "数据库选型", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "数据库选型", "summary": "采用PostgreSQL",
                 "status": "decided", "sid": "abc"},
                {"topic_id": "监控告警", "summary": "使用Grafana",
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
                {"expected_topic": "数据库选型", "expected_summary": "采用PostgreSQL",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "监控告警", "summary": "采用PostgreSQL",
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
                {"expected_topic": "数据库选型", "expected_summary": "PG",
                 "expected_status": "decided", "chat_id": "chat_0"},
                {"expected_topic": "前端框架", "expected_summary": "React",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "数据库选型", "summary": "使用PG", "status": "decided", "sid": "a"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            by_topic = comparator.report_by_topic()
            assert "数据库选型" in by_topic
            assert "前端框架" in by_topic
            assert by_topic["数据库选型"]["precision"] == 1.0
            assert by_topic["前端框架"]["recall"] == 0.0

    def test_report_by_chat_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected_path = Path(tmp) / "expected.jsonl"
            _write_jsonl(expected_path, [
                {"expected_topic": "数据库选型", "expected_summary": "PG",
                 "expected_status": "decided", "chat_id": "chat_0"},
            ])
            actual = [
                {"topic_id": "数据库选型", "summary": "使用PG", "status": "decided", "sid": "a", "chat_id": "chat_0"},
            ]
            comparator = EvalComparator(str(expected_path))
            comparator.match(actual)
            by_chat = comparator.report_by_chat()
            iso = by_chat["_isolation"]
            assert iso["score"] == 1.0
            assert iso["issues"] == 0
```

- [ ] **Step 3: Run tests to verify they fail initially**

Run: `uv run pytest tests/test_comparator.py -v`
Expected: FAIL — ImportError (module not found)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_comparator.py -v`
Expected: 7/7 PASS

---

### Task 2: EvalRunner 增强 — JSONL 输入支持

**Files:**
- Modify: `src/eval_runner.py`

- [ ] **Step 1: Modify _load_messages to support JSONL format**

Replace the `_load_messages` method in `EvalRunner`:

```python
def _load_messages(self) -> List[Dict[str, Any]]:
    path = Path(self._input_path)
    if not path.exists():
        logger.error("Input file not found: %s", self._input_path)
        return []
    if path.suffix == ".json":
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [item.get("content", "") for item in data if item.get("content")]
        return []
    if path.suffix == ".jsonl":
        import json
        messages: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]
```

- [ ] **Step 2: Update _process_one_message to handle Dict messages**

Change the processing loop to accept both `str` and `Dict`:

Modify the loop in `run()` method around line 117:
```python
for i, content in enumerate(messages_to_process, 1):
    await self._process_one_message(i, len(messages_to_process), content)
```

Update `_process_one_message` signature and chat_id logic:

```python
async def _process_one_message(self, idx: int, total: int,
                                content: Union[str, Dict[str, Any]]) -> None:
    if self._engine is None or self._episode_manager is None:
        return

    if isinstance(content, dict):
        msg_text = content.get("msg", content.get("content", ""))
        chat_id = content.get("chat_id", f"eval_{(idx - 1) % self._group_num}")
        sender = content.get("speaker", content.get("sender", "eval_user"))
    else:
        msg_text = content
        chat_id = f"eval_{(idx - 1) % self._group_num}" if self._group_num > 1 else "eval"
        sender = "eval_user"

    if not msg_text:
        return

    preview = msg_text[:60].replace("\n", " ")
    ...
```

Also add the import at top:
```python
from typing import Any, Dict, List, Optional, Union
```

And update `__init__` signature (no change needed — `_load_messages` type already covers it).

- [ ] **Step 3: Add `--expected` argument and post-run comparator integration**

Add a `--expected` CLI arg:
```python
parser.add_argument("--expected", default="",
                    help="expected.jsonl 路径，启用精度评估")
```

In the `run()` method, after step 6 (after `await engine.stop()`), add comparator integration:
```python
# 7. 精度评估（如有 expected 文件）
if hasattr(self, "_expected_path") and self._expected_path:
    self._run_comparison()
```

Add `_run_comparison` method:
```python
def _run_comparison(self) -> None:
    from src.eval.comparator import EvalComparator
    decisions = self._engine._graph.get_all_decisions() if self._engine else []
    actual = [
        {
            "sid": d.sid,
            "topic_id": d.topic_id or "",
            "summary": d.summary or "",
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            "impact": d.impact.value if hasattr(d.impact, "value") else str(d.impact),
            "chat_id": getattr(d, "chat_id", ""),
        }
        for d in decisions
    ]
    comparator = EvalComparator(self._expected_path)
    comparator.match(actual)
    report = comparator.to_dict()

    # Print colored report
    print()
    print(f"\033[1m{'=' * 62}")
    print(f"  精度评估报告")
    print(f"{'=' * 62}\033[0m")
    print(f"  预期决策:       {report['total_expected']}")
    print(f"  实际检测:       {report['total_detected']}")
    print(f"  TP:             {report['true_positives']}")
    print(f"  FP:             {report['false_positives']}")
    print(f"  FN:             {report['false_negatives']}")
    p, r, f = report["precision"], report["recall"], report["f1"]
    print(f"\n  \033[1mPrecision:  {p:.1%}   Recall:  {r:.1%}   F1:  {f:.1%}\033[0m")
    if report.get("by_topic"):
        print(f"\n  按话题:")
        for t, v in report["by_topic"].items():
            print(f"    {t:<12}  P={v['precision']:.1%}  R={v['recall']:.1%}  F1={v['f1']:.1%}")
    if report.get("by_chat"):
        iso = report["by_chat"].get("_isolation", {})
        if iso:
            print(f"\n  跨群隔离:  score={iso.get('score', 1.0):.1%}  issues={iso.get('issues', 0)}")
    print(f"\n  {'=' * 62}\033[0m")
    print()

    # Save report to JSON
    report_path = Path(self._input_path).parent / "eval_report.json"
    import json
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {report_path}")
```

And store `self._expected_path` in `run()`:
```python
# After parsing args or setting up
self._expected_path = getattr(self, "_expected_path", "")
```

Actually, let me do this more cleanly by passing it in the constructor:

In `__init__`, add parameter:
```python
def __init__(self, input_path: str = "eval_data/test_data.txt",
             delay: float = 1.0,
             max_messages: int = 0,
             group_num: int = 1,
             expected_path: str = ""):
    ...
    self._expected_path = str(PROJECT_ROOT / expected_path) if expected_path and not os.path.isabs(expected_path) else expected_path
```

Then update `parse_args` to pass it:
```python
runner = EvalRunner(input_path=args.input, delay=args.delay,
                    max_messages=args.max_messages,
                    group_num=args.group_num,
                    expected_path=args.expected)
```

- [ ] **Step 4: Verify the module imports correctly**

Run: `uv run python3 -c "from src.eval_runner import EvalRunner; print('OK')"`
Expected: OK

---

### Task 3: run_eval.py — 评估 CLI

**Files:**
- Create: `scripts/run_eval.py`

- [ ] **Step 1: Create scripts/run_eval.py**

```python
#!/usr/bin/env python3
"""大规模评估 CLI — Phase 2

加载 JSONL 消息 → EvalRunner 模拟处理 → Comparator 精度评估。

Usage:
    # 单群聊评估
    python -m scripts.run_eval \
        --input eval_dataset/single_chat/messages.jsonl \
        --expected eval_dataset/single_chat/expected.jsonl \
        --mode single

    # 多群聊评估
    python -m scripts.run_eval \
        --input eval_dataset/multi_chat/messages.jsonl \
        --expected eval_dataset/multi_chat/expected.jsonl \
        --mode multi
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.eval_runner import EvalRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="大规模评估 — 决策提取精度测试")
    parser.add_argument("--input", required=True,
                        help="输入 JSONL 消息文件路径")
    parser.add_argument("--expected", required=True,
                        help="expected.jsonl 真值文件路径")
    parser.add_argument("--mode", choices=["single", "multi"], default="single",
                        help="评估模式：single=单群聊, multi=多群聊")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="消息间延迟 (秒)")
    parser.add_argument("--max-messages", type=int, default=0,
                        help="最大处理消息数 (0=全部)")
    parser.add_argument("--model", default="deepseek-chat",
                        help="提取模型名称")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    expected_path = Path(args.expected)

    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}")
        sys.exit(1)
    if not expected_path.exists():
        print(f"错误: 真值文件不存在: {expected_path}")
        sys.exit(1)

    group_num = 1 if args.mode == "single" else 0  # 0 = 从消息中读取 chat_id

    runner = EvalRunner(
        input_path=str(input_path),
        delay=args.delay,
        max_messages=args.max_messages,
        group_num=group_num,
        expected_path=str(expected_path),
    )
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Make the CLI runnable**

Run: `uv run python -m scripts.run_eval --help`
Expected: 显示帮助信息

---

### Task 4: LLM 数据生成器

**Files:**
- Create: `src/eval/generator.py`
- Create: `eval_dataset/config.yaml` (default config)

- [ ] **Step 1: Create config file**

`eval_dataset/config.yaml`:
```yaml
generation:
  method: llm
  model: "deepseek-chat"
  temperature: 0.7

single_chat:
  topics:
    - name: "用PG还是MySQL"
      keywords: ["PostgreSQL", "MySQL", "迁移", "兼容性"]
    - name: "Redis缓存key规范"
      keywords: ["Redis", "缓存", "key命名", "过期策略"]
    - name: "分库分表方案"
      keywords: ["分库", "分表", "ShardingSphere", "MyCAT"]
    - name: "Next.js App Router迁移"
      keywords: ["Next.js", "App Router", "Pages Router", "迁移"]
    - name: "组件库选Antd还是Semi"
      keywords: ["Antd", "Semi Design", "组件库", "迁移"]
    - name: "构建工具切Vite"
      keywords: ["Vite", "Webpack", "构建", "迁移"]
    - name: "K8s版本升级策略"
      keywords: ["K8s", "版本升级", "kubeadm", "Rancher"]
    - name: "Docker镜像体积优化"
      keywords: ["Docker", "镜像", "体积", "alpine", "多阶段构建"]
    - name: "告警阈值调多少"
      keywords: ["告警", "阈值", "P99", "CPU", "内存"]
    - name: "Grafana大盘重构"
      keywords: ["Grafana", "大盘", "面板", "JSON模型"]
    - name: "日志采样率"
      keywords: ["日志", "采样", "ELK", "Loki"]
    - name: "Kafka分区数调整"
      keywords: ["Kafka", "分区", "吞吐", "重平衡"]
    - name: "RabbitMQ死信队列"
      keywords: ["RabbitMQ", "死信", "重试", "延迟队列"]
    - name: "Pulsar Topic管理"
      keywords: ["Pulsar", "Topic", "租户", "namespace"]
  num_decisions_per_topic: 5
  noise_ratio: 0.3
  difficulty:
    easy: 0.3
    medium: 0.4
    hard: 0.3
  total_messages: ~1500

multi_chat:
  num_chats: 5
  topics_per_chat: 3
  num_decisions_per_chat: 8
  overlap_ratio: 0.2
  total_messages: ~2500

speaker_styles:
  - name: "直接型"
    traits: "话少、结论前置、常用'就'字"
  - name: "分析型"
    traits: "话多、喜欢列举优缺点、长句多"
  - name: "谨慎型"
    traits: "常用反问/疑问句、倾向说'再想想''确定吗'"
  - name: "协调型"
    traits: "善于总结、常用'大家觉得呢''那就这么定了'"
```

- [ ] **Step 2: Create the Generator class**

```python
"""LLM 数据生成器 — 大规模有真值标注的群聊对话数据集生成"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

LAYER1_PROMPT_TEMPLATE = """你是一个群聊对话设计师。请根据以下配置生成一个群聊场景蓝图。

要求：
- {num_chats} 个群聊，每个群聊 {topics_per_chat} 个讨论话题
- 每个群聊 {num_participants} 个参与者，风格各异
- 每个话题嵌入 {num_decisions} 个决策点
- 决策点不要太明显，要自然融入讨论

话题列表：
{topics_json}

说话人风格：
{speaker_styles_json}

输出 JSON 格式蓝图（只输出 JSON，无额外文字）。
"""

LAYER2_PROMPT_TEMPLATE = """根据以下场景蓝图生成完整的群聊对话。

群聊配置：
{blueprint_json}

消息生成要求：
- 每条消息长度 5-80 字不等
- 句式多变：陈述句、反问句、疑问句、分析句混合
- 不同说话人有不同语言风格：
  {speaker_styles_json}
- 决策点不能太直接（避免"好，定了用X"的机械句式），
  而是通过共识形成（"X大家都同意吧""行""那就X"）
- 每 {noise_interval} 条消息插入一条完全无关的干扰消息
- 部分议题只讨论不定论（无决策的训练负样本）

输出格式：每行一个 JSON 对象。
当 expected_decision=true 时，附带 expected_topic/expected_summary/expected_status/expected_impact/difficulty 字段。
只输出 JSONL 格式，不要输出其他文字。

示例：
{{"chat_id": "chat_0", "msg_id": "m001", "speaker": "张三", "msg": "数据库选型的话，之前项目用的PG感觉还不错", "expected_decision": false, "is_distractor": false}}
{{"chat_id": "chat_0", "msg_id": "m005", "speaker": "李四", "msg": "大家都同意用PG的话就这么定了", "expected_decision": true, "expected_topic": "数据库选型", "expected_summary": "采用PostgreSQL作为主数据库", "expected_status": "decided", "expected_impact": "major", "difficulty": "easy"}}
"""


class EvalDatasetGenerator:
    """大规模评估数据集生成器

    使用 LLM 的三层生成架构：
    Layer 1: 生成场景蓝图（群聊配置、话题分布、参与者风格）
    Layer 2: 逐批生成 JSONL 消息流（含 expected 标注）
    Layer 3: 后处理提取真值 → expected.jsonl

    Usage:
        generator = EvalDatasetGenerator()
        generator.generate("eval_dataset/single_chat")
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config = self._load_config(config_path)
        self._llm: Optional[LLMClient] = None
        self._model = self._config.get("generation", {}).get("model", "deepseek-chat")
        self._temperature = self._config.get("generation", {}).get("temperature", 0.7)

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    @staticmethod
    def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        if config_path and Path(config_path).exists():
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        default = Path(__file__).resolve().parent.parent.parent / "eval_dataset" / "config.yaml"
        if default.exists():
            import yaml
            with open(default, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {"generation": {"method": "llm", "model": "deepseek-chat", "temperature": 0.7}}

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用 LLM 生成内容"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        llm = self._get_llm()
        response = llm.client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
        )
        return response.choices[0].message.content or ""

    def generate_single_chat(self, output_dir: str) -> None:
        """生成单群聊数据集"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        sc = self._config.get("single_chat", {})
        topics = sc.get("topics", [])
        decisions_per_topic = sc.get("num_decisions_per_topic", 10)
        noise_ratio = sc.get("noise_ratio", 0.3)
        styles = self._config.get("speaker_styles", [])

        logger.info("Generating single-chat dataset: %d topics", len(topics))

        # Layer 1: 生成蓝图
        layer1_prompt = LAYER1_PROMPT_TEMPLATE.format(
            num_chats=1,
            topics_per_chat=len(topics),
            num_participants=3,
            num_decisions=decisions_per_topic,
            topics_json=json.dumps(topics, ensure_ascii=False),
            speaker_styles_json=json.dumps(styles, ensure_ascii=False),
        )
        blueprint_raw = self._call_llm(layer1_prompt)
        logger.info("Layer 1 blueprint generated (%d chars)", len(blueprint_raw))

        # Layer 2: 生成消息流
        layer2_prompt = LAYER2_PROMPT_TEMPLATE.format(
            blueprint_json=blueprint_raw,
            speaker_styles_json=json.dumps(styles, ensure_ascii=False),
            noise_interval=max(1, int(1 / max(noise_ratio, 0.1))),
        )
        messages_raw = self._call_llm(layer2_prompt)
        logger.info("Layer 2 messages generated (%d chars)", len(messages_raw))

        # 解析 JSONL
        messages: List[Dict] = []
        expected: List[Dict] = []
        for line in messages_raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                messages.append(obj)
                if obj.get("expected_decision"):
                    expected.append({
                        "chat_id": obj.get("chat_id", "chat_0"),
                        "msg_id": obj.get("msg_id", ""),
                        "expected_topic": obj.get("expected_topic", ""),
                        "expected_summary": obj.get("expected_summary", ""),
                        "expected_status": obj.get("expected_status", ""),
                        "expected_impact": obj.get("expected_impact", ""),
                        "difficulty": obj.get("difficulty", "medium"),
                    })
            except json.JSONDecodeError:
                logger.warning("Skipping unparseable line: %s", line[:50])

        # 写入 messages.jsonl
        with open(out / "messages.jsonl", "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        logger.info("Wrote %d messages to %s", len(messages), out / "messages.jsonl")

        # 写入 expected.jsonl
        with open(out / "expected.jsonl", "w", encoding="utf-8") as f:
            for exp in expected:
                f.write(json.dumps(exp, ensure_ascii=False) + "\n")
        logger.info("Wrote %d expected decisions to %s", len(expected), out / "expected.jsonl")

        # 日志
        log_path = out.parent / "generation.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] single_chat: "
                    f"{len(messages)} msgs, {len(expected)} decisions\n")

    def generate_multi_chat(self, output_dir: str) -> None:
        """生成多群聊数据集"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        mc = self._config.get("multi_chat", {})
        num_chats = mc.get("num_chats", 5)
        topics_per_chat = mc.get("topics_per_chat", 3)
        decisions_per_chat = mc.get("num_decisions_per_chat", 8)
        noise_ratio = self._config.get("single_chat", {}).get("noise_ratio", 0.3)
        styles = self._config.get("speaker_styles", [])

        logger.info("Generating multi-chat dataset: %d chats", num_chats)
        topics = self._config.get("single_chat", {}).get("topics", [])

        # Layer 1
        layer1_prompt = LAYER1_PROMPT_TEMPLATE.format(
            num_chats=num_chats,
            topics_per_chat=topics_per_chat,
            num_participants=3,
            num_decisions=decisions_per_chat,
            topics_json=json.dumps(topics, ensure_ascii=False),
            speaker_styles_json=json.dumps(styles, ensure_ascii=False),
        )
        blueprint_raw = self._call_llm(layer1_prompt)

        # Layer 2
        layer2_prompt = LAYER2_PROMPT_TEMPLATE.format(
            blueprint_json=blueprint_raw,
            speaker_styles_json=json.dumps(styles, ensure_ascii=False),
            noise_interval=max(1, int(1 / max(noise_ratio, 0.1))),
        )
        messages_raw = self._call_llm(layer2_prompt)

        # 解析 (same as single_chat)
        messages: List[Dict] = []
        expected: List[Dict] = []
        for line in messages_raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                messages.append(obj)
                if obj.get("expected_decision"):
                    expected.append({
                        "chat_id": obj.get("chat_id", ""),
                        "msg_id": obj.get("msg_id", ""),
                        "expected_topic": obj.get("expected_topic", ""),
                        "expected_summary": obj.get("expected_summary", ""),
                        "expected_status": obj.get("expected_status", ""),
                        "expected_impact": obj.get("expected_impact", ""),
                        "difficulty": obj.get("difficulty", "medium"),
                    })
            except json.JSONDecodeError:
                pass

        with open(out / "messages.jsonl", "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        with open(out / "expected.jsonl", "w", encoding="utf-8") as f:
            for exp in expected:
                f.write(json.dumps(exp, ensure_ascii=False) + "\n")

        log_path = out.parent / "generation.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] multi_chat: "
                    f"{len(messages)} msgs, {len(expected)} decisions\n")
        logger.info("Generated multi-chat: %d msgs, %d decisions", len(messages), len(expected))

    def generate(self, output_dir: str, mode: str = "single_chat") -> None:
        """便捷方法：按模式生成"""
        if mode == "multi_chat":
            self.generate_multi_chat(output_dir)
        else:
            self.generate_single_chat(output_dir)
```

- [ ] **Step 3: Verify the module imports correctly**

Run: `uv run python3 -c "from src.eval.generator import EvalDatasetGenerator; print('OK')"`
Expected: OK

---

### Task 5: generate_eval_data.py — 数据生成 CLI

**Files:**
- Create: `scripts/generate_eval_data.py`

- [ ] **Step 1: Create scripts/generate_eval_data.py**

```python
#!/usr/bin/env python3
"""大规模评估数据生成 CLI — Phase 1

Usage:
    # 单群聊
    python -m scripts.generate_eval_data --mode single_chat --output eval_dataset/single_chat

    # 多群聊
    python -m scripts.generate_eval_data --mode multi_chat --output eval_dataset/multi_chat

    # 指定配置
    python -m scripts.generate_eval_data --mode multi_chat --num-chats 3 --num-decisions 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.eval.generator import EvalDatasetGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="大规模评估数据生成")
    parser.add_argument("--mode", choices=["single_chat", "multi_chat"], default="single_chat",
                        help="生成模式")
    parser.add_argument("--output", default="eval_dataset/single_chat",
                        help="输出目录")
    parser.add_argument("--config", default="",
                        help="配置文件路径 (可选)")
    parser.add_argument("--num-chats", type=int, default=0,
                        help="覆盖多群聊数量")
    parser.add_argument("--num-decisions", type=int, default=0,
                        help="覆盖每主题决策数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generator = EvalDatasetGenerator(config_path=args.config or None)
    generator.generate(str(Path(args.output).resolve()), mode=args.mode)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make the CLI runnable**

Run: `uv run python -m scripts.generate_eval_data --help`
Expected: 显示帮助信息

---

### Task 6: 更新 eval/__init__.py 导出

**Files:**
- Modify: `src/eval/__init__.py`

- [ ] **Step 1: Add exports for new modules**

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.eval.comparator import EvalComparator
from src.eval.generator import EvalDatasetGenerator

EVALDATA_DIR = Path(__file__).resolve().parent.parent.parent / "eval_data"

# ... keep all existing functions (load_jsonl, load_extraction_dialogue, etc.) ...
```

Just add the two import lines at the top after the existing imports. Keep all existing code unchanged.

- [ ] **Step 2: Verify**

Run: `uv run python3 -c "from src.eval import EvalComparator, EvalDatasetGenerator; print('OK')"`
Expected: OK

---

### Task 7: 集成测试 — 生成小型数据集并运行评估

**Files:**
- Create: `tests/test_eval_pipeline.py`

- [ ] **Step 1: Write integration test using a small pre-built dataset**

Since LLM generation is costly, create a small hand-crafted dataset for CI testing:

Create `eval_dataset/test_small/` manually with:
- `messages.jsonl`: ~20 messages with 3 decision points  
- `expected.jsonl`: 3 expected decisions

`eval_dataset/test_small/messages.jsonl`:
```jsonl
{"chat_id": "chat_0", "msg_id": "m001", "speaker": "张三", "msg": "用PG还是MySQL，之前项目用的PG感觉还不错", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m002", "speaker": "李四", "msg": "PG的扩展性确实好，而且社区活跃，但MySQL我们团队更熟，上手成本低", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m003", "speaker": "王五", "msg": "确定吗？PG的学习曲线可不低，线上万一出问题能搞定吗", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m004", "speaker": "张三", "msg": "长期看PG更值得投入，文档也全，周边生态像PostGIS这些后面可能用得上", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m005", "speaker": "李四", "msg": "要不这样，核心业务用PG，历史数据还是放MySQL读库，两边不耽误", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m006", "speaker": "王五", "msg": "行，那就PG吧，MySQL先保留着做读库", "expected_decision": true, "expected_topic": "用PG还是MySQL", "expected_summary": "核心业务采用PostgreSQL，历史数据保留MySQL作为读库", "expected_status": "decided", "expected_impact": "major", "difficulty": "easy"}
{"chat_id": "chat_0", "msg_id": "m007", "speaker": "张三", "msg": "App Router迁移了吗？新项目要不要直接用", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m008", "speaker": "李四", "msg": "App Router的streaming和server components挺香的，但Pages Router的项目迁过来工作量不小", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m009", "speaker": "王五", "msg": "Pages Router用得好好的，迁移出问题谁负责，再说吧", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m010", "speaker": "李四", "msg": "昨天试了下，路由定义更直观，loading.tsx直接丢目录就行，不用手动配了", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_0", "msg_id": "m011", "speaker": "张三", "msg": "那就迁吧，早迁早享受，新项目直接上App Router", "expected_decision": true, "expected_topic": "Next.js App Router迁移", "expected_summary": "新项目直接采用App Router，存量Pages Router项目逐步迁移", "expected_status": "decided", "expected_impact": "major", "difficulty": "medium"}
{"chat_id": "chat_1", "msg_id": "m012", "speaker": "赵六", "msg": "K8s版本升级策略大家有什么想法？现在集群还是1.24", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_1", "msg_id": "m013", "speaker": "钱七", "msg": "1.24快EOL了，至少升到1.26，但跨版本升级要一个个来，不能跳", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_1", "msg_id": "m014", "speaker": "赵六", "msg": "今天食堂的鱼香肉丝不错，比上周好", "expected_decision": false, "is_distractor": true}
{"chat_id": "chat_1", "msg_id": "m015", "speaker": "钱七", "msg": "先用kubeadm升到1.26，跑一个月稳定了再上1.28，这样风险可控", "expected_decision": false, "is_distractor": false}
{"chat_id": "chat_1", "msg_id": "m016", "speaker": "赵六", "msg": "那就按这个节奏来，先1.26再1.28，中间留够观察期", "expected_decision": true, "expected_topic": "K8s版本升级策略", "expected_summary": "先用kubeadm升级到1.26，稳定运行一个月后再升级到1.28", "expected_status": "decided", "expected_impact": "major", "difficulty": "medium"}
```

`eval_dataset/test_small/expected.jsonl`:
```jsonl
{"chat_id": "chat_0", "msg_id": "m006", "expected_topic": "用PG还是MySQL", "expected_summary": "核心业务采用PostgreSQL，历史数据保留MySQL作为读库", "expected_status": "decided", "expected_impact": "major", "difficulty": "easy"}
{"chat_id": "chat_0", "msg_id": "m011", "expected_topic": "Next.js App Router迁移", "expected_summary": "新项目直接采用App Router，存量Pages Router项目逐步迁移", "expected_status": "decided", "expected_impact": "major", "difficulty": "medium"}
{"chat_id": "chat_1", "msg_id": "m016", "expected_topic": "K8s版本升级策略", "expected_summary": "先用kubeadm升级到1.26，稳定运行一个月后再升级到1.28", "expected_status": "decided", "expected_impact": "major", "difficulty": "medium"}
```

- [ ] **Step 2: Write integration test**

`tests/test_eval_pipeline.py`:
```python
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
```

- [ ] **Step 3: Run integration test**

Run: `uv run pytest tests/test_eval_pipeline.py -v`
Expected: PASS (may need API_KEY set in env)

---

### 执行顺序总结

| # | Task | 依赖 |
|---|------|------|
| 1 | EvalComparator + 单元测试 | 无 |
| 2 | EvalRunner JSONL 增强 | Task 1 |
| 3 | run_eval.py CLI | Task 1, 2 |
| 4 | EvalDatasetGenerator | 无 (仅 LLMClient) |
| 5 | generate_eval_data.py CLI | Task 4 |
| 6 | eval/__init__.py 导出 | Task 1, 4 |
| 7 | test_small 数据集 + 集成测试 | Task 2 |