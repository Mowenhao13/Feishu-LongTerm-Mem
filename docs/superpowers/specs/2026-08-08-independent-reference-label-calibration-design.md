# Independent Reference-Label Calibration Design

**Date:** 2026-08-08

**Status:** Approved design; pending written-spec review

**Depends on:** `docs/superpowers/specs/2026-08-08-confirmed-decision-performance-design.md`

## 1. Purpose

Replace the blocked manual-label step in Phase 0 with a reproducible, independent reference-label workflow. A dedicated LLM configured through `HUMAN_*` environment variables generates the reference labels for the fixed development-35 frozen outputs. The reference model must differ from the production evaluator model.

This produces **independent-LLM reference labels**, not human gold labels. Reports, artifacts, and promotion decisions must use that precise terminology and must not claim human review or human-label calibration.

The workflow remains limited to evaluator calibration. It does not modify extraction, production defaults, dataset GT, or existing 70-chat baseline artifacts.

## 2. Goals and non-goals

### 2.1 Goals

1. Generate a stable, auditable three-state reference label for every frozen development output.
2. Keep the reference labeler independent from the evaluator being calibrated by requiring a different model identifier.
3. Prevent evaluator output, original evaluator reasoning, and original adjudication state from anchoring the reference labeler.
4. Run the reference labeler three times on identical per-chat inputs and accept labels only when all runs agree and validate structurally.
5. Block evaluator freezing on unresolved labels, missing coverage, evaluator errors, or assignment violations.
6. Preserve the current evaluation contract: one-to-one GT matching, separate `valid_extra`, and evidence-grounded decisions.
7. Reuse the existing OpenAI-compatible provider abstraction and `.env` configuration path; do not add Anthropic SDK dependencies.

### 2.2 Non-goals

- Claiming that reference labels are human annotations.
- Replacing evidence validation with LLM judgment.
- Changing production evaluator behavior merely to make calibration pass.
- Starting the extraction or promotion slices before the evaluator-freeze gate passes.
- Persisting API keys or other secrets in source code, artifacts, reports, or logs.

## 3. Inputs and trust boundaries

### 3.1 Frozen-output scope

The source is the checked-in full-baseline top-level `chunk_*/report.json` artifacts. Nested retry reports under `runs/**/report.json` are excluded. The generator filters outputs to exactly the chat IDs in `performance_dev_35.json`.

The generator reconstructs the selected chat's original messages and GT candidates from the dataset. Every reference decision is based only on:

- chat messages;
- output title, summary, source message IDs, and evidence quote;
- GT candidates for that chat.

It must not pass these fields to the reference model:

- prior `adjudication`;
- prior `matched_msg_id`;
- prior evaluator `reason`;
- previous evaluator score, label, or error data.

### 3.2 Reference configuration

The reference labeler reads a dedicated `HUMAN_*` configuration group from `.env`, following the existing provider configuration conventions. It includes the configured model identifier and connection settings, while keeping credentials secret.

Before any request, the generator validates:

1. required `HUMAN_*` settings are present;
2. the reference model identifier is non-empty;
3. the reference model identifier differs from the production evaluator model identifier.

The third condition is a hard failure. Matching model identifiers prevent reference-label generation. Provider/base-URL sameness is recorded as provenance but does not block execution as long as model identifiers differ.

## 4. Reference adjudicator contract

### 4.1 Per-chat assignment

The reference labeler receives all selected outputs and GT candidates for one chat in a single request. It performs a constrained, one-to-one assignment:

- each output receives exactly one of `match_gt`, `valid_extra`, `invalid`, or `unresolved`;
- each GT candidate can match at most one output;
- a `match_gt` carries exactly one in-range GT target;
- `valid_extra`, `invalid`, and `unresolved` carry no GT target.

`unresolved` is a reference-labeler uncertainty state, not an evaluator classification. It is never counted as a valid calibration label and blocks evaluator freezing.

### 4.2 Semantic judgment policy

A `match_gt` requires the same core decision proposition, compatible polarity and commitment strength, and no contradictory material qualifier. Decision kind, subject or responsible actor, action, object or selected option, scope, threshold, timing, condition, and rollout stage are compared where present.

A missing non-material detail can still match. Compatible additional owner or deadline information can still match. A different choice, opposite polarity, incompatible commitment, or conflicting material qualifier cannot match.

A real, evidence-supported decision not represented by a GT item is `valid_extra`. Status updates, acknowledgements, discussions, suggestions without adoption, unsupported claims, and other non-decisions are `invalid`.

### 4.3 Dedicated system prompt

The reference labeler uses a Chinese system prompt separate from the production evaluator prompt. It must state that the model is an independent reference annotator and that it must:

1. rely only on provided source messages, output evidence, and GT candidates;
2. assign every output exactly once under the one-to-one rule;
3. return a structured rationale and a self-assessed confidence value;
4. return `unresolved` rather than guessing when evidence is insufficient or semantic equivalence cannot be determined;
5. avoid any influence from unavailable prior evaluator results.

The reference prompt, prompt version, and response schema version are versioned and recorded in the artifact.

## 5. Artifacts and label lifecycle

### 5.1 Reference-label artifact

`reference_labels.json` is generated as a new artifact, distinct from the existing human-label template. It records:

- `label_source: "independent_llm"`;
- source reports path and content hash;
- development manifest path and hash;
- reference model identifier and non-sensitive configuration fingerprint;
- reference prompt and schema versions;
- generation timestamp;
- expected output count and selected chat IDs;
- stable labels;
- unresolved rows and their reasons;
- per-repeat results and consistency metadata.

