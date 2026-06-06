# Event Types Reference
Relevant source files
- [codex_autoloop/apps/cli_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py)
- [codex_autoloop/apps/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py)
- [codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py)
- [codex_autoloop/reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py)
- [tests/test_reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_reviewer.py)

This page documents all event types emitted by ArgusBot's execution pipeline. Events are used for notifications (Telegram/Feishu), state tracking, logging, and inter-component communication. Each event is emitted as a JSON object with a `type` field identifying the event category.

For information about configuring which events trigger notifications, see [Configuration Reference](/waltstephen/ArgusBot/8.2-cli-arguments-reference). For command-line options controlling event behavior, see [Command Reference](/waltstephen/ArgusBot/8.1-command-reference).

---

## Event System Overview

ArgusBot emits structured events throughout the execution lifecycle. These events flow through multiple channels:

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_notifier.py46-58](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L46-L58)[codex_autoloop/cli.py258-260](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L258-L260)[codex_autoloop/cli.py358-360](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L358-L360)

---

## Event Type Hierarchy

Events are organized into three primary categories:

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_notifier.py374-429](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L374-L429)

---

## Loop Lifecycle Events

### `loop.started`

Emitted when a new ArgusBot execution loop begins.

**Timing:** Fired immediately after loop initialization, before the first round starts.

**Payload Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | Always `"loop.started"` |
| `objective` | `string` | User-provided task objective |
| `max_rounds` | `integer` | Maximum rounds allowed for this loop |
| `timestamp` | `string` | ISO 8601 timestamp (optional) |

**Example Payload:**

```
{
  "type": "loop.started",
  "objective": "Implement feature X and keep iterating until tests pass",
  "max_rounds": 500
}
```

**Default Notification Behavior:**

- **Telegram:** ✅ Included in default event set
- **Feishu:** ✅ Included in default event set
- **Dashboard:** Always displayed
- **Terminal:** Logged to stdout if verbose events enabled

**Formatted Message Template:**

```
[autoloop] started {timestamp}
max_rounds={max_rounds}
objective={objective}

```

