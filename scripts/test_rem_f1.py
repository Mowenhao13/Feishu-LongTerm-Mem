#!/usr/bin/env python3
"""完整测试 REM Sleep 对 F1 提升效果 (single_chat & multi_chat)"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_expected_decisions(dataset: str):
    """加载预期决策"""
    expected_path = PROJECT_ROOT / "eval_dataset" / dataset / "expected.jsonl"
    if not expected_path.exists():
        return []
    expected = []
    with open(expected_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                expected.append(json.loads(line))
    return expected


def load_extracted_decisions_with_status():
    """加载提取的决策并包含 status 信息"""
    import subprocess as sp
    storage_dir = PROJECT_ROOT / "mem-data"
    if not (storage_dir / ".git").exists():
        return []

    decisions = []
    sp.run(["git", "config", "core.quotepath", "false"], cwd=str(storage_dir), capture_output=True)
    result = sp.run(
        ["git", "branch", "--list", "decision/*"],
        cwd=str(storage_dir),
        capture_output=True,
        text=True,
    )
    branches = [b.strip().lstrip("* ") for b in result.stdout.strip().split("\n") if b.strip()]

    for branch in branches:
        try:
            result = sp.run(
                ["git", "ls-tree", "-r", "--name-only", branch, "--", "decisions/"],
                cwd=str(storage_dir),
                capture_output=True,
                text=True,
            )
            md_files = [f for f in result.stdout.strip().split("\n") if f.endswith(".md")]
            for fpath in md_files:
                result = sp.run(
                    ["git", "show", f"{branch}:{fpath}"],
                    cwd=str(storage_dir),
                    capture_output=True,
                    text=True,
                )
                content = result.stdout
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        yaml_text = parts[1]
                        body = parts[2].strip()
                        record = {"sid": Path(fpath).stem}
                        for line in yaml_text.split("\n"):
                            line = line.strip()
                            if ":" in line and not line.startswith("#"):
                                k, v = line.split(":", 1)
                                record[k.strip().lower()] = v.strip().strip('"')
                        record["body"] = body
                        decisions.append(record)
        except Exception as e:
            pass
    return decisions


def compute_similarity(text1: str, text2: str):
    """字符级双字母组相似度"""
    def get_bigrams(text):
        t = text.lower()
        return set(t[i:i+2] for i in range(len(t)-1))

    b1 = get_bigrams(text1)
    b2 = get_bigrams(text2)
    if not b1 or not b2:
        return 0.0
    return len(b1 & b2) / len(b1 | b2)


def evaluate_f1(extracted: list, expected: list):
    """计算 F1，和 run_eval_accuracy.py 逻辑一致"""
    true_positive = 0
    false_positive = 0
    matched_expected = set()

    for ext in extracted:
        ext_text = ext.get("summary", "") + " " + ext.get("body", "")
        best_score = 0.0
        best_idx = -1
        for i, exp in enumerate(expected):
            if i in matched_expected:
                continue
            exp_text = exp.get("expected_summary", "") + " " + exp.get("expected_topic", "")
            score = compute_similarity(ext_text, exp_text)
            if score > best_score:
                best_score = score
                best_idx = i
        if best_score >= 0.2:
            true_positive += 1
            matched_expected.add(best_idx)
        else:
            false_positive += 1

    false_negative = len(expected) - len(matched_expected)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive > 0 else 0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative > 0 else 0
    f1 = (2 * precision * recall) / (precision + recall) if precision + recall > 0 else 0

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "extracted_count": len(extracted),
        "expected_count": len(expected),
    }


def run_eval_once(dataset: str):
    """运行一次 eval 并返回结果"""
    import subprocess
    cmd = [sys.executable, "-m", "uv", "run", "python3", "scripts/run_eval_accuracy.py", "--dataset", dataset]
    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return


async def run_sleep_with_rem():
    """运行完整的 sleep 周期，包含 REM 阶段"""
    from src.core.engine import MemoryEngine
    from src.memory.sleep import SleepManager
    from src.node.types import DecisionStatus

    print()
    print("=" * 80)
    print("RUNNING: SleepManager with REM phase")
    print("=" * 80)

    engine = MemoryEngine()
    await engine.initialize()

    llm = None
    if hasattr(engine, "_llm") and engine._llm:
        llm = engine._llm
    elif hasattr(engine, "llm_provider"):
        llm = engine.llm_provider

    sm = SleepManager(
        graph=engine._graph,
        pipeline=engine._pipeline,
        storage=engine._storage,
        llm_provider=llm,
    )
    report = sm.sleep()

    print()
    print("=" * 80)
    print("SLEEP REPORT")
    print("=" * 80)
    print(f"  total decisions:       {report.total_decisions}")
    print(f"  duplicates found:      {report.duplicates_found}")
    print(f"  duplicates merged:     {report.duplicates_merged}")
    print(f"  FP found:              {report.fp_found}")
    print(f"  FP shelved:            {report.fp_shelved}")
    print(f"  noise pruned:          {report.noise_pruned}")
    print(f"  conflicts found:       {report.conflicts_found}")
    print(f"  decisions promoted:    {report.decisions_promoted}")
    if report.errors:
        print(f"  errors: {report.errors}")

    return report


async def test_dataset(dataset: str):
    """测试单个数据集"""
    print("\n" + "=" * 80)
    print(f"TESTING DATASET: {dataset}")
    print("=" * 80)

    # 清理
    if (PROJECT_ROOT / "mem-data").exists():
        import shutil
        shutil.rmtree(PROJECT_ROOT / "mem-data")

    # Step 1: Initial eval (before sleep)
    print()
    print("=" * 80)
    print(f"STAGE 1: Eval WITHOUT Sleep ({dataset})")
    print("=" * 80)
    run_eval_once(dataset)
    extracted_before = load_extracted_decisions_with_status()
    expected = load_expected_decisions(dataset)
    score_before = evaluate_f1(extracted_before, expected)

    # Step 2: Run Sleep (with REM)
    await run_sleep_with_rem()

    # Step 3: 加载经过 sleep 后的决策（过滤 shelved）
    extracted_after_all = load_extracted_decisions_with_status()
    extracted_after = [
        d for d in extracted_after_all
        if d.get("status", "").lower() not in ("shelved", "superseded")
    ]
    score_after = evaluate_f1(extracted_after, expected)

    # 打印结果对比
    print()
    print("=" * 80)
    print(f"FINAL RESULTS FOR: {dataset}")
    print("=" * 80)
    print()
    print(f"  {'BEFORE SLEEP':<20}   |   {'AFTER SLEEP':<20}")
    print("-" * 45)
    print(f"  Extracted:   {score_before['extracted_count']:<10}   |   {score_after['extracted_count']:<10}")
    print(f"  TP:          {score_before['true_positive']:<10}   |   {score_after['true_positive']:<10}")
    print(f"  FP:          {score_before['false_positive']:<10}   |   {score_after['false_positive']:<10}")
    print(f"  FN:          {score_before['false_negative']:<10}   |   {score_after['false_negative']:<10}")
    print(f"  Precision:   {score_before['precision']*100:<7.2f}%   |   {score_after['precision']*100:<7.2f}%")
    print(f"  Recall:      {score_before['recall']*100:<7.2f}%   |   {score_after['recall']*100:<7.2f}%")
    print(f"  F1:          {score_before['f1']*100:<7.2f}%   |   {score_after['f1']*100:<7.2f}%")
    print(f"  F1 Δ:        {' ':10}   |   {(score_after['f1'] - score_before['f1'])*100:+.2f}%")
    print()

    return {
        "dataset": dataset,
        "before": score_before,
        "after": score_after,
    }


async def main():
    print("=" * 80)
    print("REM SLEEP F1 TEST SUITE")
    print("=" * 80)

    results = []
    for dataset in ["single_chat", "multi_chat"]:
        res = await test_dataset(dataset)
        results.append(res)

    # 汇总结果
    print("\n" + "=" * 80)
    print("SUMMARY: ALL DATASETS")
    print("=" * 80)
    for res in results:
        ds = res["dataset"]
        b, a = res["before"], res["after"]
        print(f"\n  {ds:>12}: F1 {b['f1']*100:.2f}% → {a['f1']*100:.2f}% (Δ {(a['f1']-b['f1'])*100:+.2f}%)")

    # 保存结果
    out_path = PROJECT_ROOT / "eval_reports" / f"rem_sleep_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
