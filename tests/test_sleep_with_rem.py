#!/usr/bin/env python3
"""REM Sleep F1 测试：single_chat + multi_chat，使用 correct STORAGE_PATH"""
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent
# 统一使用 mem-data
STORAGE_DIR = str(ROOT / "mem-data")


def load_expected(dataset):
    path = ROOT / "eval_dataset" / dataset / "expected.jsonl"
    decisions = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                decisions.append(json.loads(line))
    return decisions


def load_extracted(storage_dir):
    """从 git storage 加载提取的决策（与 run_eval_accuracy.py 一致）"""
    decisions = []
    subprocess.run(["git", "config", "core.quotepath", "false"], cwd=storage_dir, capture_output=True)
    result = subprocess.run(
        ["git", "branch", "--list", "decision/*"],
        cwd=storage_dir, capture_output=True, text=True,
    )
    branches = [b.strip().lstrip("* ") for b in result.stdout.strip().split("\n") if b.strip()]
    for branch in branches:
        try:
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", branch, "--", "decisions/"],
                cwd=storage_dir, capture_output=True, text=True,
            )
            md_files = [f for f in result.stdout.strip().split("\n") if f.endswith(".md")]
            for fpath in md_files:
                result = subprocess.run(
                    ["git", "show", f"{branch}:{fpath}"],
                    cwd=storage_dir, capture_output=True, text=True,
                )
                content = result.stdout
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        yaml_text = parts[1]
                        body = parts[2].strip()
                        sid = ""
                        summary = ""
                        topic = ""
                        status = ""
                        for line in yaml_text.split("\n"):
                            if line.startswith("sid:"):
                                sid = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("summary:"):
                                summary = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("topic_id:"):
                                topic = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("status:"):
                                status = line.split(":", 1)[1].strip().strip('"')
                        decisions.append({
                            "sid": sid,
                            "summary": summary,
                            "topic_id": topic,
                            "status": status,
                            "body": body,
                        })
        except Exception:
            pass
    return decisions


def compute_similarity(text1, text2):
    def get_bigrams(text):
        text = text.lower()
        return set(text[i:i+2] for i in range(len(text)-1))
    b1 = get_bigrams(text1)
    b2 = get_bigrams(text2)
    if not b1 or not b2:
        return 0.0
    return len(b1 & b2) / len(b1 | b2)


def evaluate(expected_list, extracted_list):
    """与 run_eval_accuracy.py 一致的评估"""
    n_expected = len(expected_list)
    n_extracted = len(extracted_list)
    matched_expected = set()
    matched_extracted = set()

    for i, ext in enumerate(extracted_list):
        ext_summary = ext.get("summary", "")
        ext_body = ext.get("body", "")
        ext_text = (ext_summary + " " + ext_body).lower()
        best_score = 0.0
        best_idx = -1
        for j, exp in enumerate(expected_list):
            if j in matched_expected:
                continue
            exp_summary = exp.get("expected_summary", "")
            exp_topic = exp.get("expected_topic", "")
            summary_sim = compute_similarity(ext_summary, exp_summary)
            body_sim = compute_similarity(ext_body, exp_summary) if ext_body else 0
            score = max(summary_sim, body_sim * 0.7)
            if exp_topic and ext_summary:
                topic_match = any(w in ext_text for w in exp_topic.lower().replace(" ", ""))
                if topic_match:
                    score = min(1.0, score + 0.15)
            if score > best_score:
                best_score = score
                best_idx = j
        if best_score >= 0.3:
            matched_expected.add(best_idx)
            matched_extracted.add(i)

    true_positives = len(matched_extracted)
    false_positives = n_extracted - true_positives
    false_negatives = n_expected - len(matched_expected)
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "n_expected": n_expected,
        "n_extracted": n_extracted,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def run_eval(dataset):
    """运行 eval"""
    print(f"  Running eval ({dataset})...")
    subprocess.run(
        ["uv", "run", "python3", "scripts/run_eval_accuracy.py", "--dataset", dataset],
        cwd=ROOT,
        check=False,
        env={**os.environ, "STORAGE_PATH": STORAGE_DIR},
    )


def run_sleep():
    """运行 SleepManager.sleep()，带正确的 STORAGE_PATH 和 LLM provider"""
    os.environ["STORAGE_PATH"] = STORAGE_DIR

    # 直接创建 LLM provider
    from src.model.llm_provider import LLMProvider as DirectLLM
    api_key = os.getenv("API_KEY", "")
    llm = None
    if api_key:
        try:
            llm = DirectLLM(
                provider_type="openai",
                base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
                api_key=api_key,
                model=os.getenv("MODEL_NAME", "deepseek-chat"),
            )
        except Exception as e:
            print(f"  LLM init error: {e}")

    from src.core.engine import MemoryEngine
    from src.memory.sleep import SleepManager
    engine = MemoryEngine()
    engine.initialize()
    print(f"  LLM available: {llm is not None}")
    sm = SleepManager(
        graph=engine._graph,
        pipeline=engine._pipeline,
        storage=engine._storage,
        llm_provider=llm,
    )
    report = sm.sleep()
    print(f"  Sleep Report:")
    print(f"    total_decisions: {report.total_decisions}")
    print(f"    fp_found: {report.fp_found}")
    print(f"    fp_shelved: {report.fp_shelved}")
    print(f"    duplicates_found: {report.duplicates_found}")
    print(f"    duplicates_merged: {report.duplicates_merged}")
    if report.errors:
        print(f"    errors: {report.errors}")
    return report


