# Command Channels Overview
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/daemon_ctl.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py)
- [codex_autoloop/telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py)
- [tests/test_telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py)

## Purpose and Scope

This page provides an overview of ArgusBot's command channels—the various mechanisms through which operators can control and monitor the system. ArgusBot supports four distinct control mechanisms: terminal/CLI, Telegram, Feishu, and the daemon-ctl utility. All channels converge on a central JSONL-based message bus that routes commands to the appropriate execution context (daemon or child process).

For detailed documentation on specific channels, see:

- Telegram integration details: [Telegram Integration](/waltstephen/ArgusBot/5.2-telegram-integration)
- Feishu integration details: [Feishu Integration](/waltstephen/ArgusBot/5.3-feishu-integration)
- Terminal and daemon-ctl specifics: [Local Control](/waltstephen/ArgusBot/5.4-local-control)

---

## Control Mechanisms

ArgusBot provides four independent command channels, each optimized for different operational scenarios:

| Channel | Primary Use Case | Implementation | Command Source |
| --- | --- | --- | --- |
| **Terminal** | Interactive local control with live output monitoring | `argusbot` CLI, attached console | Direct keyboard input with `/` prefix or plain text |
| **Telegram** | Remote control from mobile/desktop, cross-network operation | `TelegramCommandPoller` long-polling | Text messages, voice/audio transcription, inline buttons |
| **Feishu** | Remote control in CN network environments | `FeishuCommandPoller` message polling | Text messages, @mention commands in groups |
| **daemon-ctl** | Scripted/programmatic control, CI/CD integration | `argusbot-daemon-ctl` utility | CLI arguments |

All four channels support the same core command set:

- `/run <objective>` — start new execution
- `/inject <instruction>` — interrupt active run with new guidance
- `/stop` — halt active run
- `/status` — query current state
- `/mode <off|auto|record>` — switch planner mode
- `/plan <direction>` — send direction to planner
- `/review <criteria>` — send criteria to reviewer
- `/btw <question>` — ask read-only side-agent
- `/daemon-stop` — terminate daemon process

**Sources:**[README.md32-47](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L32-L47)[README.md144-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L144-L166)[codexloop.py248-301](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L248-L301)

---

## Command Flow Architecture

The following diagram illustrates how commands flow from various sources through the JSONL bus to execution contexts:

[Flowchart Diagram]

**Key architectural properties:**

1. **Unified Command Model**: All channels convert input to a common command representation with fields `kind`, `text`, and `source`.
2. **JSONL Bus Decoupling**: The daemon never directly receives commands from Telegram/Feishu pollers. Instead, all commands are published to `daemon_commands.jsonl` and consumed by the daemon's polling loop.
3. **Two-Tier Routing**: The daemon handles process-level commands (`/run`, `/daemon-stop`) and forwards execution-level commands (`/inject`, `/stop`) to the active child via `child_control.jsonl`.
4. **Source Attribution**: Each command records its source (`terminal`, `telegram`, `feishu`) for auditing and debugging.

**Sources:**[codexloop.py808-812](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L808-L812)[telegram_control.py165-330](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L165-L330)[daemon_ctl.py166-167](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L166-L167)

---

## JSONL Command Bus

The JSONL command bus provides asynchronous, file-based inter-process communication between command sources and execution contexts.

### Bus Files

| File Path | Purpose | Producer | Consumer |
| --- | --- | --- | --- |
| `.argusbot/bus/daemon_commands.jsonl` | Daemon-level commands | All channels | Daemon process |
| `.argusbot/bus/child_control.jsonl` | Child-level commands | Daemon forwarder | Active child process |
| `.argusbot/bus/daemon_status.json` | State snapshot | Daemon process | Status queries |

### BusCommand Structure

```
@dataclass
class BusCommand:
    kind: str      # Command type: run, inject, stop, etc.
    text: str      # Payload text
    source: str    # Origin: terminal, telegram, feishu
    ts: float      # Unix timestamp
```

### Command Publishing

Terminal example [codexloop.py808-812](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L808-L812):

```
def publish_command(*, bus_dir: Path, kind: str, text: str, source: str) -> None:
    bus_dir.mkdir(parents=True, exist_ok=True)
    bus = JsonlCommandBus(bus_dir / "daemon_commands.jsonl")
    bus.publish(BusCommand(kind=kind, text=text, source=source, ts=time.time()))
```

daemon-ctl example [daemon_ctl.py166-167](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L166-L167):

```
def publish(bus: JsonlCommandBus, kind: str, text: str, source: str) -> None:
    bus.publish(BusCommand(kind=kind, text=text, source=source, ts=time.time()))
```

### Polling Intervals

| Channel | Poll Interval | Notes |
| --- | --- | --- |
| Telegram | 2s base, 20s long-poll | Long-polling reduces API calls [telegram_control.py174-187](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L174-L187) |
| Feishu | 2s | Standard polling [README.md74](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L74-L74) |
| Terminal | Real-time | Direct function calls, no polling |
| Daemon bus reader | 1s | Daemon polls `daemon_commands.jsonl` |

