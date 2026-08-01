# Session Management and Resumption
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py)
- [codex_autoloop/reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py)
- [tests/test_reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_reviewer.py)
- [tests/test_telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py)

## Purpose and Scope

This page explains how ArgusBot manages session continuity across multiple runs, enabling the main agent to resume previous conversations with the Codex CLI instead of starting fresh each time. Session management includes session ID generation, persistence strategies, resolution logic, and mechanisms to force fresh starts when needed.

For information about state persistence beyond session IDs (round data, reviews, plans), see [State Persistence Details](/waltstephen/ArgusBot/7.2-state-persistence-details). For automated planning workflows that may propose follow-up sessions, see [Automated Planning System](/waltstephen/ArgusBot/7.3-automated-planning-system).

---

## Session Concept

A **session** in ArgusBot refers to a persistent conversation thread between the system and the Codex CLI. Each session is identified by a `session_id` string (typically in the format `thread-{uuid}`), which Codex CLI uses to maintain conversation history across multiple invocations.

When ArgusBot launches a run, it can either:

- **Resume** an existing session (continue previous conversation)
- **Start fresh** (begin new conversation with no prior context)

Session resumption enables iterative development workflows where the main agent builds upon previous attempts without losing context.

---

## Session ID Storage

ArgusBot persists session IDs through two complementary mechanisms, providing both current state snapshots and historical audit trails.

### State File

The **state file** (default: `.argusbot/last_state.json`) stores the current session snapshot as a JSON object. This file is updated after each round during execution.

**Location:** Configured via `--state-file` CLI argument or `run_state_file` in daemon configuration.

**Format:**

```
{
  "session_id": "thread-abc123",
  "rounds": [...],
  "latest_review_status": "continue",
  "force_fresh_session": false
}
```

**Key Fields:**

| Field | Type | Purpose |
| --- | --- | --- |
| `session_id` | string | Current Codex CLI thread ID |
| `force_fresh_session` | boolean | Flag to block next resumption |
| `force_fresh_reason` | string | Optional explanation for fresh flag |
| `rounds` | array | Per-round execution history |

**Sources:**[codex_autoloop/telegram_daemon.py280-284](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L280-L284)[tests/test_telegram_daemon.py280-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L280-L324)

### Archive Log

The **archive log** (default: `logs/argusbot-run-archive.jsonl`) records all run lifecycle events in append-only JSONL format. Each line is a JSON event with timestamp and metadata.

**Location:** Fixed at `{logs_dir}/argusbot-run-archive.jsonl` in daemon mode.

**Event Types:**

- `run.started` - Run initiated (includes `resume_session_id` if resuming)
- `run.finished` - Run completed (includes final `session_id`)
- `session.fresh.requested` - User requested fresh session
- `session.fresh.applied` - Fresh session flag consumed

**Example Events:**

```
{"ts": "2026-01-15T10:00:00Z", "event": "run.started", "run_id": "20260115-100000", "resume_session_id": "thread-old", "force_fresh_session": false}
{"ts": "2026-01-15T10:30:00Z", "event": "run.finished", "run_id": "20260115-100000", "session_id": "thread-abc123", "exit_code": 0}
```

The archive provides fallback session resolution when the state file is missing or corrupted.

**Sources:**[codex_autoloop/telegram_daemon.py353-363](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L353-L363)[codex_autoloop/telegram_daemon.py522-534](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L522-L534)

---

## Session Resolution Strategy

When starting a new run, ArgusBot follows a two-tier resolution strategy to determine whether to resume an existing session.

### Resolution Flow

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py1193-1244](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1193-L1244)[tests/test_telegram_daemon.py298-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L298-L324)

### Priority Order

1. **Force Fresh Flag** - If set, immediately return `null` (no resumption)
2. **State File** - Preferred source for current session ID
3. **Archive Log** - Fallback when state file unavailable
4. **None** - No session ID found, start fresh

### Implementation

The core resolution function combines both sources:

**Key Function:**`resolve_resume_session_id(state_file, archive_file)`

```
# Pseudo-implementation
if force_fresh_flag_set(state_file):
    return None
    
session_id = resolve_saved_session_id(state_file)
if session_id:
    return session_id
    
return resolve_last_session_id_from_archive(archive_file)
```

**Sources:**[codex_autoloop/telegram_daemon.py1193-1207](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1193-L1207)[codex_autoloop/apps/daemon_app.py717-727](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L717-L727)

---

## Force Fresh Session Mechanism

The **force fresh session** mechanism allows operators to override resumption logic and ensure the next run starts with a clean slate.

