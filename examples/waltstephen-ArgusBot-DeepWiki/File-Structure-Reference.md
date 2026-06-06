# File Structure Reference
Relevant source files
- [QUICKSTART.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1)
- [codex_autoloop/codexloop.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py)
- [codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py)
- [tests/test_codexloop.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_codexloop.py)

This page provides a comprehensive reference for all files and directories created and managed by ArgusBot. It documents the location, purpose, format, and lifecycle of each file type.

For information about the state persistence mechanism and session management, see [State Persistence Details](/waltstephen/ArgusBot/7.2-state-persistence-details). For configuration options that control these paths, see [Configuration Reference](/waltstephen/ArgusBot/8.2-cli-arguments-reference).

---

## Directory Structure Overview

ArgusBot uses a single root directory (default: `.argusbot/`) to store all persistent state, configuration, logs, and runtime artifacts. The directory is organized into functional subdirectories.

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py244-249](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L244-L249)[codex_autoloop/apps/daemon_app.py44-51](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L44-L51)

---

## Root Directory Files

### daemon_config.json

**Location:**`.argusbot/daemon_config.json`

**Purpose:** Persistent daemon configuration written by the setup wizard and read on daemon startup.

**Format:** JSON object containing:

- Control channel credentials (Telegram bot token, chat ID, Feishu app credentials)
- Model presets and overrides (main, reviewer, planner models and reasoning efforts)
- Default planner mode (`off`, `auto`, `record`)
- Default check commands
- Copilot proxy settings
- Run-time flags (YOLO, full-auto, skip git checks)

**Lifecycle:** Created by `argusbot init` or `argusbot-setup`. Updated when configuration is modified via setup wizard. Read on daemon startup.

**Example Structure:**

```
{
  "telegram_bot_token": "123456:ABC-DEF...",
  "telegram_chat_id": "987654321",
  "run_model_preset": "quality",
  "run_planner_mode": "auto",
  "run_check": ["pytest -q"],
  "run_yolo": true,
  "run_copilot_proxy": false
}
```

**Sources:**[README.md64](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L64-L64)[codex_autoloop/setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py) (referenced)

---

### daemon.pid

**Location:**`.argusbot/daemon.pid`

**Purpose:** Stores the process ID of the currently running daemon for process management and lock enforcement.

**Format:** Plain text file containing a single integer (PID).

**Lifecycle:** Created when daemon starts. Deleted when daemon stops gracefully. Used to detect stale daemons and enforce single-daemon-per-token policy.

**Sources:**[README.md488](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L488-L488) (referenced in documentation)

---

### daemon.out

**Location:**`.argusbot/daemon.out`

**Purpose:** Standard output and error stream capture for background daemon process.

**Format:** Plain text log stream.

**Lifecycle:** Created when daemon starts in background mode. Continuously appended during daemon operation. Can be monitored with `./scripts/watch_argusbot_logs.sh`.

**Sources:**[README.md513-516](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L513-L516)

---

## logs/ Directory

The `logs/` subdirectory contains all event logs, state files, run artifacts, and markdown documents.

### daemon-events.jsonl

**Location:**`.argusbot/logs/daemon-events.jsonl`

**Purpose:** Append-only event log for daemon lifecycle events and control interactions.

**Format:** JSON Lines (one JSON object per line), with fields:

- `ts`: ISO 8601 timestamp (UTC)
- `type`: Event type string (e.g., `daemon.started`, `child.launched`, `command.received`)
- Additional event-specific fields

**Event Types:**

| Event Type | Triggered When | Key Fields |
| --- | --- | --- |
| `daemon.started` | Daemon initialization complete | `run_cwd`, `logs_dir`, `bus_dir`, `token_hash` |
| `child.launched` | Run subprocess spawned | `pid`, `objective`, `log_path`, `resume_session_id` |
| `child.finished` | Run subprocess exited | `exit_code`, `objective`, `run_id` |
| `command.received` | Command parsed from any source | `source`, `kind`, `text` |
| `session.fresh.flagged` | Invalid encrypted content detected | `reason`, `log_path` |
| `plan.scheduled` | Follow-up plan generation scheduled | `scheduled_request_at`, `mode` |

**Lifecycle:** Created on daemon first start. Continuously appended. Never truncated or deleted during daemon lifetime.

