from experiments.production_ablation.repeat import aggregate_reports


def _report(tp, f1, incomplete=False, evidence_invalid=0, errors=None):
    return {
        "metadata": {"run_id": str(tp)},
        "metrics": {"strict_tp": tp, "strict_fp": 1, "strict_fn": 2, "valid_extra": 0, "invalid": 1, "evidence_valid": 3, "evidence_invalid": evidence_invalid, "precision": 0.5, "recall": 0.6, "f1": f1, "incomplete": incomplete},
        "runner_errors": errors or [],
    }

def test_aggregate_reports_keeps_variance_and_health():
    result = aggregate_reports([_report(2, 0.4), _report(4, 0.8)])
    assert result["runs"] == 2
    assert result["complete_runs"] == 2
    assert result["health"]["all_complete"]
    assert result["health"]["evidence_contract_pass_rate"] == 1.0
    assert result["numeric"]["strict_tp"]["mean"] == 3.0
    assert result["numeric"]["strict_tp"]["min"] == 2.0
    assert result["numeric"]["strict_tp"]["max"] == 4.0
    assert result["numeric"]["f1"]["stddev"] > 0

def test_aggregate_reports_does_not_hide_incomplete_runs():
    result = aggregate_reports([_report(2, 0.4), _report(0, 0.0, incomplete=True, evidence_invalid=1, errors=["provider"] )])
    assert result["complete_runs"] == 1
    assert result["incomplete_runs"] == 1
    assert not result["health"]["all_complete"]
    assert result["health"]["evidence_contract_pass_rate"] == 0.5
    assert result["health"]["runner_error_free_rate"] == 0.5
