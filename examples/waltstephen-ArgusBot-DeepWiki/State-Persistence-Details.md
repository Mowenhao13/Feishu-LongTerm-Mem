# State Persistence Details
Relevant source files
- [codex_autoloop/apps/cli_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py)
- [codex_autoloop/apps/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py)
- [codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py)
- [tests/test_telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py)

## Purpose and Scope

This page provides a deep dive into how ArgusBot persists state across runs, enabling session resumption, audit trails, and error recovery. It covers the structure of state files, session resolution logic, and the various persistence mechanisms used by both daemon and CLI modes.

For information about how sessions are resolved and resumed at runtime, see [Session Management and Resumption](/waltstephen/ArgusBot/7.1-session-management-and-resumption). For the overall architecture of state management, see [State Management and Persistence](/waltstephen/ArgusBot/3.5-state-management-and-persistence).

---

## State File Formats

ArgusBot maintains state through multiple file formats, each serving a specific persistence purpose. The system uses a combination of JSON snapshots, JSONL event logs, and markdown artifacts to create a comprehensive audit trail.

### JSON State Snapshots

The primary state file (`last_state.json` by default) contains a complete snapshot of the current loop execution state. This file is written after each round completes and serves as the authoritative source for session resumption.

**Core Structure:**

| Field | Type | Purpose |
| --- | --- | --- |
| `session_id` | string | Codex thread identifier for continuity |
| `rounds` | array | History of all completed rounds |
| `latest_review_status` | string | Cached status from most recent review |
| `latest_plan` | object | Cached plan data with follow-up directives |
| `force_fresh_session` | boolean | Flag to prevent session resumption |
| `force_fresh_reason` | string | Reason why fresh session was requested |

**Round Entry Structure:**

Each entry in the `rounds` array contains:

```
{
  "round": 1,
  "thread_id": "thread_abc123",
  "main_exit_code": 0,
  "main_turn_completed": true,
  "review": {
    "status": "continue",
    "reason": "Tests still failing",
    "next_action": "Fix the failing test in test_api.py",
    "confidence": "high"
  },
  "plan": {
    "follow_up_required": true,
    "main_instruction": "Continue to next phase"
  },
  "checks": [
    {"command": "pytest -q", "passed": false}
  ]
}
```

**Sources:**[codex_autoloop/telegram_daemon.py906-950](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L906-L950)[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py)[tests/test_telegram_daemon.py280-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L280-L324)

### JSONL Event Logs

ArgusBot maintains two primary JSONL event logs that record timestamped events with full context:

#### Archive Log (argusbot-run-archive.jsonl)

Records lifecycle events for all runs. Each line is a JSON object with:

```
{
  "ts": "2026-01-15T10:30:00.123456Z",
  "date": "2026-01-15",
  "event": "run.started",
  "workspace": "/home/user/project",
  "run_id": "20260115-103000",
  "pid": 12345,
  "objective": "Fix the API tests",
  "resume_session_id": "thread_abc123",
  "force_fresh_session": false
}
```

**Key Events:**

- `run.started` - Run initiated with objective
- `run.finished` - Run completed with session_id
- `session.fresh.requested` - User requested fresh session
- `session.fresh.applied` - Fresh session applied to run

**Sources:**[codex_autoloop/telegram_daemon.py353-363](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L353-L363)[codex_autoloop/telegram_daemon.py522-534](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L522-L534)

#### Daemon Events Log (daemon-events.jsonl)

Records daemon operational events:

```
{
  "ts": "2026-01-15T10:00:00Z",
  "type": "daemon.started",
  "run_cwd": "/home/user/project",
  "logs_dir": "/home/user/project/.argusbot",
  "bus_dir": "/home/user/project/.argusbot/bus"
}
```

**Key Event Types:**

- `daemon.started` - Daemon process initialized
- `child.launched` - Child run process spawned
- `child.finished` - Child run completed
- `command.received` - Control command received
- `plan.scheduled` - Plan follow-up scheduled
- `plan.proposed` - Plan objective generated

**Sources:**[codex_autoloop/telegram_daemon.py344-351](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L344-L351)[codex_autoloop/apps/daemon_app.py518-525](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L518-L525)

### Markdown Artifacts

ArgusBot writes human-readable markdown files that serve as both persistence and operator visibility:

