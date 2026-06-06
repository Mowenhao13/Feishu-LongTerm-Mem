#!/usr/bin/env python3
"""简化版 single_chat REM 测试"""
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
        except Exception:
            pass
    return decisions


def compute_similarity(text1: str, text2: str):
    def get_bigrams(text):
        t = text.lower()
        return set(t[i:i+2] for i in range(len(t)-1))
    b1 = get_bigrams(text1)
    b2 = get_bigrams(text2)
    if not b1 or not b2:
        return 0.0
    return len(b1 & b2) / len(b1 | b2)


def evaluate_f1(extracted: list, expected: list):
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


def main():
    dataset = "single_chat"

    print("\n" + "=" * 80)
    print(f"STAGE 1: RUN EVAL WITHOUT SLEEP - {dataset}")
    print("=" * 80)

    if (PROJECT_ROOT / "mem-data").exists():
        import shutil
        shutil.rmtree(PROJECT_ROOT / "mem-data")

    subprocess.run(
        ["uv", "run", "python3", "scripts/run_eval_accuracy.py", "--dataset", dataset],
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    expected = load_expected_decisions(dataset)
    extracted_before = load_extracted_decisions_with_status()
    score_before = evaluate_f1(extracted_before, expected)
    print("\nBEFORE SLEEP:")
    print(
        f"  Extracted: {score_before['extracted_count']}, "
        f"TP: {score_before['true_positive']}, "
        f"FP: {score_before['false_positive']}, "
        f"FN: {score_before['false_negative']}, "
        f"Precision: {score_before['precision']*100:.2f}%, "
        f"Recall: {score_before['recall']*100:.2f}%, "
        f"F1: {score_before['f1']*100:.2f}%"
    )

    print("\n" + "=" * 80)
    print("STAGE 2: RUN SLEEP WITH REM")
    print("=" * 80)

    from src.core.engine import MemoryEngine
    from src.memory.sleep import SleepManager

    engine = MemoryEngine()
    engine.initialize()

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
    print("\nSLEEP REPORT:")
    print(f"  Total decisions: {report.total_decisions}")
    print(f"  FP found: {report.fp_found}")
    print(f"  FP shelved: {report.fp_shelved}")

    print("\n" + "=" * 80)
    print("STAGE 3: EVALUATE AFTER SLEEP")
    print("=" * 80)

    extracted_after_all = load_extracted_decisions_with_status()
    extracted_after = [
        d for d in extracted_after_all
        if d.get("status", "").lower() not in ("shelved", "superseded")
    ]
    score_after = evaluate_f1(extracted_after, expected)

    print("\nAFTER SLEEP:")
    print(
        f"  Extracted: {score_after['extracted_count']}, "
        f"TP: {score_after['true_positive']}, "
        f"FP: {score_after['false_positive']}, "
        f"FN: {score_after['false_negative']}, "
        f"Precision: {score_after['precision']*100:.2f}%, "
        f"Recall: {score_after['recall']*100:.2f}%, "
        f"F1: {score_after['f1']*100:.2f}%"
    )

    print("\n" + "=" * 80)
    print("FINAL COMPARISON:")
    print("=" * 80)
    print(f"  F1: {score_before['f1']*100:.2f}% → {score_after['f1']*100:.2f}% (Δ {(score_after['f1']-score_before['f1'])*100:+.2f}%)")


if __name__ == "__main__":
    main()
