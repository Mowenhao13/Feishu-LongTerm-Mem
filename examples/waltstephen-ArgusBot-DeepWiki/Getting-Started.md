# Getting Started
Relevant source files
- [QUICKSTART.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1)
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)

This page provides a high-level orientation to ArgusBot and guides you through the essential steps to begin using the system. It covers prerequisites, installation, and the basic workflow for initial setup and first operations.

For detailed step-by-step instructions on installation and setup, see [Installation and Initial Setup](/waltstephen/ArgusBot/2.1-installation-and-initial-setup). For a hands-on tutorial with practical examples, see [Quickstart Tutorial](/waltstephen/ArgusBot/2.2-quickstart-tutorial). For in-depth configuration details, see [Configuration Overview](/waltstephen/ArgusBot/2.3-configuration-overview).

---

## What You Need Before Starting

ArgusBot is a Python-based supervisor that wraps Codex CLI to provide automated multi-agent execution loops. Before installing ArgusBot, ensure the following prerequisites are met:

| Requirement | Purpose | Verification Command |
| --- | --- | --- |
| **Codex CLI** | Core AI agent execution engine | `codex --version` |
| **Python 3.8+** | Runtime for ArgusBot components | `python --version` |
| **Authenticated Codex** | API access for agent operations | `codex auth status` |
| **Control Channel (Optional)** | Remote monitoring and control | Telegram bot token OR Feishu app credentials |

**Important**: ArgusBot cannot function without a working Codex CLI installation. The setup wizard will verify Codex availability at [codex_autoloop/setup_wizard.py82-102](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L82-L102) during initialization.

**Sources**: [README.md38-40](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L38-L40)[codex_autoloop/setup_wizard.py82-102](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L82-L102)

---

## Installation

ArgusBot is installed as a Python package. The recommended approach uses editable mode to allow easy updates:

```
# Clone the repository
git clone <argusbot-repo-url> ArgusBot
cd ArgusBot
 
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
 
# Install in editable mode
pip install -e .
```

After installation, verify the `argusbot` command is available:

```
argusbot help
```

This should display the command reference and confirm successful installation.

**Sources**: [README.md89-95](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L89-L95)[QUICKSTART.md3-9](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L3-L9)

---

## First Run Workflow

ArgusBot provides a streamlined first-run experience through the `argusbot` command. The workflow differs based on whether configuration already exists:

[Flowchart Diagram]

**Diagram: First Run Decision Flow and Setup Sequence**

