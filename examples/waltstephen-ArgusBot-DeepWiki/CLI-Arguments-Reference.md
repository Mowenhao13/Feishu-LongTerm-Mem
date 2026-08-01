# Configuration Reference
Relevant source files
- [codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py)
- [codex_autoloop/codexloop.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py)
- [codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py)
- [tests/test_codexloop.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_codexloop.py)

## Purpose and Scope

This page provides a comprehensive reference for all configuration options, command-line arguments, and environment variables used throughout ArgusBot. It covers three primary configuration surfaces:

1. **CLI arguments** for single-run execution (`argusbot-run`)
2. **Setup wizard arguments** for daemon initialization (`argusbot-setup`, `argusbot init`)
3. **Daemon configuration file** structure (`daemon_config.json`)

For information about specific commands like `/run`, `/inject`, `/status`, see [Command Reference](/waltstephen/ArgusBot/8.1-command-reference). For details on file structure and artifact locations, see [File Structure Reference](/waltstephen/ArgusBot/8.4-file-structure-reference).

---

## Configuration Architecture Overview

The following diagram illustrates how configuration flows through ArgusBot's different operational modes:

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py45-340](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L45-L340)[codex_autoloop/cli.py32-70](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L32-L70)

---

## CLI Arguments Reference (`argusbot-run`)

These arguments control single-run execution via `argusbot-run`. All arguments are optional except `objective`.

### Core Execution Parameters

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `objective` | positional (required) | - | Task objective passed to the primary agent. Can be multiple words. |
| `--codex-bin` | string | `codex` | Path to Codex CLI binary. |
| `--session-id` | string | `None` | Resume an existing Codex exec session ID. |
| `--max-rounds` | integer | `500` | Maximum primary-agent rounds before forced stop. |
| `--max-no-progress-rounds` | integer | `3` | Stop if repeated rounds produce identical main summary. |
| `--check` | string (repeatable) | `None` | Acceptance shell command. All checks must pass before completion. Can be specified multiple times. |
| `--check-timeout-seconds` | integer | `1200` | Timeout per acceptance check command (20 minutes). |

**Sources:**[codex_autoloop/cli.py81-118](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L81-L118)[README.md18-22](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L18-L22)

### Model Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--main-model` | string | `None` | Primary agent model override (e.g., `gpt-5.4`, `claude-sonnet-4.6`). |
| `--reviewer-model` | string | `None` | Reviewer sub-agent model override. |
| `--plan-model` / `--planner-model` | string | `None` | Plan agent model override. Defaults to reviewer settings when omitted. |
| `--main-reasoning-effort` | choice | `None` | Primary agent reasoning effort: `low`, `medium`, `high`, `xhigh`. |
| `--reviewer-reasoning-effort` | choice | `None` | Reviewer sub-agent reasoning effort: `low`, `medium`, `high`, `xhigh`. |
| `--plan-reasoning-effort` / `--planner-reasoning-effort` | choice | `None` | Plan agent reasoning effort: `low`, `medium`, `high`, `xhigh`. |
| `--main-extra-arg` | string (repeatable) | `None` | Extra argument passed to main `codex exec` command. |
| `--reviewer-extra-arg` | string (repeatable) | `None` | Extra argument passed to reviewer `codex exec` command. |
| `--plan-extra-arg` / `--planner-extra-arg` | string (repeatable) | `None` | Extra argument passed to planner `codex exec` command. |

**Sources:**[codex_autoloop/cli.py119-158](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L119-L158)

### Copilot Proxy Integration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--copilot-proxy` / `--no-copilot-proxy` | boolean | `False` | Route Codex CLI requests through local copilot-proxy instance. |
| `--copilot-proxy-dir` | string | `None` | Path to local copilot-proxy checkout. Auto-detects `~/copilot-proxy`, `~/copilot-codex-proxy`, `~/.argusbot/tools/copilot-proxy`. |
| `--copilot-proxy-port` | integer | `18080` | Local copilot-proxy port. |

**Sources:**[codex_autoloop/cli.py84-99](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L84-L99)[README.md98-128](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L98-L128)

### Planner Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--plan-mode` / `--planner-mode` | choice | `auto` | Planner mode: `off`, `auto`, `record`. |
| `--planner` / `--no-planner` | boolean | `True` | Enable/disable planner sub-agent. Disabled maps to `--plan-mode off`. |
| `--plan-update-interval-seconds` | integer | `1800` | Reserved compatibility flag for daemon-launched runs (30 minutes). |