### Flag File (Daemon Mode)

In daemon mode, a separate flag file controls fresh session behavior:

**File:**`{bus_dir}/next_run_new_session.flag`

**Format:** Plain text file containing `"1"` (enabled) or deleted/empty (disabled)

**Operations:**

- `write_force_new_session_next_run(path, True)` - Create flag file with `"1"`
- `read_force_new_session_next_run(path)` - Check if flag exists and contains `"1"`
- `consume_force_new_session_next_run(path)` - Read flag, then delete it

The flag is **consumed** (deleted) when starting a child process, ensuring it only affects the immediate next run.

**Sources:**[codex_autoloop/apps/daemon_app.py777-803](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L777-L803)

### State File Marker (Legacy)

The original implementation embeds the force fresh marker directly in the state file:

**Fields in state file:**

```
{
  "force_fresh_session": true,
  "force_fresh_reason": "operator_requested_from_telegram"
}
```

**Key Constant:**`FORCE_FRESH_SESSION_KEY = "force_fresh_session"`

**Operations:**

- `set_force_fresh_session_marker(state_file, enabled, reason)` - Set flag in state file
- `is_force_fresh_session_requested(state_file)` - Check flag status

**Sources:**[codex_autoloop/telegram_daemon.py43-44](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L43-L44)[codex_autoloop/telegram_daemon.py1245-1279](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1245-L1279)

### User Commands

Operators trigger force fresh sessions via:

- `/new` command (daemon mode) - Sets flag for next run
- `--session-id` omitted (CLI mode) - Implicitly starts fresh

**Command Flow:**

[Flowchart Diagram]

**Sources:**[codex_autoloop/apps/daemon_app.py192-201](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L192-L201)[codex_autoloop/telegram_daemon.py697-720](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L697-L720)

---

## Session Lifecycle

### Complete Session Lifecycle Diagram

[State Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py1116-1200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1116-L1200)[codex_autoloop/apps/daemon_app.py384-440](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L384-L440)

### Error Recovery: Invalid Encrypted Content

ArgusBot includes automatic recovery for a specific Codex CLI error: `invalid_encrypted_content`. When detected in run logs, the daemon automatically sets the force fresh flag to prevent propagating corrupted session state.

**Detection Constant:**`INVALID_ENCRYPTED_CONTENT_MARKER = "invalid encrypted content"`

**Recovery Function:**`log_contains_invalid_encrypted_content(log_path)`

- Scans log file for marker string (case-insensitive)
- Returns `True` if found

**Automatic Mitigation:**

```
# In on_child_finish() handler
if log_contains_invalid_encrypted_content(child_log_path):
    set_force_fresh_session_marker(
        state_file,
        enabled=True,
        reason="invalid_encrypted_content_detected"
    )
```

This ensures the next run starts fresh instead of attempting to resume a corrupted session.

**Sources:**[codex_autoloop/telegram_daemon.py45](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L45-L45)[codex_autoloop/telegram_daemon.py1281-1291](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1281-L1291)[tests/test_telegram_daemon.py327-334](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L327-L334)

---

## Code Implementation Details

### Key Data Structures

**Session ID Format:**

- Type: `str | None`
- Typical value: `"thread-{uuid}"` (generated by Codex CLI)
- `None` indicates no session to resume

**State File Schema:**

```
# Relevant fields only
{
    "session_id": str,                    # Current thread ID
    "force_fresh_session": bool,          # Block resumption
    "force_fresh_reason": str,            # Optional context
    "rounds": [...]                       # Per-round history
}
```

**Archive Event Schema:**

```
{
    "ts": str,                            # ISO 8601 timestamp + "Z"
    "date": str,                          # ISO 8601 date
    "event": str,                         # Event type
    "workspace": str,                     # Working directory
    "run_id": str,                        # Timestamp-based run ID
    "session_id": str,                    # Final session ID (run.finished)
    "resume_session_id": str | None,      # Resumed ID (run.started)
    "force_fresh_session": bool           # Fresh flag status
}
```

**Sources:**[codex_autoloop/telegram_daemon.py43-48](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L43-L48)[codex_autoloop/telegram_daemon.py353-363](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L353-L363)

### Resolution Functions

**Function:**`resolve_saved_session_id(state_file: str | None) -> str | None`

- Reads state file JSON
- Extracts `session_id` field
- Returns stripped string or `None`

**Location:**[codex_autoloop/telegram_daemon.py1209-1224](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1209-L1224)[codex_autoloop/apps/daemon_app.py717-727](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L717-L727)

---

**Function:**`resolve_last_session_id_from_archive(archive_file: Path) -> str | None`