The entry point `argusbot` is defined in [setup.py18](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/setup.py#L18-L18) as a console script that invokes [codex_autoloop/codexloop.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#LNaN-LNaN)

**Sources**: [README.md129-149](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L129-L149)[QUICKSTART.md12-42](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L12-L42)[codex_autoloop/codexloop.py1-50](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L1-L50)[codex_autoloop/setup_wizard.py1-300](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L1-L300)

---

## Command Entry Points and Code Mapping

ArgusBot provides multiple command-line entry points, each mapping to specific Python modules. Understanding this mapping helps troubleshoot issues and customize behavior:

[Flowchart Diagram]

**Diagram: Command Entry Points to Code Module Mapping**

All console scripts are registered in [setup.py17-24](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/setup.py#L17-L24) The `argusbot` command implements intelligent routing logic at [codex_autoloop/codexloop.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L1-L100) to determine whether to run setup, start daemon, or attach to existing process.

**Sources**: [setup.py17-24](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/setup.py#L17-L24)[codex_autoloop/codexloop.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L1-L100)[codex_autoloop/telegram_daemon.py1-50](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1-L50)

---

## Operational Modes

ArgusBot operates in two distinct modes, each suited for different use cases:

### CLI Mode (Single Run)

Execute a one-time task without persistent background process:

```
argusbot-run \
  --max-rounds 10 \
  --check "pytest -q" \
  "Implement feature X and iterate until tests pass"
```

**Key characteristics**:

- Process exits when objective completes or max rounds reached
- Session state saved to `.argusbot/last_state.json` for potential resumption
- Direct terminal output streaming
- No persistent daemon required

The CLI mode entry point is [codex_autoloop/codexloop.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#LNaN-LNaN) which directly instantiates `LoopEngine` without daemon supervision.

### Daemon Mode (Always-On)

Run a persistent background process that can accept commands even when idle:

```
# Start daemon (done automatically by argusbot on first run)
argusbot-daemon --telegram-bot-token "$TOKEN"
 
# Control via Telegram or terminal
/run "Implement feature X"
/inject "Change approach to Y"
/status
/stop
```

**Key characteristics**:

- Daemon process remains active 24/7
- Spawns child processes for each `/run` command
- Session continuity across multiple runs via `session_id` resolution
- Multi-channel control (Telegram, Feishu, terminal)
- Automated follow-up planning when planner mode is `auto`

The daemon implementation is in [codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py) which manages child process lifecycle and routes commands via JSONL bus files in `.argusbot/bus/`.

**Sources**: [README.md192-228](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L192-L228)[README.md423-453](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L423-L453)[codex_autoloop/codexloop.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#LNaN-LNaN)[codex_autoloop/telegram_daemon.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1-L100)

---

## Configuration Persistence

After running setup, ArgusBot creates a configuration directory structure in your target project:

```
<your-project>/
└── .argusbot/
    ├── daemon_config.json          # Persistent daemon configuration
    ├── daemon.pid                  # Active daemon process ID
    ├── daemon.out                  # Daemon stdout/stderr log
    ├── daemon_status.json          # Current daemon state snapshot
    ├── bus/
    │   ├── daemon_commands.jsonl   # Command bus for daemon
    │   └── child_control.jsonl     # Control bus for active child
    └── logs/
        ├── operator_messages.md    # Global inject history
        ├── last_state.json         # Latest session state
        ├── daemon-events.jsonl     # Event archive
        └── argusbot-run-archive.jsonl  # Run history log

```

The `daemon_config.json` structure is written by [codex_autoloop/setup_wizard.py200-250](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L200-L250) and contains:

- Control channel credentials (Telegram or Feishu)
- Model preset selection or custom model overrides
- Planner mode setting (`off`, `auto`, `record`)
- Optional default check command
- Copilot proxy configuration

**Sources**: [codex_autoloop/setup_wizard.py200-250](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L200-L250)[README.md64](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L64-L64)[README.md476-489](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L476-L489)

---

## Basic Command Reference

Once ArgusBot is running, you can control it through multiple channels. Here are the essential commands:

| Command | Channel | Purpose | Example |
| --- | --- | --- | --- |
| `/run <objective>` | All | Start new execution loop | `/run Implement auth module` |
| `/inject <instruction>` | All | Modify current run mid-execution | `/inject Fix tests first` |
| `/status` | All | Query current state | `/status` |
| `/stop` | All | Halt active run | `/stop` |
| `/new` | Terminal | Force fresh session on next run | `/new` |
| `/mode <off\|auto\|record>` | Terminal | Change planner behavior | `/mode record` |
| `/daemon-stop` | All | Shut down daemon process | `/daemon-stop` |

**Plain text routing**: When daemon is idle, plain text messages are interpreted as `/run` commands. When a run is active, plain text is treated as `/inject` instructions.

Voice messages sent via Telegram are automatically transcribed using the Whisper API and processed as text commands.

For the complete command reference, see [Command Reference](/waltstephen/ArgusBot/8.1-command-reference).

**Sources**: [README.md149-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L149-L166)[README.md385-391](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L385-L391)[codex_autoloop/telegram_daemon.py300-400](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L300-L400)

---

## Next Steps

After completing initial setup, proceed to the following pages based on your needs:

- **[Installation and Initial Setup](/waltstephen/ArgusBot/2.1-installation-and-initial-setup)**: Detailed walkthrough of installation process, setup wizard, and control channel configuration
- **[Quickstart Tutorial](/waltstephen/ArgusBot/2.2-quickstart-tutorial)**: Hands-on tutorial with practical examples covering first run, common workflows, and troubleshooting
- **[Configuration Overview](/waltstephen/ArgusBot/2.3-configuration-overview)**: In-depth explanation of `daemon_config.json`, model presets, and planner modes

For understanding the system architecture, see [Architecture](/waltstephen/ArgusBot/3-architecture). For advanced features like session resumption and automated planning, see [Advanced Topics](/waltstephen/ArgusBot/7-advanced-topics).

**Sources**: [README.md1-638](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L1-L638)[QUICKSTART.md1-183](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L1-L183)