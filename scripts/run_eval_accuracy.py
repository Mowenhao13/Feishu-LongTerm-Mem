"""Run eval on converted eval_dataset and compare against expected.jsonl."""

import argparse
import json
import os
import subprocess
import sys
import shutil
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
STORAGE_DIR = os.environ.get("STORAGE_PATH", os.path.join(ROOT, "mem-data"))
DECISIONS_DIR = os.path.join(STORAGE_DIR, "decisions")


def load_expected(expected_path):
    """Load expected decisions from expected.jsonl."""
    decisions = []
    with open(expected_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            decisions.append(json.loads(line))
    return decisions


def load_extracted_decisions(storage_dir):
    """Load all extracted decisions from git storage branches."""
    import subprocess as sp

    decisions = []

    # Disable path quoting to handle Chinese characters
    sp.run(["git", "config", "core.quotepath", "false"], cwd=storage_dir, capture_output=True)

    # Get all decision branches
    result = sp.run(
        ["git", "branch", "--list", "decision/*"],
        cwd=storage_dir,
        capture_output=True,
        text=True,
    )
    branches = [b.strip().lstrip("* ") for b in result.stdout.strip().split("\n") if b.strip()]

    for branch in branches:
        try:
            result = sp.run(
                ["git", "ls-tree", "-r", "--name-only", branch, "--", "decisions/"],
                cwd=storage_dir,
                capture_output=True,
                text=True,
            )
            md_files = [f for f in result.stdout.strip().split("\n") if f.endswith(".md")]

            for fpath in md_files:
                result = sp.run(
                    ["git", "show", f"{branch}:{fpath}"],
                    cwd=storage_dir,
                    capture_output=True,
                    text=True,
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
                        for line in yaml_text.split("\n"):
                            if line.startswith("sid:"):
                                sid = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("summary:"):
                                summary = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("topic_id:"):
                                topic = line.split(":", 1)[1].strip().strip('"')
                        decisions.append({
                            "sid": sid,
                            "summary": summary,
                            "topic_id": topic,
                            "body": body,
                        })
        except Exception as e:
            print(f"  Warning: Failed to read branch {branch}: {e}")

    return decisions


def compute_similarity(text1, text2):
    """Character-level overlap similarity for Chinese text."""
    # Use character bigrams for better Chinese text matching
    def get_bigrams(text):
        text = text.lower()
        return set(text[i:i+2] for i in range(len(text)-1))

    b1 = get_bigrams(text1)
    b2 = get_bigrams(text2)
    if not b1 or not b2:
        return 0.0
    intersection = b1 & b2
    union = b1 | b2
    return len(intersection) / len(union)


def match_decision(extracted, expected_list, threshold=0.20):
    """Try to match an extracted decision to an expected one using summary + body similarity."""
    best_score = 0.0
    best_idx = -1
    # Combine summary and body for richer matching
    ext_summary = extracted.get("summary", "")
    ext_body = extracted.get("body", "")
    ext_text = (ext_summary + " " + ext_body).lower()
    for i, exp in enumerate(expected_list):
        exp_summary = exp.get("expected_summary", "")
        exp_topic = exp.get("expected_topic", "")
        # Check topic name overlap (Chinese topic -> LLM topic)
        topic_match = False
        if exp_topic and ext_summary:
            # Check if key Chinese topic words appear in the extracted text
            exp_topic_clean = exp_topic.lower()
            # Simple heuristic: if the topic words overlap significantly
            topic_match = any(w in ext_text for w in exp_topic_clean.replace(" ", ""))
        # Check summary similarity (may be English vs Chinese, use lower threshold)
        summary_sim = compute_similarity(ext_summary, exp_summary)
        # Also try matching extracted body against expected summary
        body_sim = compute_similarity(ext_body, exp_summary) if ext_body else 0
        # Take the best similarity score
        score = max(summary_sim, body_sim * 0.7)
        # Boost if topic matches
        if topic_match:
            score = min(1.0, score + 0.15)
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx, best_score


def evaluate(expected_list, extracted_list):
    """Evaluate extracted decisions against expected."""
    n_expected = len(expected_list)
    n_extracted = len(extracted_list)

    matched_expected = set()
    matched_extracted = set()

    results = []
    for i, ext in enumerate(extracted_list):
        exp_idx, score = match_decision(ext, expected_list)
        if exp_idx >= 0 and score >= 0.3:
            matched_expected.add(exp_idx)
            matched_extracted.add(i)
            results.append({
                "extracted": ext["summary"][:80],
                "expected": expected_list[exp_idx]["expected_summary"][:80],
                "topic_match": ext["topic_id"] == expected_list[exp_idx]["expected_topic"],
                "score": score,
                "status": "MATCH",
            })
        else:
            results.append({
                "extracted": ext["summary"][:80],
                "expected": "(no match)",
                "topic_match": False,
                "score": score,
                "status": "FALSE POSITIVE",
            })

    # Check for false negatives (expected but not extracted)
    for i, exp in enumerate(expected_list):
        if i not in matched_expected:
            results.append({
                "extracted": "(not extracted)",
                "expected": exp["expected_summary"][:80],
                "topic_match": False,
                "score": 0.0,
                "status": "FALSE NEGATIVE",
            })

    true_positives = len(matched_extracted)
    false_positives = n_extracted - true_positives
    false_negatives = n_expected - len(matched_expected)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "n_expected": n_expected,
        "n_extracted": n_extracted,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Run eval and evaluate extraction accuracy")
    parser.add_argument("--dataset", required=True, help="Dataset name (test_small, single_chat, multi_chat)")
    parser.add_argument("--base-dir", default=os.path.join(ROOT, "eval_dataset"), help="Eval dataset base dir")
    parser.add_argument("--converted-input", help="Path to converted test_data.txt (auto-detected if not provided)")
    args = parser.parse_args()

    dataset_dir = os.path.join(args.base_dir, args.dataset)
    messages_path = os.path.join(dataset_dir, "messages.jsonl")
    expected_path = os.path.join(dataset_dir, "expected.jsonl")

    if not os.path.exists(expected_path):
        print(f"Error: {expected_path} not found")
        sys.exit(1)

    # Determine converted input path
    if args.converted_input:
        converted_path = args.converted_input
    else:
        converted_path = os.path.join(ROOT, "eval_data", f"{args.dataset}_converted.jsonl")
        if not os.path.exists(converted_path):
            print(f"Error: Converted file not found at {converted_path}")
            print(f"Run: python scripts/convert_eval_dataset.py --dataset {args.dataset}")
            sys.exit(1)

    # Load expected decisions
    expected_list = load_expected(expected_path)
    print(f"=== Eval Accuracy Test: {args.dataset} ===")
    print(f"  Expected decisions: {len(expected_list)}")
    print(f"  Input: {converted_path}")

    # Clear storage dir for clean test
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)
    os.makedirs(STORAGE_DIR, exist_ok=True)

    # Count messages
    with open(converted_path, "r") as f:
        msg_count = sum(1 for line in f if line.strip())
    print(f"  Messages: {msg_count}")

    # Run eval
    print(f"\n  Running eval (model=qwen3-4B) ...")
    result = subprocess.run(
        [
            sys.executable,
            os.path.join(ROOT, "main.py"),
            "--eval",
            "--input", converted_path,
            "--delay", "0",
            "--group-num", "1",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        env={**os.environ, "STORAGE_PATH": STORAGE_DIR},
    )

    # Parse eval output
    output = result.stdout + result.stderr
    print(output[-2000:] if len(output) > 2000 else output)

    if result.returncode != 0:
        print(f"\n  Eval failed with return code {result.returncode}")
        sys.exit(1)

    # Load extracted decisions
    extracted_list = load_extracted_decisions(STORAGE_DIR)
    print(f"\n  Extracted decisions: {len(extracted_list)}")

    # Evaluate
    report = evaluate(expected_list, extracted_list)

    print(f"\n{'=' * 60}")
    print(f"  Accuracy Report: {args.dataset}")
    print(f"{'=' * 60}")
    print(f"  Expected:     {report['n_expected']}")
    print(f"  Extracted:    {report['n_extracted']}")
    print(f"  True Positive:{report['true_positives']}")
    print(f"  False Positive:{report['false_positives']}")
    print(f"  False Negative:{report['false_negatives']}")
    print(f"  Precision:    {report['precision']:.2%}")
    print(f"  Recall:       {report['recall']:.2%}")
    print(f"  F1 Score:     {report['f1']:.2%}")
    print(f"\n  Detail:")
    for r in report["results"]:
        status_icon = "✅" if r["status"] == "MATCH" else ("❌" if r["status"] == "FALSE NEGATIVE" else "⚠️")
        print(f"    {status_icon} [{r['status']}] (score={r['score']:.2f})")
        print(f"       Extracted: {r['extracted']}")
        print(f"       Expected:  {r['expected']}")

    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
