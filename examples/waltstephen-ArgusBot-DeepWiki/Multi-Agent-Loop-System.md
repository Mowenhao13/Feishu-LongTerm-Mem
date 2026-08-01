# Multi-Agent Loop System
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py)
- [codex_autoloop/reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py)
- [tests/test_reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_reviewer.py)

This page describes the core multi-agent execution loop that orchestrates task completion through iterative refinement. The loop coordinates four specialized agent types—Main, Reviewer, Planner, and Stall—each with distinct responsibilities in the execution pipeline. The system implements quality gates, background monitoring, and multiple safety mechanisms to ensure robust autonomous operation.

For information about the Loop Engine component that implements this system, see [Loop Engine](/waltstephen/ArgusBot/4.1-autolooporchestrator). For details on individual agent implementations, see [Agent System](/waltstephen/ArgusBot/4.2-reviewer-sub-agent). For state management across rounds, see [State Management and Persistence](/waltstephen/ArgusBot/3.5-state-management-and-persistence).

---

## Overview

The multi-agent loop operates as a continuous refinement cycle where the Main Agent executes tasks through Codex CLI, the Reviewer Agent gates each round's completion, the Planner Agent maintains strategic oversight in background sweeps, and the Stall Agent monitors for execution hangs. Each round increments until one of several stop conditions is met: reviewer approval with passing checks, max rounds exceeded, repeated no-progress detection, reviewer blockage, or user intervention.

### Core Loop Architecture

[Flowchart Diagram]

**Sources:**[codex_autoloop/apps/cli_app.py427-456](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L427-L456)[codex_autoloop/core/engine.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/engine.py) (referenced), [README.md9-16](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L9-L16)

---

## Round Execution Flow

Each loop iteration follows a structured sequence: main agent execution, acceptance check validation, optional planner sweep, reviewer evaluation, and progress analysis. External interrupts (inject, stop, plan, review commands) can alter this flow at designated checkpoints.

### Round Sequence Diagram

[Flowchart Diagram]

**Sources:**[README.md611-625](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L611-L625)[codex_autoloop/apps/cli_app.py289-400](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L289-L400) Diagram 3 from high-level architecture

---

## Agent Types and Responsibilities

### Main Agent

The Main Agent executes the primary task through Codex CLI subprocess invocation. It operates in two modes: initial execution (`codex exec`) for new sessions and resume execution (`codex exec resume`) for continuing existing threads. The agent receives context from `operator_messages.md`, the current `plan_overview.md`, and previous round history.

**Configuration Parameters:**

| Parameter | CLI Argument | Purpose |
| --- | --- | --- |
| `main_model` | `--main-model` | Model override for main agent |
| `main_reasoning_effort` | `--main-reasoning-effort` | Reasoning effort (low/medium/high/xhigh) |
| `main_extra_args` | `--main-extra-arg` | Additional codex CLI arguments |
| `skip_git_repo_check` | `--skip-git-repo-check` | Pass through to Codex CLI |
| `full_auto` | `--full-auto` | Enable full-auto mode |
| `dangerous_yolo` | `--yolo` | Bypass approvals and sandbox |

**Execution Flow:**

[State Diagram]

**Sources:**[codex_autoloop/apps/cli_app.py420-424](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L420-L424)[codex_autoloop/apps/daemon_app.py552-660](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L552-L660)[README.md10-11](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L10-L11)

### Reviewer Agent

The Reviewer Agent acts as a quality gate, evaluating whether the main agent's work satisfies completion criteria. It receives structured context including all operator messages, check command results, review-only criteria, and the latest round output. The reviewer responds with JSON-structured output containing `status` (done/continue/blocked), `confidence` level, `reason` for decision, and `next_action` guidance.

**Reviewer Status Values:**

| Status | Meaning | Loop Behavior |
| --- | --- | --- |
| `done` | Task completed successfully | Stop loop if checks pass |
| `continue` | Iteration needed | Continue to next round |
| `blocked` | Fatal issue, cannot proceed | Stop loop immediately |

**Context Inputs:**

[Flowchart Diagram]

**Sources:**[codex_autoloop/apps/cli_app.py425](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L425-L425)[codex_autoloop/apps/daemon_app.py836-882](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L836-L882)[README.md12](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L12-L12)

### Planner Agent

The Planner Agent operates in background sweeps (not in the critical path of each round) to maintain strategic oversight. It updates `plan_report.md` with high-level objectives, current progress, workstream breakdown, and proposed next steps. The planner receives plan-only directions from `/plan` commands, broadcast operator inputs, and the current objective.

**Planner Modes:**

