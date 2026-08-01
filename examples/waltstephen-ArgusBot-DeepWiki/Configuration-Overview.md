# Configuration Overview
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py)
- [codex_autoloop/setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py)

This page explains the core configuration concepts in ArgusBot: the persistent daemon configuration file, model presets for controlling AI quality and cost, and planner modes for automated follow-up behavior. These settings are established during initial setup and stored in `daemon_config.json`.

For detailed reference documentation on all configuration fields and CLI arguments, see [Configuration Reference](/waltstephen/ArgusBot/8.2-cli-arguments-reference). For information on the interactive setup process, see [Installation and Initial Setup](/waltstephen/ArgusBot/2.1-installation-and-initial-setup).

---

## Configuration File Location

ArgusBot stores its persistent configuration in `.argusbot/daemon_config.json` within your project directory. This file is created by the setup wizard and contains all settings needed for daemon operation.

**Typical file structure:**

```
<your-project>/
├── .argusbot/
│   ├── daemon_config.json      # Persistent daemon configuration
│   ├── daemon.pid              # Process ID of running daemon
│   ├── daemon.out              # Daemon output log
│   ├── bus/                    # Command bus directory
│   └── logs/                   # Session state and event logs

```

The configuration file has restricted permissions (mode `0600`) to protect sensitive credentials like Telegram bot tokens and Feishu app secrets.

**Sources:**[codex_autoloop/setup_wizard.py198-200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L198-L200)

---

## daemon_config.json Structure

The daemon configuration file contains the following major sections:

| Section | Fields | Purpose |
| --- | --- | --- |
| **Control Channels** | `control_channel`, `telegram_bot_token`, `telegram_chat_id`, `feishu_app_id`, `feishu_app_secret`, `feishu_chat_id` | Defines which communication channels are enabled (Telegram, Feishu, or both) |
| **Run Settings** | `run_cd`, `run_check`, `run_max_rounds`, `run_yolo`, `run_full_auto`, `run_skip_git_repo_check` | Default settings for daemon-launched runs |
| **Model Configuration** | `run_model_preset`, `run_main_model`, `run_main_reasoning_effort`, `run_reviewer_model`, `run_reviewer_reasoning_effort` | AI model selection and reasoning effort levels |
| **Copilot Proxy** | `run_copilot_proxy`, `run_copilot_proxy_dir`, `run_copilot_proxy_port` | GitHub Copilot proxy integration settings |
| **Planner Configuration** | `run_planner_mode`, `follow_up_auto_execute_seconds` | Automated planning and follow-up behavior |
| **Session Management** | `run_resume_last_session` | Whether to resume previous session or start fresh |
| **Paths** | `bus_dir`, `logs_dir`, `codex_autoloop_bin` | Directory locations for command bus and logs |

**Example configuration file:**

```
{
  "control_channel": "telegram",
  "telegram_bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
  "telegram_chat_id": "987654321",
  "run_cd": "/home/user/myproject",
  "run_check": "pytest -q",
  "run_max_rounds": 100,
  "run_yolo": true,
  "run_model_preset": "balanced",
  "run_copilot_proxy": false,
  "run_planner_mode": "auto",
  "follow_up_auto_execute_seconds": 600,
  "bus_dir": "/home/user/myproject/.argusbot/bus",
  "logs_dir": "/home/user/myproject/.argusbot/logs"
}
```

**Sources:**[codex_autoloop/setup_wizard.py169-197](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L197)

---

## Configuration Resolution Diagram

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py79-137](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L79-L137)[codex_autoloop/setup_wizard.py203-276](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L203-L276)

---

## Model Presets

Model presets provide named configurations for the main agent, reviewer agent, and planner agent. Each preset specifies a model name and reasoning effort level for each agent type.

### Available Presets

