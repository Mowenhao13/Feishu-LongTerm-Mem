# Confirmed-Decision Performance Improvement Design

**Date:** 2026-08-08

**Status:** Approved design; pending written-spec review

**Depends on:** `docs/superpowers/specs/2026-08-07-production-ablation-evaluation-design.md`

## 1. Purpose

Improve confirmed-decision extraction quality without increasing the production-path LLM call count. The primary objective is cross-domain stability measured by macro-F1; micro-F1 is a secondary constraint. The work must preserve the evidence contract, keep one unified runtime strategy across all domains, and separate evaluator changes from extractor changes so metric movement remains attributable.

This design responds to the completed 70-chat production-path runs:

| Variant | Micro F1 | Macro F1 | TP | Invalid / strict FP | FN | Valid extra |
|---|---:|---:|---:|---:|---:|---:|
| `full` | 0.5658 | 0.5821 | 86 | 86 | 46 | 109 |
| `no_entity_context` | 0.5859 | 0.5616 | 87 | 78 | 45 | 99 |
| `no_memory_extractor` | 0.5850 | 0.5822 | 86 | 76 | 46 | 109 |

All three runs completed 70/70 chats, 2373 messages, 132 GT rows, and 24/24 chunks with `evidence_invalid=0` and no runner errors. The one-run component deltas are heterogeneous by domain and chat, so they do not justify changing production defaults.

## 2. Measured failure model

The performance program is based on measured failure classes rather than broad threshold tuning.

### 2.1 Evaluator boundary errors

In the final `full` reports, 38 of 86 invalid outputs were downgraded because a judge-selected semantic match had character-set overlap below `0.35`. Ten more invalid outputs came from unknown-GT linkage. Equivalent patterns appear in both ablations.

The current lexical veto is unsuitable as a semantic guard because it:

- compresses compound and qualified decision meaning into one scalar;
- rejects valid paraphrases with different wording;
- cannot distinguish a missing non-material detail from a contradictory material condition;
- converts evaluator uncertainty or malformed linkage into extractor false positives;
- makes item-level results sensitive to output order and duplicate GT claims.

The 38 lexical rejections are the affected upper bound, not 38 presumed true positives. Human calibration must determine how many are `match_gt`, `valid_extra`, or genuinely `invalid`.

### 2.2 Persistent extraction misses

Across the three runs, 72 GT items were missed at least once, including 23 missed in all three. The persistent misses cluster around:

- compound architecture or policy decisions combining choice, constraints, rollout, and ownership;
- conditional or staged decisions;
- execution commitments rather than headline technology choices;
- security and compliance policy statements.

### 2.3 Genuine over-generation

The `full` invalid set also contains status updates, acknowledgements, suggestions, non-committal discussion, and execution-adjacent statements that are not GT-equivalent. These are production extraction/filtering problems rather than evidence failures.

### 2.4 Valid extras are not false positives

`valid_extra` is an evidence-supported real decision that conservative GT does not cover. It remains separate from strict FP and must not be suppressed merely to improve strict precision. Every report and promotion decision must present `invalid` and `valid_extra` separately.

## 3. Goals and non-goals

### 3.1 Goals

1. Replace the brittle lexical veto with an auditable, one-to-one semantic assignment contract.
2. Measure and freeze evaluator quality before changing extraction.
3. Improve compound, conditional, commitment, and policy decision extraction in the existing Stage 2 call.
4. Reduce status/discussion/suggestion noise with deterministic typed filtering.
5. Preserve `evidence_invalid=0`.
6. Keep the production default-path LLM call count unchanged.
7. Require stable improvement across all seven domains.
8. Add paired-repeat, cost, token, and latency evidence to production promotion decisions.

### 3.2 Non-goals for the first implementation

- changing the production model or provider;
- adding a universal verifier or self-consistency call;
- turning off MemoryExtractor, entity context, project context, Neo4j history, or dedup components;
- changing dedup similarity thresholds;
- changing the `0.70` extraction confidence threshold;
- adding domain-specific prompts or thresholds;
- changing GT contents or redefining strict metrics;
- treating evaluator-score improvement as production extractor improvement.