**Sources:**[codex_autoloop/telegram_daemon.py247-351](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L247-L351)[codex_autoloop/apps/daemon_app.py49-525](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L49-L525)

---

### argusbot-run-archive.jsonl

**Location:**`.argusbot/logs/argusbot-run-archive.jsonl`

**Purpose:** Append-only archive of all run start/finish events with session metadata, enabling session ID resolution for resumption.

**Format:** JSON Lines, with fields:

- `ts`: ISO 8601 timestamp (UTC)
- `date`: ISO 8601 date string
- `event`: Event name (`run.started`, `run.finished`)
- `workspace`: Absolute path to working directory
- `run_id`: Timestamp-based unique run identifier
- `session_id`: Codex session ID (for finished runs)
- `resume_session_id`: Session ID used for resumption (for started runs)
- `objective`: Run objective (truncated to 700 chars)

**Lifecycle:** Created on first daemon run. Appended on every run start and finish. Used by session resolution logic in `resolve_resume_session_id()`.

**Example Entry:**

```
{
  "ts": "2024-01-15T10:30:00.000000Z",
  "date": "2024-01-15",
  "event": "run.finished",
  "workspace": "/home/user/project",
  "run_id": "20240115-103000-123456",
  "session_id": "abc123def456",
  "objective": "Implement feature X...",
  "exit_code": 0
}
```

**Sources:**[codex_autoloop/telegram_daemon.py248-1187](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L248-L1187)[README.md488](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L488-L488)

---

### operator_messages.md

**Location:**`.argusbot/logs/operator_messages.md`

**Purpose:** Shared markdown log of all operator interactions (initial objectives, injections, plan directions, review criteria) across runs, enabling reviewer and planner to access global context.

**Format:** Markdown bullet list with prefixed message kinds:

- `- [timestamp] [source] initial objective: <text>`
- `- [timestamp] [source] `broadcast`: <text>`
- `- [timestamp] [source] `plan`: <text>`
- `- [timestamp] [source] `review`: <text>`

**Lifecycle:** Created on first run. Appended on every operator input (objective, inject, plan direction, review criteria). Never truncated. Messages are categorized by kind for targeted consumption by agents.

**Sources:**[codex_autoloop/telegram_daemon.py249](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L249-L249)[README.md486-487](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L486-L487)[codex_autoloop/apps/daemon_app.py806-833](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L806-L833)

---

### last_state.json

**Location:**`.argusbot/logs/last_state.json` (configurable via `--state-file`)

**Purpose:** Primary session state snapshot written after each round, containing session ID, round history, and latest agent outputs.

**Format:** JSON object with structure:

```
{
  "session_id": "abc123def456",
  "force_fresh_session": false,
  "force_fresh_reason": null,
  "rounds": [
    {
      "round": 1,
      "thread_id": "thread_xyz",
      "review": {
        "status": "continue",
        "confidence": 0.85,
        "reason": "Tests passing but feature incomplete"
      }
    }
  ]
}
```

**Lifecycle:** Created/overwritten after each round by `LoopStateStore.save_state()`. Read on daemon startup for session resumption via `resolve_resume_session_id()`. Contains `force_fresh_session` flag for recovery from invalid encrypted content errors.

**Sources:**[codex_autoloop/telegram_daemon.py462-1173](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L462-L1173)[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py) (referenced)

---

### btw_messages.md

**Location:**`.argusbot/logs/btw_messages.md`

**Purpose:** Message history for BTW side-agent interactions, separate from main run history.

**Format:** Markdown append log of question/answer pairs.

**Lifecycle:** Created on first BTW query. Appended on each BTW interaction. Never truncated.

**Sources:**[codex_autoloop/btw_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/btw_agent.py) (referenced), [codex_autoloop/apps/daemon_app.py90](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L90-L90)

---

### plan-agent-records.md

**Location:**`.argusbot/logs/plan-agent-records.md` (when planner mode is `record`)

**Purpose:** Tabular log of completed runs for record-only planner mode, used for manual review without automated follow-ups.

**Format:** Markdown table with columns:

- Timestamp
- Objective (truncated)
- Exit code
- Review status

**Lifecycle:** Created on first run completion in `record` mode. Appended on each subsequent run. Only written when `planner_mode=record`.

**Sources:**[codex_autoloop/telegram_daemon.py908-934](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L908-L934)

---

### run-{TIMESTAMP}.log

**Location:**`.argusbot/logs/run-YYYYMMDD-HHMMSS-mmmmmm.log`