| Preset Name | Main Agent | Reviewer Agent | Planner Agent | Use Case |
| --- | --- | --- | --- | --- |
| `quality` | gpt-5.4/high | gpt-5.4/high | gpt-5.4/high | Highest quality, balanced cost |
| `copilot` | gpt-5.4/high | gpt-5.4/high | gpt-5.4/high | For use with GitHub Copilot proxy |
| `codex52-xhigh` | gpt-5.2-codex/xhigh | gpt-5.2-codex/xhigh | gpt-5.2-codex/xhigh | Maximum reasoning on Codex 5.2 |
| `quality-xhigh` | gpt-5.4/xhigh | gpt-5.4/xhigh | gpt-5.4/xhigh | Maximum quality and reasoning |
| `balanced` | gpt-5.3-codex/high | gpt-5.1-codex/medium | gpt-5.1-codex/medium | Strong main agent, cheaper reviewer |
| `codex-xhigh` | gpt-5.3-codex/xhigh | gpt-5.3-codex/xhigh | gpt-5.3-codex/xhigh | Pure codex with max reasoning |
| `cheap` | gpt-5.1-codex-mini/medium | gpt-5-codex-mini/low | gpt-5-codex-mini/low | Cost-optimized for long runs |
| `max` | gpt-5.1-codex-max/xhigh | gpt-5.3-codex/high | gpt-5.3-codex/high | Most expensive, long-horizon |

**Inherit Codex Default:** During setup, selecting option `0` (inherit codex default) leaves model fields as `null` in the configuration, causing daemon-launched runs to use whatever models are configured in `~/.codex/config.toml`.

**Sources:**[codex_autoloop/model_catalog.py42-123](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L42-L123)

### Reasoning Effort Levels

Each model can be configured with a reasoning effort level that controls the depth of analysis:

| Level | Token Cost | Quality | Typical Use |
| --- | --- | --- | --- |
| `low` | Lowest | Basic | Quick iterations, cheap reviewer |
| `medium` | Moderate | Good | Balanced quality/cost, recommended for 24/7 daemon |
| `high` | High | Very Good | Default for quality presets |
| `xhigh` | Highest | Maximum | Complex tasks requiring deep reasoning |

**Sources:**[codex_autoloop/setup_wizard.py801-808](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L801-L808)[codex_autoloop/codex_runner.py278-279](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L278-L279)

### Model Preset Resolution Flow

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py775-798](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L775-L798)[codex_autoloop/model_catalog.py156-161](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L156-L161)[codex_autoloop/codex_runner.py271-298](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L271-L298)

---

## Planner Modes

Planner modes control whether and how the planner agent operates after a run completes. The planner maintains strategic overview documents (`plan_report.md`, `plan_todo.md`) and can propose follow-up objectives.

### Mode Comparison

| Mode | Planner Runs? | Records Plan? | Proposes Follow-up? | Auto-executes? |
| --- | --- | --- | --- | --- |
| `off` | No | No | No | No |
| `record` | Yes | Yes | No | No |
| `auto` | Yes | Yes | Yes | Yes (after delay) |

### Detailed Mode Behavior

**`off` mode:**

- Planner agent is completely disabled
- No `plan_report.md` or `plan_todo.md` files are created
- Daemon returns to idle state immediately after run completion
- Suitable for simple, isolated tasks where strategic planning is not needed

**`record` mode:**

- Planner agent runs background sweeps during execution
- Strategic overview documents are maintained
- After run completion, the final plan is appended to `plan-records.md`
- No follow-up proposals are generated
- Daemon returns to idle state
- Suitable when you want planning context but manual control over execution

**`auto` mode (default):**

- Planner agent runs background sweeps during execution
- Strategic overview documents are maintained
- After successful run completion, planner proposes next objective
- Proposal is sent to control channel (Telegram/Feishu) with approval buttons
- After `follow_up_auto_execute_seconds` delay (default: 600s / 10 minutes), the follow-up executes automatically
- User can approve immediately, reject, or modify the objective before execution
- If workspace is dirty before auto-execution, daemon creates a git checkpoint commit
- Suitable for autonomous, multi-session projects

**Sources:**[codex_autoloop/planner_modes.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/planner_modes.py)[codex_autoloop/setup_wizard.py836-847](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L836-L847)[README.md168-172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L168-L172)

### Planner Mode State Machine

[State Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py) (main daemon loop handling planner follow-up)

---

## Copilot Proxy Configuration

The Copilot proxy integration allows ArgusBot to route Codex CLI requests through GitHub Copilot quota instead of direct OpenAI API billing.

### Proxy Detection and Installation

ArgusBot auto-detects proxy checkouts in the following locations:

- `~/copilot-proxy`
- `~/copilot-codex-proxy`
- `~/.argusbot/tools/copilot-proxy`