#### operator_messages.md

Records all operator interactions (injects, plan directions, review criteria) with timestamp and source attribution. Shared across all agents for global context.

```
- 2026-01-15 10:30:00 UTC - operator (`broadcast`): Fix the failing API tests
- 2026-01-15 10:35:00 UTC - operator (`plan`): Focus on authentication layer
- 2026-01-15 10:40:00 UTC - operator (`review`): Check that all endpoints return proper status codes
```

**Sources:**[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py)[codex_autoloop/telegram_daemon.py249](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L249-L249)

#### plan_report.md / plan_overview.md

Strategic overview maintained by the planner agent, updated during background sweeps:

```
# Planning Snapshot
 
## Current Objective
Fix the failing API tests
 
## Progress Summary
- Authentication tests passing
- Rate limiting tests still failing
 
## Suggested Next Objective
Implement proper rate limit error handling in the client library
 
## Reviewer Context
- Status: continue
- Reason: Rate limit tests failing
```

**Sources:**[codex_autoloop/telegram_daemon.py458](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L458-L458)[codex_autoloop/apps/daemon_app.py391](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L391-L391)

#### review_summaries/

Directory containing per-round review summaries:

- `index.md` - Latest review summary
- `round-001.md`, `round-002.md`, etc. - Historical reviews

**Sources:**[codex_autoloop/telegram_daemon.py460](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L460-L460)[codex_autoloop/apps/daemon_app.py392](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L392-L392)

---

## Session Resolution Strategy

ArgusBot uses a two-tier fallback strategy to resolve which session to resume, with explicit override capability.

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py1267-1289](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1267-L1289)[tests/test_telegram_daemon.py298-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L298-L324)

### Resolution Functions

**Primary Resolution:**

- `resolve_resume_session_id(state_file, archive_file)` - Main entry point, implements fallback chain
- `resolve_saved_session_id(state_file)` - Reads session_id from JSON state snapshot
- `resolve_last_session_id_from_archive(archive_file)` - Scans JSONL for latest `run.finished` event

**Force Fresh Mechanism:**

- `is_force_fresh_session_requested(state_file)` - Checks if `force_fresh_session` flag is set
- `set_force_fresh_session_marker(state_file, enabled, reason)` - Sets/clears the flag with reason
- Triggered by `/new` command or automatic error recovery

**Sources:**[codex_autoloop/telegram_daemon.py1267-1335](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1267-L1335)[tests/test_telegram_daemon.py312-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L312-L324)

### Preference Order

1. **force_fresh_session flag** - Explicit override, always wins
2. **state_file** - Current snapshot, preferred for continuity
3. **archive_file** - Event log fallback, scans for last `run.finished`
4. **None** - Fresh session when no prior state exists

---

## State Writing and Reading Mechanisms

### Write Operations

State is written through the `LoopStateStore` component, which maintains consistency across multiple file formats simultaneously.

[Flowchart Diagram]

**Sources:**[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py)

### Atomic Write Pattern

State files use atomic write-and-replace to prevent corruption:

```
# Pattern used in state persistence
temp_path = state_file.with_suffix(".tmp")
temp_path.write_text(json.dumps(payload), encoding="utf-8")
temp_path.replace(state_file)  # Atomic on POSIX systems
```

This ensures that even if the process crashes mid-write, the state file remains valid (either old or new, never corrupted).

**Sources:**[codex_autoloop/daemon_bus.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py)

### Read Operations

Reading state is defensive with multiple fallback levels:

[Flowchart Diagram]

**Sources:**[codex_autoloop/daemon_bus.py50-63](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py#L50-L63)

---

## Recovery Mechanisms

ArgusBot implements multiple layers of error recovery to handle corruption and invalid state.

### Invalid Encrypted Content Detection

When Codex CLI encounters corrupt session data, it returns an "Invalid Encrypted Content" error. ArgusBot detects this and automatically sets the `force_fresh_session` flag.

**Detection Flow:**

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py1347-1357](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1347-L1357)[tests/test_telegram_daemon.py327-333](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L327-L333)

### Implementation Details

**Detection Function:**

```
log_contains_invalid_encrypted_content(log_path: Path) -> bool

```

Performs case-insensitive search through log file for the marker string. Returns `True` if corruption is detected.

**Auto-Recovery:**

