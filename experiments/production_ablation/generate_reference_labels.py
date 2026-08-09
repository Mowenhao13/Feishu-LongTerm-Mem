from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments.production_ablation.calibrate_evaluator import load_final_outputs
from experiments.production_ablation.performance_manifest import DOMAINS
from src.config import ModelConfig
from src.eval.confirmed_decision_eval import (
    DatasetSelection,
    EvidenceDecision,
    GlobalAdjudicationGroup,
    build_global_adjudication_groups,
)
from src.eval.reference_decision_adjudicator import (
    ReferenceAssignmentRow,
    ReferenceChatAssignment,
    ReferenceDecisionAdjudicator,
)
from src.model.openai_provider import OpenAIProvider


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_stable_json(payload), encoding="utf-8")


def _tmp_path(path: Path) -> Path:
    suffix = path.suffix + ".tmp" if path.suffix else ".tmp"
    return path.with_suffix(suffix)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_reports_root(reports_root: Path) -> str:
    digest = hashlib.sha256()
    for report_path in sorted(reports_root.glob("chunk_*/report.json")):
        if report_path.is_file():
            digest.update(report_path.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(report_path.read_bytes())
    return digest.hexdigest()


def _manifest_chat_ids(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    chat_ids = manifest.get("chat_ids", [])
    if not isinstance(chat_ids, list) or not all(isinstance(chat_id, str) for chat_id in chat_ids):
        raise ValueError("manifest chat_ids must be a list of strings")
    return tuple(chat_ids)


def _required_output_fields() -> tuple[str, ...]:
    return ("chat_id", "title", "summary", "source_message_ids", "evidence_quote")


def _normalize_output_row(row: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in _required_output_fields() if field not in row]
    if missing:
        raise ValueError(f"missing output fields: {missing}")
    source_message_ids = row.get("source_message_ids")
    if not isinstance(source_message_ids, (list, tuple)) or not all(isinstance(item, str) for item in source_message_ids):
        raise ValueError("source_message_ids must be a list of strings")
    chat_id = str(row["chat_id"]).strip()
    title = str(row["title"]).strip()
    summary = str(row["summary"]).strip()
    evidence_quote = str(row["evidence_quote"]).strip()
    if not chat_id or not title or not summary or not evidence_quote:
        raise ValueError("output row missing required text fields")
    return {
        "chat_id": chat_id,
        "title": title,
        "summary": summary,
        "status": str(row.get("status", "decided")),
        "is_suggestion": bool(row.get("is_suggestion", False)),
        "source_message_ids": [str(item) for item in source_message_ids],
        "evidence_quote": evidence_quote,
        "_chunk": str(row.get("_chunk", "")),
        "adjudication": str(row.get("adjudication", "")),
        "matched_msg_id": str(row.get("matched_msg_id", "")),
        "reason": str(row.get("reason", "")),
    }


def load_dev_outputs(reports_root: Path, manifest_path: Path) -> list[dict[str, Any]]:
    manifest = _read_json(manifest_path)
    allowed_chat_ids = set(_manifest_chat_ids(manifest))
    outputs: list[dict[str, Any]] = []
    for row in load_final_outputs(reports_root):
        if row.get("chat_id") not in allowed_chat_ids:
            continue
        outputs.append(_normalize_output_row(row))
    return outputs


def _group_outputs_by_chat(
    outputs: Sequence[Mapping[str, Any]],
    chat_order: Sequence[str],
) -> tuple[dict[str, tuple[dict[str, Any], ...]], list[dict[str, Any]]]:
    by_chat: dict[str, list[dict[str, Any]]] = {chat_id: [] for chat_id in chat_order}
    filtered: list[dict[str, Any]] = []
    for row in outputs:
        chat_id = str(row.get("chat_id", ""))
        if chat_id not in by_chat:
            continue
        normalized = dict(row)
        by_chat[chat_id].append(normalized)
        filtered.append(normalized)
    return {chat_id: tuple(rows) for chat_id, rows in by_chat.items()}, filtered


def _state_signature(
    *,
    manifest_sha256: str,
    source_reports_sha256: str,
    dataset_hash: str,
    reference_model: str,
    repeats: int,
    selected_chat_ids: Sequence[str],
) -> dict[str, Any]:
    return {
        "label_source": "independent_llm",
        "manifest_sha256": manifest_sha256,
        "source_reports_sha256": source_reports_sha256,
        "dataset_hash": dataset_hash,
        "reference_model": reference_model,
        "reference_prompt_version": ReferenceDecisionAdjudicator.PROMPT_VERSION,
        "reference_schema_version": ReferenceDecisionAdjudicator.SCHEMA_VERSION,
        "repeats": repeats,
        "selected_chat_ids": list(selected_chat_ids),
    }


def _load_generation_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        state = _read_json(path)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    if state.get("label_source") != "independent_llm":
        return None
    return state


def _state_matches(state: Mapping[str, Any], signature: Mapping[str, Any]) -> bool:
    for key, value in signature.items():
        if state.get(key) != value:
            return False
    return True


def _write_generation_state(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _tmp_path(path)
    tmp_path.write_text(_stable_json(payload), encoding="utf-8")
    tmp_path.replace(path)


def output_identity(output: EvidenceDecision) -> str:
    payload = {
        "chat_id": output.chat_id,
        "title": output.title,
        "summary": output.summary,
        "status": output.status,
        "is_suggestion": output.is_suggestion,
        "source_message_ids": list(output.source_message_ids),
        "evidence_quote": output.evidence_quote,
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _coverage_from_rows(
    rows: Sequence[Mapping[str, Any]],
    source_outputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    class_counts = Counter(str(row.get("classification", "")) for row in rows)
    domain_counts = Counter(
        str(row.get("chat_id", "")).split("_channel_", 1)[0]
        for row in rows
        if str(row.get("chat_id", "")).count("_channel_") >= 1
    )
    slice_counts = Counter()
    for row in source_outputs:
        reason = str(row.get("reason", "")).lower()
        if "lexical overlap" in reason:
            slice_counts["lexical_veto"] += 1
        if "unknown" in reason and "gt" in reason:
            slice_counts["unknown_gt"] += 1
    coverage = {
        "classes": {key: class_counts.get(key, 0) for key in ("match_gt", "valid_extra", "invalid")},
        "domains": {domain: domain_counts.get(domain, 0) for domain in DOMAINS},
        "failure_slices": {
            "lexical_veto": slice_counts.get("lexical_veto", 0),
            "unknown_gt": slice_counts.get("unknown_gt", 0),
        },
    }
    coverage["ready"] = (
        all(count > 0 for count in coverage["classes"].values())
        and all(count > 0 for count in coverage["domains"].values())
        and all(count > 0 for count in coverage["failure_slices"].values())
        and len(rows) == len({row["output_normalized"] for row in rows})
    )
    return coverage


def build_groups(
    outputs: Sequence[Mapping[str, Any]],
    selection: DatasetSelection,
) -> tuple[GlobalAdjudicationGroup, ...]:
    decisions = [
        EvidenceDecision(
            chat_id=str(row["chat_id"]),
            title=str(row["title"]),
            summary=str(row["summary"]),
            status=str(row.get("status", "decided")),
            is_suggestion=bool(row.get("is_suggestion", False)),
            source_message_ids=tuple(str(item) for item in row.get("source_message_ids", ())),
            evidence_quote=str(row["evidence_quote"]),
        )
        for row in outputs
        if row.get("chat_id") in selection.chat_ids
    ]
    return build_global_adjudication_groups(decisions, selection)


def stabilize_assignments(
    runs: Sequence[Mapping[str, Mapping[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve repeat assignments via majority vote.

    Unanimous agreement (3/3) is preferred. When repeats disagree, the
    classification chosen by the strict majority wins. If no majority
    exists (e.g. three-way tie), the row is unresolved.

    Each stable row records ``repeat_agreement`` (fraction of repeats
    that matched the chosen classification) so downstream calibration
    can weight or filter by confidence.
    """
    all_keys = sorted({key for run in runs for key in run})
    stable_rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    n_runs = len(runs)

    for key in all_keys:
        entries = [run.get(key) for run in runs]
        if any(entry is None for entry in entries):
            unresolved.append({"output_normalized": key, "reason": "repeat_disagreement"})
            continue

        valid_entries = [e for e in entries if str(e.get("classification", "")) != "unresolved"]
        if not valid_entries:
            unresolved.append({"output_normalized": key, "reason": "repeat_disagreement"})
            continue

        cls_counter = Counter(str(e.get("classification", "")) for e in valid_entries)
        majority_cls, majority_count = cls_counter.most_common(1)[0]

        if majority_count <= n_runs // 2:
            # No strict majority (e.g. 3-way tie with 3 repeats)
            unresolved.append({"output_normalized": key, "reason": "repeat_disagreement"})
            continue

        # Pick the first entry whose classification matches the majority
        winner = next(e for e in valid_entries if str(e.get("classification", "")) == majority_cls)
        row = dict(winner, output_normalized=key)
        row["repeat_agreement"] = round(majority_count / n_runs, 4)
        stable_rows.append(row)

    return stable_rows, unresolved


def validate_reference_artifact(artifact: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    if artifact.get("label_source") != "independent_llm":
        raise ValueError("label_source must be independent_llm")
    if not artifact.get("reference_model"):
        raise ValueError("reference_model missing")
    if not artifact.get("reference_prompt_version"):
        raise ValueError("reference_prompt_version missing")
    if not artifact.get("reference_schema_version"):
        raise ValueError("reference_schema_version missing")
    if not artifact.get("manifest_sha256"):
        raise ValueError("manifest_sha256 missing")
    if not artifact.get("source_reports_sha256"):
        raise ValueError("source_reports_sha256 missing")
    if not artifact.get("dataset_hash"):
        raise ValueError("dataset_hash missing")

    rows = list(artifact.get("rows", []))
    unresolved = list(artifact.get("unresolved", []))
    expected = int(artifact.get("expected_output_count", 0))
    if expected <= 0:
        raise ValueError("expected_output_count must be positive")
    if len(rows) + len(unresolved) != expected:
        raise ValueError("expected_output_count mismatch")

    identities = [str(row.get("output_normalized", "")) for row in rows]
    unresolved_ids = [str(row.get("output_normalized", "")) for row in unresolved]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate stable output identities")
    if len(set(unresolved_ids)) != len(unresolved_ids):
        raise ValueError("duplicate unresolved output identities")
    if set(identities) & set(unresolved_ids):
        raise ValueError("stable and unresolved outputs overlap")
    if unresolved:
        raise ValueError("unresolved rows block readiness")

    classes = artifact.get("coverage", {}).get("classes", {})
    domains = artifact.get("coverage", {}).get("domains", {})
    failure_slices = artifact.get("coverage", {}).get("failure_slices", {})
    if set(classes) != {"match_gt", "valid_extra", "invalid"}:
        raise ValueError("missing classes coverage")
    if set(domains) != set(DOMAINS):
        raise ValueError("missing domain coverage")
    if set(failure_slices) != {"lexical_veto", "unknown_gt"}:
        raise ValueError("missing failure slice coverage")
    if any(int(value) <= 0 for value in classes.values()):
        raise ValueError("classes coverage incomplete")
    if any(int(value) <= 0 for value in domains.values()):
        raise ValueError("domains coverage incomplete")
    if any(int(value) <= 0 for value in failure_slices.values()):
        raise ValueError("failure slices coverage incomplete")
    if not artifact.get("coverage", {}).get("ready", False):
        raise ValueError("coverage not ready")

    manifest_chat_ids = _manifest_chat_ids(manifest)
    selected_chat_ids = artifact.get("selected_chat_ids", [])
    if tuple(selected_chat_ids) != manifest_chat_ids:
        raise ValueError("selected chat ids do not match manifest")


def build_reference_provider() -> OpenAIProvider:
    ModelConfig.validate_reference_model()
    config = ModelConfig.reference_llm_config
    return OpenAIProvider(
        model=str(config["model"]),
        base_url=str(config["base_url"]),
        api_key=str(config["api_key"]),
        temperature=float(config["temperature"]),
        max_tokens=int(config["max_tokens"]),
        enable_stats=False,
    )


async def generate_reference_labels(
    reports_root: Path,
    dataset_dir: Path,
    manifest_path: Path,
    repeats: int = 3,
    max_concurrency: int = 8,
    progress_path: Path | None = None,
    adjudicator: ReferenceDecisionAdjudicator | None = None,
) -> dict[str, Any]:
    ModelConfig.validate_reference_model()
    manifest = _read_json(manifest_path)
    chat_ids = _manifest_chat_ids(manifest)
    selection = DatasetSelection.from_jsonl(dataset_dir, chat_ids=chat_ids)
    outputs = load_dev_outputs(reports_root, manifest_path)
    _, filtered_outputs = _group_outputs_by_chat(outputs, chat_ids)
    groups = build_groups(filtered_outputs, selection)

    provider = build_reference_provider() if adjudicator is None else None
    reference_adjudicator = adjudicator or ReferenceDecisionAdjudicator(provider)

    repeat_runs: list[dict[str, Mapping[str, Any]]] = []
    repeat_details: list[dict[str, Any]] = []

    reference_config = ModelConfig.reference_model_config()
    source_reports_sha256 = _hash_reports_root(reports_root)
    manifest_sha256 = _hash_file(manifest_path)
    signature = _state_signature(
        manifest_sha256=manifest_sha256,
        source_reports_sha256=source_reports_sha256,
        dataset_hash=selection.dataset_hash,
        reference_model=str(reference_config["model"]),
        repeats=repeats,
        selected_chat_ids=chat_ids,
    )

    if progress_path is not None:
        existing_state = _load_generation_state(progress_path)
        if existing_state is not None and _state_matches(existing_state, signature):
            artifact_state = existing_state.get("artifact")
            if isinstance(artifact_state, Mapping):
                try:
                    validate_reference_artifact(artifact_state, manifest)
                except Exception:
                    artifact_state = None
                else:
                    return dict(artifact_state)

            loaded_runs = existing_state.get("repeat_runs", [])
            loaded_details = existing_state.get("repeat_details", [])
            if (
                isinstance(loaded_runs, list)
                and isinstance(loaded_details, list)
                and len(loaded_runs) == len(loaded_details)
                and len(loaded_runs) < repeats
                and all(isinstance(detail, Mapping) and detail.get("complete") is True for detail in loaded_details)
            ):
                repeat_runs = [dict(run) if isinstance(run, Mapping) else {} for run in loaded_runs]
                repeat_details = [dict(detail) if isinstance(detail, Mapping) else {} for detail in loaded_details]

    concurrency = max(1, min(max_concurrency, len(groups)))

    async def _adjudicate_group(group: GlobalAdjudicationGroup) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        assignment = await reference_adjudicator.adjudicate_chat(group)
        rows_by_index = {row.output_index: row for row in assignment.rows}
        group_rows: list[dict[str, Any]] = []
        for output_index, output in enumerate(group.outputs):
            row = rows_by_index[output_index]
            key = output_identity(output)
            group_rows.append(
                {
                    "output_normalized": key,
                    "chat_id": output.chat_id,
                    "classification": row.classification,
                    "matched_msg_id": row.matched_msg_id,
                    "decision_kind": row.decision_kind,
                    "core_equivalent": row.core_equivalent,
                    "polarity_compatible": row.polarity_compatible,
                    "commitment_compatible": row.commitment_compatible,
                    "material_qualifier_conflict": row.material_qualifier_conflict,
                    "confidence": row.confidence,
                    "rationale": row.rationale,
                }
            )
        return group.chat_id, group_rows, {
            "chat_id": group.chat_id,
            "input_hash": assignment.input_hash,
            "row_count": len(assignment.rows),
        }

    for repeat_index in range(len(repeat_runs), repeats):
        repeat_map: dict[str, Mapping[str, Any]] = {}
        repeat_error = False
        group_details: list[dict[str, Any]] = []

        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded(group: GlobalAdjudicationGroup):
            async with semaphore:
                return await _adjudicate_group(group)

        tasks = [asyncio.create_task(_bounded(group)) for group in groups]
        completed_groups = 0
        for task in asyncio.as_completed(tasks):
            try:
                chat_id, rows, detail = await task
                group_details.append(detail)
                for row in rows:
                    repeat_map[row["output_normalized"]] = row
                completed_groups += 1
                if progress_path is not None:
                    _write_generation_state(
                        progress_path,
                        {
                            **signature,
                            "repeat_index": repeat_index + 1,
                            "repeats": repeats,
                            "completed_groups": completed_groups,
                            "total_groups": len(groups),
                            "completed_rows": len(repeat_map),
                            "last_chat_id": chat_id,
                            "concurrency": concurrency,
                            "repeat_runs": repeat_runs + [repeat_map],
                            "repeat_details": repeat_details + [
                                {
                                    "repeat_index": repeat_index + 1,
                                    "complete": not repeat_error,
                                    "group_details": sorted(group_details, key=lambda item: item.get("chat_id", "")),
                                    "row_count": len(repeat_map),
                                    "concurrency": concurrency,
                                }
                            ],
                        },
                    )
            except Exception as exc:
                repeat_error = True
                group_details.append({"error": f"{exc.__class__.__name__}: {exc}"})

        repeat_runs.append(repeat_map)
        repeat_details.append(
            {
                "repeat_index": repeat_index + 1,
                "complete": not repeat_error,
                "group_details": sorted(group_details, key=lambda item: item.get("chat_id", "")),
                "row_count": len(repeat_map),
                "concurrency": concurrency,
            }
        )
        if progress_path is not None:
            _write_generation_state(
                progress_path,
                {
                    **signature,
                    "repeat_index": repeat_index + 1,
                    "repeats": repeats,
                    "completed_groups": len(groups),
                    "total_groups": len(groups),
                    "completed_rows": len(repeat_map),
                    "complete": not repeat_error,
                    "concurrency": concurrency,
                    "repeat_runs": repeat_runs,
                    "repeat_details": repeat_details,
                },
            )

    stable_rows, unresolved = stabilize_assignments(repeat_runs)
    coverage = _coverage_from_rows(stable_rows, outputs)

    artifact: dict[str, Any] = {
        "label_source": "independent_llm",
        "reference_model": str(reference_config["model"]),
        "reference_prompt_version": ReferenceDecisionAdjudicator.PROMPT_VERSION,
        "reference_schema_version": ReferenceDecisionAdjudicator.SCHEMA_VERSION,
        "manifest_path": str(manifest_path),
        "manifest_sha256": _hash_file(manifest_path),
        "source_reports_root": str(reports_root),
        "source_reports_sha256": _hash_reports_root(reports_root),
        "dataset_hash": selection.dataset_hash,
        "selected_chat_ids": list(chat_ids),
        "expected_output_count": len(outputs),
        "repeats": repeats,
        "rows": stable_rows,
        "unresolved": unresolved,
        "coverage": coverage,
        "repeat_runs": repeat_details,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if progress_path is not None:
        _write_generation_state(
            progress_path,
            {
                **signature,
                "repeat_index": repeats,
                "repeats": repeats,
                "completed_groups": len(groups),
                "total_groups": len(groups),
                "completed_rows": len(stable_rows),
                "complete": True,
                "concurrency": concurrency,
                "repeat_runs": repeat_runs,
                "repeat_details": repeat_details,
                "artifact": artifact,
            },
        )
    validate_reference_artifact(artifact, manifest)
    return artifact


def _error_message(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate independent reference labels")
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--progress", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    tmp_path = _tmp_path(args.output)
    try:
        ModelConfig.validate_reference_model()
        artifact = asyncio.run(
            generate_reference_labels(
                reports_root=args.reports_root,
                dataset_dir=args.dataset,
                manifest_path=args.manifest,
                repeats=args.repeats,
                max_concurrency=args.max_concurrency,
                progress_path=args.progress,
            )
        )
        _write_json(tmp_path, artifact)
        validate_reference_artifact(artifact, _read_json(args.manifest))
        tmp_path.replace(args.output)
        return 0
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        print(_error_message(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
