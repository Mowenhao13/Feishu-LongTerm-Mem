"""分析 FN（False Negatives）的模式 — LLM 分析为何 pipeline 漏掉了这些决策。

用法:
    LANGFUSE_ENABLE=false .venv/bin/python scripts/analyze_fn_patterns.py
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from src.eval.comparator import EvalComparator
from src.model.embedding_provider import EmbeddingProvider

load_dotenv()


def load_decisions(cache_path: str):
    with open(cache_path) as f:
        return json.load(f)


def build_actual_decisions(raw: list, use_with: bool):
    decs = []
    for r in raw:
        if not r.get("ok"):
            continue
        key = "with_project" if use_with else "without_project"
        for d_summary in r["stage2"][key]["decision_summaries"]:
            decs.append({
                "sid": f"eval_{r['episode_id']}_{hash(d_summary) % 100000:05d}",
                "topic_id": r.get("topic", ""),
                "summary": d_summary,
                "status": "decided",
                "impact": "major",
                "chat_id": r["chat_id"],
                "is_suggestion": False,
            })
    return decs


def main():
    raw = load_decisions("eval_results/decisions_cache.json")
    embedder = EmbeddingProvider()
    expected_path = Path("eval_dataset/argusbot_v3/expected.jsonl")

    # 用 embedding 模式跑有 project context 的版本
    actual = build_actual_decisions(raw, use_with=True)
    comp = EvalComparator(str(expected_path), embedding_provider=embedder)
    comp.match(actual)
    m = comp.compute_metrics()

    print(f"=== FN 分析（有 project context, embedding） ===")
    print(f"Total FN: {m['false_negatives']}")
    print(f"Total expected: {m['total_expected']}")
    print()

    # 按 topic 统计 FN 分布
    fn_topics = Counter()
    for exp in comp._false_negatives:
        t = exp.get("expected_topic", "unknown")
        fn_topics[t] += 1

    print("FN 按 Topic 分布:")
    for topic, count in fn_topics.most_common(20):
        print(f"  {topic}: {count}")

    # 列出所有 FN 以分析模式
    print(f"\n=== 所有 {len(comp._false_negatives)} 个 FN 详情 ===")
    for i, exp in enumerate(comp._false_negatives):
        summary = exp.get("expected_summary", "")[:60]
        topic = exp.get("expected_topic", "")
        chat = exp.get("chat_id", "")
        tp_count = sum(1 for e, a in comp._true_positives
                       if e.get("expected_topic") == topic and e.get("chat_id") == chat)
        print(f"  FN {i:3d} [{topic:20s}] [{chat:20s}] (chat has {tp_count} TP) | {summary}")


if __name__ == "__main__":
    main()