## 4. Architecture

The program has three isolated layers.

```text
Layer 1: trusted evaluation
frozen outputs
→ exact-source matching
→ per-chat global semantic assignment
→ structural validation
→ calibrated three-state scores

Layer 2: single-call extraction quality
existing Stage 1 MemoryExtractor call
→ existing Stage 2 decision call with revised schema/prompt
→ deterministic typed filtering and evidence validation
→ existing mutation/dedup/storage path

Layer 3: promotion funnel
frozen-output evaluator calibration
→ fixed 35-chat development smoke
→ 70-chat development/holdout/full confirmation
→ three paired 70-chat repeats
```

Only one layer changes in an experiment. Evaluator calibration does not regenerate extractor outputs. Extractor A/B tests use a frozen evaluator. Component ablations do not simultaneously change prompts, schemas, or thresholds.

## 5. Trusted evaluation layer

### 5.1 Exact-source matching

Retain deterministic exact-source matching for unambiguous cases. An output matches a GT item directly only when:

- the output cites the GT source message;
- its evidence quote occurs in that cited message;
- the GT item is not already assigned.

Exact matches are removed before semantic assignment.

### 5.2 Normalized per-chat assignment input

For each chat, normalize the remaining outputs and remaining GT candidates into a stable payload.

Each output includes:

- stable `output_index`;
- title and summary;
- status and suggestion flag;
- source message IDs;
- evidence quote;
- cited message text.

Each GT candidate includes:

- stable `gt_index`;
- GT message ID;
- expected topic and summary;
- expected status and impact.

Normalization must:

- sort collections and object keys deterministically;
- exclude timestamps, run IDs, and unrelated variant results;
- preserve Unicode text exactly;
- produce a content hash for provenance and caching.

### 5.3 Global semantic matcher

Call the judge at most once per chat for all residual outputs and GT candidates. The judge solves a constrained one-to-one assignment rather than classifying each output independently.

For every output, the response contains:

```json
{
  "output_index": 0,
  "classification": "match_gt",
  "matched_gt_index": 1,
  "decision_kind": "conditional_choice",
  "core_equivalent": true,
  "polarity_compatible": true,
  "commitment_compatible": true,
  "material_qualifier_conflict": false,
  "reason": "同为订单服务 Saga 试点，并约定一个月后评估"
}
```

The required `classification` values are:

- `match_gt`: an evidence-supported real decision equivalent to one GT item;
- `valid_extra`: an evidence-supported real decision with no equivalent GT item;
- `invalid`: a status, acknowledgement, discussion item, unsupported statement, non-committal suggestion, or other non-decision output.

The judge applies these semantic dimensions:

- decision kind;
- subject or responsible actor;
- action or choice;
- object or selected option;
- polarity;
- commitment strength;
- material qualifiers such as scope, threshold, timing, condition, or rollout stage.

A `match_gt` requires the same core proposition, compatible polarity and commitment, and no contradictory material qualifier. Missing non-material detail may still match. Added compatible owner or deadline detail may still match. A different option, opposite polarity, incompatible commitment level, or conflicting material condition must not match.

A GT item may match at most one output. Outputs may remain `valid_extra` or `invalid`. GT items may remain unmatched and become FN.

### 5.4 Structural assignment validator

Deterministic code validates only facts that code can prove:

- every residual output is classified exactly once;
- output and GT indexes are in range;
- a GT index is assigned at most once;
- `match_gt` carries one valid GT index;
- `valid_extra` and `invalid` carry no GT index;
- enum and schema values are legal;
- `match_gt` is not internally inconsistent with `core_equivalent=false`, incompatible polarity/commitment, or a material qualifier conflict.

The validator must not use character overlap, embedding similarity, or keyword scoring to override semantic equivalence.

Malformed schema, unknown indexes, duplicate assignments, missing outputs, and internal contradictions become `evaluation_error`. The affected chat makes the chunk and run incomplete. Evaluator failures never increment extractor `invalid`.

