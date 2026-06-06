# Reference
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/daemon_ctl.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py)
- [codex_autoloop/telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py)
- [tests/test_telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py)

This section provides comprehensive reference documentation for all commands, configuration options, events, and file structures in ArgusBot. Use this as a lookup guide when you need precise details about specific features, arguments, or system artifacts.

**Related Pages:**

- For getting started tutorials and examples, see [Getting Started](/waltstephen/ArgusBot/2-getting-started)
- For architectural concepts and design patterns, see [Architecture](/waltstephen/ArgusBot/3-architecture)
- For control channel setup and usage, see [Control and Communication](/waltstephen/ArgusBot/5-control-and-communication)
- For model configuration and AI backends, see [Models and AI Configuration](/waltstephen/ArgusBot/6-models-and-ai-configuration)

---

## Reference Categories

ArgusBot reference documentation is organized into four main categories, each detailed in its own subsection:

| Category | Page | Purpose |
| --- | --- | --- |
| **Commands** | [8.1](/waltstephen/ArgusBot/8.1-command-reference) | All user-facing commands (`/run`, `/inject`, `/stop`, etc.) with syntax and behavior |
| **Configuration** | [8.2](/waltstephen/ArgusBot/8.2-cli-arguments-reference) | CLI arguments, daemon config fields, and environment variables |
| **Events** | [8.3](/waltstephen/ArgusBot/8.3-event-types-reference) | Event types emitted by the system for notifications and logging |
| **File Structure** | [8.4](/waltstephen/ArgusBot/8.4-file-structure-reference) | Directory layout, state files, logs, and artifacts created by ArgusBot |

---

## Command Entry Points

ArgusBot provides multiple command entry points that route to different subsystems:

[Flowchart Diagram]

**Sources:**[README.md129-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L129-L166)[QUICKSTART.md23-42](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L23-L42)

---

## Configuration Hierarchy

Configuration flows from multiple sources with precedence rules:

[Flowchart Diagram]

**Sources:**[README.md88-96](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L88-L96)[README.md454-489](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L454-L489)

---

## Event Flow Architecture

Events are emitted at key execution milestones and routed to multiple consumers:

[Flowchart Diagram]

**Sources:**[README.md216-218](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L216-L218)[README.md245-248](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L245-L248)

---

## File Structure Overview

ArgusBot creates a standardized directory structure under `.argusbot/`:

[Flowchart Diagram]

**Sources:**[README.md454-489](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L454-L489)

---

## Quick Reference Tables

### Core Commands

| Command | Context | Purpose |
| --- | --- | --- |
| `/run <objective>` | Daemon idle | Start new run with objective |
| `/inject <text>` | Active run | Add instruction to next round |
| `/stop` | Active run | Halt current run |
| `/status` | Any | Show daemon/run status |
| `/plan <direction>` | Active run | Update planner direction |
| `/review <criteria>` | Active run | Update review criteria |
| `/btw <question>` | Any | Ask read-only question |
| `/new` | Any | Force fresh session on next run |
| `/mode <off\|auto\|record>` | Any | Change planner mode |
| `/daemon-stop` | Any | Shutdown daemon process |

See [Command Reference](/waltstephen/ArgusBot/8.1-command-reference) for complete details.

**Sources:**[README.md149-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L149-L166)[QUICKSTART.md28-42](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L28-L42)

### Key CLI Arguments

| Argument | Type | Purpose |
| --- | --- | --- |
| `--max-rounds` | int | Maximum loop iterations (default: 500) |
| `--session-id` | str | Codex session to resume |
| `--check` | str | Acceptance test command |
| `--main-model` | str | Model for main agent |
| `--reviewer-model` | str | Model for reviewer agent |
| `--planner-model` | str | Model for planner agent |
| `--copilot-proxy` | flag | Route through GitHub Copilot |
| `--yolo` | flag | Enable no-sandbox mode |
| `--state-file` | path | State persistence file |
| `--telegram-bot-token` | str | Telegram bot credentials |
| `--feishu-app-id` | str | Feishu app credentials |

See [Configuration Reference](/waltstephen/ArgusBot/8.2-cli-arguments-reference) for complete details.