**Sources:**[codex_autoloop/cli.py159-178](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L159-L178)[README.md167-172](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L167-L172)

### Codex CLI Pass-through Flags

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--skip-git-repo-check` | boolean | `False` | Pass `--skip-git-repo-check` to Codex CLI. |
| `--full-auto` | boolean | `False` | Pass `--full-auto` to Codex CLI. |
| `--yolo` | boolean | `False` | Pass `--dangerously-bypass-approvals-and-sandbox` to Codex CLI. **Security risk: grants high local execution power.** |

**Sources:**[codex_autoloop/cli.py179-185](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L179-L185)[README.md24-29](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L24-L29)

### State Persistence

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--state-file` | string | `None` | Write state JSON after each loop round. If set, auto-resolves related files. |
| `--operator-messages-file` | string | auto-resolved | Markdown document path for operator message history used by reviewer. |
| `--plan-overview-file` / `--plan-report-file` | string | auto-resolved | Markdown document path for plan agent overall summary. |
| `--plan-todo-file` | string | `None` | Optional planner TODO markdown path. Current plan markdown mirrored here. |
| `--review-summaries-dir` | string | auto-resolved | Directory for per-round reviewer summary markdown files. |
| `--main-prompt-file` | string | auto-resolved | Markdown file path for latest main prompt sent to Codex. |
| `--control-file` | string | `None` | Local JSONL control file for terminal commands (inject/stop/status). |
| `--control-poll-interval-seconds` | integer | `1` | Polling interval for local control file. |

**Sources:**[codex_autoloop/cli.py186-224](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L186-L224)[codex_autoloop/cli.py435-456](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L435-L456)

### Stall Detection

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--stall-soft-idle-seconds` | integer | `3600` | Soft idle threshold (1 hour). Stall sub-agent inspects and decides whether to restart. |
| `--stall-hard-idle-seconds` | integer | `10800` | Hard idle threshold (3 hours). Force restart as hard safety valve. |

**Validation:**`stall-hard-idle-seconds` must be ≥ `stall-soft-idle-seconds`.

**Sources:**[codex_autoloop/cli.py226-242](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L226-L242)[README.md400-403](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L400-L403)

### Dashboard

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--dashboard` / `--no-dashboard` | boolean | `False` | Enable/disable local live dashboard while running. |
| `--dashboard-host` | string | `127.0.0.1` | Dashboard host bind address. Use `0.0.0.0` for LAN access. |
| `--dashboard-port` | integer | `8787` | Dashboard TCP port. |

**Sources:**[codex_autoloop/cli.py244-250](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L244-L250)[README.md351-362](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L351-L362)

### Telegram Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--telegram-bot-token` | string | `None` | Telegram bot token for progress messages. Format: `<digits>:<secret>`. |
| `--telegram-chat-id` | string | `auto` | Telegram chat ID to receive messages. Use `auto` to resolve from updates. |
| `--telegram-events` | string | (see below) | Comma-separated event names to send to Telegram. |
| `--telegram-timeout-seconds` | integer | `10` | HTTP timeout for Telegram API calls. |
| `--telegram-chat-id-resolve-timeout-seconds` | integer | `90` | Seconds to poll getUpdates when resolving `chat_id=auto`. |
| `--telegram-no-typing` | boolean | `False` | Disable Telegram typing heartbeats during loop execution. |
| `--telegram-typing-interval-seconds` | integer | `4` | Seconds between Telegram typing heartbeats. |
| `--telegram-live-updates` / `--no-telegram-live-updates` | boolean | `True` | Enable/disable batched live agent message push to Telegram. |
| `--telegram-live-interval-seconds` | integer | `30` | Push interval for Telegram live updates; sends only when changed. |
| `--telegram-control` / `--no-telegram-control` | boolean | `True` | Enable/disable Telegram inbound control commands. |
| `--telegram-control-poll-interval-seconds` | integer | `2` | Polling interval for Telegram control command loop. |
| `--telegram-control-long-poll-timeout-seconds` | integer | `20` | Long-poll timeout for Telegram getUpdates control loop. |
| `--telegram-control-plain-text-inject` / `--no-telegram-control-plain-text-inject` | boolean | `True` | Treat plain text Telegram messages as injected instruction updates. |

**Default Telegram events:**`loop.started,round.review.completed,loop.completed`

**Sources:**[codex_autoloop/cli.py251-320](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L251-L320)[README.md363-422](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L363-L422)