### 5.5 Judge configuration and cache

The evaluator remains provider-neutral and uses the existing `LLMProvider` interface and current OpenAI-compatible gateway. This work does not add Anthropic SDK dependencies.

Where supported by the configured model, judge calls explicitly request `temperature=0`. This reduces variance but does not guarantee bitwise determinism.

Cache keys contain:

```text
judge model identifier
+ judge prompt version
+ response schema version
+ evaluator version
+ normalized chat input hash
```

Only structurally valid assignments enter the cache. Changes to the model, prompt, schema, evaluator, or input invalidate the key. Cache hits must be reported separately from judge calls.

### 5.6 Calibration dataset and labels

Build evaluator gold from the fixed 35-chat development set. Prioritize:

- every lexical-overlap rejection;
- every unknown-GT linkage case;
- outputs that flipped among `match_gt`, `valid_extra`, and `invalid` across runs;
- candidates near persistent FN items;
- stratified clear positives, valid extras, and invalid negatives.

Each human label records:

- expected three-state classification;
- matched GT ID when applicable;
- decision kind;
- whether a material qualifier conflict exists;
- a short evidence-based rationale;
- final adjudication when two annotators disagree.

Evaluator calibration metrics are separate from extractor metrics:

- per-class precision, recall, and F1;
- one-to-one assignment violation rate;
- evaluation-error rate;
- same-input three-run classification agreement;
- confusion by decision kind.

The evaluator may be frozen only when:

- `match_gt` precision is at least `0.95`;
- `valid_extra` precision is at least `0.90`;
- same-input three-run agreement is at least `0.98`;
- structural assignment violations are zero;
- evaluator macro-F1 on human gold exceeds the old evaluator;
- lexical-rejection and unknown-linkage slices are represented.

## 6. Single-call extraction quality layer

This layer begins only after the evaluator is frozen. Its first candidate modifies the existing Stage 2 extraction call and deterministic post-processing. Stage 1, context providers, dedup, storage, model, and call count remain unchanged.

### 6.1 Decision-kind schema

Every Stage 2 candidate has one `decision_kind`:

- `choice`;
- `conditional_choice`;
- `execution_commitment`;
- `policy_constraint`;
- `suggestion`;
- `status`;
- `discussion`.

Only `choice`, `conditional_choice`, `execution_commitment`, and `policy_constraint` may become confirmed decisions. `suggestion` remains separately represented. `status` and `discussion` are filtered before mutation.

### 6.2 Compound-decision preservation

The prompt defines an atomic decision as one proposition that is adopted, rejected, constrained, or committed to. Choice, conditions, rollout, ownership, and deadline remain one output when they jointly define that proposition. Two clauses split only when they can be independently executed or reversed.

Titles express the core action and object. Summaries retain material conditions, scope, rollout, owner, and timing. Evidence may cite multiple messages, but every quote must come from a cited source message.

### 6.3 Context boundaries

Entity, project, history, and existing-decision context remain available but have a uniform role:

- resolve names and actors;
- normalize terminology;
- identify likely duplicates;
- provide no new evidence and no independent basis for a decision.

The conversation must independently support every output. Context cannot turn a file change, historical decision, or known entity into a new commitment. When context conflicts with current messages, current cited messages control.

### 6.4 Deterministic typed filtering

Post-processing enforces:

- `status` and `discussion` never become confirmed decisions;
- `choice`, `conditional_choice`, and `policy_constraint` contain an explicit action and object;
- `execution_commitment` contains an action and an actor attributable from cited evidence;
- material qualifiers in title or summary are supported by cited evidence;
- a suggestion cannot become confirmed solely because confidence is high;
- evidence attachment remains mandatory.

Evidence-attachment drops are counted explicitly instead of being indistinguishable from a model returning no decision.

### 6.5 Sampling configuration

Where supported by the current model, Stage 1, Stage 2, and adjudication calls request `temperature=0`. The report records the effective model and request configuration. Repeated runs remain mandatory because low temperature does not guarantee identical outputs.

## 7. Fixed 35/35 split

