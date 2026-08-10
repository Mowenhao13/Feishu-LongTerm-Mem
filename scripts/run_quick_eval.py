"""快速评估脚本：读取 pipeline 输出的中间决策文件，跑 Embedding + EvalComparator + 可选 LLM Judge 评估。

用法:
    # 先跑 LLM pipeline（--save-decisions 保存中间决策到 JSON）
    LANGFUSE_ENABLE=false .venv/bin/python scripts/run_full_pipeline_test.py --no-docs --save-decisions

    # 然后单独跑评估（embedding + LLM Judge）
    LANGFUSE_ENABLE=false .venv/bin/python scripts/run_quick_eval.py \
        --decisions eval_results/decisions_cache.json \
        --llm-judge

    # 只跑 embedding，不加 LLM Judge
    LANGFUSE_ENABLE=false .venv/bin/python scripts/run_quick_eval.py \
        --decisions eval_results/decisions_cache.json
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

from src.eval.comparator import EvalComparator
from src.model.embedding_provider import EmbeddingProvider
from src.model.openai_provider import OpenAIProvider

load_dotenv()


def load_decisions(cache_path: str):
    with open(cache_path) as f:
        return json.load(f)


def build_actual_decisions(raw: list, use_with: bool):
    """_build_decisions 的纯函数版"""
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


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", default="eval_results/decisions_cache.json")
    parser.add_argument("--expected", default="eval_dataset/argusbot_v3/expected.jsonl")
    parser.add_argument("--llm-judge", action="store_true",
                        help="启用 LLM Judge 二次验证（对 embedding 匹配的低置信度 TP 做 LLM 确认）")
    parser.add_argument("--llm-concurrency", type=int, default=5,
                        help="LLM Judge 并发数（默认 5）")
    args = parser.parse_args()

    expected_path = Path(args.expected)
    if not expected_path.exists():
        print(f"✗ expected not found: {expected_path}")
        return

    raw = load_decisions(args.decisions)
    print(f"Loaded {len(raw)} episode results from cache")

    t0 = time.time()
    embedder = EmbeddingProvider()
    print(f"[Embedding] init: {time.time()-t0:.1f}s")

    # 可选的 LLM Judge provider
    llm_provider = None
    base_url = os.getenv("BASE_URL", "https://aigw.sysu.edu.cn/v1")
    api_key = os.getenv("API_KEY")
    if args.llm_judge and api_key:
        llm_provider = OpenAIProvider(
            base_url=base_url,
            api_key=api_key,
            model="deepseek-local",
        )
        print("[LLM Judge] enabled (deepseek-local)")

    for label, use_with in [("有 project context", True), ("无 project context", False)]:
        actual = build_actual_decisions(raw, use_with=use_with)
        print(f"\n{'=' * 50}")
        print(f"{label}")
        print(f"{'=' * 50}")
        print(f"  实际决策: {len(actual)}, 预期: {len(raw) if use_with else len(raw)}")

        comp = EvalComparator(
            str(expected_path),
            embedding_provider=embedder,
            llm_provider=llm_provider,
        )
        comp.match(actual)

        # LLM Judge 二次验证
        if llm_provider:
            print("  LLM Judge 验证中...")
            v_t0 = time.time()
            judge_result = await comp.llm_verify_matches(max_concurrent=args.llm_concurrency)
            v_time = time.time() - v_t0
            print(f"    Verified TP: {judge_result['verified_tp']}, "
                  f"Rejected TP: {judge_result['rejected_tp']} "
                  f"({v_time:.1f}s)")
            if judge_result.get("details"):
                for d in judge_result["details"][:5]:
                    print(f"    → Rejected: \"{d['expected_summary']}\" ↔ \"{d['actual_summary']}\"")

        m = comp.compute_metrics()
        print(f"  TP={m['true_positives']} FP={m['false_positives']} FN={m['false_negatives']}")
        print(f"  Precision={m['precision']:.2%}  Recall={m['recall']:.2%}  F1={m['f1']:.2%}")
        print(f"  (expected={m['total_expected']}, detected={m['total_detected']})")

    print(f"\n总耗时: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())