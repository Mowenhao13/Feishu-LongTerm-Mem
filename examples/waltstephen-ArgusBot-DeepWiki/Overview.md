# Overview
Relevant source files
- [QUICKSTART.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1)
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)

This document provides a high-level introduction to ArgusBot, explaining its purpose, key capabilities, and system architecture. For installation and setup instructions, see [Getting Started](/waltstephen/ArgusBot/2-getting-started). For detailed architectural deep dives, see [Architecture](/waltstephen/ArgusBot/3-architecture).

## Purpose and Scope

ArgusBot is an automated supervisor system for Codex CLI that implements a multi-agent loop architecture to solve the "agent stopped early and asked for next instruction" problem. This overview explains what ArgusBot is, its core capabilities, and how its major components interact.

## What is ArgusBot?

ArgusBot is a Python-based automation layer wrapping Codex CLI execution. Core modules:

- **Multi-agent orchestration**: `CodexRunner` executes tasks via `codex exec`/`codex exec resume`, while `ReviewerAgent` and `PlannerAgent` provide quality control and strategic oversight
- **Persistent execution loops**: `AutoLoopOrchestrator` (class in [src/codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/orchestrator.py)) continues iterating until reviewer returns `done` status and all acceptance checks pass
- **Remote control**: `TelegramNotifier`/`FeishuNotifier` classes provide 24/7 monitoring; `TelegramCommandPoller`/`FeishuCommandPoller` handle command injection
- **State management**: Session persistence via `last_state.json` and `argusbot-run-archive.jsonl` enables cross-run continuity

The system addresses premature agent stopping by implementing a reviewer gate (`done`/`continue`/`blocked` schema) and loop mechanism that only terminates on explicit completion.

**Sources**: [README.md9-23](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L9-L23)[src/codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/orchestrator.py)[src/codex_autoloop/reviewer_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/reviewer_agent.py)[src/codex_autoloop/codex_runner.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/codex_runner.py)

## Key Capabilities

| Capability | Description |
| --- | --- |
| **Multi-Agent Loop** | Main agent for task execution, reviewer agent for quality gating (`done`/`continue`/`blocked`), planner agent for strategic overview |
| **Daemon Mode** | Persistent background process that accepts remote commands even when no run is active |
| **CLI Mode** | Single-run execution for immediate tasks |
| **Remote Control** | Telegram and Feishu integration for `/run`, `/inject`, `/stop`, `/status` commands |
| **Session Resumption** | Automatic session ID tracking and continuation across runs |
| **Stall Detection** | Watchdog monitoring with soft diagnosis (1h) and hard restart (3h) thresholds |
| **Automated Planning** | Background planner sweeps generate strategic reports and propose follow-up objectives |
| **Voice Transcription** | Telegram voice/audio messages auto-transcribed via Whisper API |
| **Copilot Proxy** | Optional routing through GitHub Copilot quota instead of OpenAI API |

**Sources**: [README.md66-83](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L66-L83)[README.md18-22](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L18-L22)

## System Architecture

The following diagram shows the high-level architecture and component relationships:

### Overall System Structure

[Flowchart Diagram]

**Sources**: [README.md1-23](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L1-L23) High-level architecture diagrams

### Core Components to Code Mapping

[Flowchart Diagram]

**Sources**: [README.md129-190](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L129-L190) High-level system architecture diagrams

## Operational Modes

ArgusBot supports two primary operational modes:

### Daemon Mode

**Entry point**: `argusbot-daemon` or `argusbot init`**Implementation**: [src/codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/telegram_daemon.py)**Main class**: `TelegramDaemon` with `DaemonApp.run_until_shutdown()`[src/codex_autoloop/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/daemon_app.py)

Daemon mode provides persistent, always-on operation:

- Background process tracked via `.argusbot/daemon.pid`
- `TelegramCommandPoller.poll_updates()`, `FeishuCommandPoller.poll_messages()`, and `JsonlCommandBus.read_commands()` accept commands when idle
- `DaemonApp.handle_command()` spawns child processes via `subprocess.Popen()` for each `/run` command
- `DaemonApp.check_plan_follow_up()` implements automated follow-up in `auto` planner mode
- Token-exclusive locking via `/tmp/argusbot-token-locks/{token_hash}` (one daemon per Telegram token)

**Default behavior**: Child runs use `--yolo` mode (line 286 in [src/codex_autoloop/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/daemon_app.py)); `session_id` resumed from `last_state.json` or `argusbot-run-archive.jsonl` fallback.

### CLI Mode

**Entry point**: `argusbot-run`**Implementation**: [src/codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/cli.py) and [src/codex_autoloop/cli_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/cli_app.py)**Main function**: `cli_app.main()` → `AutoLoopOrchestrator.run_full_loop()`

CLI mode provides single-run, synchronous execution:

- Executes one objective via `Orchestrator.run_full_loop()` and exits
- No daemon process or PID file
- Full terminal streaming via `LiveTerminalPrinter`[src/codex_autoloop/live_terminal_printer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/live_terminal_printer.py)
- Optional Telegram/Feishu notifications via `TelegramNotifier.send_message()` and `FeishuNotifier.send_message()`
- Suitable for one-off tasks or scripted automation

**Sources**: [README.md32-63](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L32-L63)[README.md192-228](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L192-L228)[src/codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/telegram_daemon.py)[src/codex_autoloop/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/daemon_app.py)[src/codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/cli.py)[src/codex_autoloop/cli_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/cli_app.py)

