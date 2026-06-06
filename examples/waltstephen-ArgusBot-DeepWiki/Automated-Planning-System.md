# Automated Planning System
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py)
- [tests/test_telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py)

## Purpose and Scope

This document describes ArgusBot's automated planning system, which enables the daemon to automatically propose and execute follow-up objectives after a run completes. The planning system operates in three distinct modes (`off`, `record`, `auto`) and integrates with the multi-agent loop to provide continuity across work sessions.

For information about the planner agent itself (background sweeps, plan reports), see [Agent System](/waltstephen/ArgusBot/4.2-reviewer-sub-agent). For session continuity and resumption, see [Session Management and Resumption](/waltstephen/ArgusBot/7.1-session-management-and-resumption). For daemon lifecycle and child process management, see [Daemon Mode Architecture](/waltstephen/ArgusBot/3.2-daemon-mode-architecture).

---

## Planning Modes Overview

The planning system supports three operational modes that control post-run behavior. The mode is configured at daemon startup via `--run-planner-mode` and can be changed at runtime via the `/mode` command.

| Mode | Identifier | Plan Agent Enabled | Follow-Up Proposal | Auto-Execution | Record to Table |
| --- | --- | --- | --- | --- | --- |
| **Off** | `off` | No | No | No | No |
| **Record** | `record` | Yes | No | No | Yes |
| **Auto** | `auto` | Yes | Yes | Yes | No |

**Sources:**[README.md168-172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L168-L172)[codex_autoloop/telegram_daemon.py39-42](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L39-L42)

---

## Mode Behavior Details

### Off Mode (`execute-only`)

When planner mode is `off`, the daemon executes runs without any planning capabilities:

- Planner agent is disabled for all child runs
- No follow-up proposals are generated after completion
- No plan records are written
- Daemon returns to idle state immediately after child exit

This mode is suitable for manual operation where the user provides all objectives explicitly.

**Implementation:** The daemon checks `plan_mode == PLAN_MODE_EXECUTE_ONLY` at [codex_autoloop/telegram_daemon.py902-904](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L902-L904) and clears planner state immediately.

**Sources:**[codex_autoloop/telegram_daemon.py39](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L39-L39)[codex_autoloop/telegram_daemon.py902-904](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L902-L904)

---

### Record Mode (`record-only`)

Record mode enables the planner agent but only logs results to a markdown table without proposing follow-ups:

- Planner agent runs background sweeps during execution
- After run completion, a row is appended to `plan-agent-records.md`
- Record includes: timestamp, objective, exit code, review status, session ID, log path
- Daemon returns to idle state after recording

This mode is useful for tracking execution history while maintaining manual control over follow-up decisions.

**Record Table Format:**

```
| finished_at | objective | exit_code | review_status | review_next_action | session_id | log |
|---|---|---:|---|---|---|---|
| 2024-01-15T10:30:00Z | Implement feature X | 0 | done | ... | sess_abc123 | .argusbot/logs/run-20240115-103000.log |
```

**Implementation:** The daemon calls `append_plan_record_row` at [codex_autoloop/telegram_daemon.py914-922](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L914-L922) to write table rows.

**Sources:**[codex_autoloop/telegram_daemon.py40](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L40-L40)[codex_autoloop/telegram_daemon.py908-934](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L908-L934)[codex_autoloop/telegram_daemon.py1868-1900](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1868-L1900)

---

### Auto Mode (`fully-plan`)

Auto mode provides full automated planning with follow-up proposals and optional auto-execution:

1. **Run Completion:** Child process exits
2. **Eligibility Check:** Verify conditions for follow-up (exit code, review status, planner state)
3. **Delay Phase:** Schedule plan request generation after `plan_request_delay_seconds`
4. **Request Generation:** Build follow-up objective from state context
5. **Countdown Phase:** Auto-execute after `plan_auto_execute_delay_seconds` unless overridden
6. **Execution:** Launch new child run with proposed objective

