# Control and Communication
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/daemon_ctl.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py)
- [codex_autoloop/telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py)
- [tests/test_telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py)

This page explains how users control ArgusBot and receive notifications through various channels. It covers the command flow architecture, the JSONL-based message bus, and the integration of multiple control interfaces (Telegram, Feishu, terminal).

For details on the daemon's lifecycle management and process orchestration, see [Daemon Mode Architecture](/waltstephen/ArgusBot/3.2-daemon-mode-architecture). For specifics on each control channel's implementation, see [Command Channels Overview](/waltstephen/ArgusBot/5.1-command-system-overview).

## Purpose and Scope

ArgusBot supports multiple control interfaces that converge on a unified command bus architecture. Users can issue commands via:

- **Telegram bot** - Remote control with mobile/desktop clients
- **Feishu (Lark) app** - Remote control optimized for Chinese network environments
- **Terminal CLI** - Direct command-line interface (`argusbot` command)
- **Monitor console** - Interactive terminal session attached to daemon
- **daemon-ctl utility** - Programmatic local control

All control channels produce normalized `BusCommand` objects that flow through a JSONL-based message bus to the daemon process, which routes them to appropriate handlers.

## Control Flow Architecture

The following diagram illustrates how commands from different sources flow through the system to reach the daemon and active child processes:

[Flowchart Diagram]

**Sources:**[codex_autoloop/codexloop.py808-812](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L808-L812)[codex_autoloop/telegram_control.py165-330](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L165-L330)[codex_autoloop/daemon_ctl.py166-167](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L166-L167)

## Command Bus System

ArgusBot uses a JSONL (JSON Lines) file-based message bus for inter-process communication. This architecture enables:

- **Decoupled communication** - Daemon and pollers operate independently
- **Persistence** - Commands survive process crashes
- **Observability** - Commands visible as plain text files
- **Simplicity** - No external message broker required

### Bus Architecture

[Flowchart Diagram]

**Sources:**[codex_autoloop/codexloop.py808-812](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L808-L812)[codex_autoloop/daemon_ctl.py23-24](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L23-L24)

### BusCommand Structure

The `BusCommand` dataclass normalizes all commands regardless of source:

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `str` | Command type: `"run"`, `"inject"`, `"stop"`, `"mode"`, etc. |
| `text` | `str` | Command payload (objective, instruction, mode name) |
| `source` | `str` | Origin identifier: `"telegram"`, `"feishu"`, `"terminal"` |
| `ts` | `float` | Unix timestamp when command was created |

**Sources:**[codex_autoloop/daemon_bus.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py) (referenced in imports at [codex_autoloop/codexloop.py19](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L19-L19))

## Command Parsing and Normalization

Each control channel implements its own parser but produces the same `BusCommand` output:

### Telegram Command Parsing

The `parse_command_from_update` function handles:

- Text commands (`/run`, `/inject`, `/stop`)
- Callback queries from inline keyboards (`plan_run:`, `plan_reject:`)
- Voice messages (via Whisper API transcription)
- Plain text auto-routing (inject when running, run when idle)

[Flowchart Diagram]

**Example command patterns:**

| Input | Parsed Command |
| --- | --- |
| `/run build feature` | `kind="run"`, `text="build feature"` |
| `/inject fix tests` | `kind="inject"`, `text="fix tests"` |
| `plain text` (when running) | `kind="inject"`, `text="plain text"` |
| `/mode auto` | `kind="mode"`, `text="auto"` |
| `/btw what is the plan?` | `kind="btw"`, `text="what is the plan?"` |
| `/new` | `kind="new"`, `text=""` |

**Sources:**[codex_autoloop/telegram_control.py332-361](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L332-L361)[codex_autoloop/telegram_control.py420-488](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L420-L488)

### Terminal Command Parsing

The `parse_terminal_command` function provides similar normalization for terminal input:

[Flowchart Diagram]

