# Task Plan

## Goal
Create reproducible balanced 35/35 development and holdout manifests from the approved baseline aggregate, with deterministic selection, validation, tests, CLI verification, and committed outputs.

## Phases
- [x] Phase 1: Write failing tests for manifest generation and validation
- [x] Phase 2: Implement minimal manifest generator and validator
- [x] Phase 3: Generate and verify checked-in manifests via CLI
- [x] Phase 4: Run required pytest and CLI verification
- [ ] Phase 5: Commit changes and write implementation report

## Decisions
- Use only `experiments/production_ablation/chunked_runs/full_70_adjudicate_20260807_s3/aggregate.json` as the source aggregate.
- Keep scope limited to the task brief; do not touch unrelated experimental artifacts.
- Use a stable JSON hash computed over the payload without `manifest_sha256`.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Worktree path mismatch when using shared checkout path | 1 | Switched to worktree-local file paths |
| Test fixture missing parent directories | 1 | Added `mkdir(parents=True, exist_ok=True)` in helpers |
| Duplicate-chat validation reported length before duplicate | 1 | Checked duplicates before length |
| Paired-manifest overlap was masked by per-manifest validation | 1 | Checked overlap before validating the pair |
| Hash test recomputed after mutating payload | 1 | Recompute hash only for internally consistent cases |