### Telegram Whisper Transcription

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--telegram-control-whisper` / `--no-telegram-control-whisper` | boolean | `True` | Enable/disable Whisper transcription for voice/audio control messages. |
| `--telegram-control-whisper-api-key` | string | `$OPENAI_API_KEY` | OpenAI API key for Whisper. Defaults to environment variable. |
| `--telegram-control-whisper-model` | string | `whisper-1` | OpenAI transcription model used for voice/audio messages. |
| `--telegram-control-whisper-base-url` | string | `https://api.openai.com/v1` | OpenAI-compatible API base URL for Whisper transcription. |
| `--telegram-control-whisper-timeout-seconds` | integer | `90` | Timeout in seconds for Whisper transcription requests. |

**Sources:**[codex_autoloop/cli.py323-347](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L323-L347)[README.md393-398](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L393-L398)

### Feishu Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--feishu-app-id` | string | `None` | Feishu app ID for control/notifications. |
| `--feishu-app-secret` | string | `None` | Feishu app secret for control/notifications. |
| `--feishu-chat-id` | string | `None` | Feishu chat ID for control/notifications (format: `oc_xxx` for `chat_id` type). |
| `--feishu-receive-id-type` | string | `chat_id` | Feishu receive_id_type used for outgoing messages. |
| `--feishu-events` | string | (see below) | Comma-separated event names to send to Feishu. |
| `--feishu-timeout-seconds` | integer | `10` | HTTP timeout for Feishu API calls. |
| `--feishu-live-updates` / `--no-feishu-live-updates` | boolean | `True` | Enable/disable batched live agent message push to Feishu. |
| `--feishu-live-interval-seconds` | integer | `30` | Push interval for Feishu live updates; sends only when changed. |
| `--feishu-control` / `--no-feishu-control` | boolean | `True` | Enable/disable Feishu inbound control commands. |
| `--feishu-control-poll-interval-seconds` | integer | `2` | Polling interval for Feishu control command loop. |
| `--feishu-control-plain-text-inject` / `--no-feishu-control-plain-text-inject` | boolean | `True` | Treat plain text Feishu messages as injected instruction updates. |

**Default Feishu events:**`loop.started,round.review.completed,loop.completed`

**Sources:**[codex_autoloop/cli.py348-396](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L348-L396)[README.md230-276](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L230-L276)

### Terminal Output

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--live-terminal` / `--no-live-terminal` | boolean | `True` | Enable/disable realtime terminal printing of agent messages. |
| `--verbose-events` | boolean | `False` | Print raw Codex JSONL and stderr lines while running. |

**Sources:**[codex_autoloop/cli.py398-407](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L398-L407)

---

## Setup Wizard Arguments (`argusbot-setup`, `argusbot init`)

The setup wizard (`argusbot-setup` / `argusbot init`) creates `daemon_config.json` and launches the background daemon. Most arguments have interactive prompts if omitted.

### Directory Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--home-dir` | string | `.argusbot` | Directory to store daemon config/log/pid/bus files. |
| `--run-cd` | string | `.` | Working directory for launched ArgusBot runs. |

**Sources:**[codex_autoloop/setup_wizard.py922-929](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L922-L929)

### Daemon Run Defaults

These arguments configure default behavior for daemon-launched runs:

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--run-max-rounds` | integer | `100` | Default max rounds for daemon-launched runs. |
| `--run-skip-git-repo-check` | boolean | `False` | Pass `--skip-git-repo-check` for daemon-launched runs. |
| `--run-full-auto` | boolean | `False` | Pass `--full-auto` for daemon-launched runs. |
| `--run-yolo` / `--no-run-yolo` | boolean | `True` | Enable/disable `--yolo` for daemon-launched runs. **Default enabled.** |
| `--run-resume-last-session` / `--no-run-resume-last-session` | boolean | `True` | Resume from last saved session_id when daemon receives new run while idle. |

**Sources:**[codex_autoloop/setup_wizard.py931-949](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L931-L949)

### Daemon Model Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--run-model-preset` | string | `None` | Optional preset name for daemon-launched models. Interactive setup prompts. |
| `--run-main-model` | string | `None` | Override main agent model for daemon-launched runs. |
| `--run-main-reasoning-effort` | choice | `None` | Override main agent reasoning effort: `low`, `medium`, `high`, `xhigh`. |
| `--run-reviewer-model` | string | `None` | Override reviewer agent model for daemon-launched runs. |
| `--run-reviewer-reasoning-effort` | choice | `None` | Override reviewer agent reasoning effort: `low`, `medium`, `high`, `xhigh`. |

