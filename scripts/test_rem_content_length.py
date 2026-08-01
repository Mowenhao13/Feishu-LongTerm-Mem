#!/usr/bin/env python3
"""测试不同 content 长度对 REM Sleep FP 识别准确率的影响"""
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STORAGE_DIR = str(ROOT / "mem-data")
CONTENT_LENGTHS = [200, 400, 600, 800]
DATASETS = ["single_chat", "multi_chat"]


def load_expected(dataset):
    path = ROOT / "eval_dataset" / dataset / "expected.jsonl"
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_extracted(storage_dir):
    """从 git storage 加载提取的决策"""
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
                        sid = summary = topic = status = ""
                        confidence = 0.85
                        for line in yaml_text.split("\n"):
                            if line.startswith("sid:"):
                                sid = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("summary:"):
                                summary = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("topic_id:"):
                                topic = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("status:"):
                                status = line.split(":", 1)[1].strip().strip('"')
                            elif line.startswith("confidence:"):
                                try:
                                    confidence = float(line.split(":", 1)[1].strip())
                                except ValueError:
                                    pass
                        decisions.append({
                            "sid": sid, "summary": summary,
                            "topic_id": topic, "status": status,
                            "body": body, "confidence": confidence,
                        })
        except Exception:
            pass
    return decisions


def compute_similarity(text1, text2):
    def get_bigrams(text):
        text = text.lower()
        return set(text[i:i+2] for i in range(len(text)-1))
    b1, b2 = get_bigrams(text1), get_bigrams(text2)
    if not b1 or not b2:
        return 0.0
    return len(b1 & b2) / len(b1 | b2)


def match_extracted_to_expected(extracted_list, expected_list):
    """Map each extracted decision to best matching expected (or None)"""
    matches = {}
    matched_expected = set()
    for i, ext in enumerate(extracted_list):
        ext_summary = ext.get("summary", "")
        ext_body = ext.get("body", "")
        ext_text = (ext_summary + " " + ext_body).lower()
        best_score, best_j = 0.0, -1
        for j, exp in enumerate(expected_list):
            if j in matched_expected:
                continue
            exp_summary = exp.get("expected_summary", "")
            exp_topic = exp.get("expected_topic", "")
            summary_sim = compute_similarity(ext_summary, exp_summary)
            body_sim = compute_similarity(ext_body, exp_summary) if ext_body else 0
            score = max(summary_sim, body_sim * 0.7)
            if exp_topic and ext_summary:
                if any(w in ext_text for w in exp_topic.lower().replace(" ", "")):
                    score = min(1.0, score + 0.15)
            if score > best_score:
                best_score, best_j = score, j
        if best_score >= 0.3:
            matched_expected.add(best_j)
            matches[ext["sid"]] = {"expected_idx": best_j, "is_tp": True, "score": best_score}
        else:
            matches[ext["sid"]] = {"expected_idx": None, "is_tp": False, "score": best_score}
    return matches


def run_test_for_length(dataset, sm, decisions, expected_list, content_len, matches):
    """Test REM accuracy for a specific content_len"""
    # Get graph decisions (DecisionNode objects)
    graph_decisions = sm._graph.get_all_decisions()
    
    # Debug: count active decisions with confidence < 0.8
    low_conf = [d for d in graph_decisions if d.status.is_active() and d.confidence < 0.8]
    high_conf = [d for d in graph_decisions if d.status.is_active() and d.confidence >= 0.8]
    if content_len == 200:
        print(f"  [Debug] active={len(low_conf)+len(high_conf)}, <0.8={len(low_conf)}, >=0.8={len(high_conf)}")
    
    # Map by sid for lookup
    dec_map = {d.sid: d for d in graph_decisions}
    
    # Call _batch_fp_judge with custom content_len
    judgments = sm._batch_fp_judge(graph_decisions, content_len=content_len)
    
    if content_len == 200:
        print(f"  [Debug] raw judgments: {len(judgments)} total, {sum(1 for j in judgments if j[1]=='shelve')} shelve, {sum(1 for j in judgments if j[1]=='keep')} keep")
        if judgments:
            for j in judgments[:3]:
                print(f"    sid={j[0][:10]} action={j[1]} reason={j[2][:50]}")
    
    if not judgments:
        return {"content_len": content_len, "dataset": dataset, "shelved": 0, "correct_fp": 0, "wrong_shelve": 0, "accuracy": None, "skipped": True}
    
    # For each shelved decision, check if it's truly FP
    correct_shelve = 0  # REM said shelve AND it was actually FP
    wrong_shelve = 0     # REM said shelve BUT it was actually TP
    shelved_total = 0
    
    for sid, action, reason in judgments:
        if action != "shelve":
            continue
        shelved_total += 1
        match = matches.get(sid, {"is_tp": False})
        if match["is_tp"]:
            # REM shelved a correct decision — bad
            wrong_shelve += 1
        else:
            # REM correctly identified an FP
            correct_shelve += 1
    
    accuracy = correct_shelve / shelved_total if shelved_total > 0 else None
    
    return {
        "content_len": content_len,
        "dataset": dataset,
        "shelved": shelved_total,
        "correct_fp": correct_shelve,
        "wrong_shelve": wrong_shelve,
        "accuracy": accuracy,
        "skipped": False,
    }