**Purpose:** Complete stdout/stderr capture for a single child run subprocess.

**Format:** Plain text stream combining codex CLI output, agent outputs, and system messages.

**Lifecycle:** Created when child process spawns. Continuously appended during run. Closed when process exits. Scanned for `invalid encrypted content` marker on non-zero exit codes.

**Sources:**[codex_autoloop/telegram_daemon.py455-486](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L455-L486)[codex_autoloop/apps/daemon_app.py387-413](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L387-L413)

---

### run-{TIMESTAMP}-main-prompt.md

**Location:**`.argusbot/logs/run-YYYYMMDD-HHMMSS-mmmmmm-main-prompt.md`

**Purpose:** Latest prompt sent to main agent, written after each round for debugging and review.

**Format:** Markdown document containing the full prompt text with objective, context, and continuation instructions.

**Lifecycle:** Written/overwritten after each main agent invocation. Persists after run completion. Accessible via `/show-main-prompt` command.

**Sources:**[codex_autoloop/telegram_daemon.py457-1278](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L457-L1278)[codex_autoloop/apps/daemon_app.py390-595](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L390-L595)

---

### run-{TIMESTAMP}-plan-report.md

**Location:**`.argusbot/logs/run-YYYYMMDD-HHMMSS-mmmmmm-plan-report.md`

**Purpose:** Planner agent's strategic overview document containing workstream table, accomplishments, and next-step recommendations.

**Format:** Structured markdown with sections:

- Current Status
- Workstreams Table (ID, Goal, Status, Priority, Notes)
- Recent Accomplishments
- Next Steps
- Follow-up Recommendation

**Lifecycle:** Created on first planner sweep. Overwritten on subsequent sweeps (typically every 30 minutes). Persists after run completion. Used for follow-up proposal generation.

**Sources:**[codex_autoloop/telegram_daemon.py458-1279](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L458-L1279)[README.md69](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L69-L69)

---

### run-{TIMESTAMP}-todo.md

**Location:**`.argusbot/logs/run-YYYYMMDD-HHMMSS-mmmmmm-todo.md`

**Purpose:** Mirrored copy of current plan's TODO items, maintained for CLI/terminal visibility.

**Format:** Markdown task list mirroring planner's workstream table.

**Lifecycle:** Updated in sync with plan-report.md. Provides lightweight view of current priorities.

**Sources:**[codex_autoloop/telegram_daemon.py459-1282](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L459-L1282)[README.md70](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L70-L70)

---

### run-{TIMESTAMP}-review/

**Location:**`.argusbot/logs/run-YYYYMMDD-HHMMSS-mmmmmm-review/`

**Purpose:** Directory containing reviewer agent output summaries for the current run.

**Contents:**

- `index.md` - Latest review summary (linked for quick access)
- `round-NNN.md` - Per-round review summaries
- `completion.md` - Final completion assessment (when review status is `done`)

**Format:** Each file is a markdown document with structured sections:

- Review Status (`done` / `continue` / `blocked`)
- Confidence Score
- Reasoning
- Next Action

**Lifecycle:** Directory created on first review. Files appended/overwritten as rounds progress. Accessible via `/show-review` command.

**Sources:**[codex_autoloop/telegram_daemon.py460](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L460-L460)[codex_autoloop/apps/daemon_app.py392-599](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L392-L599)

---

## bus/ Directory

The `bus/` subdirectory contains all control communication files and runtime status.

### daemon_status.json

**Location:**`.argusbot/bus/daemon_status.json`

**Purpose:** Real-time daemon state snapshot for status queries and monitoring tools.

**Format:** JSON object updated on every state change:

```
{
  "updated_at": "2024-01-15T10:30:00.000000Z",
  "daemon_pid": 12345,
  "daemon_running": true,
  "running": true,
  "child_pid": 12346,
  "child_objective": "Implement feature...",
  "child_log_path": "/path/to/run.log",
  "last_session_id": "abc123",
  "force_fresh_session": false,
  "plan_mode": "auto",
  "btw_busy": false
}
```

**Lifecycle:** Created on daemon start. Updated after every command, child state change, or periodic poll. Read by `/status` command and `argusbot-daemon-ctl status`.

**Sources:**[codex_autoloop/telegram_daemon.py269-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L269-L444)[codex_autoloop/apps/daemon_app.py50-516](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L50-L516)

