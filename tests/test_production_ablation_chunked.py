from experiments.production_ablation.chunked import merge_chunk_reports, split_chunks

def test_split_chunks_preserves_order():
    assert split_chunks(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]

def _report(chat_id, tp, fp, fn):
    return {
        "metadata": {"run_id": chat_id},
        "metrics": {"strict_tp": tp, "strict_fp": fp, "strict_fn": fn, "valid_extra": 1, "invalid": fp, "evidence_valid": tp + fp, "evidence_invalid": 0, "incomplete": False},
        "runner_errors": [],
        "chat_metrics": {chat_id: {"expected": tp + fn, "tp": tp, "fp": fp, "fn": fn, "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0, "f1": 0.5}},
    }

def test_merge_chunk_reports_sums_micro_and_keeps_macro():
    result = merge_chunk_reports([_report("a", 1, 1, 0), _report("b", 2, 0, 1)], [], "full", "job-1")
    assert result["metrics"]["strict_tp"] == 3
    assert result["metrics"]["strict_fp"] == 1
    assert result["metrics"]["strict_fn"] == 1
    assert result["metrics"]["precision"] == 0.75
    assert result["metrics"]["recall"] == 0.75
    assert result["health"]["all_complete"]
    assert set(result["per_chat"]) == {"a", "b"}

def test_merge_chunk_reports_marks_timeout_incomplete():
    result = merge_chunk_reports([_report("a", 1, 0, 0)], [{"index": 1, "status": "timeout"}], "full", "job-2")
    assert result["failed_chunks"] == 1
    assert not result["health"]["all_complete"]
    assert result["metrics"]["incomplete"]