**Sources:**[codex_autoloop/codexloop.py947-988](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L947-L988)[tests/test_codexloop.py7-38](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_codexloop.py#L7-L38)

## Command Routing Logic

The daemon implements a two-tier routing system:

### Daemon-Level Commands

Handled directly by the daemon process:

| Command | Action | Implementation |
| --- | --- | --- |
| `/run <objective>` | Spawn new child process | [telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py)`_on_command` |
| `/mode <mode>` | Update planner mode | Sets `default_plan_mode` |
| `/btw <question>` | Start BTW side-agent | Spawns read-only query agent |
| `/daemon-stop` | Shutdown daemon | Sets `_stop_requested` flag |
| `/status` | Report status | Returns `daemon_status.json` |

### Child-Level Commands

Forwarded to active child process via `child_control.jsonl`:

| Command | Action | Implementation |
| --- | --- | --- |
| `/inject <text>` | Add to operator messages | Appends to `operator_messages.md` |
| `/plan <direction>` | Set plan direction | Updates plan agent context |
| `/review <criteria>` | Set review criteria | Updates reviewer agent context |
| `/stop` | Halt execution | Sets stop flag in state |

**Sources:**[codex_autoloop/codexloop.py123](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L123-L123) (command dispatch), [codex_autoloop/daemon_ctl.py18-164](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L18-L164)

## Response and Notification Flow

The system sends responses back through the same channels:

[Flowchart Diagram]

**Sources:** Referenced in architecture diagrams; implementation in `telegram_notifier.py` and `feishu_notifier.py` (not provided)

## Monitor Console

The `run_monitor_console` function provides an interactive terminal session that:

1. **Tails log files** - Shows daemon output, event log, and child process logs
2. **Accepts commands** - Parses terminal input and publishes to bus
3. **Displays status** - Shows state file snapshots on demand
4. **Auto-tracks child** - Switches to new child log when run starts

### Monitor Console Flow

[State Diagram]

**Sources:**[codex_autoloop/codexloop.py814-946](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L814-L946)

## Whisper Voice Transcription

The Telegram integration supports voice message transcription via OpenAI's Whisper API:

### Transcription Flow

1. **Extract audio file** - Detects `voice`, `audio`, or `document` with audio MIME type
2. **Download from Telegram** - Uses `getFile` and file download APIs
3. **Transcribe via Whisper** - POSTs multipart form to `/v1/audio/transcriptions`
4. **Parse as command** - Treats transcript as text command input

### Supported Audio Formats

| Message Type | File Extension | Notes |
| --- | --- | --- |
| Voice | `.ogg` | Native Telegram voice messages |
| Audio | `.m4a`, `.mp3` | Audio files with `file_name` |
| Document | Any with `audio/*` MIME | Generic audio documents |

**Sources:**[codex_autoloop/telegram_control.py33-163](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L33-L163)[codex_autoloop/telegram_control.py381-407](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L381-L407)[tests/test_telegram_control.py282-298](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py#L282-L298)

## Command List Reference

The following table summarizes all supported commands across channels:

| Command | Telegram | Terminal | daemon-ctl | Description |
| --- | --- | --- | --- | --- |
| `/run <obj>` | ✓ | ✓ | ✓ | Start new run with objective |
| `/inject <text>` | ✓ | ✓ | ✓ | Inject instruction to active run |
| `/stop` | ✓ | ✓ | ✓ | Stop active run |
| `/new` | ✓ | ✓ | ✓ | Force fresh session on next run |
| `/mode <mode>` | ✓ | ✓ | ✓ | Set planner mode (off/auto/record) |
| `/plan <direction>` | ✓ | ✓ | ✓ | Send direction to planner |
| `/review <criteria>` | ✓ | ✓ | ✓ | Send criteria to reviewer |
| `/btw <question>` | ✓ | ✓ | ✓ | Ask BTW read-only agent |
| `/status` | ✓ | ✓ | ✓ | Show daemon status |
| `/daemon-stop` | ✓ | ✓ | ✓ | Shutdown daemon |
| `/show-main-prompt` | ✓ | ✓ | ✓ | Display latest main prompt |
| `/show-plan` | ✓ | ✓ | ✓ | Display plan report |
| `/show-review [N]` | ✓ | ✓ | ✓ | Display review summary |
| `/help` | ✓ | ✓ | ✓ | Show command help |
| Voice messages | ✓ | ✗ | ✗ | Transcribe and parse as command |

**Sources:**[codex_autoloop/codexloop.py248-301](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L248-L301)[codex_autoloop/daemon_ctl.py213-247](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L213-L247)[tests/test_telegram_control.py43-216](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py#L43-L216)

## Error Handling

Each control channel implements error handling appropriate to its context:

### Telegram Poller Error Handling

- **Network errors** - Logged but do not crash polling loop
- **API errors** - Reported via `on_error` callback
- **Malformed responses** - Skipped silently
- **Timeout errors** - Expected and handled gracefully

### Terminal Monitor Error Handling

- **Log file disappears** - Continues tracking, awaits reappearance
- **Input stream closes** - Exits monitor cleanly with `"Input closed"`
- **Command parsing fails** - Silently ignores invalid input
- **Bus write fails** - Raises exception to user

**Sources:**[codex_autoloop/telegram_control.py219-253](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L219-L253)[codex_autoloop/telegram_control.py284-330](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L284-L330)[tests/test_telegram_control.py315-357](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py#L315-L357)