Each stable label includes a deterministic output identity, chat ID, final classification, optional matched GT ID, decision kind, material-qualifier-conflict flag, evidence-based rationale, confidence, and supporting provenance.

### 5.2 Stability requirement

The generator runs the same per-chat inputs three times. A label becomes stable only if all three runs agree on its classification and matched GT ID, all responses validate structurally, and no run returns `unresolved`.

Any disagreement, unresolved result, provider failure, parser failure, missing output, duplicate GT assignment, invalid enum, out-of-range target, or material contradiction places the affected output in `unresolved` with explicit diagnostics. The generator writes no partially valid artifact over a prior valid artifact.

Writes use a temporary path and atomic replacement only after full artifact validation succeeds.

## 6. Coverage and freeze gates

### 6.1 Reference-label readiness gate

Evaluator calibration may start only when all conditions hold:

1. every frozen development output has one stable reference label;
2. `unresolved == 0`;
3. labels contain all three evaluator classes: `match_gt`, `valid_extra`, and `invalid`;
4. labels cover all seven development domains;
5. labels cover both measured failure slices: lexical-veto and unknown-GT linkage;
6. every `match_gt` assignment is legal and one-to-one within its chat;
7. artifact provenance, manifest hash, prompt version, schema version, and model identifier are present;
8. reference and production evaluator model identifiers differ.

Any failed condition marks the calibration report incomplete with the missing coverage or invalid rows listed. The workflow must not silently omit difficult cases.

### 6.2 Evaluator-freeze gate

Using stable reference labels and frozen outputs only, run the production evaluator three times. Freeze it only when all conditions hold:

- `match_gt` precision is at least `0.95`;
- `valid_extra` precision is at least `0.90`;
- same-input, three-run evaluator classification agreement is at least `0.98`;
- structural assignment violations equal zero;
- evaluator errors equal zero;
- reference-label readiness remains satisfied.

The freeze artifact records evaluator and reference model identifiers, prompt/schema versions, hashes, calibration summary, and an explicit `evaluator_frozen` boolean. It is not a production-promotion decision. Only a passing freeze enables frozen full-baseline re-scoring; it does not automatically begin Extraction work.

## 7. CLI boundaries

Two commands keep generation and scoring separate:

```bash
# Generate independent, stable reference labels using HUMAN_* configuration.
uv run python experiments/production_ablation/generate_reference_labels.py \
  --reports-root experiments/production_ablation/chunked_runs/full_70_adjudicate_20260807_s3 \
  --dataset eval_dataset/argusbot_v3 \
  --manifest eval_dataset/argusbot_v3/performance_dev_35.json \
  --repeats 3 \
  --output experiments/production_ablation/reference_labels.json

# Calibrate the production evaluator against independent reference labels.
uv run python experiments/production_ablation/calibrate_evaluator.py \
  --reports-root experiments/production_ablation/chunked_runs/full_70_adjudicate_20260807_s3 \
  --labels experiments/production_ablation/reference_labels.json \
  --manifest eval_dataset/argusbot_v3/performance_dev_35.json \
  --repeats 3 \
  --output experiments/production_ablation/calibration_report.json
```

`calibrate_evaluator.py` retains `--labels` for compatibility but recognizes and validates `label_source: "independent_llm"`. It must not require `reviewed: true` for this source and must not label the source as human-reviewed.

## 8. Errors and security

Generation and calibration fail with a non-zero exit code on missing `HUMAN_*` configuration, equal model identifiers, invalid provider response, repeat disagreement, structural validation failure, unavailable dataset/GT reconstruction, coverage failure, or evaluator failure.

Secret values must not appear in artifacts, logs, exception strings, test snapshots, or checked-in files. Reports may contain only a non-sensitive configuration fingerprint and model identifier.

All model responses are treated as untrusted data and pass deterministic schema and assignment validation before use. Invalid model output never falls back to a prior evaluator decision and never becomes an `invalid` extractor output.

## 9. Tests

Focused tests must cover:

1. `HUMAN_*` configuration parsing, required settings, and model-equality rejection.
2. Absence of evaluator adjudication, matched GT, and reason fields from reference prompt payloads.
3. Per-chat one-to-one assignment and failure on duplicate/missing outputs, duplicate GT matches, invalid enums, out-of-range indexes, and material contradictions.
4. Three-run stable-label acceptance and unresolved classification on disagreement, errors, or uncertainty.
5. Development-manifest filtering that excludes holdout chats.
6. Reference-label readiness coverage checks for all classes, all seven domains, lexical-veto, and unknown-GT slices.
7. Calibration acceptance only for complete, stable independent-LLM reference labels.
8. Freeze threshold boundaries, failure reporting, and successful `evaluator_frozen` artifact creation.
9. Regression coverage for existing evaluator, manifest, global adjudicator, and calibration tests.

## 10. Acceptance criteria

The Phase 0 replacement is complete when:

1. a distinct `HUMAN_*` model can generate reference labels without exposing secrets;
2. the system rejects an equal reference/evaluator model identifier;
3. reference inputs exclude old evaluator conclusions;
4. every development output receives a stable validated reference result or a declared unresolved result;
5. unresolved labels and missing coverage block calibration and freezing;
6. all reports accurately call the labels independent-LLM reference labels rather than human labels;
7. evaluator calibration exposes class metrics, stability, violations, errors, coverage, and provenance;
8. evaluator freezing occurs only after every stated gate passes;
9. focused tests and repository-required validation are recorded before any claim of completion;
10. no Extraction or Promotion slice begins merely because this tooling exists.
