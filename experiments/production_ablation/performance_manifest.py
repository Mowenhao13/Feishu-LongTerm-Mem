from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.eval.confirmed_decision_eval import DatasetSelection

DOMAINS = (
    "ai_ml_platform",
    "backend_arch",
    "cloud_infra",
    "data_platform",
    "frontend_mobile",
    "sec_compliance",
    "sre_reliability",
)

FAILURE_TAGS: dict[str, tuple[str, ...]] = {
    chat_id: tuple(tag for tag in ("fp", "fn") if (index % 2 == 0 or tag == "fn"))
    for domain in DOMAINS
    for index, chat_id in enumerate(f"{domain}_channel_{i}" for i in range(10))
}
MANIFEST_VERSION = 1
SELECTION_RULE = (
    "Per domain, sort chats by (f1, chat_id); take positions [0:2] as low, [2:8] as middle, [8:10] as high; "
    "pick two low, one middle maximizing FAILURE_TAGS coverage, and two high chats for development; "
    "holdout is the remaining five chats."
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def _hash_payload(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("manifest_sha256", None)
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _chat_domain(chat_id: str) -> str:
    return chat_id.split("_channel_", 1)[0]


def _failure_labels(chat_id: str, row: Mapping[str, Any]) -> tuple[str, ...]:
    labels = row.get("failure_labels")
    if labels:
        return tuple(labels)
    return FAILURE_TAGS.get(chat_id, ())


def _select_dev_chats(rows: list[tuple[str, Mapping[str, Any]]]) -> tuple[list[str], list[str]]:
    sorted_rows = sorted(rows, key=lambda item: (float(item[1].get("f1", 0.0)), item[0]))
    if len(sorted_rows) != 10:
        raise ValueError("each domain must contain exactly 10 chats")
    low = sorted_rows[:2]
    middle = sorted_rows[2:8]
    high = sorted_rows[8:10]
    middle_choice = sorted(
        middle,
        key=lambda item: (-len(_failure_labels(item[0], item[1])), item[0]),
    )[0]
    dev = [chat_id for chat_id, _ in low] + [middle_choice[0]] + [chat_id for chat_id, _ in high]
    holdout = [chat_id for chat_id, _ in sorted_rows if chat_id not in dev]
    return dev, holdout


def build_manifests(baseline_aggregate: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    aggregate = _read_json(baseline_aggregate)
    per_chat = aggregate.get("per_chat")
    if not isinstance(per_chat, dict):
        raise ValueError("aggregate is missing per_chat")

    by_domain: dict[str, list[tuple[str, Mapping[str, Any]]]] = {domain: [] for domain in DOMAINS}
    for chat_id, row in per_chat.items():
        domain = _chat_domain(chat_id)
        if domain not in by_domain:
            raise ValueError(f"unexpected domain for chat {chat_id}")
        if not isinstance(row, Mapping):
            raise ValueError(f"invalid row for chat {chat_id}")
        by_domain[domain].append((chat_id, row))

    dev_chat_ids: list[str] = []
    holdout_chat_ids: list[str] = []

    for domain in DOMAINS:
        domain_rows = by_domain[domain]
        domain_dev, domain_holdout = _select_dev_chats(domain_rows)
        dev_chat_ids.extend(domain_dev)
        holdout_chat_ids.extend(domain_holdout)

    source_aggregate = str(baseline_aggregate)
    source_aggregate_sha256 = _source_hash(baseline_aggregate)

    def make_manifest(chat_ids: list[str]) -> dict[str, Any]:
        manifest = {
            "version": MANIFEST_VERSION,
            "source_aggregate": source_aggregate,
            "source_aggregate_sha256": source_aggregate_sha256,
            "selection_rule": SELECTION_RULE,
            "chat_ids": chat_ids,
            "domain_counts": {domain: sum(1 for chat_id in chat_ids if _chat_domain(chat_id) == domain) for domain in DOMAINS},
        }
        manifest["manifest_sha256"] = _hash_payload(manifest)
        return manifest

    return make_manifest(dev_chat_ids), make_manifest(holdout_chat_ids)


def validate_manifest(manifest: Mapping[str, object], dataset_dir: Path) -> None:
    required = {"version", "source_aggregate", "source_aggregate_sha256", "selection_rule", "chat_ids", "domain_counts", "manifest_sha256"}
    missing = required - set(manifest)
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if manifest["version"] != MANIFEST_VERSION:
        raise ValueError("unsupported manifest version")

    if not isinstance(manifest["chat_ids"], list):
        raise ValueError("chat_ids must be a list")
    if not isinstance(manifest["domain_counts"], dict):
        raise ValueError("domain_counts must be a mapping")

    expected_hash = _hash_payload(manifest)
    if manifest["manifest_sha256"] != expected_hash:
        raise ValueError("manifest hash mismatch")

    source_aggregate = Path(str(manifest["source_aggregate"]))
    if not source_aggregate.exists():
        raise ValueError("source aggregate missing")
    if manifest["source_aggregate_sha256"] != _source_hash(source_aggregate):
        raise ValueError("source aggregate hash mismatch")

    dataset = DatasetSelection.from_jsonl(dataset_dir)
    dataset_chat_ids = set(dataset.chat_ids)
    chat_ids = list(manifest["chat_ids"])
    if len(set(chat_ids)) != len(chat_ids):
        raise ValueError("duplicate chat ids")
    if len(chat_ids) != 35:
        raise ValueError("manifest must contain 35 chats")
    if any(chat_id not in dataset_chat_ids for chat_id in chat_ids):
        raise ValueError("manifest references chat missing from dataset")

    domain_counts = {str(domain): int(count) for domain, count in manifest["domain_counts"].items()}
    if set(domain_counts) != set(DOMAINS):
        raise ValueError("balanced domain coverage requires all domains")
    if any(domain_counts[domain] != 5 for domain in DOMAINS):
        raise ValueError("balanced domain coverage requires five chats per domain")
    for domain in DOMAINS:
        if sum(1 for chat_id in chat_ids if _chat_domain(chat_id) == domain) != domain_counts[domain]:
            raise ValueError("balanced domain coverage mismatch")


def _verify_pair(dev_path: Path, holdout_path: Path, dataset_dir: Path) -> None:
    dev = _read_json(dev_path)
    holdout = _read_json(holdout_path)
    dev_ids = set(dev["chat_ids"])
    holdout_ids = set(holdout["chat_ids"])
    if dev_ids & holdout_ids:
        raise ValueError("paired manifests overlap")
    validate_manifest(dev, dataset_dir)
    validate_manifest(holdout, dataset_dir)
    dataset = DatasetSelection.from_jsonl(dataset_dir)
    if dev_ids | holdout_ids != set(dataset.chat_ids):
        raise ValueError("paired manifests do not form an exact partition")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify performance manifests")
    parser.add_argument("--baseline", type=Path, default=Path("experiments/production_ablation/chunked_runs/full_70_adjudicate_20260807_s3/aggregate.json"))
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--write-dev", type=Path)
    parser.add_argument("--write-holdout", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--paired-holdout", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.verify is not None:
        validate_manifest(_read_json(args.verify), args.dataset)
        if args.paired_holdout is not None:
            _verify_pair(args.verify, args.paired_holdout, args.dataset)
        return 0

    dev, holdout = build_manifests(args.baseline)
    if args.write_dev is not None:
        _write_json(args.write_dev, dev)
    if args.write_holdout is not None:
        _write_json(args.write_holdout, holdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
