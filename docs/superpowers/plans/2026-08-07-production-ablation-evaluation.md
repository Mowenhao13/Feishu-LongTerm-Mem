# Production Ablation Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the extractor-only ablation runner with a reproducible production-path benchmark that gives evidence-aware confirmed-decision metrics.

**Architecture:** Add option gates at existing `MemoryEngine` boundaries; the benchmark instantiates isolated engines and exports normalized decisions after real mutation and dedup. A new evaluator aligns samples with GT and classifies unmatched evidence-supported outputs as GT matches, valid extras, or invalid.

**Tech Stack:** Python 3.12, pytest/pytest-asyncio, MemoryEngine, ChatEpisodeManager, JSONL benchmark, existing LLM provider.

## Global Constraints

- Main metric evaluates confirmed decisions only; suggestions remain separate.
- Every variant differs from full by exactly one option.
- Selection filters chats, messages, and GT together.
- API, parsing, Judge, and schema failures cannot silently become negative matches.
- Variant state/caches/storage are isolated.
- Legacy results remain visible but are labelled exploratory.

---

### Task 1: Add production option gates

**Files:**
- Create: `src/core/pipeline_options.py`
- Modify: `src/core/engine.py`
- Test: `tests/test_pipeline_options.py`

**Interfaces:** `PipelineOptions` with `enable_memory_extraction`, `inject_entity_context`, `inject_project_context`, `enable_neo4j_history`, `enable_embedding_dedup`, and `enable_llm_dedup`; `changed_fields_from(other) -> set[str]`.

- [ ] Write default and one-field-difference tests.
- [ ] Implement immutable options and engine constructor injection.
- [ ] Gate the matching production boundaries.
- [ ] Run `pytest tests/test_pipeline_options.py -v`.
- [ ] Commit.

### Task 2: Add confirmed-decision evaluator

**Files:**
- Create: `src/eval/confirmed_decision_eval.py`
- Test: `tests/test_confirmed_decision_eval.py`

**Interfaces:** `DatasetSelection.from_jsonl()`, `EvidenceDecision`, `EvaluationOutcome`, `ConfirmedDecisionEvaluator.evaluate()`.

- [ ] Test sample/GT alignment, evidence/cross-chat validation, order invariance, and errors.
- [ ] Implement source/evidence matching, one-to-one assignment, three-state adjudication and incomplete status.
- [ ] Run `pytest tests/test_confirmed_decision_eval.py -v`.
- [ ] Commit.

### Task 3: Add isolated production runner

**Files:**
- Create: `experiments/production_ablation/runner.py`
- Create: `experiments/production_ablation/variants.py`
- Create: `experiments/production_ablation/fixtures.py`
- Test: `tests/test_production_ablation_runner.py`

**Interfaces:** `ProductionVariant(name, options)` and `run_variant(selection, variant, run_dir, providers, fixtures)`.

- [ ] Test synthetic confirmed, suggestion-only, and history/project-context chats.
- [ ] Implement isolated engine, state, fixtures, post-mutation export and traces.
- [ ] Validate every variant has exactly one option difference.
- [ ] Run `pytest tests/test_production_ablation_runner.py -v`.
- [ ] Commit.

### Task 4: Add CLI and report hygiene

**Files:**
- Create: `experiments/production_ablation/run.py`
- Modify: `EXPERIMENTS.md`
- Test: `tests/test_production_ablation_cli.py`

- [ ] Test aligned report counts and unique atomic run outputs.
- [ ] Implement `--sample`, `--chat-id`, `--variant`, `--repeat`, `--synthetic`, `--run-root`.
- [ ] Record commit, dataset hash, model/prompt/options hashes, real calls and errors.
- [ ] Annotate legacy experiments as exploratory and withdraw invalid component claims.
- [ ] Run `pytest tests/test_production_ablation_cli.py -v`.
- [ ] Commit.

### Task 5: Verification

- [ ] Run new focused tests and affected legacy tests.
- [ ] Run synthetic all-variant smoke and assert component traces.
- [ ] Run three-chat real smoke with aligned GT and zero unresolved errors.
- [ ] Append only verified results to EXPERIMENTS.md.
- [ ] Commit verification artifacts.