| Mode | Behavior | Use Case |
| --- | --- | --- |
| `off` | Planner disabled | No strategic overhead needed |
| `auto` | Full automation with follow-up proposals | Continuous autonomous operation |
| `record` | Record-only, no auto-execution | Human-in-loop planning |

**Planner Sweep Trigger:**

Planner sweeps occur after the main agent completes and before the reviewer evaluates. The sweep is skipped when `--plan-mode off` is set. Background operation ensures planner overhead does not block the critical round completion path.

[Flowchart Diagram]

**Sources:**[codex_autoloop/apps/cli_app.py426](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L426-L426)[codex_autoloop/cli.py162-172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L162-L172)[README.md13](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L13-L13)[README.md168-172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L168-L172)

### Stall Agent

The Stall Agent provides watchdog monitoring with dual-threshold detection. When the main agent produces no new output for extended periods, the system invokes stall diagnosis or forces restart. This prevents indefinite hangs while allowing legitimate long-running operations.

**Threshold Configuration:**

| Threshold | Default | CLI Argument | Behavior |
| --- | --- | --- | --- |
| Soft Idle | 3600s (1h) | `--stall-soft-idle-seconds` | Run stall diagnosis agent |
| Hard Idle | 10800s (3h) | `--stall-hard-idle-seconds` | Force kill + restart |

**Stall Detection Flow:**

[State Diagram]

**Sources:**[codex_autoloop/cli.py226-242](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L226-L242)[README.md400-404](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L400-L404)[README.md225-227](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L225-L227)

---

## External Control and Interrupts

The loop system supports real-time intervention through control commands that modify execution state between rounds. Commands are processed at the start of each round iteration, before the main agent executes. The state store maintains queued control requests which are consumed and applied during the round preparation phase.

### Control Command Types

[Flowchart Diagram]

**Control Command Handlers:**

| Command | Method | Effect |
| --- | --- | --- |
| `/inject <text>` | `state_store.request_inject()` | Appends to operator_messages.md, broadcast to all agents |
| `/plan <direction>` | `state_store.request_plan_direction()` | Plan-only direction, visible to planner agent |
| `/review <criteria>` | `state_store.request_review_criteria()` | Review-only criteria, visible to reviewer agent |
| `/stop` | `state_store.request_stop()` | Sets stop flag, loop exits after current round |
| `/mode <off\|auto\|record>` | `state_store.request_plan_mode()` | Hot-switches planner mode during execution |

**Sources:**[codex_autoloop/apps/cli_app.py289-414](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L289-L414)[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py) (referenced), [README.md149-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L149-L166)

---

## Stop Conditions

The loop terminates when one of five distinct conditions is met. Each condition has specific precedence and handling logic to ensure clean shutdown and proper state recording.

### Stop Condition Precedence

[Flowchart Diagram]

**Stop Condition Details:**

| Condition | Check Order | Exit Code | Success Flag | Description |
| --- | --- | --- | --- | --- |
| `user_stop` | 1st | 2 | false | User sent `/stop` command |
| `max_rounds` | 2nd | 2 | false | `round_index >= max_rounds` (default 500) |
| `reviewer_blocked` | 3rd | 2 | false | Reviewer returned `status: blocked` |
| `no_progress` | 4th | 2 | false | `max_no_progress_rounds` consecutive identical summaries (default 3) |
| `done` | 5th | 0 | true | Reviewer returned `status: done` AND all checks passed |

**No-Progress Detection:**

The system tracks the main agent's summary output across rounds. If `max_no_progress_rounds` consecutive rounds produce identical summary text (after normalization), the loop terminates with `stop_reason: no_progress`. This prevents infinite loops when the agent is stuck or repeating the same ineffective action.

**Sources:**[codex_autoloop/cli.py101-107](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L101-L107)[README.md621-625](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L621-L625)[codex_autoloop/core/engine.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/engine.py) (referenced)

---

## Acceptance Checks

Acceptance checks are shell commands executed after each main agent round to validate external success criteria (tests, linting, builds). All checks must pass for the loop to complete successfully, even if the reviewer returns `done` status.

### Check Execution Model

[Flowchart Diagram]

**Check Configuration:**

| Parameter | CLI Argument | Default | Purpose |
| --- | --- | --- | --- |
| `check_commands` | `--check` (repeatable) | `[]` | Shell commands to execute |
| `check_timeout_seconds` | `--check-timeout-seconds` | 1200 | Timeout per check command |

**Check Result Structure:**

Each check execution produces a result record containing:

- `command`: The shell command executed
- `exit_code`: Process exit code (0 = success)
- `stdout`: Standard output capture
- `stderr`: Standard error capture
- `passed`: Boolean derived from `exit_code == 0`
- `timed_out`: Boolean indicating timeout occurred