- Reads archive JSONL in reverse
- Prioritizes `run.finished` events (has final `session_id`)
- Falls back to `run.started` events (has `resume_session_id`)
- Returns first valid session ID found

**Location:**[codex_autoloop/telegram_daemon.py1226-1244](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1226-L1244)

---

**Function:**`resolve_resume_session_id(state_file: str | None, archive_file: Path) -> str | None`

- Main orchestrator for session resolution
- Checks force fresh flag first
- Tries state file, then archive
- Returns combined result

**Location:**[codex_autoloop/telegram_daemon.py1193-1207](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1193-L1207)

**Sources:**[tests/test_telegram_daemon.py280-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L280-L324)

### Child Process Invocation

When daemon spawns a child process, it passes the resolved session ID via CLI argument:

```
def build_child_command(..., resume_session_id: str | None) -> list[str]:
    cmd = [...]
    if resume_session_id:
        cmd.extend(["--session-id", resume_session_id])
    cmd.append(objective)
    return cmd
```

**CLI Argument:**`--session-id {thread-id}`

- Passed to `codex exec` or `codex resume` commands
- Tells Codex CLI which thread to continue
- Omitting this argument starts a fresh session

**Sources:**[codex_autoloop/apps/daemon_app.py641-642](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L641-L642)[codex_autoloop/telegram_daemon.py1400-1514](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1400-L1514)

### Force Fresh Flag Management

**Legacy State File Approach:**

```
def set_force_fresh_session_marker(
    state_file: str,
    *,
    enabled: bool,
    reason: str | None = None
) -> bool:
    # Read existing state
    payload = read_status(state_file) or {}
    
    # Set flag
    payload[FORCE_FRESH_SESSION_KEY] = enabled
    if reason:
        payload[FORCE_FRESH_REASON_KEY] = reason
    elif not enabled:
        payload.pop(FORCE_FRESH_REASON_KEY, None)
    
    # Write back
    write_status(state_file, payload)
    return True
```

**Location:**[codex_autoloop/telegram_daemon.py1245-1279](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1245-L1279)

---

**Modern Flag File Approach:**

```
def write_force_new_session_next_run(path: Path, value: bool) -> None:
    if value:
        path.write_text("1", encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
 
def consume_force_new_session_next_run(path: Path) -> bool:
    value = read_force_new_session_next_run(path)
    if value:
        write_force_new_session_next_run(path, False)  # Delete
    return value
```

**Location:**[codex_autoloop/apps/daemon_app.py787-803](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L787-L803)

**Sources:**[tests/test_telegram_daemon.py312-324](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L312-L324)

---

## Session Management Comparison: Daemon vs CLI Mode

| Aspect | Daemon Mode | CLI Mode |
| --- | --- | --- |
| **Session Storage** | State file + Archive log | State file only |
| **Resumption** | Automatic (unless flag set) | Via `--session-id` argument |
| **Force Fresh** | `/new` command + flag file | Omit `--session-id` |
| **Multi-Run Support** | Yes (archive tracks all runs) | No (single run execution) |
| **Flag Consumption** | Auto-consumed on next `/run` | N/A |
| **Error Recovery** | Auto-detect invalid content | Manual intervention |

**Sources:**[codex_autoloop/telegram_daemon.py446-537](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L446-L537)[codex_autoloop/apps/cli_app.py42-93](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L42-L93)

---

## Resumption Best Practices

### When to Force Fresh Sessions

1. **After Breaking Changes** - Code structure or API changes that invalidate prior context
2. **Context Pollution** - Previous session explored irrelevant paths
3. **Error Recovery** - Corrupted session state (auto-detected for `invalid_encrypted_content`)
4. **Testing** - Verify fresh-start behavior

### When to Resume Sessions

1. **Iterative Refinement** - Building on previous agent attempts
2. **Incremental Tasks** - Multi-step objectives across multiple runs
3. **Context Preservation** - Maintain knowledge of prior decisions and rationale

### Monitoring Session Health

Check the archive log for session continuity patterns:

```
# View recent session IDs
grep -E 'run\.(started|finished)' logs/argusbot-run-archive.jsonl | tail -10
 
# Detect force fresh events
grep 'session.fresh' logs/argusbot-run-archive.jsonl
```

Frequent force fresh requests may indicate:

- Recurring errors requiring investigation
- Workflow incompatible with resumption
- User preference for fresh starts

**Sources:**[codex_autoloop/telegram_daemon.py353-363](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L353-L363)[codex_autoloop/telegram_daemon.py704-710](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L704-L710)