Users can intervene during countdown via `/run` or `/inject` commands, which clear the pending plan and execute the manual objective instead.

**Sources:**[README.md168-172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L168-L172)[codex_autoloop/telegram_daemon.py41](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L41-L41)[codex_autoloop/telegram_daemon.py936-1037](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L936-L1037)

---

## Auto Mode Workflow Diagram

[State Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py893-1037](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L893-L1037)[codex_autoloop/telegram_daemon.py975-1037](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L975-L1037)

---

## Follow-Up Eligibility Conditions

Before scheduling a plan request, the daemon evaluates several conditions at [codex_autoloop/telegram_daemon.py1627-1636](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1627-L1636):

### Eligibility Check Logic

[Flowchart Diagram]

**Conditions:**

1. **Exit Code:** Run must complete successfully (exit code 0)
2. **Review Status:** Reviewer must not mark the run as `blocked`
3. **Planner State:**`latest_plan.follow_up_required` must not be explicitly `False`

**Sources:**[codex_autoloop/telegram_daemon.py1627-1636](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1627-L1636)

---

## Plan Request Generation

When conditions are met, the daemon builds a follow-up objective using `build_plan_request()` at [codex_autoloop/telegram_daemon.py1681-1719](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1681-L1719) The function uses a priority hierarchy to select the most appropriate next objective.

### Priority Hierarchy

[Flowchart Diagram]

### Priority Order

1. **Planner Main Instruction** (highest priority): From `state_payload.latest_plan.main_instruction`
2. **Planner Report Objective**: Extracted from `## Suggested Next Objective` section in `plan_report.md`
3. **Reviewer Next Action**: From `state_payload.rounds[-1].review.next_action` (if actionable)
4. **Fallback Objective** (lowest priority): Generic continuation message with context

**Sources:**[codex_autoloop/telegram_daemon.py1681-1719](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1681-L1719)[codex_autoloop/telegram_daemon.py1810-1840](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1810-L1840)

---

## State Variables and Timers

The daemon maintains several state variables to track planning workflow at [codex_autoloop/telegram_daemon.py308-317](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L308-L317):

### Daemon Planning State

| Variable | Type | Purpose |
| --- | --- | --- |
| `scheduled_plan_context` | `dict[str, Any]` | Context from completed run (objective, exit_code, state_payload, paths) |
| `scheduled_plan_request_at` | `datetime` | Timestamp when plan request should be generated |
| `pending_plan_request` | `str` | Generated follow-up objective text |
| `pending_plan_generated_at` | `datetime` | Timestamp when request was generated |
| `pending_plan_auto_execute_at` | `datetime` | Timestamp when auto-execution should trigger |

### Timer Processing

The daemon runs `process_planner_timers()` every 1 second at [codex_autoloop/telegram_daemon.py1083-1124](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1083-L1124) This function:

1. **Checks Mode:** Only processes if `plan_mode == PLAN_MODE_FULLY_PLAN`
2. **Checks Child State:** Only processes if no child is running
3. **Auto-Execute Check:** If `pending_plan_auto_execute_at` is reached, launches child
4. **Request Generation Check:** If `scheduled_plan_request_at` is reached, generates request

**Sources:**[codex_autoloop/telegram_daemon.py308-317](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L308-L317)[codex_autoloop/telegram_daemon.py975-1037](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L975-L1037)

---

## Clear State Mechanism

The daemon provides `clear_planner_state()` at [codex_autoloop/telegram_daemon.py381-396](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L381-L396) to reset all planning variables. This is called when:

- Child process starts (reason: `child_started`)
- Manual `/run` or `/inject` overrides pending plan (reason: `manual_override`)
- Daemon stops (reason: `daemon_stopped`)
- Planning is skipped due to eligibility failure (reason varies)

```
def clear_planner_state(*, reason: str | None = None) -> None:
    """Reset all planning state variables and optionally log the reason."""
    # Sets pending_plan_request = None
    # Sets pending_plan_auto_execute_at = None
    # Sets scheduled_plan_context = None
    # Sets scheduled_plan_request_at = None
```