## Multi-Agent System

ArgusBot implements a four-agent architecture:

### Agent Roles

| Agent | Implementation | Primary Method | Role |
| --- | --- | --- | --- |
| **Main Agent** | `CodexRunner`[src/codex_autoloop/codex_runner.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/codex_runner.py) | `exec_codex()` | Task execution via `codex exec` or `codex exec resume`; makes code changes, runs commands |
| **Reviewer Agent** | `ReviewerAgent`[src/codex_autoloop/reviewer_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/reviewer_agent.py) | `execute()` | Quality gate; returns `ReviewDecision` with status `done`, `continue`, or `blocked` |
| **Planner Agent** | `PlannerAgent`[src/codex_autoloop/planner_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/planner_agent.py) | `execute()` | Strategic oversight; maintains `plan_report.md` and proposes follow-up objectives |
| **Stall Agent** | `StallAgent`[src/codex_autoloop/stall_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/stall_agent.py) | `check_and_diagnose()` | Watchdog monitoring; diagnoses and recommends recovery from stalls |

### Round Execution Flow

[Flowchart Diagram]

**Sources**: [src/codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/orchestrator.py)[src/codex_autoloop/codex_runner.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/codex_runner.py)[src/codex_autoloop/reviewer_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/reviewer_agent.py)[src/codex_autoloop/planner_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/planner_agent.py)[src/codex_autoloop/stall_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/stall_agent.py)

## Integration Points

ArgusBot integrates with external services through well-defined adapters:

### External Service Integration

| Service | Purpose | Implementation | Key Methods |
| --- | --- | --- | --- |
| **Telegram Bot API** | Remote control and notifications | [src/codex_autoloop/telegram_notifier.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/telegram_notifier.py)[src/codex_autoloop/telegram_command_poller.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/telegram_command_poller.py) | `TelegramNotifier.send_message()`, `TelegramCommandPoller.poll_updates()` |
| **Feishu API** | CN-optimized remote control | [src/codex_autoloop/feishu_notifier.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/feishu_notifier.py)[src/codex_autoloop/feishu_command_poller.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/feishu_command_poller.py) | `FeishuNotifier.send_message()`, `FeishuCommandPoller.poll_messages()` |
| **Codex CLI** | Core task execution engine | [src/codex_autoloop/codex_runner.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/codex_runner.py) | `CodexRunner.exec_codex()` wraps `subprocess.run(['codex', 'exec', ...])` |
| **Whisper API** | Voice transcription (Telegram) | [src/codex_autoloop/telegram_command_poller.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/telegram_command_poller.py) | `transcribe_audio()` calls OpenAI Whisper API with `whisper-1` model |
| **Copilot Proxy** | GitHub Copilot quota routing | [src/codex_autoloop/copilot_proxy_manager.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/copilot_proxy_manager.py) | `CopilotProxyManager.ensure_proxy_running()`, provider override injection |

### State Persistence and Configuration

The system persists configuration and state across multiple files:

[Flowchart Diagram]

**Sources**: [src/codex_autoloop/setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/setup_wizard.py)[src/codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/orchestrator.py)[src/codex_autoloop/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/daemon_app.py)[src/codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/telegram_daemon.py)[src/codex_autoloop/reviewer_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/reviewer_agent.py)[src/codex_autoloop/planner_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/planner_agent.py)[src/codex_autoloop/btw_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/btw_agent.py)

## Key Design Principles

ArgusBot's architecture embodies several core design principles:

1. **Separation of Concerns**: `TelegramDaemon` manages lifecycle; `AutoLoopOrchestrator` orchestrates execution; agents (`ReviewerAgent`, `PlannerAgent`, `StallAgent`) perform specialized tasks
2. **State Persistence**: JSON (`last_state.json`, `daemon_status.json`) and markdown (`operator_messages.md`, `plan_report.md`, `review_summaries/`) enable session resumption and audit trails
3. **Loose Coupling**: External services integrated via adapters (`TelegramNotifier`, `FeishuNotifier`); system functions without remote control if not configured
4. **Progressive Enhancement**: CLI mode (`cli_app.main()`) works independently; daemon mode (`DaemonApp.run_until_shutdown()`) adds persistence; remote control adds convenience
5. **Fail-Safe Mechanisms**: Multiple stop conditions (`max_rounds`, `has_made_progress()`, `ReviewDecision.status == "blocked"`); stall detection via `check_stall_watchdog()` with soft (1h) and hard (3h) thresholds
6. **Operator Visibility**: Markdown logging; `LiveTerminalPrinter` real-time streaming; event emissions via `emit_event()`

**Sources**: [src/codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/orchestrator.py)[src/codex_autoloop/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/daemon_app.py)[src/codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/telegram_daemon.py)[src/codex_autoloop/reviewer_agent.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/reviewer_agent.py)[src/codex_autoloop/live_terminal_printer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/src/codex_autoloop/live_terminal_printer.py)

## Next Steps

- For installation and first-run setup, see [Getting Started](/waltstephen/ArgusBot/2-getting-started)
- For architectural deep dives, see [Architecture](/waltstephen/ArgusBot/3-architecture)
- For command reference, see [Command Reference](/waltstephen/ArgusBot/8.1-command-reference)
- For configuration details, see [Configuration Reference](/waltstephen/ArgusBot/8.2-cli-arguments-reference)

**Sources**: [README.md1-638](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L1-L638)[QUICKSTART.md1-183](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L1-L183)