---

### daemon_commands.jsonl

**Location:**`.argusbot/bus/daemon_commands.jsonl`

**Purpose:** Message bus for terminal-to-daemon control commands via `argusbot-daemon-ctl`.

**Format:** JSON Lines, each line a `BusCommand`:

```
{
  "kind": "run",
  "text": "Implement feature X",
  "source": "terminal",
  "ts": 1705318200.0
}
```

**Command Kinds:**`run`, `inject`, `stop`, `status`, `daemon-stop`, `new`, `mode`, `btw`, `plan`, `review`

**Lifecycle:** Created on daemon start. Appended by `argusbot-daemon-ctl`. Polled by daemon main loop every 1 second. Commands are consumed but file persists for debugging.

**Sources:**[codex_autoloop/telegram_daemon.py268-1089](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L268-L1089)[codex_autoloop/daemon_bus.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py) (referenced)

---

### child-control-{TIMESTAMP}.jsonl

**Location:**`.argusbot/bus/child-control-YYYYMMDD-HHMMSS-mmmmmm.jsonl`

**Purpose:** Per-run control bus for daemon-to-child command forwarding during active execution.

**Format:** JSON Lines of `BusCommand` objects, same structure as daemon_commands.jsonl.

**Lifecycle:** Created when child process spawns. Appended when daemon forwards commands (inject, plan, review, stop, mode) to active child. Polled by child's `LoopStateStore` via `LocalBusControlChannel`. Persists after run for audit trail.

**Sources:**[codex_autoloop/telegram_daemon.py456-1276](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L456-L1276)[codex_autoloop/apps/daemon_app.py388-591](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L388-L591)

---

### next_run_new_session.flag

**Location:**`.argusbot/bus/next_run_new_session.flag`

**Purpose:** Signal file for forcing the next run to start with a fresh session instead of resuming.

**Format:** Plain text file containing `1` when flag is set, or absent/empty when cleared.

**Lifecycle:** Created/set when `/new` command is issued or `invalid_encrypted_content` is detected. Consumed (deleted) when next run starts, applying the fresh-session behavior.

**Sources:**[codex_autoloop/apps/daemon_app.py51-803](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L51-L803)

---

## File Lifecycle Diagram

[State Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py446-1212](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L446-L1212)[codex_autoloop/apps/daemon_app.py384-480](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L384-L480)

---

## File Ownership by Component

This diagram maps file types to the components that create and consume them.

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py) (referenced), [codex_autoloop/telegram_daemon.py200-1239](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L200-L1239)[codex_autoloop/apps/daemon_app.py40-546](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L40-L546)[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py) (referenced)

---

## Per-Run File Naming Convention

All per-run files use a consistent timestamp-based naming scheme to enable chronological organization and easy correlation across file types.

**Timestamp Format:**`YYYYMMDD-HHMMSS-mmmmmm`

- Example: `20240115-143022-456789`
- Generated via: `dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")`

**File Patterns:**

| Pattern | Purpose | Example |
| --- | --- | --- |
| `run-{TS}.log` | Main run output | `run-20240115-143022-456789.log` |
| `child-control-{TS}.jsonl` | Control bus | `child-control-20240115-143022-456789.jsonl` |
| `run-{TS}-main-prompt.md` | Main agent prompt | `run-20240115-143022-456789-main-prompt.md` |
| `run-{TS}-plan-report.md` | Planner output | `run-20240115-143022-456789-plan-report.md` |
| `run-{TS}-todo.md` | TODO mirror | `run-20240115-143022-456789-todo.md` |
| `run-{TS}-review/` | Review directory | `run-20240115-143022-456789-review/` |

**Timestamp Correlation:** The `run_id` field in `argusbot-run-archive.jsonl` and `daemon-events.jsonl` uses the same timestamp, enabling cross-file lookups.

**Sources:**[codex_autoloop/telegram_daemon.py454-499](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L454-L499)[codex_autoloop/apps/daemon_app.py386-392](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L386-L392)

---

## File Access Patterns by Command

This table shows which files are read or written in response to common commands.

