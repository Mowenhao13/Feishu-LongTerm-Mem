# Installation and Initial Setup
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py)
- [tests/test_setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_setup_wizard.py)

This page covers the initial installation of ArgusBot and running the setup wizard to configure your first daemon instance. It walks through installing dependencies, running the interactive setup, choosing a control channel (Telegram or Feishu), and verifying the daemon is running.

For hands-on usage after setup, see [Quickstart Tutorial](/waltstephen/ArgusBot/2.2-quickstart-tutorial). For detailed configuration reference, see [Configuration Overview](/waltstephen/ArgusBot/2.3-configuration-overview).

---

## Prerequisites

Before installing ArgusBot, the following requirements must be met:

| Requirement | Purpose | Verification Command |
| --- | --- | --- |
| Codex CLI | Core execution engine that ArgusBot supervises | `codex --version` |
| Python 3.8+ | Runtime environment for ArgusBot | `python --version` |
| Git | For cloning the repository | `git --version` |
| Control Channel Credentials | For remote control via Telegram or Feishu | See sections below |

**Critical**: Codex CLI must be installed and authenticated before running ArgusBot setup. The setup wizard verifies Codex availability by executing a probe request ([codex_autoloop/setup_wizard.py342-352](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L342-L352)[codex_autoloop/setup_wizard.py355-386](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L355-L386)).

Sources: [README.md38-39](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L38-L39)[codex_autoloop/setup_wizard.py51-58](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L51-L58)

---

## Installation

ArgusBot is installed as a Python package in editable mode. This allows the codebase to remain linked to the installation, useful for development or customization.

```
# Clone the repository
git clone <ArgusBot-repository-url> ArgusBot
cd ArgusBot
 
# Create and activate virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
 
# Install in editable mode
pip install -e .
```

After installation, the following command-line entry points become available:

- `argusbot` - Main operator interface (auto-setup on first run, attach on subsequent runs)
- `argusbot-setup` - Explicit setup wizard invocation
- `argusbot-daemon` - Daemon process launcher
- `argusbot-daemon-ctl` - Daemon control utility
- `argusbot-run` - Single-run CLI mode

Sources: [README.md89-95](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L89-L95)[README.md129-141](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L129-L141)

---

## Running the Setup Wizard

### Invocation

The setup wizard can be launched through multiple entry points:

```
# Method 1: First-time argusbot invocation (recommended)
cd /path/to/your/project
argusbot init
 
# Method 2: Explicit setup command
argusbot-setup --run-cd /path/to/your/project
 
# Method 3: Python module invocation
python -m codex_autoloop.setup_wizard --run-cd /path/to/your/project
```

The wizard operates in the target project directory (where you want ArgusBot to control work), not in the ArgusBot repository itself. It creates a `.argusbot/` directory in the target project to store configuration and state.

Sources: [README.md43-62](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L43-L62)[codex_autoloop/setup_wizard.py45-340](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L45-L340)

---

## Setup Wizard Flow

The setup wizard executes a multi-stage initialization sequence with validation at each step.

**Setup Wizard Execution Flow**

[Flowchart Diagram]

Sources: [codex_autoloop/setup_wizard.py45-340](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L45-L340)[codex_autoloop/setup_wizard.py610-646](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L610-L646)

---

## Control Channel Configuration

ArgusBot supports three control channel configurations:

### Configuration Options

| Channel | Use Case | Required Credentials |
| --- | --- | --- |
| `telegram` | Global access, recommended for most users | `bot_token`, `chat_id` |
| `feishu` | Optimized for Chinese network environments | `app_id`, `app_secret`, `chat_id` |
| `both` | Dual-channel redundancy | All of the above |

**Control Channel Selection Flow**

[Flowchart Diagram]

Sources: [codex_autoloop/setup_wizard.py726-743](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L726-L743)[codex_autoloop/setup_wizard.py850-870](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L850-L870)

### Telegram Setup Details