**Sources:**[codex_autoloop/telegram_daemon.py381-396](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L381-L396)

---

## Configuration Parameters

### Daemon Arguments

| Argument | Default | Description |
| --- | --- | --- |
| `--run-planner-mode` | `auto` | Planning mode: `off`, `record`, or `auto` |
| `--run-plan-request-delay-seconds` | `0` | Delay before generating plan request after run completion |
| `--run-plan-auto-execute-delay-seconds` | `0` | Delay before auto-executing generated plan |
| `--follow-up-auto-execute-seconds` | `600` | Legacy parameter for follow-up countdown (10 minutes) |
| `--run-plan-record-file` | `.argusbot/logs/plan-agent-records.md` | Path for record-mode table output |

### Runtime Mode Changes

The `/mode` command at [codex_autoloop/telegram_daemon.py721-741](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L721-L741) allows hot-switching planner mode:

```
# From terminal or Telegram
/mode auto    # Enable auto planning
/mode record  # Enable record-only mode
/mode off     # Disable planning
```

Mode changes affect:

- Default mode for future runs (`args.run_planner_mode`)
- Active child run (forwarded via `child_control_bus`)

**Sources:**[codex_autoloop/telegram_daemon.py2049-2077](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L2049-L2077)[codex_autoloop/telegram_daemon.py721-741](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L721-L741)

---

## Interaction with Daemon Commands

### Manual Override Flow

When a user sends `/run` or `/inject` during countdown phase:

1. Daemon detects command at [codex_autoloop/telegram_daemon.py822-856](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L822-L856)
2. Calls `clear_planner_state(reason="manual_override")` at [codex_autoloop/telegram_daemon.py853](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L853-L853)
3. Notifies user that pending plan was cleared
4. Executes manual objective immediately

### Status Reporting

The `/status` command includes planning state at [codex_autoloop/telegram_daemon.py672-696](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L672-L696):

```
[daemon] status=idle
planner_mode=auto
pending_plan_request=Continue implementing feature X and run tests
plan_auto_execute_at=2024-01-15T10:45:00Z

```

**Sources:**[codex_autoloop/telegram_daemon.py822-856](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L822-L856)[codex_autoloop/telegram_daemon.py1372-1434](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1372-L1434)

---

## Plan Context Building

The daemon builds `scheduled_plan_context` at [codex_autoloop/telegram_daemon.py952-958](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L952-L958) with:

```
{
    "objective": str,              # Original run objective
    "exit_code": int,              # Child process exit code
    "log_path": str,               # Path to run log
    "state_payload": dict,         # Full state from last_state.json
    "plan_report_path": str,       # Path to plan_report.md
}
```

This context is passed to `build_plan_request()` to generate the next objective.

**Sources:**[codex_autoloop/telegram_daemon.py952-973](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L952-L973)

---

## State Extraction Functions

The daemon uses several helper functions to extract information from `state_payload`:

### `extract_latest_plan()`

Extracts planner state from `state_payload.latest_plan` at [codex_autoloop/telegram_daemon.py1792-1807](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1792-L1807):

```
@dataclass
class LatestPlanState:
    follow_up_required: bool | None      # Whether follow-up is needed
    main_instruction: str                # Planner's proposed objective
```

### `extract_latest_review()`

Extracts reviewer information from last round at [codex_autoloop/telegram_daemon.py1843-1865](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1843-L1865):

```
# Returns tuple: (status, reason, next_action)
# Example: ("continue", "Tests failing", "Fix test failures before proceeding")
```

### `extract_suggested_next_objective_from_plan_report()`

Parses `plan_report.md` to find content under `## Suggested Next Objective` section at [codex_autoloop/telegram_daemon.py1810-1840](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1810-L1840)

**Sources:**[codex_autoloop/telegram_daemon.py1792-1865](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1792-L1865)[codex_autoloop/telegram_daemon.py1810-1840](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1810-L1840)

