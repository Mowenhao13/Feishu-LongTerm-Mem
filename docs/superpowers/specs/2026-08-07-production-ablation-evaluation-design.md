# Production-Path Ablation and Evaluation Redesign

**Date:** 2026-08-07  
**Status:** Approved design

## Problem

The original ablation runner bypassed `MemoryEngine`; several variants did not apply their claimed intervention, samples did not filter ground truth, project context was fabricated, and evaluation/API failures became false matches. Existing results remain exploratory evidence, not valid component-contribution estimates.

## Benchmark contract

Primary metrics cover **confirmed technical decisions only**, matching the 132 `expected_status=decided` rows in the current main benchmark. Suggestions remain a separately scored output. Confirmed decisions must carry `source_message_ids` and `evidence_quote`. A dataset selection filters chat IDs, messages, and expected rows together.

## Production architecture

Introduce immutable options to the production engine:

```python
@dataclass(frozen=True)
class PipelineOptions:
    enable_memory_extraction: bool = True
    inject_entity_context: bool = True
    inject_project_context: bool = True
    enable_neo4j_history: bool = True
    enable_embedding_dedup: bool = True
    enable_llm_dedup: bool = True
```

Every variant follows one production path:

```text
selected messages
→ ChatEpisodeManager
→ MemoryEngine
→ DecisionNode conversion
→ mutation / dedup / conflict handling
→ isolated graph and storage
→ normalized decision export
→ evaluator
```

The experiment runner must not reimplement extraction, context assembly, or dedup. Each variant changes exactly one option; the registry rejects zero-difference and multi-difference configurations.

| Variant | Only changed option |
|---|---|
| `full` | none |
| `no_memory_extractor` | `enable_memory_extraction=False` |
| `no_entity_context` | `inject_entity_context=False` |
| `no_project_context` | `inject_project_context=False` |
| `no_neo4j_history` | `enable_neo4j_history=False` |
| `no_embedding` | `enable_embedding_dedup=False` |
| `no_llm_dedup` | `enable_llm_dedup=False` |
| `single_stage_direct` | direct extraction while retaining mutation/storage |

Each variant receives independent graph, entity store, storage directory, history fixture namespace, extraction cache, and evaluation cache. Project and Neo4j-history fixtures are chat-specific.

## Evaluation

### Evidence validation

Each output source ID must exist in the same chat, and its evidence quote must be traceable to its cited messages. Invalid evidence cannot become a true positive.

### Deterministic matching

Match confirmed outputs in this order:

1. exact `(chat_id, source_message_id)`;
2. evidence/source-ID overlap within the same chat;
3. semantic adjudication for remaining candidates.

Use one-to-one maximum-weight assignment rather than order-dependent greedy matching.

### Three-state adjudication

For unmatched outputs, a judge receives the source chat, extracted output, source IDs, and evidence. It returns:

- `match_gt` — corresponds to a GT decision;
- `valid_extra` — evidence-supported confirmed decision absent from GT;
- `invalid` — unsupported, wrong chat, non-decision, or a suggestion incorrectly classified as confirmed.

The judge uses temperature `0`, structured output, and cache keys containing model, prompt, schema, source input, dataset hash, and evaluator version. API/JSON failures produce `evaluation_error`, never a negative decision. Runs with unresolved errors are incomplete and cannot rank variants.

### Reported metrics

- Strict-GT Precision / Recall / F1;
- confirmed-output validity precision;
- valid-extra rate;
- evidence-validity rate;
- suggestion metrics when suggestion GT exists;
- per-chat output density and GT density;
- schema, extraction, API, and evaluator failure rates;
- latency, actual LLM calls, tokens, and cost.

## Reproducibility

Use temperature `0` where provider support permits it. Record model, prompt hash, commit SHA, dataset hash, options, and run ID. Run `full`, `single_stage_direct`, and any candidate winner at least three times. Report mean, standard deviation, and confidence interval; only attribute a component effect if repeats agree and it exceeds observed run-to-run noise.

Reports are written atomically to unique run directories; concurrent experiments must not overwrite one shared report.

## Tests

### Unit tests

1. Dataset sampling filters messages and ground truth together.
2. Variant registry validates exactly one option difference.
3. Each option gates the intended production boundary.
4. Evidence validation rejects cross-chat and fabricated evidence.
5. Matching is invariant to output order.
6. Judge failures mark a run incomplete.
7. Cache keys change with model, prompt, schema, input, and evaluator version.
8. Report paths are unique and writes are atomic.

### Synthetic integration fixture

Use three chats:

- one explicit confirmed decision;
- one suggestion-only conversation;
- one repeated/updated decision with real project-context and Neo4j-history fixtures.

Tests prove all enabled components run, every ablation skips exactly its target, dedup/embedding affect mutation outcomes, fixtures are chat-specific, and no cross-chat leakage occurs.

### Smoke and full runs

A three-chat real benchmark smoke run validates execution with GT aligned to the selected chats. A full 70-chat run follows only after unit and integration tests pass. A full Claude Code baseline uses the same selected chats and same evidence-aware scorer.

## Legacy result handling

Preserve existing `EXPERIMENTS.md` entries for provenance but mark them exploratory because:

- sample runs included GT from unselected chats;
- embedding, Neo4j-history, and dedup interventions were not executed;
- project context was fabricated and unrelated to chats;
- several variants were duplicate implementations;
- evaluator and extraction failures were treated as model errors.

The unsupported prior estimate that the true F1 is 60–70% is withdrawn.

## Acceptance criteria

1. All variants execute the production engine and differ by one option.
2. Sample runs align GT with selected chats.
3. Evidence-aware scoring is auditable.
4. Infrastructure failures are visible and cannot silently become model errors.
5. Unit and synthetic integration tests pass.
6. Three-chat smoke run completes without infrastructure failure.
7. Full runs create unique artifacts.
8. Claude Code and system outputs share one scoring contract.
9. `EXPERIMENTS.md` separates invalid legacy conclusions from validated results.
