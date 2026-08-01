# Advanced Topics
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py)

This section covers advanced features and operational details for power users who need deeper control over ArgusBot's behavior. These topics include session continuity mechanisms, state persistence strategies, automated planning workflows, and error recovery systems.

For basic configuration, see [Configuration Overview](/waltstephen/ArgusBot/2.3-configuration-overview). For command reference, see [Command Reference](/waltstephen/ArgusBot/8.1-command-reference). For detailed exploration of each advanced topic, see the subsections: [Session Management and Resumption](/waltstephen/ArgusBot/7.1-session-management-and-resumption), [State Persistence Details](/waltstephen/ArgusBot/7.2-state-persistence-details), [Automated Planning System](/waltstephen/ArgusBot/7.3-automated-planning-system), and [Error Recovery and Resilience](/waltstephen/ArgusBot/7.4-error-recovery-and-resilience).

---

## Session Continuity Overview

ArgusBot maintains session continuity across multiple runs through a two-tier resolution system. When the daemon launches a new run, it first checks the `state_file` for a saved `session_id`, then falls back to the `archive_file` event log to locate the most recent session. This allows runs to resume mid-conversation with Codex CLI rather than starting fresh threads every time.

The system supports explicit session control through the `force_fresh_session` flag, which can be set manually via the `/new` command or automatically when certain error conditions are detected.

### Session Resolution Flow

[Flowchart Diagram]

**Session Resolution Components:**

| Component | File Location | Purpose |
| --- | --- | --- |
| `resolve_resume_session_id()` | [telegram_daemon.py1513-1520](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1513-L1520) | Primary resolution entry point |
| `resolve_saved_session_id()` | [telegram_daemon.py1449-1453](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1449-L1453) | Reads from state_file |
| `resolve_last_session_id_from_archive()` | [telegram_daemon.py1484-1511](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1484-L1511) | Fallback to archive log |
| `is_force_fresh_session_requested()` | [telegram_daemon.py1455-1462](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1455-L1462) | Checks override flag |
| `FORCE_FRESH_SESSION_KEY` | [telegram_daemon.py43](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L43-L43) | JSON key constant |

Sources: [telegram_daemon.py43-48](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L43-L48)[telegram_daemon.py1437-1520](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1437-L1520)

---

## State Persistence Architecture

ArgusBot maintains comprehensive state across multiple file formats, segregated by purpose. This multi-file strategy enables both machine-readable resumption and human-readable audit trails.

### State File Ecosystem

[Flowchart Diagram]

**State File Schema:**

| Field | Type | Purpose | Updated By |
| --- | --- | --- | --- |
| `session_id` | string | Current Codex session ID | LoopEngine per round |
| `force_fresh_session` | boolean | Override flag for next run | Daemon on error or `/new` |
| `force_fresh_reason` | string | Why fresh session was requested | Daemon |
| `rounds` | array | Round-by-round history | LoopEngine per round |
| `latest_review_status` | string | Most recent reviewer verdict | LoopEngine |
| `latest_plan` | object | Most recent planner output | LoopEngine |

Sources: [telegram_daemon.py398-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L398-L444)[telegram_daemon.py1437-1482](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1437-L1482)

---

## Automated Planning Workflow

The planner system operates in three distinct modes, each with different automation levels and data retention strategies.

### Planner Mode State Machine

[State Diagram]

**Planner Mode Constants:**

```
# From telegram_daemon.py:39-42
PLAN_MODE_EXECUTE_ONLY = "execute-only"  # Maps to off
PLAN_MODE_FULLY_PLAN = "fully-plan"      # Maps to auto
PLAN_MODE_RECORD_ONLY = "record-only"    # Maps to record
```

**Planning Timer Configuration:**

| Parameter | Default | Purpose |
| --- | --- | --- |
| `plan_request_delay_seconds` | 600s (10min) | Delay before generating plan proposal |
| `plan_auto_execute_delay_seconds` | 600s (10min) | Countdown before auto-executing plan |
| `follow_up_auto_execute_seconds` | 600s (10min) | Legacy countdown parameter |

Sources: [telegram_daemon.py39-42](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L39-L42)[telegram_daemon.py310-316](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L310-L316)[telegram_daemon.py893-974](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L893-L974)[telegram_daemon.py975-1038](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L975-L1038)

---

## Error Recovery Mechanisms

ArgusBot implements multiple layers of error detection and recovery to maintain system stability across long-running operations.

### Invalid Encrypted Content Recovery

When Codex CLI encounters session decryption errors (typically from cross-version incompatibilities), ArgusBot detects the error signature in logs and automatically arms the `force_fresh_session` flag for the next run.