def main():
    os.environ["STORAGE_PATH"] = STORAGE_DIR
    
    # Build LLM provider
    from src.model.llm_provider import LLMProvider as DirectLLM
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        print("Error: No API_KEY in .env")
        sys.exit(1)
    llm = DirectLLM(
        provider_type="openai",
        base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
        api_key=api_key,
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
    )
    
    all_results = []
    
    for dataset in DATASETS:
        print(f"\n{'='*80}")
        print(f"  Dataset: {dataset}")
        print(f"{'='*80}")
        
        # Clean and run eval
        if os.path.exists(STORAGE_DIR):
            shutil.rmtree(STORAGE_DIR)
        
        print(f"  Running eval...")
        subprocess.run(
            ["uv", "run", "python3", "scripts/run_eval_accuracy.py", "--dataset", dataset],
            cwd=ROOT, check=False, capture_output=True,
            env={**os.environ, "STORAGE_PATH": STORAGE_DIR},
        )
        
        # Load data
        expected_list = load_expected(dataset)
        extracted_list = load_extracted(STORAGE_DIR)
        matches = match_extracted_to_expected(extracted_list, expected_list)
        
        all_fp = [e for e in extracted_list if not matches[e["sid"]]["is_tp"]]
        all_tp = [e for e in extracted_list if matches[e["sid"]]["is_tp"]]
        print(f"  Total extracted: {len(extracted_list)}, TP: {len(all_tp)}, FP: {len(all_fp)}")
        
        # Debug: show confidence distribution
        confs = [e.get("confidence", 0.85) for e in extracted_list]
        below_8 = sum(1 for c in confs if c < 0.8)
        between = sum(1 for c in confs if 0.8 <= c < 0.85)
        above_85 = sum(1 for c in confs if c >= 0.85)
        print(f"  Confidence dist: <0.8={below_8}, 0.8-0.85={between}, >=0.85={above_85}")
        if confs:
            print(f"  Confidence range: {min(confs):.3f} ~ {max(confs):.3f}")
        
        # Initialize engine to load decisions into graph
        from src.core.engine import MemoryEngine
        from src.memory.sleep import SleepManager
        engine = MemoryEngine()
        engine.initialize()
        sm = SleepManager(
            graph=engine._graph,
            pipeline=engine._pipeline,
            storage=engine._storage,
            llm_provider=llm,
        )
        
        graph_decisions = engine._graph.get_all_decisions()
        print(f"  Graph decisions: {len(graph_decisions)}")
        
        # Test each content length
        print(f"  Testing content lengths: {CONTENT_LENGTHS}")
        for cl in CONTENT_LENGTHS:
            result = run_test_for_length(dataset, sm, graph_decisions, expected_list, cl, matches)
            all_results.append(result)
            
            if result["skipped"]:
                print(f"    len={cl:>4}: skipped (no low-confidence decisions)")
            else:
                acc_str = f"{result['accuracy']*100:.0f}%" if result['accuracy'] is not None else "N/A"
                print(f"    len={cl:>4}: shelved={result['shelved']:>2}, "
                      f"correct={result['correct_fp']:>2}, "
                      f"wrong={result['wrong_shelve']:>2}, "
                      f"acc={acc_str}")
    
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"  {'dataset':<14} {'len':>5} {'shelved':>8} {'correct':>8} {'wrong':>8} {'accuracy':>10}")
    print(f"  {'-'*53}")
    for r in all_results:
        acc = f"{r['accuracy']*100:.0f}%" if r['accuracy'] is not None else ("skip" if r['skipped'] else "N/A")
        print(f"  {r['dataset']:<14} {r['content_len']:>5} {r['shelved']:>8} {r['correct_fp']:>8} {r['wrong_shelve']:>8} {acc:>10}")
    
    # Save report
    out_path = ROOT / "eval_reports" / "rem_content_len_test.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved to {out_path}")


if __name__ == "__main__":
    main()