Create a versioned development and holdout manifest containing exactly 35 chats each.

- Each of the seven domains contributes five development and five holdout chats.
- Within each domain, sort chats by full-baseline per-chat F1 and choose two from the low stratum, one from the middle stratum, and two from the high stratum for development; the other five become holdout.
- Within an F1 tie, prefer the combination that covers more of the measured failure types (lexical rejection, unknown linkage, status/noise, compound FN, conditional FN, and execution-commitment FN), then break any remaining tie by ascending chat ID.
- Record the selected chat IDs, baseline artifact ID, selection rule version, and resulting manifest hash. Do not regenerate the split when scores or prompts change.
- Item-level holdout results are not inspected during prompt, schema, or rule tuning.

The 35-chat stage is a screening tool, not promotion evidence. Final promotion always requires all 70 chats.

## 8. Experiment and promotion funnel

### Phase 0: frozen-output evaluator calibration

1. Reuse existing top-level final report outputs; do not rerun extraction.
2. Build human evaluator gold from the development set.
3. Score identical frozen outputs with old and new evaluators.
4. Run the new evaluator three times on identical inputs.
5. Freeze the evaluator only after all calibration gates pass.
6. Re-score the frozen full baseline under the frozen evaluator.

Scores produced by the new evaluator cannot be compared directly with old published scores. Full and candidate must always be scored by the same frozen evaluator version.

### Phase 1: one-run 35-chat development smoke

Run full and the Stage 2 candidate on the fixed development manifest using identical chat selection, chunking, model, and evaluator.

The candidate advances when:

- development macro-F1 does not decrease;
- development micro-F1 does not decrease;
- no domain decreases by more than `0.03`;
- `evidence_invalid=0`;
- runner health is 100%;
- production LLM calls do not increase;
- valid extras are not globally suppressed to inflate strict precision;
- material output-count reductions explain where TP and valid extras went.

### Phase 2: one-run 70-chat confirmation

Run all 70 chats and report development 35, untouched holdout 35, and full 70 separately. The candidate is rejected if holdout macro-F1 decreases or any holdout domain decreases by more than `0.03`. Development and holdout must agree in direction before repeated full runs.

### Phase 3: three paired 70-chat repeats

Run baseline and candidate on the same code commit, dataset, chunk manifest, model, provider configuration, and evaluator/cache version. Alternate order to reduce time-window bias:

1. full, then candidate;
2. candidate, then full;
3. full, then candidate.

The candidate is eligible for production promotion only when:

- mean paired macro-F1 delta is at least `+0.02`;
- mean paired micro-F1 delta is non-negative;
- every domain's mean F1 delta is at least `-0.02`;
- `evidence_invalid=0` in every run;
- every chunk completes with zero runner errors;
- production default-path LLM calls do not increase;
- at least two of three paired macro-F1 deltas are positive, and the third is not materially negative;
- no single chat contributes a dominant share of the total improvement.

Report paired deltas rather than only independent means. Means, standard deviations, medians, min/max, and per-chat/domain distributions remain descriptive; confidence intervals or paired bootstrap estimates are included when the implementation adds them.

## 9. Cost and latency observability

Production-ablation reports add stage-level accounting:

- Stage 1 calls, duration, input/output tokens;
- Stage 2 calls, duration, input/output tokens;
- fallback extraction calls;
- embedding and LLM dedup activity;
- offline adjudicator calls and cache hits, reported separately;
- per-chat and aggregate median and p95 latency.

Quality promotion has two auxiliary efficiency limits:

- mean production-token growth no greater than `10%`;
- p95 end-to-end latency growth no greater than `10%`.

A candidate that passes quality gates but exceeds an efficiency limit enters a focused cost/latency optimization step; it does not silently promote and is not automatically discarded.

## 10. Error handling and health

### 10.1 Production extraction

- Provider/network failure preserves existing incomplete-run semantics.
- JSON/schema failures record stage, model, and prompt/schema version; they must not silently become “no decision.”
- Evidence-attachment failures drop the candidate and increment `evidence_attachment_drop`.
- Fallback calls are counted and timed.