The reviewer agent receives check results as part of its context and can factor them into its decision. However, the loop enforces that checks must pass for successful completion regardless of reviewer opinion.

**Sources:**[codex_autoloop/cli.py109-118](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L109-L118)[codex_autoloop/apps/cli_app.py438](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L438-L438)[README.md196-198](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L196-L198)

---

## State Progression Across Rounds

Each round modifies the loop state by appending round data, updating session context, and recording agent outputs. The `LoopStateStore` persists this progression to `state_file` (JSON) and various markdown artifacts.

### State Artifacts

[Flowchart Diagram]

**Round Append Cycle:**

1. **Pre-Round:** Read current state from `state_file`, load `session_id` and round history
2. **Main Execution:** Execute main agent, capture output, extract summary
3. **Check Execution:** Run all acceptance checks, record results
4. **Planner Sweep:** (if enabled) Update `plan_report.md`, append plan data
5. **Reviewer Execution:** Run reviewer, parse JSON response
6. **Round Record:** Append complete round data to `rounds` array
7. **State Write:** Serialize updated state to `state_file`
8. **Markdown Write:** Update `operator_messages.md`, `main_prompt.md`, `review_summaries/`

**Sources:**[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py) (referenced), [codex_autoloop/apps/cli_app.py72-81](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L72-L81) Diagram 4 from high-level architecture

---

## Configuration Reference

The multi-agent loop system is configured through `LoopConfig` which aggregates all execution parameters. This configuration is built from CLI arguments or daemon preset defaults.

### LoopConfig Structure

[Class Diagram]

**Default Values:**

| Field | Default | Environment Variable | Notes |
| --- | --- | --- | --- |
| `max_rounds` | 500 | - | Upper bound on iterations |
| `max_no_progress_rounds` | 3 | - | No-progress detection threshold |
| `check_timeout_seconds` | 1200 | - | 20 minutes per check |
| `plan_mode` | `"auto"` | - | Setup wizard default |
| `stall_soft_idle_seconds` | 3600 | - | 1 hour soft threshold |
| `stall_hard_idle_seconds` | 10800 | - | 3 hours hard threshold |
| `dangerous_yolo` | `false` (CLI), `true` (daemon) | - | Daemon enables by default |

**Model Resolution Priority:**

When model or reasoning effort is not explicitly set, the system follows this resolution order:

1. Explicit CLI argument (`--main-model`, `--reviewer-model`, etc.)
2. Preset value from `--run-model-preset` (daemon mode)
3. Codex CLI global config defaults

**Sources:**[codex_autoloop/apps/cli_app.py433-455](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L433-L455)[codex_autoloop/cli.py73-408](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L73-L408)[README.md20-23](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L20-L23)

---

## Loop Result Structure

Upon loop termination, the `LoopEngine` returns a result object containing success status, stop reason, session ID, and per-round details. This result is serialized to JSON for programmatic consumption.

### Result Payload

```
{
  "success": true,
  "session_id": "session-abc123",
  "stop_reason": "done",
  "plan_mode": "auto",
  "main_prompt_file": "/path/to/main_prompt.md",
  "plan_overview_file": "/path/to/plan_report.md",
  "review_summaries_dir": "/path/to/review_summaries/",
  "rounds": [
    {
      "round": 1,
      "thread_id": "thread-xyz",
      "main_exit_code": 0,
      "main_turn_completed": true,
      "main_turn_failed": false,
      "review_status": "continue",
      "review_confidence": "high",
      "review_reason": "Feature implemented, tests need update",
      "check_count": 1,
      "checks_passed": false,
      "plan_next_explore": "Update test fixtures"
    },
    {
      "round": 2,
      "thread_id": "thread-xyz",
      "main_exit_code": 0,
      "main_turn_completed": true,
      "main_turn_failed": false,
      "review_status": "done",
      "review_confidence": "high",
      "review_reason": "All tests passing, feature complete",
      "check_count": 1,
      "checks_passed": true,
      "plan_next_explore": null
    }
  ]
}
```

**Result Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `success` | boolean | True if loop completed with `done` + checks passed |
| `session_id` | string | Codex session ID for potential resumption |
| `stop_reason` | string | One of: `done`, `max_rounds`, `reviewer_blocked`, `no_progress`, `user_stop` |
| `plan_mode` | string | Planner mode active during execution |
| `main_prompt_file` | string | Path to latest main prompt markdown |
| `plan_overview_file` | string | Path to plan report markdown |
| `review_summaries_dir` | string | Path to review summaries directory |
| `rounds` | array | Per-round execution details |

**Sources:**[codex_autoloop/apps/cli_app.py460-484](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L460-L484)[codex_autoloop/core/engine.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/engine.py) (referenced)