```
# After child exits with error
if log_contains_invalid_encrypted_content(child_log_path):
    set_force_fresh_session_marker(state_file, enabled=True, 
                                   reason="invalid_encrypted_content_detected")

```

**Sources:**[codex_autoloop/telegram_daemon.py1347-1357](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1347-L1357)[codex_autoloop/telegram_daemon.py43-45](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L43-L45)

### Manual Recovery

Users can manually trigger fresh session via:

- `/new` command - Sets flag for next run
- `daemon-ctl new` - CLI utility to set flag
- Direct state file edit - Set `force_fresh_session: true`

Once the flag is set, the next `/run` command will ignore any saved `session_id` and start fresh. The flag is automatically cleared after being consumed.

**Sources:**[codex_autoloop/telegram_daemon.py697-720](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L697-L720)[tests/test_telegram_daemon.py312-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L312-L324)

---

## Daemon State Files

The daemon process maintains separate operational state from run session state, allowing it to manage multiple runs over time.

### Daemon Status (daemon_status.json)

Updated continuously as daemon state changes, providing runtime visibility:

```
{
  "updated_at": "2026-01-15T10:30:00Z",
  "daemon_pid": 12345,
  "daemon_running": true,
  "running": true,
  "child_pid": 12346,
  "child_objective": "Fix API tests",
  "child_log_path": "/home/user/project/.argusbot/run-20260115-103000.log",
  "child_main_prompt_path": "/home/user/project/.argusbot/run-20260115-103000-main-prompt.md",
  "child_plan_report_path": "/home/user/project/.argusbot/run-20260115-103000-plan-report.md",
  "child_started_at": "2026-01-15T10:30:00Z",
  "last_session_id": "thread_abc123",
  "force_fresh_session": false,
  "run_cwd": "/home/user/project",
  "logs_dir": "/home/user/project/.argusbot",
  "events_log": "/home/user/project/.argusbot/daemon-events.jsonl",
  "run_archive_log": "/home/user/project/.argusbot/argusbot-run-archive.jsonl",
  "operator_messages_file": "/home/user/project/.argusbot/operator_messages.md",
  "plan_mode": "auto",
  "btw_busy": false,
  "btw_session_id": null
}
```

**Key Fields:**

| Field | Purpose |
| --- | --- |
| `daemon_running` | Whether daemon main loop is active |
| `running` | Whether a child run is currently executing |
| `child_*` | Paths to artifacts from active/last run |
| `last_session_id` | Resolved session_id for next resumption |
| `force_fresh_session` | Whether next run will ignore session_id |
| `plan_mode` | Current planner mode (off/auto/record) |
| `btw_busy` | Whether BTW side-agent is processing query |

**Sources:**[codex_autoloop/telegram_daemon.py398-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L398-L444)[codex_autoloop/apps/daemon_app.py482-516](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L482-L516)

### Daemon PID File (daemon.pid)

Simple text file containing the daemon's process ID. Used for:

- Detecting if daemon is already running
- Sending signals to daemon process
- Cleanup on daemon shutdown

**Sources:**[codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py)

### Process Relationship

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py296-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L296-L444)[codex_autoloop/apps/daemon_app.py482-516](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L482-L516)

---

## File Locations and Naming Conventions

### Default Locations

ArgusBot follows a consistent directory structure for state persistence:

```
.argusbot/
├── last_state.json              # Current session state
├── argusbot-run-archive.jsonl   # Run history log
├── daemon-events.jsonl          # Daemon lifecycle log
├── daemon_status.json           # Daemon runtime status
├── daemon.pid                   # Daemon process ID
├── operator_messages.md         # Operator interaction log
├── plan-agent-records.md        # Plan mode=record table
├── btw_messages.md             # BTW side-agent history
├── bus/
│   ├── daemon_commands.jsonl    # Control command bus
│   └── child-control-*.jsonl    # Per-run control bus
└── run-20260115-103000/        # Per-run artifacts
    ├── run-20260115-103000.log
    ├── run-20260115-103000-main-prompt.md
    ├── run-20260115-103000-plan-report.md
    ├── run-20260115-103000-todo.md
    └── run-20260115-103000-review/
        ├── index.md
        ├── round-001.md
        └── round-002.md

```