---

## Sanitization and Validation

### Objective Sanitization

The function `sanitize_follow_up_objective()` at [codex_autoloop/telegram_daemon.py1722-1738](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1722-L1738) cleans proposed objectives:

1. Strips leading `/run` or `run` prefixes
2. Removes objective context suffixes like `（目标上下文：...）`
3. Returns clean, executable objective text

### Terminal Handoff Detection

The function `looks_like_terminal_handoff_instruction()` at [codex_autoloop/telegram_daemon.py1767-1783](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1767-L1783) identifies non-actionable reviewer instructions:

- "wait for the user's next instruction"
- "stop the autoloop"
- "等待用户下一步指令"

These are filtered out to prevent auto-proposing idle commands.

**Sources:**[codex_autoloop/telegram_daemon.py1722-1783](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1722-L1783)

---

## Integration with Loop State

The planning system reads from `last_state.json` via `read_status()` at [codex_autoloop/telegram_daemon.py906](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L906-L906):

### Required State Fields

- `session_id`: For session continuity
- `latest_review_status`: For eligibility checking
- `latest_plan`: For follow-up proposal extraction
- `rounds[]`: For extracting last review details

The daemon checks `is_force_fresh_session_requested()` at [codex_autoloop/telegram_daemon.py401](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L401-L401) and passes `resume_session_id=None` if fresh session is armed, ensuring follow-up runs can start fresh.

**Sources:**[codex_autoloop/telegram_daemon.py906](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L906-L906)[codex_autoloop/telegram_daemon.py1455-1461](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1455-L1461)

---

## Event Logging

The daemon logs planning events to `daemon-events.jsonl`:

| Event Type | When | Key Fields |
| --- | --- | --- |
| `plan.scheduled` | Request generation scheduled | `scheduled_request_at`, `objective` |
| `plan.proposed` | Request generated | `request`, `auto_execute_at` |
| `plan.auto_execute` | Auto-execution triggered | `request` |
| `plan.cleared` | State cleared | `reason` |
| `plan.recorded` | Row appended in record mode | `record_file`, `objective`, `exit_code` |
| `plan.skipped` | Follow-up skipped | `reason`, `objective`, `exit_code` |

**Sources:**[codex_autoloop/telegram_daemon.py396](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L396-L396)[codex_autoloop/telegram_daemon.py922-928](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L922-L928)[codex_autoloop/telegram_daemon.py963-973](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L963-L973)[codex_autoloop/telegram_daemon.py1028-1037](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1028-L1037)

---

## Fallback Objective Template

When no high-priority objective source is available, the daemon constructs a fallback at [codex_autoloop/telegram_daemon.py1710-1719](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1710-L1719):

```
parts = [f"继续推进目标：{objective_text}"]
if exit_code != 0:
    parts.append("先定位并修复上一轮失败原因。")
if review_reason:
    parts.append(f"优先关注：{review_reason}")
if review_status:
    parts.append(f"当前审核状态：{review_status}")
if not review_reason:
    parts.append("补齐剩余实现并运行关键验证命令后再继续。")
return " ".join(parts).strip()
```

This ensures the daemon can always propose a reasonable continuation even with minimal state information.

**Sources:**[codex_autoloop/telegram_daemon.py1710-1719](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1710-L1719)

---

## Skip Messages

When follow-up is skipped, the daemon sends user-friendly explanations via `build_plan_skip_message()` at [codex_autoloop/telegram_daemon.py1639-1666](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1639-L1666):

### Skip Reasons

| Reason | Message |
| --- | --- |
| `planner_no_follow_up` | "Planner did not propose a follow-up objective. The last run appears complete..." |
| `review_blocked` | "Skip auto-plan (review_blocked). The reviewer marked the run as blocked..." |
| `last_run_failed` | "Skip auto-plan (last_run_failed). The previous run exited non-zero..." |

**Sources:**[codex_autoloop/telegram_daemon.py1639-1666](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1639-L1666)