| Command | Files Read | Files Written/Appended |
| --- | --- | --- |
| `argusbot init` | - | `daemon_config.json` |
| Daemon start | `daemon_config.json` | `daemon.pid`, `daemon_status.json`, `daemon-events.jsonl` |
| `/run` | `last_state.json`, `argusbot-run-archive.jsonl` | `daemon-events.jsonl`, `argusbot-run-archive.jsonl`, `run-*.log`, `child-control-*.jsonl` |
| `/inject` | - | `daemon_commands.jsonl` → `child-control-*.jsonl`, `operator_messages.md` |
| `/status` | `daemon_status.json` | - |
| `/new` | - | `next_run_new_session.flag` |
| `/show-plan` | `run-*-plan-report.md` | - |
| `/show-review` | `run-*-review/index.md` or `run-*-review/round-NNN.md` | - |
| Round execution | `child-control-*.jsonl`, `operator_messages.md` | `last_state.json`, `main-prompt.md`, `plan-report.md`, `review/round-NNN.md` |
| Run completion | `last_state.json`, `run-*.log` | `argusbot-run-archive.jsonl`, `next_run_new_session.flag` (conditional) |

**Sources:**[codex_autoloop/telegram_daemon.py643-886](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L643-L886)[codex_autoloop/apps/daemon_app.py187-383](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L187-L383)

---

## State File JSON Schemas

### daemon_status.json Schema

```
{
  "updated_at": "string (ISO 8601 UTC)",
  "daemon_pid": "integer",
  "daemon_running": "boolean",
  "running": "boolean (child active)",
  "child_pid": "integer | null",
  "child_objective": "string | null",
  "child_log_path": "string | null",
  "child_main_prompt_path": "string | null",
  "child_plan_report_path": "string | null",
  "child_plan_todo_path": "string | null",
  "child_review_summaries_dir": "string | null",
  "child_started_at": "string (ISO 8601) | null",
  "last_session_id": "string | null",
  "force_fresh_session": "boolean",
  "run_cwd": "string",
  "logs_dir": "string",
  "bus_dir": "string",
  "events_log": "string",
  "run_archive_log": "string",
  "operator_messages_file": "string",
  "plan_mode": "string (off|auto|record)",
  "default_plan_mode": "string",
  "btw_busy": "boolean",
  "btw_session_id": "string | null",
  "btw_messages_file": "string"
}
```

**Sources:**[codex_autoloop/telegram_daemon.py398-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L398-L444)[codex_autoloop/apps/daemon_app.py482-516](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L482-L516)

---

### last_state.json Schema

```
{
  "session_id": "string",
  "force_fresh_session": "boolean",
  "force_fresh_reason": "string | null",
  "rounds": [
    {
      "round": "integer",
      "thread_id": "string",
      "main_exit_code": "integer",
      "main_turn_completed": "boolean",
      "main_turn_failed": "boolean",
      "review": {
        "status": "string (done|continue|blocked)",
        "confidence": "number (0-1)",
        "reason": "string",
        "next_action": "string"
      },
      "checks": [
        {
          "command": "string",
          "passed": "boolean",
          "output": "string"
        }
      ],
      "plan": {
        "next_explore": "string | null",
        "workstreams": "array"
      } | null
    }
  ]
}
```

**Sources:**[codex_autoloop/core/state_store.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/core/state_store.py) (referenced in state persistence logic)

---

## Event Log Entry Schemas

### daemon-events.jsonl Entry Types

All entries share base fields:

- `ts`: ISO 8601 UTC timestamp
- `type`: Event type string

**Common Event Types:**

```
// daemon.started
{
  "type": "daemon.started",
  "run_cwd": "string",
  "logs_dir": "string",
  "bus_dir": "string",
  "token_hash": "string | null"
}
 
// child.launched
{
  "type": "child.launched",
  "pid": "integer",
  "objective": "string (truncated 700)",
  "log_path": "string",
  "control_path": "string",
  "resume_session_id": "string | null",
  "run_id": "string (timestamp)"
}
 
// child.finished
{
  "type": "child.finished",
  "exit_code": "integer",
  "objective": "string (truncated 700)",
  "log_path": "string",
  "run_id": "string"
}
 
// command.received
{
  "type": "command.received",
  "source": "string (telegram|feishu|terminal)",
  "kind": "string (run|inject|stop|...)",
  "text": "string (truncated 700)"
}
 
// session.fresh.flagged
{
  "type": "session.fresh.flagged",
  "run_id": "string",
  "reason": "string (invalid_encrypted_content)",
  "log_path": "string"
}
```

**Sources:**[codex_autoloop/telegram_daemon.py344-1172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L344-L1172)