If no proxy is detected and the `copilot` preset is selected, the setup wizard offers to install it automatically into `~/.argusbot/tools/copilot-proxy`.

### Proxy Configuration Fields

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `run_copilot_proxy` | boolean | false | Enable/disable proxy routing |
| `run_copilot_proxy_dir` | string | null | Path to proxy checkout (auto-detected if null) |
| `run_copilot_proxy_port` | integer | 18080 | Local port for proxy server |

**Important:** When proxy is enabled, ArgusBot automatically starts `proxy.mjs` if not already running and injects provider overrides at runtime. You do not need to modify your global `~/.codex/config.toml`.

**Sources:**[codex_autoloop/copilot_proxy.py16-24](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/copilot_proxy.py#L16-L24)[codex_autoloop/setup_wizard.py389-432](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L389-L432)

### Proxy Integration Flow

[Flowchart Diagram]

**Sources:**[codex_autoloop/copilot_proxy.py69-154](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/copilot_proxy.py#L69-L154)[codex_autoloop/codex_runner.py51-62](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L51-L62)[codex_autoloop/codex_runner.py72-74](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L72-L74)

---

## Default Run Settings

These settings control the default behavior of daemon-launched runs:

| Setting | Config Field | Default | Description |
| --- | --- | --- | --- |
| Working Directory | `run_cd` | `.` (current dir) | Directory where runs execute |
| Check Command | `run_check` | null | Acceptance test command run after each round |
| Max Rounds | `run_max_rounds` | 100 | Maximum loop iterations before forced stop |
| YOLO Mode | `run_yolo` | true | Bypass approvals and sandbox (daemon default) |
| Full Auto | `run_full_auto` | false | Full automation without any prompts |
| Skip Git Check | `run_skip_git_repo_check` | false | Allow runs outside git repositories |
| Resume Session | `run_resume_last_session` | true | Resume last session when daemon is idle |

**Security Warning:** Daemon-launched runs use `--yolo` by default, which grants high local execution power. Only run ArgusBot in trusted repositories.

**Sources:**[codex_autoloop/setup_wizard.py169-197](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L197)[README.md175-177](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L175-L177)[README.md477-482](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L477-L482)

---

## Viewing and Modifying Configuration

### Display Current Configuration

To view the active daemon configuration:

```
cat .argusbot/daemon_config.json | jq .
```

### Modify Configuration

To change configuration settings:

1. **Stop the daemon:**

```
argusbot daemon-stop
```
2. **Edit the configuration file:**

```
nano .argusbot/daemon_config.json
```
3. **Restart with new settings:**

```
argusbot init --restart-existing
```

Alternatively, run `argusbot init` without stopping first; the setup wizard includes `--restart-existing` by default, which stops any running daemon before starting the new one.

### Runtime Overrides

Some settings can be overridden per-run via control commands:

| Command | Override Capability |
| --- | --- |
| `/run` | Cannot override model/planner settings (uses daemon config) |
| `/mode <off\|auto\|record>` | Changes `planner_mode` for current and future runs |
| `/new` | Forces fresh session (overrides `run_resume_last_session`) |

**Note:** Model presets and Copilot proxy settings are fixed at daemon configuration time and cannot be changed via control commands. You must restart the daemon with new configuration to change these.

**Sources:**[codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py) (daemon command handlers), [codex_autoloop/setup_wizard.py610-646](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L610-L646)

---

## Configuration During Setup

The setup wizard prompts for configuration in this sequence:

1. **Control channel selection** (Telegram, Feishu, or both)
2. **Channel credentials** (bot tokens, chat IDs)
3. **Check command** (optional acceptance tests)
4. **Model preset or custom models**
5. **Copilot proxy** (auto-detect, install, or skip)
6. **Planner mode** (off, record, or auto)
7. **Follow-up auto-execute delay** (when planner mode is auto)

The wizard validates credentials by:

- Checking Codex CLI availability and authentication
- Acquiring a token lock (for Telegram) to ensure no conflicts
- Resolving chat IDs via `getUpdates` API (for Telegram)
- Testing Copilot proxy startup if enabled

All settings are persisted to `daemon_config.json` with restricted permissions before the daemon launches.

**Sources:**[codex_autoloop/setup_wizard.py45-340](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L45-L340)