**Sources:**[codex_autoloop/setup_wizard.py950-999](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L950-L999)

### Daemon Copilot Proxy

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--run-copilot-proxy` / `--no-run-copilot-proxy` | boolean | `None` | Use local copilot-proxy for daemon-launched Codex runs. |
| `--run-copilot-proxy-dir` | string | `None` | Path to local copilot-proxy checkout. Auto-detects standard locations. |
| `--run-copilot-proxy-port` | integer | `18080` | Local copilot-proxy port. |

**Sources:**[codex_autoloop/setup_wizard.py956-971](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L956-L971)

### Daemon Planner Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--run-planner-mode` | choice | `None` | Planner mode for daemon-launched runs: `off`, `auto`, `record`. Interactive setup prompts when omitted. |
| `--follow-up-auto-execute-seconds` | integer | `600` | Auto execute planner follow-up after this many seconds in auto mode (10 minutes). |

**Validation:**`follow-up-auto-execute-seconds` must be ≥ 0.

**Sources:**[codex_autoloop/setup_wizard.py972-1032](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L972-L1032)

### Control Channel Configuration

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--channel` | choice | `None` | Control channel to enable: `telegram`, `feishu`, `both`. Interactive setup prompts. |
| `--telegram-bot-token` | string | `None` | Optional Telegram bot token. Prompted if channel requires it. |
| `--telegram-chat-id` | string | `None` | Optional Telegram chat ID or `auto`. Prompted if channel requires it. |
| `--feishu-app-id` | string | `None` | Optional Feishu app ID. Prompted if channel requires it. |
| `--feishu-app-secret` | string | `None` | Optional Feishu app secret. Prompted if channel requires it. |
| `--feishu-chat-id` | string | `None` | Optional Feishu chat ID. Prompted if channel requires it. |
| `--feishu-receive-id-type` | string | `chat_id` | Feishu receive_id_type used for outgoing messages. |

**Sources:**[codex_autoloop/setup_wizard.py1005-1020](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L1005-L1020)

### Daemon Lifecycle

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `--restart-existing` / `--no-restart-existing` | boolean | `True` | Stop existing daemon under same home-dir before starting new one. |
| `--token-lock-dir` | string | `/tmp/argusbot-token-locks` | Global lock directory to enforce one daemon per Telegram token. |

**Sources:**[codex_autoloop/setup_wizard.py1021-1032](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L1021-L1032)[codex_autoloop/setup_wizard.py610-646](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L610-L646)

---

## Daemon Configuration File Structure

The daemon configuration file is persisted at `.argusbot/daemon_config.json` (or `{home_dir}/daemon_config.json`). It is created by the setup wizard and consumed by the daemon process.

### Configuration File Mapping

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py169-197](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L197)[codex_autoloop/setup_wizard.py204-277](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L204-L277)

### JSON Schema

The `daemon_config.json` file contains the following fields:

| Field | Type | Description |
| --- | --- | --- |
| `control_channel` | string | Control channel: `telegram`, `feishu`, or `both`. |
| `telegram_bot_token` | string \| null | Telegram bot token (format: `<digits>:<secret>`). |
| `telegram_chat_id` | string \| null | Telegram chat ID (numeric or `auto`). |
| `feishu_app_id` | string \| null | Feishu app ID. |
| `feishu_app_secret` | string \| null | Feishu app secret. |
| `feishu_chat_id` | string \| null | Feishu chat ID (format: `oc_xxx` for `chat_id` type). |
| `feishu_receive_id_type` | string | Feishu receive_id_type (default: `chat_id`). |
| `run_cd` | string | Working directory for launched ArgusBot runs. |
| `run_check` | string \| null | Default check command for daemon-launched runs. |
| `run_max_rounds` | integer | Default max rounds for daemon-launched runs. |
| `run_skip_git_repo_check` | boolean | Pass `--skip-git-repo-check` for daemon-launched runs. |
| `run_full_auto` | boolean | Pass `--full-auto` for daemon-launched runs. |
| `run_yolo` | boolean | Enable `--yolo` for daemon-launched runs. |
| `run_resume_last_session` | boolean | Resume from last saved session_id when idle. |
| `run_main_reasoning_effort` | string \| null | Main agent reasoning effort: `low`, `medium`, `high`, `xhigh`. |
| `run_reviewer_reasoning_effort` | string \| null | Reviewer agent reasoning effort: `low`, `medium`, `high`, `xhigh`. |
| `run_main_model` | string \| null | Main agent model override. |
| `run_reviewer_model` | string \| null | Reviewer agent model override. |
| `run_model_preset` | string \| null | Model preset name (e.g., `quality`, `balanced`, `copilot`). |
| `run_copilot_proxy` | boolean | Enable copilot-proxy for daemon-launched runs. |
| `run_copilot_proxy_dir` | string \| null | Path to copilot-proxy checkout directory. |
| `run_copilot_proxy_port` | integer | Copilot-proxy port (default: 18080). |
| `run_planner_mode` | string | Planner mode: `off`, `auto`, `record`. |
| `follow_up_auto_execute_seconds` | integer | Auto execute planner follow-up after this many seconds in auto mode. |
| `codex_autoloop_bin` | string | Command to execute argusbot-run (typically Python module invocation). |
| `bus_dir` | string | Path to daemon bus directory for JSONL command files. |
| `logs_dir` | string | Path to daemon logs directory. |

**File permissions:** The configuration file is created with mode `0o600` (owner read/write only) to protect credentials.

**Sources:**[codex_autoloop/setup_wizard.py169-200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L200)

---

## Environment Variables

ArgusBot respects the following environment variables:

| Variable | Purpose | Used By |
| --- | --- | --- |
| `OPENAI_API_KEY` | Default API key for Whisper transcription and fallback model authentication | Telegram Whisper transcription, Codex CLI |
| `TELEGRAM_BOT_TOKEN` | Convenience variable for Telegram bot token (can override via `--telegram-bot-token`) | Setup wizard, daemon scripts |
| `TELEGRAM_CHAT_ID` | Convenience variable for Telegram chat ID (can override via `--telegram-chat-id`) | Setup wizard, daemon scripts |
| `FEISHU_APP_ID` | Convenience variable for Feishu app ID | Setup wizard, daemon scripts |
| `FEISHU_APP_SECRET` | Convenience variable for Feishu app secret | Setup wizard, daemon scripts |
| `FEISHU_CHAT_ID` | Convenience variable for Feishu chat ID | Setup wizard, daemon scripts |
| `CODEX_AUTOLOOP_DAEMON_BIN` | Override command prefix for launching daemon (for development/testing) | Setup wizard |

**Sources:**[codex_autoloop/cli.py329](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L329-L329)[codex_autoloop/setup_wizard.py454-463](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L454-L463)[README.md449](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L449-L449)

---

## Configuration Precedence and Resolution

ArgusBot follows a hierarchical configuration precedence model:

[Flowchart Diagram]

### Resolution Examples

**Model configuration:**

1. If `--main-model gpt-5.4` passed to `argusbot-run` → use `gpt-5.4`
2. Else if `daemon_config.json` contains `"run_main_model": "gpt-5.3-codex"` → use `gpt-5.3-codex`
3. Else if Codex global config specifies model → use Codex default
4. Else → use Codex CLI's built-in default

**Telegram chat ID:**

1. If `--telegram-chat-id 123456` passed → use `123456`
2. Else if `daemon_config.json` contains `"telegram_chat_id": "654321"` → use `654321`
3. Else if `$TELEGRAM_CHAT_ID` environment variable set → use that value
4. Else if `auto` → attempt resolution via `getUpdates` API

**Copilot proxy:**

1. If `--copilot-proxy` / `--no-copilot-proxy` explicitly passed → use that
2. Else if `daemon_config.json` contains `"run_copilot_proxy": true` → enable proxy
3. Else if proxy checkout auto-detected AND preset is `copilot` → prompt user during setup
4. Else → disabled

**Sources:**[codex_autoloop/setup_wizard.py79-138](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L79-L138)[codex_autoloop/cli.py32-70](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L32-L70)

---

## Configuration File Locations

### Standard Paths

| File | Default Location | Configured By |
| --- | --- | --- |
| `daemon_config.json` | `.argusbot/daemon_config.json` | `--home-dir` in setup wizard |
| `daemon.pid` | `.argusbot/daemon.pid` | `--home-dir` in setup wizard |
| `daemon.out` | `.argusbot/daemon.out` | `--home-dir` in setup wizard |
| `daemon_status.json` | `.argusbot/daemon_status.json` | Daemon process (runtime) |
| `last_state.json` | `.argusbot/logs/last_state.json` | `--state-file` in run |
| `operator_messages.md` | `.argusbot/logs/operator_messages.md` | Auto-resolved from state file |
| `plan_report.md` | `.argusbot/logs/plan_report.md` | `--plan-overview-file` in run |
| `plan_todo.md` | `.argusbot/logs/plan_todo.md` | `--plan-todo-file` in run |
| `review_summaries/` | `.argusbot/logs/review_summaries/` | `--review-summaries-dir` in run |
| `daemon-events.jsonl` | `.argusbot/logs/daemon-events.jsonl` | Daemon process (runtime) |
| `argusbot-run-archive.jsonl` | `.argusbot/logs/argusbot-run-archive.jsonl` | Loop engine (runtime) |
| `daemon_commands.jsonl` | `.argusbot/bus/daemon_commands.jsonl` | Daemon command bus |
| `child_control.jsonl` | `.argusbot/bus/child_control.jsonl` | Child process control bus |

**Sources:**[codex_autoloop/setup_wizard.py61-66](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L61-L66)[codex_autoloop/apps/shell_utils.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/shell_utils.py)

---

## Special Configuration Behaviors

### Session ID Resolution

When `--session-id` is not provided and `run_resume_last_session` is enabled (daemon default), the system resolves the session ID via:

1. Check `last_state.json` for `session_id` field
2. Fallback to last `run.finished` event in `argusbot-run-archive.jsonl`
3. If neither found, start fresh session

**Sources:**[README.md22-23](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L22-L23)[README.md438-439](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L438-L439)

### Force Fresh Session

If the system detects `invalid_encrypted_content` errors during a resumed run, it automatically sets an internal `force_fresh_session` flag for the next run, preventing infinite resume loops.

**Sources:**[README.md485-486](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L485-L486)

### Copilot Proxy Auto-Detection

When `--copilot-proxy` is enabled without `--copilot-proxy-dir`, the system searches:

1. `~/copilot-proxy`
2. `~/copilot-codex-proxy`
3. `~/.argusbot/tools/copilot-proxy`

If not found and `copilot` preset is selected, the setup wizard offers to bootstrap installation to `~/.argusbot/tools/copilot-proxy`.

**Sources:**[codex_autoloop/copilot_proxy.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/copilot_proxy.py)[codex_autoloop/setup_wizard.py389-432](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L389-L432)

### Model Preset Expansion

When a preset name like `quality` or `balanced` is used, it expands to specific model + reasoning effort combinations:

```
# Example: "quality" preset expands to:
# main_model="gpt-5.4", main_reasoning_effort="high"
# reviewer_model="gpt-5.4", reviewer_reasoning_effort="high"
```

**Sources:**[codex_autoloop/model_catalog.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py)[README.md524-547](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L524-L547)

---

## Validation Rules

The system enforces the following validation constraints:

| Rule | Error Message |
| --- | --- |
| `objective` must be non-empty | `"objective cannot be empty"` |
| `stall_soft_idle_seconds` ≥ 0 | `"--stall-soft-idle-seconds must be >= 0"` |
| `stall_hard_idle_seconds` ≥ 0 | `"--stall-hard-idle-seconds must be >= 0"` |
| `stall_hard_idle_seconds` ≥ `stall_soft_idle_seconds` | `"--stall-hard-idle-seconds must be >= --stall-soft-idle-seconds"` |
| `plan_update_interval_seconds` ≥ 0 | `"--plan-update-interval-seconds must be >= 0"` |
| `follow_up_auto_execute_seconds` ≥ 0 | `"--follow-up-auto-execute-seconds must be >= 0"` |
| Telegram token format: `<digits>:<secret>` | `"Invalid token format. Expected <digits>:<secret>."` |
| Telegram chat ID: numeric or `-` prefix | `"Invalid chat id. Use 'auto' or a numeric chat id like 123456 or -100123456."` |
| Feishu chat ID (chat_id type): starts with `oc_` | `"Invalid Feishu chat id. For receive_id_type=chat_id, expected a value like oc_xxx."` |
| Reasoning effort: must be `low`, `medium`, `high`, or `xhigh` | `"Invalid reasoning effort. Choose low, medium, high, xhigh, or leave blank."` |

**Sources:**[codex_autoloop/cli.py36-49](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L36-L49)[codex_autoloop/setup_wizard.py48-49](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L48-L49)[codex_autoloop/setup_wizard.py745-824](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L745-L824)