### 10.2 Offline evaluator

- Provider retry remains bounded by the provider policy.
- Invalid schema, unknown index, duplicate assignment, missing assignment, or internal contradiction becomes `evaluation_error`.
- One chat assignment failure makes its chunk incomplete.
- Evaluator failures never increment extractor `invalid`.
- Cache writes occur only after structural validation.
- No malformed response falls back to the old lexical gate.

### 10.3 Gateway health

When consecutive chunks fail at the provider boundary:

1. stop the run after a configured consecutive-failure threshold;
2. execute a minimal provider health probe through the same provider path;
3. diagnose endpoint/configuration before changing code;
4. resume only after the probe succeeds;
5. rerun incomplete/running chunks and preserve completed chunks.

## 11. Testing

### 11.1 Evaluator unit tests

- normalization is deterministic;
- cache keys change with every versioned input;
- exact-source matching remains one-to-one;
- global assignments are output-order invariant;
- unknown, duplicate, missing, or contradictory assignments make evaluation incomplete;
- evaluator failures never alter strict FP;
- valid extras remain separate from invalid;
- frozen cache hits return the same validated result.

### 11.2 Extractor unit tests

- each decision kind parses and filters correctly;
- compound decisions retain material conditions;
- independently executable commitments split;
- status and discussion are removed;
- suggestions cannot become confirmed through confidence alone;
- context text cannot become evidence;
- material qualifiers must be present in cited evidence;
- evidence-attachment drops are observable.

### 11.3 Calibration and integration tests

- lexical-rejection cases;
- unknown-GT cases;
- compound, conditional, policy, and commitment cases;
- valid-extra positive cases;
- clear invalid negative cases;
- one-to-one competition where two outputs target one GT;
- chunk resume and aggregate accounting;
- call/token/latency instrumentation;
- one-toggle variant invariant.

### 11.4 Repository-required validation

Every later implementation follows `CLAUDE.md` requirements:

- full two-layer versus four-layer A/B;
- direct versus two-stage pipeline A/B;
- production 35-chat smoke, 70-chat confirmation, and three paired full repeats;
- threshold scan only after typed extraction is isolated and frozen;
- `EXPERIMENTS.md` updated with metrics, calls, latency, and interpretation.

## 12. Implementation sequence

The first implementation slice contains only evaluator work:

1. fixed 35/35 development/holdout manifests;
2. frozen-output calibration harness;
3. per-chat global semantic matcher;
4. structural validator;
5. versioned adjudication cache;
6. evaluator unit tests and human calibration labels;
7. frozen-output full-baseline re-score.

The second slice begins only after evaluator calibration passes:

1. Stage 2 decision-kind schema;
2. compound-decision and context-boundary prompt changes;
3. deterministic typed filtering;
4. evidence-attachment diagnostics;
5. explicit supported low-variance request configuration;
6. unit and integration tests;
7. 35-chat development smoke.

The third slice is experiment execution and promotion evidence:

1. one-run 70-chat development/holdout/full report;
2. three paired 70-chat repeats;
3. cost and latency aggregation;
4. final promotion decision against every quality, health, domain, and efficiency gate.

## 13. Acceptance criteria

The design is implemented when:

1. the `<0.35` lexical veto is absent from semantic classification;
2. residual outputs are assigned globally once per chat under one-to-one constraints;
3. malformed judge output makes evaluation incomplete and never becomes invalid;
4. evaluator precision and agreement meet calibration gates;
5. full and candidate are scored with the same frozen evaluator;
6. Stage 2 adds decision kinds and compound-decision preservation without extra production calls;
7. fixed development and holdout manifests cover all seven domains equally;
8. reports separate strict FP, valid extras, evaluator errors, evidence drops, and health;
9. reports include stage-level call, token, and latency accounting;
10. the candidate passes the 35-chat smoke, untouched holdout check, and all three paired 70-chat promotion gates;
11. repository-required A/B tests pass or any change is explicitly explained in the experiment report;
12. no production default changes until all gates pass.