**Sources:**[codex_autoloop/telegram_notifier.py378-385](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L378-L385)[tests/test_telegram_notifier.py13-22](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_notifier.py#L13-L22)

---

### `loop.completed`

Emitted when the execution loop terminates, regardless of success or failure.

**Timing:** Fired after the final round completes or when a stop condition is met.

**Payload Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | Always `"loop.completed"` |
| `success` | `boolean` | `true` if reviewer returned `done` and checks passed |
| `stop_reason` | `string` | Human-readable termination reason |
| `timestamp` | `string` | ISO 8601 timestamp (optional) |

**Example Payload:**

```
{
  "type": "loop.completed",
  "success": true,
  "stop_reason": "Reviewer marked task as done, all checks passed"
}
```

**Possible Stop Reasons:**

- `"Reviewer marked task as done, all checks passed"`
- `"Maximum rounds (500) reached"`
- `"Reviewer blocked: {reason}"`
- `"User requested stop"`
- `"Repeated no-progress rounds"`
- `"Stall watchdog triggered force restart"`

**Default Notification Behavior:**

- **Telegram:** ✅ Included in default event set
- **Feishu:** ✅ Included in default event set
- **Dashboard:** Always displayed
- **Terminal:** Logged to stdout if verbose events enabled

**Formatted Message Template:**

```
[autoloop] completed {timestamp}
success={success}
stop_reason={stop_reason}

```

**Sources:**[codex_autoloop/telegram_notifier.py413-418](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L413-L418)

---

## Round Execution Events

### `round.started`

Emitted at the beginning of each execution round, before the main agent runs.

**Timing:** Fired immediately before `codex exec` or `codex exec resume` invocation.

**Payload Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | Always `"round.started"` |
| `round_index` | `integer` | Zero-based round counter (0, 1, 2, ...) |
| `session_id` | `string` | Codex session identifier for continuity |
| `timestamp` | `string` | ISO 8601 timestamp (optional) |

**Example Payload:**

```
{
  "type": "round.started",
  "round_index": 3,
  "session_id": "01234567-89ab-cdef-0123-456789abcdef"
}
```

**Default Notification Behavior:**

- **Telegram:** ❌ Not included in default event set
- **Feishu:** ❌ Not included in default event set
- **Dashboard:** Always displayed
- **Terminal:** Logged to stdout if verbose events enabled

**Formatted Message Template:**

```
[autoloop] round started {timestamp}
round={round_index}
session_id={session_id}

```

**Sources:**[codex_autoloop/telegram_notifier.py386-391](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L386-L391)

---

### `round.main.completed`

Emitted when the main agent (Codex CLI) finishes executing for a round.

**Timing:** Fired after `codex exec` or `codex exec resume` exits, before acceptance checks or reviewer evaluation.

**Payload Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | Always `"round.main.completed"` |
| `round_index` | `integer` | Zero-based round counter |
| `session_id` | `string` | Codex session identifier |
| `exit_code` | `integer` | Main agent process exit code |
| `turn_completed` | `integer` | Number of completed turns in this round |
| `turn_failed` | `integer` | Number of failed turns in this round |
| `interrupted` | `boolean` | `true` if execution was interrupted by user/system |
| `last_message` | `string` | Final agent message (truncated to 400 chars) |
| `timestamp` | `string` | ISO 8601 timestamp (optional) |

**Example Payload:**

```
{
  "type": "round.main.completed",
  "round_index": 3,
  "session_id": "01234567-89ab-cdef-0123-456789abcdef",
  "exit_code": 0,
  "turn_completed": 5,
  "turn_failed": 0,
  "interrupted": false,
  "last_message": "Successfully implemented the validation logic and all unit tests are passing."
}
```

**Default Notification Behavior:**

- **Telegram:** ❌ Not included in default event set
- **Feishu:** ❌ Not included in default event set
- **Dashboard:** Always displayed
- **Terminal:** Logged to stdout if verbose events enabled

**Formatted Message Template:**

```
[autoloop] main completed {timestamp}
round={round_index} exit={exit_code} turn_completed={turn_completed} turn_failed={turn_failed} interrupted={interrupted}
session_id={session_id}
summary={last_message}

```

**Sources:**[codex_autoloop/telegram_notifier.py392-402](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L392-L402)

---

### `round.review.completed`

Emitted when the reviewer agent finishes evaluating a round's completion status.

**Timing:** Fired after the reviewer agent returns its structured JSON decision.

**Payload Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | Always `"round.review.completed"` |
| `round_index` | `integer` | Zero-based round counter |
| `status` | `string` | Reviewer decision: `"done"`, `"continue"`, or `"blocked"` |
| `confidence` | `number` | Confidence score (0.0 to 1.0) |
| `reason` | `string` | Reviewer's reasoning for the decision |
| `next_action` | `string` | Recommended next steps (for `continue` status) |
| `timestamp` | `string` | ISO 8601 timestamp (optional) |

**Example Payload:**

```
{
  "type": "round.review.completed",
  "round_index": 3,
  "status": "continue",
  "confidence": 0.75,
  "reason": "Core logic implemented but edge case handling incomplete",
  "next_action": "Add error handling for empty input and null references"
}
```

**Reviewer Status Values:**

| Status | Meaning | Loop Behavior |
| --- | --- | --- |
| `done` | Task completed successfully | Loop terminates if checks pass |
| `continue` | More work needed | Loop proceeds to next round |
| `blocked` | Irrecoverable error or constraint violation | Loop terminates immediately |

**Default Notification Behavior:**

- **Telegram:** ✅ Included in default event set
- **Feishu:** ✅ Included in default event set
- **Dashboard:** Always displayed
- **Terminal:** Logged to stdout if verbose events enabled

**Formatted Message Template:**

```
[autoloop] reviewer decision {timestamp}
round={round_index} status={status} confidence={confidence}
reason={reason}
next_action={next_action}

```

**Sources:**[codex_autoloop/telegram_notifier.py403-412](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L403-L412)[tests/test_telegram_notifier.py25-37](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_notifier.py#L25-L37)

---

## Planning Events

### `plan.updated`

Emitted during background planning sweeps when the planner updates its strategic overview.

**Timing:** Fired during periodic planning sweeps (default interval: 1800 seconds) or when triggered by user commands.

**Payload Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | Always `"plan.updated"` |
| `trigger` | `string` | What triggered this update: `"periodic"`, `"manual"`, etc. |
| `terminal` | `boolean` | `true` if this is a final planning pass |
| `summary` | `string` | High-level summary of current progress |
| `suggested_next_objective` | `string` | Recommended objective for follow-up session |
| `timestamp` | `string` | ISO 8601 timestamp (optional) |

**Example Payload:**

```
{
  "type": "plan.updated",
  "trigger": "periodic",
  "terminal": false,
  "summary": "Core pipeline implementation in progress, validation layer complete",
  "suggested_next_objective": "Implement error handling and add integration tests"
}
```

**Default Notification Behavior:**

- **Telegram:** ❌ Not included in default event set
- **Feishu:** ❌ Not included in default event set
- **Dashboard:** Always displayed
- **Terminal:** Logged to stdout if verbose events enabled

**Formatted Message Template:**

```
[autoloop] planner update {timestamp}
trigger={trigger} terminal={terminal}
summary={summary}
next_objective={suggested_next_objective}

```

**Sources:**[codex_autoloop/telegram_notifier.py419-428](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L419-L428)

---

### `plan.finalized`

Emitted when the planner generates its final strategic report at loop completion.

**Timing:** Fired after the loop terminates successfully, before `loop.completed` event.

**Payload Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | Always `"plan.finalized"` |
| `trigger` | `string` | What triggered finalization: `"final"`, `"completion"`, etc. |
| `terminal` | `boolean` | Always `true` for finalized plans |
| `summary` | `string` | High-level summary of what was accomplished |
| `suggested_next_objective` | `string` | Recommended objective for follow-up session |
| `follow_up_required` | `boolean` | Whether planner recommends a follow-up session |
| `timestamp` | `string` | ISO 8601 timestamp (optional) |

**Example Payload:**

```
{
  "type": "plan.finalized",
  "trigger": "final",
  "terminal": true,
  "summary": "Pipeline implementation complete with validation and error handling",
  "suggested_next_objective": "Benchmark the new pipeline end-to-end and document performance characteristics",
  "follow_up_required": true
}
```

**Default Notification Behavior:**

- **Telegram:** ❌ Not included in default event set (but used for follow-up proposals in daemon mode)
- **Feishu:** ❌ Not included in default event set
- **Dashboard:** Always displayed
- **Terminal:** Logged to stdout if verbose events enabled

**Formatted Message Template:**

```
[autoloop] planner final {timestamp}
trigger={trigger} terminal={terminal}
summary={summary}
next_objective={suggested_next_objective}

```

**Automated Follow-up:** When `planner_mode=auto` in daemon mode, this event triggers the automated follow-up proposal mechanism. The daemon sends an inline keyboard to Telegram/Feishu allowing one-click execution of the suggested objective.

**Sources:**[codex_autoloop/telegram_notifier.py419-428](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L419-L428)[tests/test_telegram_notifier.py44-55](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_notifier.py#L44-L55)

---

## Event Configuration

### Selecting Events for Notifications

Events are filtered per notification channel using comma-separated lists:

**Telegram Events:**

```
--telegram-events "loop.started,round.review.completed,loop.completed"
```

**Feishu Events:**

```
--feishu-events "loop.started,round.started,round.review.completed,loop.completed"
```

**Default Event Sets:**

| Channel | Default Events |
| --- | --- |
| Telegram | `loop.started`, `round.review.completed`, `loop.completed` |
| Feishu | `loop.started`, `round.review.completed`, `loop.completed` |
| Dashboard | All events (not configurable) |
| Verbose Terminal | All events when `--verbose-events` enabled |

**Sources:**[codex_autoloop/cli.py258-260](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L258-L260)[codex_autoloop/cli.py358-360](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L358-L360)

---

## Event Flow Through System Components

```

```

**Sources:**[codex_autoloop/telegram_notifier.py46-58](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L46-L58)

---

## Event Payload Formatting

### Telegram Formatting

The `TelegramNotifier.format_event_message()` function transforms event payloads into human-readable messages:

**Formatting Rules:**

- Timestamps are rendered as UTC strings in format `YYYY-MM-DD HH:MM:SSZ`
- Long text fields (objective, reason, summary) are truncated to prevent message splitting
- Newlines in multi-line fields are replaced with spaces for compact display
- Key-value pairs are presented on separate lines for readability

**Character Limits by Field:**

| Field | Character Limit | Truncation Point |
| --- | --- | --- |
| `objective` | 600 | Telegram message formatting |
| `last_message` | 400 | Summary display in notifications |
| `reason` | 320 | Reviewer reasoning in notifications |
| `next_action` | 320 | Reviewer recommendations |
| `summary` | 320 | Planner summary in notifications |
| `suggested_next_objective` | 320 | Follow-up proposal preview |
| `stop_reason` | 500 | Loop termination reason |

**Message Splitting:** If a formatted message exceeds 3900 characters, it is split into multiple chunks at newline or space boundaries. When `reply_markup` (inline keyboards) is provided, it is only attached to the final chunk.

**Sources:**[codex_autoloop/telegram_notifier.py374-429](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L374-L429)[codex_autoloop/telegram_notifier.py351-371](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L351-L371)[tests/test_telegram_notifier.py170-187](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_notifier.py#L170-L187)

---

## Event Filtering and Routing

### Event Type Matching

Notifiers check event types using exact string matching:

```
if event_type in self.config.events:
    # Process and send notification
```

**Case Sensitivity:** Event type strings are case-sensitive. `"loop.started"` ≠ `"Loop.Started"`.

**Unknown Events:** Events with unrecognized type strings are silently ignored by notifiers. No error is raised.

### Conditional Event Handling

Some events trigger special behaviors beyond simple notification:

**`loop.started` Special Behavior:**

- Starts Telegram typing heartbeat thread
- Initializes dashboard state if enabled
- Resets internal counters

**`loop.completed` Special Behavior:**

- Stops Telegram typing heartbeat thread
- Triggers follow-up proposal in daemon mode when `planner_mode=auto`
- Finalizes archive log entry

**Sources:**[codex_autoloop/telegram_notifier.py46-52](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L46-L52)[codex_autoloop/telegram_notifier.py128-147](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L128-L147)

---

## Event Persistence

### Archive Log Format

Events are persisted to `.argusbot/logs/argusbot-run-archive.jsonl` in JSONL format (one JSON object per line):

**Example Archive Entries:**

```
{"type": "run.started", "timestamp": "2024-01-15T10:30:00Z", "workspace": "/path/to/project", "session_id": "abc123", "objective": "Implement pipeline"}
{"type": "loop.started", "objective": "Implement pipeline", "max_rounds": 500}
{"type": "round.review.completed", "round_index": 0, "status": "continue", "confidence": 0.8, "reason": "Initial setup complete"}
{"type": "loop.completed", "success": true, "stop_reason": "Task complete"}
{"type": "run.finished", "timestamp": "2024-01-15T11:15:00Z", "exit_code": 0, "session_id": "abc123"}
```

**Additional Metadata:** The daemon appends `run.started` and `run.finished` wrapper events that include workspace paths, session IDs, and timestamps for continuity tracking.

**Sources:** README.md lines 488-489

---

## Complete Event Type Reference Table

| Event Type | Category | Default TG | Default FS | Purpose |
| --- | --- | --- | --- | --- |
| `loop.started` | Loop Lifecycle | ✅ | ✅ | Loop initialization |
| `loop.completed` | Loop Lifecycle | ✅ | ✅ | Loop termination |
| `round.started` | Round Execution | ❌ | ❌ | Round begins |
| `round.main.completed` | Round Execution | ❌ | ❌ | Main agent exits |
| `round.review.completed` | Round Execution | ✅ | ✅ | Reviewer decision |
| `plan.updated` | Planning | ❌ | ❌ | Periodic plan sweep |
| `plan.finalized` | Planning | ❌ | ❌ | Final plan at completion |

**Legend:**

- **Default TG:** Included in default Telegram event set
- **Default FS:** Included in default Feishu event set

**Sources:**[codex_autoloop/cli.py258-260](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L258-L260)[codex_autoloop/cli.py358-360](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L358-L360)[codex_autoloop/telegram_notifier.py374-429](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L374-L429)