[Flowchart Diagram]

**Error Detection Implementation:**

| Function | Location | Purpose |
| --- | --- | --- |
| `log_contains_invalid_encrypted_content()` | [telegram_daemon.py1522-1536](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1522-L1536) | Scans log tail for error marker |
| `INVALID_ENCRYPTED_CONTENT_MARKER` | [telegram_daemon.py45](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L45-L45) | Error signature constant |

Sources: [telegram_daemon.py45](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L45-L45)[telegram_daemon.py1139-1172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1139-L1172)[telegram_daemon.py1522-1536](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1522-L1536)

### Stall Watchdog System

The stall watchdog operates on dual thresholds to detect and recover from hanging processes:

**Stall Detection Thresholds:**

| Threshold Type | Default | Behavior |
| --- | --- | --- |
| Soft idle timeout | 3600s (1h) | Triggers stall agent diagnosis |
| Hard idle timeout | 10800s (3h) | Forces process termination |

**Process Termination Strategy:**

[Flowchart Diagram]

Sources: [telegram_daemon.py46-47](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L46-L47)[telegram_daemon.py144-198](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L144-L198)[telegram_daemon.py858-882](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L858-L882)

---

## Run Archive Event Stream

The `argusbot-run-archive.jsonl` file maintains a complete event stream of all runs, enabling session continuity across daemon restarts and providing audit trails for debugging.

**Archive Event Types:**

| Event | Trigger | Key Fields |
| --- | --- | --- |
| `run.started` | Child process spawned | `run_id`, `pid`, `objective`, `resume_session_id` |
| `run.finished` | Child process exited | `exit_code`, `session_id`, `plan_mode` |
| `session.fresh.requested` | `/new` command | `source`, `running`, `active_run_id` |
| `session.fresh.flagged` | Error detection | `reason`, `log_path` |
| `session.fresh.cleared` | Successful fresh run | `session_id` |
| `session.fresh.applied` | Force flag used | `run_id` |

**Archive Record Structure:**

```
{
  "ts": "2024-01-15T12:34:56.789Z",
  "date": "2024-01-15",
  "event": "run.finished",
  "workspace": "/path/to/workspace",
  "run_id": "20240115-123456-789012",
  "objective": "Implement feature X...",
  "plan_mode": "fully-plan",
  "exit_code": 0,
  "session_id": "abc123-def456",
  "resume_session_id": "abc123-def456",
  "started_at": "2024-01-15T12:30:00.000Z",
  "finished_at": "2024-01-15T12:34:56.789Z"
}
```

Sources: [telegram_daemon.py353-363](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L353-L363)[telegram_daemon.py522-534](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L522-L534)[telegram_daemon.py1174-1187](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1174-L1187)

---

## Daemon Status Synchronization

The daemon maintains operational state in `daemon_status.json`, which is updated after every significant event to enable external monitoring and control.

**Status Update Triggers:**

[Flowchart Diagram]

**Status Fields:**

| Field | Type | Purpose |
| --- | --- | --- |
| `daemon_running` | boolean | True if daemon is online |
| `running` | boolean | True if child is active |
| `child_pid` | integer | Current child process ID |
| `last_session_id` | string | Last known session ID |
| `force_fresh_session` | boolean | Fresh session flag state |
| `pending_plan_request` | string | Generated but not yet executed plan |
| `pending_plan_auto_execute_at` | ISO timestamp | Auto-execution deadline |
| `scheduled_plan_request_at` | ISO timestamp | Plan generation deadline |
| `btw_busy` | boolean | Side-agent execution state |

Sources: [telegram_daemon.py398-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L398-L444)[telegram_daemon.py1080-1125](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1080-L1125)

---

## Cross-Run Context Injection

The `operator_messages.md` file accumulates all operator inputs across runs, providing the reviewer agent with global context about human guidance and priorities.

**Message Accumulation Pattern:**

```
# Operator Messages

## 2024-01-15 12:30:00Z - Initial Objective (run.started)
Implement feature X and keep iterating until tests pass.

## 2024-01-15 12:45:00Z - /inject (terminal)
先修测试再继续

## 2024-01-15 13:00:00Z - /plan (telegram)
Focus on implementing the core logic before optimizing.

## 2024-01-15 13:15:00Z - /review (feishu)
Stricter criteria: all edge cases must have test coverage.

```

This persistent history ensures that reviewer decisions incorporate cumulative operator intent rather than treating each run in isolation.

Sources: [telegram_daemon.py249](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L249-L249)[telegram_daemon.py461](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L461-L461)[telegram_daemon.py514](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L514-L514)