**Token Acquisition**: Create a bot via [@BotFather](https://t.me/BotFather) on Telegram. The token format is `<bot_id>:<secret>`, for example `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`.

**Chat ID Resolution**: The setup wizard supports automatic chat ID resolution via the `resolve_effective_chat_id()` function ([codex_autoloop/setup_wizard.py473-518](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L473-L518)):

1. If explicit chat ID provided, use it directly
2. If `"auto"` specified:

- Poll Telegram `getUpdates` API for 120 seconds
- User must send `/start` or any message to the bot during this window
- Extract chat ID from update
- On conflict (409 error), fallback to existing `daemon_config.json` or token lock metadata

**Token Lock Enforcement**: The `acquire_token_lock()` call ([codex_autoloop/setup_wizard.py143-152](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L143-L152)) ensures only one daemon process can claim a given bot token. Lock files are stored in `/tmp/argusbot-token-locks/` by default.

Sources: [codex_autoloop/setup_wizard.py473-518](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L473-L518)[codex_autoloop/setup_wizard.py745-759](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L745-L759)[codex_autoloop/setup_wizard.py873-890](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L873-L890)

### Feishu Setup Details

**Prerequisites**:

1. Create a Feishu app in the Open Platform
2. Enable bot capability for the app
3. Grant scopes: `im:message.history:readonly`, `im:message:readonly`, or `im:message`
4. Publish and install the app in your tenant
5. Add bot to target group chat

**Chat ID Format**: For `receive_id_type=chat_id` (default), the chat ID must start with `oc_` ([codex_autoloop/setup_wizard.py826-833](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L826-L833)). Example: `oc_1a2b3c4d5e6f`.

**Validation**: The `resolve_feishu_config()` function ([codex_autoloop/setup_wizard.py893-913](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L893-L913)) validates all three fields (app_id, app_secret, chat_id) are provided together and the chat_id matches the expected format.

Sources: [README.md230-276](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L230-L276)[codex_autoloop/setup_wizard.py761-772](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L761-L772)[codex_autoloop/setup_wizard.py893-913](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L893-L913)

---

## Model and Proxy Configuration

### Model Preset Selection

The wizard prompts for model configuration via `prompt_model_choice()` ([codex_autoloop/setup_wizard.py775-798](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L775-L798)):

**Available Options**:

- `0` - Inherit Codex CLI defaults (recommended for most users)
- `1-N` - Named presets from `MODEL_PRESETS` (quality, balanced, cheap, copilot, etc.)
- `N+1` - Custom model specification

If a preset is selected, the wizard extracts `main_model`, `main_reasoning_effort`, `reviewer_model`, and `reviewer_reasoning_effort` from the preset definition. For custom selection, the wizard prompts for each field individually ([codex_autoloop/setup_wizard.py127-134](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L127-L134)).

Sources: [codex_autoloop/setup_wizard.py775-798](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L775-L798)[codex_autoloop/setup_wizard.py106-134](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L106-L134)

### Copilot Proxy Integration

The `resolve_copilot_proxy_settings()` function ([codex_autoloop/setup_wizard.py389-432](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L389-L432)) handles automatic detection and installation of the `copilot-proxy` tool:

**Auto-Detection Locations**:

- `~/copilot-proxy`
- `~/copilot-codex-proxy`
- `~/.argusbot/tools/copilot-proxy`

**Bootstrap Installation**: If no proxy is detected and the user selects the `copilot` preset or explicitly enables proxy:

1. Prompt user for installation confirmation ([codex_autoloop/setup_wizard.py435-451](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L435-L451))
2. Call `bootstrap_proxy_checkout()` to clone and install proxy to `~/.argusbot/tools/copilot-proxy`
3. Store proxy directory in configuration

Sources: [codex_autoloop/setup_wizard.py389-451](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L389-L451)[README.md97-127](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L97-L127)

---

## Planner Mode Selection

The setup wizard prompts for planner mode via `prompt_planner_mode_choice()` ([codex_autoloop/setup_wizard.py836-847](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L836-L847)):

| Mode | Description | Auto-Execution |
| --- | --- | --- |
| `off` | Planner agent disabled | No |
| `auto` | Planner enabled with follow-up proposals and auto-execution | Yes (after delay) |
| `record` | Planner enabled for markdown reports only | No |

Default selection is `auto` (option 2). The planner mode determines whether the daemon will propose and auto-execute follow-up objectives after a run completes.

Sources: [codex_autoloop/setup_wizard.py836-847](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L836-L847)[README.md167-172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L167-L172)

---

## Directory Structure Created

The setup wizard creates the following directory hierarchy in the target project:

```
<target-project>/
└── .argusbot/
    ├── daemon_config.json          # Persistent daemon configuration
    ├── daemon.pid                  # Current daemon process ID
    ├── daemon.out                  # Daemon stdout/stderr log
    ├── bus/
    │   ├── daemon_commands.jsonl   # Incoming command bus
    │   └── child_control.jsonl     # Commands forwarded to active child
    └── logs/
        ├── daemon-events.jsonl     # Daemon lifecycle and control events
        ├── operator_messages.md    # All inject/plan/review inputs
        ├── argusbot-run-archive.jsonl  # Run history metadata
        ├── last_state.json         # Latest session state snapshot
        ├── plan_report.md          # Latest planner overview
        ├── plan_todo.md            # Mirrored TODO board
        └── review_summaries/       # Per-round review artifacts
            ├── index.md            # Latest review summary
            └── round-NNN.md        # Individual round reviews

```

**Directory Creation Code Flow**:

[Flowchart Diagram]

Sources: [codex_autoloop/setup_wizard.py61-66](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L61-L66)[codex_autoloop/setup_wizard.py195-196](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L195-L196)

---

## Daemon Launch Process

After configuration is written, the setup wizard launches the daemon as a background process.

**Daemon Launch Sequence**:

```

```

The `resolve_daemon_launch_prefix()` function ([codex_autoloop/setup_wizard.py454-463](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L454-L463)) determines the correct invocation method:

1. Check `CODEX_AUTOLOOP_DAEMON_BIN` environment variable
2. If in local repo context, use `python -m codex_autoloop.telegram_daemon`
3. Otherwise, search for `argusbot-daemon` binary in PATH
4. Fallback to `python -m codex_autoloop.telegram_daemon`

Sources: [codex_autoloop/setup_wizard.py202-290](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L202-L290)[codex_autoloop/setup_wizard.py454-463](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L454-L463)

---

## Configuration File Structure

The setup wizard writes `daemon_config.json` with the following schema ([codex_autoloop/setup_wizard.py169-197](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L197)):

```
{
  "control_channel": "telegram | feishu | both",
  "telegram_bot_token": "<token or null>",
  "telegram_chat_id": "<chat_id or null>",
  "feishu_app_id": "<app_id or null>",
  "feishu_app_secret": "<secret or null>",
  "feishu_chat_id": "<chat_id or null>",
  "feishu_receive_id_type": "chat_id",
  "run_cd": "/absolute/path/to/project",
  "run_check": "<command or null>",
  "run_max_rounds": 100,
  "run_skip_git_repo_check": false,
  "run_full_auto": false,
  "run_yolo": true,
  "run_resume_last_session": true,
  "run_main_model": "<model or null>",
  "run_main_reasoning_effort": "<effort or null>",
  "run_reviewer_model": "<model or null>",
  "run_reviewer_reasoning_effort": "<effort or null>",
  "run_model_preset": "<preset_name or null>",
  "run_copilot_proxy": false,
  "run_copilot_proxy_dir": "<path or null>",
  "run_copilot_proxy_port": 18080,
  "run_planner_mode": "auto | off | record",
  "follow_up_auto_execute_seconds": 600,
  "codex_autoloop_bin": "python -m codex_autoloop.cli",
  "bus_dir": "/absolute/path/.argusbot/bus",
  "logs_dir": "/absolute/path/.argusbot/logs"
}
```

The file is written with mode `0o600` (user read/write only) for credential security ([codex_autoloop/setup_wizard.py199-200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L199-L200)).

Sources: [codex_autoloop/setup_wizard.py169-200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L200)

---

## Verification and Next Steps

### Verify Daemon is Running

After setup completes, verify the daemon process:

```
# Check daemon.pid exists
cat .argusbot/daemon.pid
 
# Verify process is running (Linux/Mac)
ps aux | grep <pid>
 
# Check daemon log for errors
tail -f .argusbot/daemon.out
```

### Test Control Channel

The setup wizard prints control examples at completion ([codex_autoloop/setup_wizard.py321-339](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L321-L339)):

**Terminal control**:

```
argusbot-daemon-ctl --bus-dir .argusbot/bus status
argusbot-daemon-ctl --bus-dir .argusbot/bus run "implement feature X"
```

**Telegram control** (if configured):

- Send `/status` to your bot
- Should receive current daemon status

**Feishu control** (if configured):

- Send `/status` in the configured group
- Should receive current daemon status

### Common Setup Issues

| Issue | Cause | Resolution |
| --- | --- | --- |
| `codex CLI not found in PATH` | Codex not installed | Install Codex CLI before running setup |
| `Could not verify Codex auth` | Invalid API credentials | Re-authenticate Codex: `codex auth` |
| `Telegram getUpdates HTTP 409` | Another instance polling same bot | Stop other instances or use different bot token |
| `Daemon failed to start` | Port conflict or invalid config | Check `daemon.out` log for error details |
| Invalid Feishu chat_id | Wrong receive_id_type or chat format | Ensure chat_id starts with `oc_` for `receive_id_type=chat_id` |

Sources: [codex_autoloop/setup_wizard.py296-339](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L296-L339)[README.md272-276](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L272-L276)

---

## Re-Running Setup

To reconfigure an existing installation, use the `--restart-existing` flag (default: enabled):

```
argusbot init
```

This will:

1. Stop the existing daemon via `stop_existing_daemon()` ([codex_autoloop/setup_wizard.py610-646](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L610-L646))
2. Send `daemon-stop` command to the bus
3. Wait for graceful shutdown
4. Force-terminate if still running after timeout
5. Delete old `daemon.pid`
6. Proceed with new setup

Sources: [codex_autoloop/setup_wizard.py68-69](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L68-L69)[codex_autoloop/setup_wizard.py610-646](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L610-L646)[README.md488-489](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L488-L489)