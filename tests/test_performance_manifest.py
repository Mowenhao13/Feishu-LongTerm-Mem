from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from experiments.production_ablation.performance_manifest import (
    DOMAINS,
    build_manifests,
    validate_manifest,
)


BASELINE_AGGREGATE = "experiments/production_ablation/chunked_runs/full_70_adjudicate_20260807_s3/aggregate.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _manifest_hash(payload: dict) -> str:
    body = deepcopy(payload)
    body.pop("manifest_sha256", None)
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _make_dataset(root: Path, chat_ids: list[str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    messages = [
        {"chat_id": chat_id, "msg_id": f"{chat_id}_msg_1", "msg": f"message for {chat_id}"}
        for chat_id in chat_ids
    ]
    expected = [
        {"chat_id": chat_id, "msg_id": f"{chat_id}_msg_1", "title": f"title for {chat_id}"}
        for chat_id in chat_ids
    ]
    _write_jsonl(root / "messages.jsonl", messages)
    _write_jsonl(root / "expected.jsonl", expected)
    return root


def _make_aggregate(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    per_chat: dict[str, dict[str, object]] = {}
    for domain_index, domain in enumerate(DOMAINS):
        for chat_index in range(10):
            chat_id = f"{domain}_channel_{chat_index:02d}"
            per_chat[chat_id] = {
                "domain": domain,
                "f1": 0.5,
                "failure_labels": [f"{domain_index}:{chat_index}"],
            }
    aggregate = {
        "job_id": "synthetic",
        "variant": "full",
        "chunks": 1,
        "completed_chunks": 1,
        "failed_chunks": 0,
        "failures": [],
        "totals": {},
        "metrics": {"precision": 0.5, "recall": 0.5, "f1": 0.5},
        "macro": {},
        "per_chat": per_chat,
        "health": {"all_complete": True},
    }
    path = root / "aggregate.json"
    _write_json(path, aggregate)
    return path


def test_build_manifests_creates_balanced_and_reproducible_35_chat_halves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dataset_dir = _make_dataset(tmp_path / "dataset", [f"{domain}_channel_{i:02d}" for domain in DOMAINS for i in range(10)])
    aggregate_path = _make_aggregate(tmp_path / "baseline")
    monkeypatch.setattr(
        "experiments.production_ablation.performance_manifest.FAILURE_TAGS",
        {f"{domain}_channel_{i:02d}": ("tag_a", "tag_b") if i == 3 else ("tag_a",) for domain in DOMAINS for i in range(10)},
        raising=False,
    )

    dev, holdout = build_manifests(aggregate_path)
    dev_again, holdout_again = build_manifests(aggregate_path)

    assert (dev, holdout) == (dev_again, holdout_again)
    assert len(dev["chat_ids"]) == len(holdout["chat_ids"]) == 35
    assert dev["domain_counts"] == {domain: 5 for domain in DOMAINS}
    assert holdout["domain_counts"] == {domain: 5 for domain in DOMAINS}
    assert not set(dev["chat_ids"]) & set(holdout["chat_ids"])
    assert set(dev["chat_ids"]) | set(holdout["chat_ids"]) == {f"{domain}_channel_{i:02d}" for domain in DOMAINS for i in range(10)}
    assert dev["source_aggregate"] == str(aggregate_path)
    assert holdout["source_aggregate"] == str(aggregate_path)
    assert validate_manifest(dev, dataset_dir) is None
    assert validate_manifest(holdout, dataset_dir) is None


@pytest.mark.parametrize(
    "mutator, expected_error, recompute_hash",
    [
        (
            lambda manifest: manifest.__setitem__("chat_ids", manifest["chat_ids"] + [manifest["chat_ids"][0]]),
            "duplicate",
            True,
        ),
        (
            lambda manifest: manifest.__setitem__("manifest_sha256", "0" * 64),
            "hash",
            False,
        ),
        (
            lambda manifest: manifest.__setitem__("domain_counts", {domain: 4 for domain in DOMAINS}),
            "balanced",
            True,
        ),
        (
            lambda manifest: manifest.__setitem__("chat_ids", manifest["chat_ids"][:-1] + ["missing_chat_id"]),
            "dataset",
            True,
        ),
    ],
)
def test_validate_manifest_rejects_invalid_payloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_error: str, recompute_hash: bool):
    dataset_dir = _make_dataset(tmp_path / "dataset", [f"{domain}_channel_{i:02d}" for domain in DOMAINS for i in range(10)])
    aggregate_path = _make_aggregate(tmp_path / "baseline")
    monkeypatch.setattr(
        "experiments.production_ablation.performance_manifest.FAILURE_TAGS",
        {f"{domain}_channel_{i:02d}": ("tag_a",) for domain in DOMAINS for i in range(10)},
        raising=False,
    )
    manifest, _ = build_manifests(aggregate_path)
    mutator(manifest)
    if recompute_hash:
        manifest["manifest_sha256"] = _manifest_hash(manifest)

    with pytest.raises(ValueError, match=expected_error):
        validate_manifest(manifest, dataset_dir)


def test_cli_verify_rejects_overlapping_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dataset_dir = _make_dataset(tmp_path / "dataset", [f"{domain}_channel_{i:02d}" for domain in DOMAINS for i in range(10)])
    aggregate_path = _make_aggregate(tmp_path / "baseline")
    monkeypatch.setattr(
        "experiments.production_ablation.performance_manifest.FAILURE_TAGS",
        {f"{domain}_channel_{i:02d}": ("tag_a",) for domain in DOMAINS for i in range(10)},
        raising=False,
    )
    dev, holdout = build_manifests(aggregate_path)
    holdout["chat_ids"] = holdout["chat_ids"][:-1] + [dev["chat_ids"][0]]
    holdout["domain_counts"] = {domain: 5 for domain in DOMAINS}
    holdout["manifest_sha256"] = _manifest_hash(holdout)

    dev_path = tmp_path / "dev.json"
    holdout_path = tmp_path / "holdout.json"
    _write_json(dev_path, dev)
    _write_json(holdout_path, holdout)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "experiments.production_ablation.performance_manifest",
            "--verify",
            str(dev_path),
            "--paired-holdout",
            str(holdout_path),
            "--dataset",
            str(dataset_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "overlap" in (result.stderr + result.stdout).lower()