**Sources:**[README.md200-228](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L200-L228)[README.md236-248](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L236-L248)

### Common Event Types

| Event Type | Trigger | Consumers |
| --- | --- | --- |
| `loop.started` | Loop initialization | Terminal, Telegram, Feishu |
| `round.started` | Round begins | Terminal, logs |
| `round.review.completed` | Reviewer finishes | Terminal, Telegram, Feishu |
| `loop.completed` | Loop exits | Terminal, Telegram, Feishu, archive |
| `run.finished` | Child process exits | Daemon, archive |

See [Event Types Reference](/waltstephen/ArgusBot/8.3-event-types-reference) for complete details.

**Sources:**[README.md216-218](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L216-L218)[README.md245-248](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L245-L248)

### Key Files

| File | Purpose | Format |
| --- | --- | --- |
| `daemon_config.json` | Persistent daemon settings | JSON |
| `daemon_status.json` | Current daemon state | JSON |
| `last_state.json` | Latest session state | JSON |
| `daemon_commands.jsonl` | Command bus (daemon) | JSONL |
| `child_control.jsonl` | Command bus (child) | JSONL |
| `operator_messages.md` | Inject history | Markdown |
| `daemon-events.jsonl` | Event log | JSONL |
| `argusbot-run-archive.jsonl` | Run history | JSONL |

See [File Structure Reference](/waltstephen/ArgusBot/8.4-file-structure-reference) for complete details.

**Sources:**[README.md454-489](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L454-L489)

---

## Model Presets

ArgusBot provides predefined model presets for common use cases:

| Preset | Main Agent | Reviewer Agent | Use Case |
| --- | --- | --- | --- |
| `quality` | gpt-5.4/high | gpt-5.4/high | High-quality results |
| `copilot` | gpt-5.4/high | gpt-5.4/high | GitHub Copilot quota |
| `codex52-xhigh` | gpt-5.2-codex/xhigh | gpt-5.2-codex/xhigh | Maximum reasoning |
| `quality-xhigh` | gpt-5.4/xhigh | gpt-5.4/xhigh | Highest quality |
| `balanced` | gpt-5.3-codex/high | gpt-5.1-codex/medium | Cost/quality balance |
| `codex-xhigh` | gpt-5.3-codex/xhigh | gpt-5.3-codex/xhigh | Extended reasoning |
| `cheap` | gpt-5.1-codex-mini/medium | gpt-5-codex-mini/low | Low cost |
| `max` | gpt-5.1-codex-max/xhigh | gpt-5.3-codex/high | Maximum capability |

View available presets:

```
python -m codex_autoloop.model_catalog
```

**Sources:**[README.md524-548](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L524-L548)

---

## Planner Modes

| Mode | Behavior | Follow-up Proposals | Auto-execution |
| --- | --- | --- | --- |
| `off` | Disabled | No | No |
| `auto` | Enabled | Yes | Yes (after delay) |
| `record` | Enabled | Yes | No (manual approval) |

Default mode is `auto` after setup. Change mode:

```
argusbot-daemon-ctl --bus-dir .argusbot/bus mode auto
```

**Sources:**[README.md167-173](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L167-L173)[QUICKSTART.md44-47](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L44-L47)

---

## Command Routing Map

This diagram shows how commands map to actual code handlers:

[Flowchart Diagram]

**Sources:**[README.md149-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L149-L166) Diagram 2 from context

---

## State File Schema

The `last_state.json` file persists session state across runs:

[Flowchart Diagram]

**Sources:** Diagram 4 from context, [README.md454-489](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L454-L489)

---

## For Detailed Information

Each subsection provides complete reference material:

- **[Command Reference](/waltstephen/ArgusBot/8.1-command-reference)**: Full syntax, parameters, and behavior for all commands
- **[Configuration Reference](/waltstephen/ArgusBot/8.2-cli-arguments-reference)**: Complete CLI argument reference, daemon config schema, and environment variables
- **[Event Types Reference](/waltstephen/ArgusBot/8.3-event-types-reference)**: All event types, their payloads, and when they're emitted
- **[File Structure Reference](/waltstephen/ArgusBot/8.4-file-structure-reference)**: Complete directory layout, file formats, and artifact descriptions