def test_dataset(dataset):
    """测试单个数据集"""
    print(f"\n{'#'*80}")
    print(f"# Testing {dataset}")
    print(f"{'#'*80}")

    # 清理
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)

    # Step 1: eval without sleep
    print(f"\n{'='*60}")
    print("STAGE 1: Eval WITHOUT Sleep")
    print(f"{'='*60}")
    run_eval(dataset)
    expected = load_expected(dataset)
    extracted_before = load_extracted(STORAGE_DIR)
    score_before = evaluate(expected, extracted_before)
    print(f"  Extracted: {score_before['n_extracted']}, Expected: {score_before['n_expected']}")
    print(f"  F1: {score_before['f1']*100:.2f}%, TP: {score_before['true_positives']}, FP: {score_before['false_positives']}")

    # Step 2: sleep with REM
    print(f"\n{'='*60}")
    print("STAGE 2: Sleep with REM")
    print(f"{'='*60}")
    sleep_report = run_sleep()

    # Step 3: evaluate after sleep
    print(f"\n{'='*60}")
    print("STAGE 3: Evaluate AFTER Sleep")
    print(f"{'='*60}")
    extracted_after_all = load_extracted(STORAGE_DIR)
    extracted_after = [d for d in extracted_after_all if d.get("status", "").lower() not in ("shelved", "superseded")]
    score_after = evaluate(expected, extracted_after)

    # 输出对比
    print(f"\n{'='*60}")
    print(f"FINAL RESULT: {dataset}")
    print(f"{'='*60}")
    print(f"  {'':<15} | {'Before Sleep':<15} | {'After Sleep':<15}")
    print("  " + "-" * 48)
    print(f"  {'Extracted':<15} | {score_before['n_extracted']:<15} | {score_after['n_extracted']:<15}")
    print(f"  {'TP':<15} | {score_before['true_positives']:<15} | {score_after['true_positives']:<15}")
    print(f"  {'FP':<15} | {score_before['false_positives']:<15} | {score_after['false_positives']:<15}")
    print(f"  {'FN':<15} | {score_before['false_negatives']:<15} | {score_after['false_negatives']:<15}")
    print(f"  {'Precision':<15} | {score_before['precision']*100:<14.2f}% | {score_after['precision']*100:<14.2f}%")
    print(f"  {'Recall':<15} | {score_before['recall']*100:<14.2f}% | {score_after['recall']*100:<14.2f}%")
    print(f"  {'F1':<15} | {score_before['f1']*100:<14.2f}% | {score_after['f1']*100:<14.2f}%")
    f1_diff = (score_after['f1'] - score_before['f1']) * 100
    print(f"  {'F1 Δ':<15} | {'':<15} | {'+' if f1_diff > 0 else ''}{f1_diff:.2f}%")

    return {
        "dataset": dataset,
        "before": score_before,
        "after": score_after,
        "sleep": {
            "fp_found": sleep_report.fp_found,
            "fp_shelved": sleep_report.fp_shelved,
            "duplicates_found": sleep_report.duplicates_found,
            "duplicates_merged": sleep_report.duplicates_merged,
        },
    }


def main():
    os.environ["STORAGE_PATH"] = STORAGE_DIR  # set early for all subprocesses

    print("=" * 80)
    print("REM SLEEP F1 TEST")
    print("=" * 80)
    results = []
    for dataset in ["single_chat", "multi_chat"]:
        try:
            results.append(test_dataset(dataset))
        except Exception as e:
            print(f"\nError: {e}\n{traceback.format_exc()}")

    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    for r in results:
        ds = r["dataset"]
        b, a = r["before"], r["after"]
        f1_diff = (a["f1"] - b["f1"]) * 100
        print(f"  {ds:>12}: F1 {b['f1']*100:.2f}% → {a['f1']*100:.2f}% (Δ {f1_diff:+.2f}%)")
        print(f"           FP {b['false_positives']} → {a['false_positives']}, Sleep shelved={r['sleep']['fp_shelved']}")

    out_path = ROOT / "eval_reports" / f"rem_f1_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(exist_ok=True, parents=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to {out_path}")


if __name__ == "__main__":
    main()