---

### argusbot-run-archive.jsonl Entry Types

```
// run.started
{
  "ts": "string (ISO 8601 UTC)",
  "date": "string (ISO 8601 date)",
  "event": "run.started",
  "workspace": "string (absolute path)",
  "run_id": "string (timestamp)",
  "pid": "integer",
  "objective": "string (truncated 700)",
  "log_path": "string",
  "control_path": "string",
  "operator_messages_file": "string",
  "resume_session_id": "string | null",
  "force_fresh_session": "boolean",
  "plan_mode": "string",
  "started_at": "string (ISO 8601 UTC)"
}
 
// run.finished
{
  "ts": "string (ISO 8601 UTC)",
  "date": "string (ISO 8601 date)",
  "event": "run.finished",
  "workspace": "string (absolute path)",
  "run_id": "string (timestamp)",
  "objective": "string (truncated 700)",
  "plan_mode": "string",
  "exit_code": "integer",
  "log_path": "string",
  "control_path": "string",
  "operator_messages_file": "string",
  "resume_session_id": "string | null",
  "session_id": "string | null",
  "started_at": "string (ISO 8601 UTC)",
  "finished_at": "string (ISO 8601 UTC)"
}
 
// session.fresh.requested
{
  "ts": "string (ISO 8601 UTC)",
  "date": "string (ISO 8601 date)",
  "event": "session.fresh.requested",
  "workspace": "string (absolute path)",
  "source": "string",
  "running": "boolean",
  "active_run_id": "string | null",
  "active_objective": "string"
}
```

**Sources:**[codex_autoloop/telegram_daemon.py353-1187](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L353-L1187)

---

## File Retention and Cleanup

ArgusBot does **not** automatically delete or rotate any files. All artifacts persist indefinitely for audit trails and debugging.

**Manual Cleanup Recommendations:**

1. **Old run logs:** Archive or delete `logs/run-*.log` files older than your retention policy
2. **Event logs:** Truncate `daemon-events.jsonl` and `argusbot-run-archive.jsonl` periodically (requires daemon restart)
3. **Review directories:** Remove `logs/run-*-review/` directories for old runs
4. **Stale flags:** Delete orphaned `next_run_new_session.flag` if daemon crashes

**Files Safe to Delete While Daemon Running:**

- Old `run-*.log` files (not current run)
- Old `run-*-plan-report.md` files
- Old `run-*-review/` directories

**Files Never Delete While Daemon Running:**

- `daemon_config.json`
- `daemon_status.json`
- `daemon_commands.jsonl`
- `daemon-events.jsonl`
- Current `child-control-*.jsonl`

**Sources:**[README.md488](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L488-L488) (documentation describes persistent nature)

---

## Cross-Platform Path Handling

ArgusBot handles paths differently on Windows vs Unix systems.

**Path Resolution:**

- All paths are resolved to absolute via `Path().resolve()`
- Configuration paths use `expanduser()` for `~` expansion
- Child processes inherit `PYTHONPATH` with repo root prepended

**Windows-Specific Handling:**

- Command splitting uses `shlex.split(posix=False)` on Windows
- Wrapping quotes are stripped manually
- Process termination uses `taskkill /T /F` instead of SIGTERM

**Unix-Specific Handling:**

- Process groups for child termination via `os.killpg()`
- `start_new_session=True` for clean process hierarchy

**Sources:**[codex_autoloop/telegram_daemon.py72-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L72-L100)[codex_autoloop/apps/daemon_app.py25-37](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L25-L37)

---

## File Access Permissions

ArgusBot does not enforce special permissions on created files. All files inherit default user permissions.

**Security Considerations:**

1. **daemon_config.json** contains sensitive tokens - ensure appropriate file permissions (recommend `chmod 600`)
2. **daemon.pid** enables process control - protect from unauthorized modification
3. **daemon_commands.jsonl** allows command injection - restrict write access
4. **Event logs** may contain sensitive data from objectives and outputs

**Recommended Permissions:**

```
chmod 600 .argusbot/daemon_config.json    # Config with secrets
chmod 644 .argusbot/daemon_status.json    # Read-only for monitoring
chmod 600 .argusbot/bus/daemon_commands.jsonl  # Write requires trust
chmod 644 .argusbot/logs/*.jsonl          # Read-only event logs
```

**Sources:** Implementation detail (permissions not explicitly set in code)