**Sources:**[codexloop.py808-812](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L808-L812)[daemon_ctl.py166-167](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L166-L167)[telegram_control.py165-330](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L165-L330)

---

## Command Parsing and Normalization

Each channel implements command parsing with channel-specific features:

### Terminal Command Parsing

The terminal supports both slash commands and plain text routing [codexloop.py848-918](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L848-L918):

```

```

**Sources:**[codexloop.py848-918](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L848-L918)[tests/test_codexloop.py7-40](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_codexloop.py#L7-L40)

### Telegram Command Parsing

Telegram parsing [telegram_control.py332-488](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L332-L488) handles:

- Text messages with `/` prefix
- Plain text routed to `/inject` when `plain_text_as_inject=True`
- CJK punctuation normalization (`／` → `/`, `、` → `/`)
- Caption fields from media messages
- Callback queries from inline buttons (`plan_run:`, `plan_reject:`, etc.)

Voice/audio messages undergo transcription before parsing [telegram_control.py33-163](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L33-L163):

[Flowchart Diagram]

**Sources:**[telegram_control.py332-488](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L332-L488)[telegram_control.py33-163](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L33-L163)[tests/test_telegram_control.py43-280](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py#L43-L280)

### Feishu Command Parsing

Feishu supports mention-prefixed commands in groups. A message like `@bot /stop` is normalized to `/stop` before parsing. The parsing logic mirrors Telegram's structure.

**Sources:**[README.md74](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L74-L74)[README.md250-254](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L250-L254)

### daemon-ctl Direct Arguments

The `argusbot-daemon-ctl` utility accepts commands as CLI subcommands [daemon_ctl.py213-247](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L213-L247):

```
argusbot-daemon-ctl --bus-dir .argusbot/bus run "implement feature X"
argusbot-daemon-ctl --bus-dir .argusbot/bus inject "fix tests first"
argusbot-daemon-ctl --bus-dir .argusbot/bus status
```

Each subcommand directly constructs a `BusCommand` and publishes to the JSONL file.

**Sources:**[daemon_ctl.py18-164](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L18-L164)[daemon_ctl.py213-247](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L213-L247)

---

## Daemon vs Child Command Routing

The daemon implements a two-tier command routing strategy based on command type:

[Flowchart Diagram]

### Daemon-Level Commands

Handled directly by the daemon without forwarding [codexloop.py695-793](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L695-L793):

| Command | Action | Implementation |
| --- | --- | --- |
| `/run <objective>` | Spawn new child process with objective | Builds `argusbot-run` command, executes via `subprocess.Popen` |
| `/daemon-stop` | Terminate daemon and any active child | Graceful shutdown, removes PID file |
| `/mode <mode>` | Update default planner mode for future runs | Modifies `daemon_status.json` default_plan_mode field |
| `/btw <question>` | Start BTW side-agent in separate process | Spawns read-only query agent |
| `/status` | Return current daemon and child state | Serializes `daemon_status.json` and sends to requester |
| `/new` | Set fresh session flag for next run | Arms `force_fresh_session` flag |

### Child-Level Commands

Forwarded to active child via `child_control.jsonl`:

| Command | Action | Loop Handler |
| --- | --- | --- |
| `/inject <instruction>` | Append to operator messages, apply next round | Updates `operator_messages.md` |
| `/stop` | Halt current execution loop | Sets `loop.should_stop = True` |
| `/plan <direction>` | Send direction to planner agent | Appends to plan direction queue |
| `/review <criteria>` | Send criteria to reviewer agent | Appends to review criteria queue |
| `/show-main-prompt` | Return latest main agent prompt | Reads and returns markdown file |
| `/show-plan` | Return latest plan report | Reads and returns `plan_report.md` |
| `/show-review [round]` | Return review summary | Reads from `review_summaries/` directory |

### Command Forwarding Logic

When a child is active, the daemon forwards eligible commands [based on Diagram 2](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/based on Diagram 2):

1. Daemon polls `daemon_commands.jsonl` at 1s intervals
2. Classifies command as daemon-level or child-level
3. For child-level commands:

- Constructs new `BusCommand` with same `kind` and `text`
- Publishes to `.argusbot/bus/child_control.jsonl`
4. Child process polls `child_control.jsonl` at its own interval
5. Child's `LoopStateStore.on_control_command()` processes the forwarded command

**Sources:**[README.md436-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L436-L444)[codexloop.py695-793](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L695-L793)

---

## Command Availability by Channel

All channels support the core command set, but some features are channel-specific:

| Feature | Terminal | Telegram | Feishu | daemon-ctl |
| --- | --- | --- | --- | --- |
| Plain text auto-routing | ✓ | ✓ | ✓ | ✗ |
| Voice transcription | ✗ | ✓ | ✗ | ✗ |
| Inline button callbacks | ✗ | ✓ | ✗ | ✗ |
| Live log streaming | ✓ | ✗ | ✗ | ✗ |
| BTW response waiting | ✗ | ✗ | ✗ | ✓ (blocks) |
| Multi-workspace support | ✓ | ✗ | ✗ | ✓ |

### Terminal-Specific Features

The terminal monitor console [codexloop.py814-1603](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L814-L1603) provides:

- Real-time log tailing from `daemon.out` and `daemon-events.jsonl`
- Interactive command input with history
- `/exit` to detach without stopping daemon
- Automatic session resume on re-attach

### Telegram-Specific Features

Telegram integration uniquely supports:

- **Voice transcription** via Whisper API [telegram_control.py33-163](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L33-L163)
- **Inline keyboards** for plan approval workflows [README.md441-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L441-L444)
- **Long-polling** to reduce API call frequency [telegram_control.py174-187](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L174-L187)
- **Typing indicators** during execution [README.md405-409](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L405-L409)

### daemon-ctl-Specific Features

The daemon-ctl utility [daemon_ctl.py18-164](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L18-L164) provides:

- Synchronous `/btw` execution with response waiting (180s timeout)
- Exit code-based success/failure reporting
- JSON output for `/status` suitable for parsing
- Scriptable integration for CI/CD pipelines

**Sources:**[codexloop.py814-1603](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L814-L1603)[telegram_control.py33-163](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L33-L163)[daemon_ctl.py18-164](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_ctl.py#L18-L164)

---

## Authentication and Access Control

### Telegram Chat ID Filtering

The Telegram poller enforces single-chat access control [telegram_control.py332-379](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L332-L379):

```
def extract_message_for_chat(*, update: dict[str, Any], expected_chat_id: str) -> dict[str, Any] | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    if not _message_matches_chat(message=message, expected_chat_id=expected_chat_id):
        return None  # Ignore messages from other chats
    return message
```

The `expected_chat_id` is configured during setup [codexloop.py322-374](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L322-L374) and persisted in `daemon_config.json`. Messages from other chat IDs are silently ignored.

### Feishu Chat ID Filtering

Feishu uses the same pattern with `feishu_chat_id` (typically format `oc_xxx`). Group messages require the bot to be added to the chat [README.md265-277](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L265-L277)

### Token-Based Daemon Lock

For Telegram, the daemon enforces single-daemon-per-token exclusivity using lock files in `/tmp/argusbot-token-locks/`[codexloop.py626-649](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L626-L649):

1. On daemon start, creates `<token_hash>.json` with PID and bus_dir
2. If lock file exists with live PID, daemon exits with error
3. On graceful shutdown, removes lock file
4. Stale lock files (dead PID) are overwritten

This prevents multiple daemons from conflicting on `getUpdates` API calls (which returns 409 Conflict).

### No Built-in Authentication

ArgusBot does not implement password-based authentication. Security relies on:

- Bot token secrecy (Telegram/Feishu)
- Filesystem permissions on `.argusbot/` directory
- Network isolation for terminal/daemon-ctl access

**Sources:**[telegram_control.py332-379](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L332-L379)[codexloop.py322-374](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L322-L374)[codexloop.py626-649](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L626-L649)[README.md265-277](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L265-L277)

---

## Error Handling and Reliability

### Telegram Polling Resilience

The `TelegramCommandPoller` implements retry logic for transient failures [telegram_control.py219-253](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L219-L253):

```
def _run(self) -> None:
    while not self._stop_event.is_set():
        try:
            updates = self._fetch_updates()
        except Exception as exc:
            self._emit_error(f"telegram getUpdates unexpected error: {exc}")
            self._stop_event.wait(self.poll_interval_seconds)  # Back off before retry
            continue
        # Process updates...
```

Network errors (`URLError`, `TimeoutError`) are caught, logged, and retried after `poll_interval_seconds`.

### Whisper Transcription Fallback

If Whisper API transcription fails, the command is skipped but polling continues [telegram_control.py54-80](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L54-L80):

```
def transcribe_update(self, *, update: dict[str, Any], expected_chat_id: str) -> str | None:
    # ... extract audio ...
    if not self.api_key:
        if not self._missing_api_key_reported:
            self._emit_error("missing OPENAI_API_KEY")
            self._missing_api_key_reported = True  # Report only once
        return None
    # ... attempt transcription ...
```

The `_missing_api_key_reported` flag prevents log spam from repeated failures.

### JSONL Bus Corruption Protection

The `JsonlCommandBus` implementation (not in provided files, but referenced) handles malformed lines by skipping them and logging errors. The append-only nature of JSONL files prevents partial writes from corrupting the entire file.

### Child Process Crash Recovery

When a child process crashes, the daemon detects it via `poll()` and logs the exit code. The daemon remains running and accepts new `/run` commands to start fresh child processes [codexloop.py695-793](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L695-L793)

**Sources:**[telegram_control.py219-253](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L219-L253)[telegram_control.py54-80](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_control.py#L54-L80)[codexloop.py695-793](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codexloop.py#L695-L793)