**Sources:**[codex_autoloop/telegram_daemon.py243-249](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L243-L249)[codex_autoloop/telegram_daemon.py454-460](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L454-L460)

### Timestamped Artifacts

Run-specific files use timestamp prefixes for uniqueness and chronological ordering:

**Format:**`run-YYYYMMDD-HHMMSS-ffffff`

Example: `run-20260115-103000-123456`

This pattern ensures:

- Lexicographic sorting matches chronological order
- No filename collisions for concurrent runs
- Easy identification of run time from filename

**Sources:**[codex_autoloop/telegram_daemon.py454](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L454-L454)[codex_autoloop/apps/daemon_app.py386](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L386-L386)

### Configuration Override

File paths can be overridden via CLI arguments:

| Default | CLI Argument | Purpose |
| --- | --- | --- |
| `.argusbot/last_state.json` | `--state-file` | Session state snapshot |
| `.argusbot/operator_messages.md` | `--operator-messages-file` | Operator interaction log |
| `.argusbot/run-*-plan-report.md` | `--plan-report-file` | Plan overview output |
| `.argusbot/run-*-review/` | `--review-summaries-dir` | Review summaries directory |
| `.argusbot/run-*-main-prompt.md` | `--main-prompt-file` | Latest main prompt |

**Sources:**[codex_autoloop/apps/cli_app.py49-78](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L49-L78)[codex_autoloop/telegram_daemon.py446-479](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L446-L479)

---

## State Store Implementation

The `LoopStateStore` class centralizes all state persistence operations, maintaining consistency across multiple file formats.

### Core Methods

**State Lifecycle:**

```
__init__(objective, state_file, operator_messages_file, ...)
  └─> Initializes file paths and loads existing state

save_state()
  ├─> Writes last_state.json with full state snapshot
  ├─> Updates operator_messages.md with new entries
  ├─> Writes main_prompt.md with current prompt
  └─> Updates review_summaries/ if review completed

record_message(text, source, kind)
  └─> Appends to operator_messages.md with timestamp

request_inject(text, source)
request_plan_direction(text, source)
request_review_criteria(text, source)
  └─> Records targeted operator inputs by kind

```

**Read Operations:**

```
read_plan_overview_markdown() -> str | None
read_main_prompt_markdown() -> str | None
read_review_summaries_markdown(round_index) -> str | None
render_plan_context_markdown() -> str
render_review_context_markdown() -> str

```

**Sources:**[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py)

### State Snapshot Structure

When `save_state()` is called, it constructs a complete payload:

```
{
  "session_id": self.session_id,
  "rounds": [
    {
      "round": round_obj.round_index,
      "thread_id": round_obj.thread_id,
      "main_exit_code": round_obj.main_exit_code,
      "review": {
        "status": round_obj.review.status,
        "reason": round_obj.review.reason,
        "next_action": round_obj.review.next_action
      },
      "plan": round_obj.plan.to_dict() if round_obj.plan else None,
      "checks": [...]
    }
    for round_obj in self.rounds
  ],
  "latest_review_status": self.latest_review_status,
  "latest_plan": self.latest_plan.to_dict() if self.latest_plan else None
}
```

**Sources:**[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py)

---

## Archive Log Event Types

The archive log (`argusbot-run-archive.jsonl`) records a comprehensive history of all runs. Understanding these event types enables powerful audit capabilities.

### Event Type Reference

| Event Type | When Emitted | Key Fields |
| --- | --- | --- |
| `run.started` | Child process spawned | `run_id`, `objective`, `resume_session_id`, `force_fresh_session` |
| `run.finished` | Child process exited | `session_id`, `exit_code`, `stop_reason` |
| `session.fresh.requested` | `/new` command received | `source`, `running`, `active_run_id` |
| `session.fresh.applied` | Fresh session flag consumed | `run_id` |

**Querying Archive:**

The archive log enables queries like:

- "What was the last successful run?" - Find latest `run.finished` with `exit_code=0`
- "Which runs used session X?" - Grep for `session_id` field
- "When was fresh session requested?" - Find `session.fresh.requested` events

**Sources:**[codex_autoloop/telegram_daemon.py353-363](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L353-L363)[codex_autoloop/telegram_daemon.py522-534](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L522-L534)[codex_autoloop/telegram_daemon.py704-719](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L704-L719)