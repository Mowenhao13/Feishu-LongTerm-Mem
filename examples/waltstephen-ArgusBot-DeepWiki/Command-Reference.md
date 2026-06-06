# Command Reference
Relevant source files
- [QUICKSTART.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1)
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/daemon_ctl.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py)
- [codex_autoloop/telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py)
- [tests/test_telegram_control.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py)

This page provides a comprehensive reference for all commands available in ArgusBot. Commands can be sent through multiple control channels: Telegram bot messages, Feishu messages, local terminal (`argusbot-daemon-ctl`), and the monitor console (`argusbot` attach mode).

For information about configuring control channels, see [Configuration Overview](/waltstephen/ArgusBot/2.3-configuration-overview). For details on how commands are routed and processed internally, see [Command System Overview](/waltstephen/ArgusBot/5.1-command-system-overview).

---

## Command Channels and Routing

ArgusBot accepts commands through four distinct control channels, all converging on unified command handling logic:

**Command Routing Architecture**

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_control.py165-330](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L165-L330)[codex_autoloop/daemon_ctl.py18-163](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L18-L163)[codex_autoloop/apps/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py)

---

## Command Categories

Commands are organized into functional categories based on their purpose:

| Category | Commands | Primary Use |
| --- | --- | --- |
| **Run Control** | `/run`, `/new`, `/stop` | Start, configure, and stop execution runs |
| **Execution Interrupts** | `/inject`, `/mode` | Modify behavior of active runs |
| **Planning** | `/plan`, `/mode`, plan callbacks | Control planner sub-agent behavior |
| **Review** | `/review`, `/show-review`, `/show-review-context` | Control reviewer sub-agent and view decisions |
| **Queries** | `/btw`, `/status`, `/show-*` | Read-only information retrieval |
| **Daemon Control** | `/daemon-stop`, `/help` | Daemon lifecycle management |
| **Special** | Voice messages, plain text, callbacks | Alternative input methods |

---

## Run Control Commands

### `/run <objective>`

**Syntax:**

```
/run <objective text>

```

**Description:**
Starts a new ArgusBot execution run with the specified objective. Behavior depends on daemon state:

- **Daemon idle:** Spawns a new child process running `argusbot-run` with the objective
- **Daemon running:** Returns error message indicating a run is already active
- **Session resumption:** If `session_id` is available in state, attempts to resume previous session; otherwise starts fresh

**Examples:**

```
/run Implement feature X and keep iterating until tests pass
/run 帮我在这个文件夹写一下pipeline
/run Reproduce the paper's core result and generate a report

```

**Aliases:** None

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Related Configuration:**

- `--yolo` flag automatically applied for daemon-launched runs
- Default check command from `daemon_config.json` applied if configured
- Model preset from daemon configuration used unless overridden

**Sources:**[README.md436-442](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L436-L442)[codex_autoloop/apps/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py)[codex_autoloop/telegram_control.py471-474](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L471-L474)

---

### `/new`

**Syntax:**

```
/new

```

**Description:**
Forces the next `/run` command to start with a fresh Codex session, ignoring any saved `session_id`. The fresh session marker is persisted across daemon restarts until consumed by the next run.

**Behavior:**

- Sets `force_fresh_session` flag in daemon state
- Does not affect currently running child process
- Next run will not attempt session resumption
- Marker is cleared after being consumed

**Examples:**

```
/new
/run Start a clean implementation of the parser

```

**Aliases:**`/fresh`, `/fresh-session`, `/new-session`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md149-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L149-L166)[codex_autoloop/telegram_control.py439-442](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L439-L442)[codex_autoloop/daemon_ctl.py94-97](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L94-L97)

---

### `/stop`

**Syntax:**

```
/stop

```

**Description:**
Stops the currently active ArgusBot run. Sends termination signal to child process and updates daemon state to idle.

**Behavior:**

- If run is active: Sends `SIGTERM` to child process, updates status
- If daemon is idle: Returns message indicating no active run
- Does not stop the daemon process itself (use `/daemon-stop` for that)
- Child process may complete current round before terminating

**Examples:**

```
/stop

```

**Aliases:**`/halt`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md389-391](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L389-L391)[codex_autoloop/telegram_control.py475-476](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L475-L476)[codex_autoloop/daemon_ctl.py153-156](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L153-L156)

---

## Execution Interrupt Commands

### `/inject <instruction>`

**Syntax:**

```
/inject <instruction text>

```

**Description:**
Injects additional instruction into the currently running main agent. The instruction is:

1. Appended to `operator_messages.md` for cross-run persistence
2. Forwarded to child process via control bus
3. Applied in the next orchestrator round as prompt override
4. Included in reviewer context for decision-making

**Behavior:**

- **During active run:** Instruction queued for next round
- **Daemon idle:** Treated as equivalent to `/run` command (auto-routing)
- **Plain text routing:** When enabled, plain text messages automatically become `/inject` during active runs

**Examples:**

```
/inject 先修测试再继续
/inject Switch to a more conservative approach and run tests first
/inject Stop current experiment, run only 100 steps and save checkpoint

```

**Aliases:**`/interrupt` (deprecated)

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Plain Text Auto-routing:** When `plain_text_as_inject=True`, any non-command text during an active run is automatically treated as `/inject`

**Sources:**[README.md387-388](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L387-L388)[codex_autoloop/telegram_control.py465-470](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L465-L470)[codex_autoloop/daemon_ctl.py127-130](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L127-L130)

---

### `/mode <off|auto|record>`

**Syntax:**

```
/mode <mode_value>

```

**Description:**
Hot-switches the planner mode for both daemon default and active child process.

**Mode Values:**

| Mode | Behavior |
| --- | --- |
| `off` | Disables planner sub-agent; no planning sweeps or follow-up proposals |
| `auto` | Enables planner with automated follow-up execution after countdown |
| `record` | Enables planner recording only; no automatic follow-up execution |

**Behavior:**

- Updates daemon default `plan_mode` in configuration
- If child is running, forwards mode change via control bus
- Mode persists across daemon restarts
- Follow-up countdown defaults to 10 minutes in `auto` mode

**Examples:**

```
/mode off
/mode auto
/mode record

```

**Interactive Menu:**
Sending `/mode` without arguments in Telegram triggers an inline keyboard menu:

```
1️⃣ No Planner (off)
2️⃣ Auto Planner (auto) 
3️⃣ Record-Only Planner (record)

```

**Aliases:**`/plan-mode`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md168-173](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L168-L173)[codex_autoloop/telegram_control.py425-430](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L425-L430)[codex_autoloop/daemon_ctl.py132-135](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L132-L135)

---

## Planning Commands

### `/plan <direction>`

**Syntax:**

```
/plan <direction text>

```

**Description:**
Sends specific planning direction to the planner sub-agent without affecting the main execution loop. The direction is:

1. Written to `operator_messages.md`
2. Forwarded to active child via control bus
3. Applied in next planner background sweep

**Use Cases:**

- Request focus on specific workstreams: `/plan Focus on state persistence layer`
- Ask for clarification: `/plan Explain the dependency between modules X and Y`
- Update priorities: `/plan Deprioritize performance optimization, focus on correctness`

**Examples:**

```
/plan Focus on state persistence
/plan Explain the current architecture bottleneck
/plan Re-evaluate the testing strategy

```

**Behavior:**

- Only affects planner sub-agent, not main execution
- Planner incorporates direction in next 30-minute update cycle
- Results appear in `plan_report.md` and `plan_todo.md`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md158-159](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L158-L159)[codex_autoloop/telegram_control.py443-446](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L443-L446)[codex_autoloop/daemon_ctl.py137-140](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L137-L140)

---

### Plan Follow-up Callbacks

**Telegram Inline Keyboards:**

After a run completes in `auto` planner mode, Telegram receives an inline keyboard with three options:

[Flowchart Diagram]

**Callback Data Formats:**

- `plan_run:<plan-id>` — Execute proposed objective immediately
- `plan_modify:<plan-id>` — Expect modified text, then execute
- `plan_reject:<plan-id>` — Reject proposal, cancel countdown

**Git Checkpoint:**
Before executing follow-up, daemon creates checkpoint commit if workspace is dirty:

```
git add -A
git commit -m "argusbot checkpoint before follow-up: <objective-preview>"

```

**Sources:**[README.md441-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L441-L444)[codex_autoloop/telegram_control.py349-354](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L349-L354)[codex_autoloop/apps/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py)

---

## Review Commands

### `/review <criteria>`

**Syntax:**

```
/review <criteria text>

```

**Description:**
Sends additional review criteria to the reviewer sub-agent. The criteria:

1. Appended to `operator_messages.md`
2. Forwarded to active child via control bus
3. Included in reviewer prompt as acceptance conditions

**Use Cases:**

- Add completion criteria: `/review Must pass pytest -q before done`
- Clarify expectations: `/review Code must include docstrings and type hints`
- Set quality gates: `/review Performance must not regress by >10%`

**Examples:**

```
/review Must pass pytest -q
/review Code should be production-ready with error handling
/review All APIs must have integration tests

```

**Behavior:**

- Only affects reviewer sub-agent decisions
- Does not replace existing acceptance checks (specified with `--check`)
- Reviewer considers criteria alongside check results and objectives

**Aliases:**`/criteria`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md159](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L159-L159)[codex_autoloop/telegram_control.py447-452](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L447-L452)[codex_autoloop/daemon_ctl.py142-145](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L142-L145)

---

### `/show-review [round]`

**Syntax:**

```
/show-review [round_number]

```

**Description:**
Retrieves and displays reviewer decision summaries from the active run.

**Behavior:**

- **Without argument:** Returns the latest review summary (index.md)
- **With round number:** Returns specific round's review (e.g., `round-003.md`)
- Returns error if no active run or review summaries unavailable

**Examples:**

```
/show-review
/show-review 3
/show-review 12

```

**Review Summary Structure:**
Each review summary contains:

- Decision: `done`, `continue`, or `blocked`
- Reasoning: Explanation of the decision
- Progress assessment: What was accomplished in the round
- Next steps: What should happen next (if `continue`)

**Aliases:**`/review-md`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md163-164](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L163-L164)[codex_autoloop/telegram_control.py459-462](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L459-L462)[codex_autoloop/daemon_ctl.py54-70](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L54-L70)

---

### `/show-review-context`

**Syntax:**

```
/show-review-context

```

**Description:**
Displays the full context provided to the reviewer sub-agent, including:

- Operator messages (initial objective + all injections)
- Review summaries from previous rounds
- Configured acceptance checks (`--check` commands)
- Current state file information

**Use Cases:**

- Debugging unexpected reviewer decisions
- Understanding what information reviewer has access to
- Verifying that injected criteria are being considered

**Examples:**

```
/show-review-context

```

**Aliases:**`/review-context`, `/show-criteria`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md164](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L164-L164)[codex_autoloop/telegram_control.py463-464](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L463-L464)[codex_autoloop/daemon_ctl.py72-82](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L72-L82)

---

## Query Commands

### `/btw <question>`

**Syntax:**

```
/btw <question text>

```

**Description:**
Sends a read-only query to the BTW side-agent, which runs asynchronously without blocking the main execution loop. The agent:

- Has read-only access to the codebase
- Can perform searches and analysis
- May return file attachments (code snippets, images, etc.)
- Writes responses to `btw_messages.md`

**Attachment Handling:**

When BTW returns >5 attachments, confirmation is required:

| Command | Effect |
| --- | --- |
| `/confirm-send` | Upload all attachments to Telegram/Feishu |
| `/cancel-send` | Skip attachment upload |

**Aliases for confirmation:**

- `/confirm-send`, `/files-confirm`, `/confirm-files`
- `/cancel-send`, `/files-cancel`, `/cancel-files`

**Examples:**

```
/btw How is the planner integrated?
/btw 这个项目的 planner 怎么接的
/btw Explain the session resumption logic
/btw Show me the command parsing flow

```

**Response Format:**
BTW responses are appended to `btw_messages.md` with:

- Question text
- Answer text
- List of returned attachments (if any)

**Channels:** Telegram, Feishu, Terminal (with wait loop), Monitor Console

**Sources:**[README.md154-157](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L154-L157)[codex_autoloop/telegram_control.py431-438](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L431-L438)[codex_autoloop/daemon_ctl.py99-125](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L99-L125)

---

### `/status`

**Syntax:**

```
/status

```

**Description:**
Returns current daemon and child process status as JSON payload.

**Status Payload Fields:**

```
{
  "daemon_running": true,
  "daemon_status_live": true,
  "daemon_status_state": "live|stale|offline",
  "running": true,
  "child_pid": 12345,
  "child_start_time": 1234567890.0,
  "child_session_id": "abc123",
  "child_round": 3,
  "default_plan_mode": "auto",
  "run_check": ["pytest -q"],
  "child_main_prompt_path": ".argusbot/logs/main_prompt.md",
  "child_plan_report_path": ".argusbot/logs/plan_report.md",
  "child_review_summaries_dir": ".argusbot/logs/review_summaries"
}
```

**State Values:**

- `live` — Daemon heartbeat recent, actively running
- `stale` — Status file old, daemon may have crashed
- `offline` — Daemon explicitly stopped

**Examples:**

```
/status

```

**Aliases:**`/stat`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Terminal Exit Codes:**

- `0` — Status is live
- `1` — Status is stale or offline

**Sources:**[README.md389](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L389-L389)[codex_autoloop/telegram_control.py479-480](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L479-L480)[codex_autoloop/daemon_ctl.py26-29](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L26-L29)

---

### `/show-main-prompt`

**Syntax:**

```
/show-main-prompt

```

**Description:**
Returns the latest main agent prompt text from `main_prompt.md`. This is the exact prompt sent to the main agent in the most recent round.

**Contents:**

- Initial objective or continue prompt
- Applied injections and overrides
- Context from previous rounds (if resumed session)

**Examples:**

```
/show-main-prompt

```

**Aliases:**`/main-prompt`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md160](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L160-L160)[codex_autoloop/telegram_control.py453-454](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L453-L454)[codex_autoloop/daemon_ctl.py37-41](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L37-L41)

---

### `/show-plan`

**Syntax:**

```
/show-plan

```

**Description:**
Returns the current planner overview markdown from `plan_report.md`. This contains:

- High-level project overview
- Workstream status table
- Completed objectives
- Remaining work
- Next proposed objective

**Examples:**

```
/show-plan

```

**Aliases:**`/plan-md`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md161](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L161-L161)[codex_autoloop/telegram_control.py455-456](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L455-L456)[codex_autoloop/daemon_ctl.py31-35](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L31-L35)

---

### `/show-plan-context`

**Syntax:**

```
/show-plan-context

```

**Description:**
Displays the full context provided to the planner sub-agent:

- Operator messages (initial objective + planning directions)
- Current plan overview (`plan_report.md`)
- Configured planner mode

**Use Cases:**

- Understanding what information planner has
- Debugging unexpected plan proposals
- Verifying planning directions are being applied

**Examples:**

```
/show-plan-context

```

**Aliases:**`/plan-context`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md162](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L162-L162)[codex_autoloop/telegram_control.py457-458](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L457-L458)[codex_autoloop/daemon_ctl.py43-52](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L43-L52)

---

## Daemon Control Commands

### `/daemon-stop`

**Syntax:**

```
/daemon-stop

```

**Description:**
Stops the ArgusBot daemon process entirely, including any active child runs. This command:

1. Sends `SIGTERM` to active child process (if any)
2. Cleans up daemon PID file
3. Releases Telegram token lock
4. Terminates daemon main loop

**Behavior:**

- Daemon will not restart automatically
- Use `argusbot init` or `argusbot-daemon` to restart
- In-progress work is not saved beyond normal state persistence

**Examples:**

```
/daemon-stop

```

**Aliases:**`/shutdown-daemon`, `/disable`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md181-182](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L181-L182)[codex_autoloop/telegram_control.py477-478](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L477-L478)[codex_autoloop/daemon_ctl.py158-161](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L158-L161)

---

### `/help`

**Syntax:**

```
/help

```

**Description:**
Returns a summary of available commands for the current control channel.

**Response Format:**

```
Available commands:
  /run <objective> - Start new run
  /inject <text> - Add instruction to active run
  /mode <off|auto|record> - Switch planner mode
  /status - Show daemon/child status
  /stop - Stop active run
  /daemon-stop - Shutdown daemon
  ...

```

**Examples:**

```
/help

```

**Aliases:**`/commands`

**Channels:** Telegram, Feishu, Terminal, Monitor Console

**Sources:**[README.md140](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L140-L140)[codex_autoloop/telegram_control.py481-482](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L481-L482)[codex_autoloop/daemon_ctl.py84-87](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L84-L87)

---

## Special Input Methods

### Voice and Audio Transcription

**Telegram Voice Messages:**

Telegram voice messages, audio files, and audio documents are automatically transcribed via OpenAI Whisper API and treated as text commands.

**Supported Audio Types:**

- Voice messages (`.ogg` format)
- Audio files (`.mp3`, `.m4a`, etc.)
- Documents with `audio/*` MIME type

**Transcription Flow:**

[Flowchart Diagram]

**Configuration:**

- `--telegram-control-whisper` — Enable/disable (default: enabled)
- `--telegram-control-whisper-api-key` — OpenAI API key (default: `OPENAI_API_KEY` env var)
- `--telegram-control-whisper-model` — Model name (default: `whisper-1`)
- `--telegram-control-whisper-base-url` — API base URL (default: `https://api.openai.com/v1`)
- `--telegram-control-whisper-timeout-seconds` — Request timeout (default: 90)

**Error Handling:**

- Missing API key: Logs warning once, skips transcription
- Network errors: Logged but do not crash poller
- Transcription failures: Logged, message ignored

**Examples:**

```
[User sends voice message: "inject 先修测试再继续"]
→ Transcribed to: "inject 先修测试再继续"
→ Parsed as: TelegramCommand(kind="inject", text="先修测试再继续")

```

**Sources:**[README.md387-398](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L387-L398)[codex_autoloop/telegram_control.py33-163](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L33-L163)[codex_autoloop/telegram_control.py381-407](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L381-L407)

---

### Plain Text Auto-routing

**Behavior:**

When `plain_text_as_inject=True` (default), plain text messages without command prefix are automatically routed:

| Daemon State | Plain Text Behavior |
| --- | --- |
| Running | Treated as `/inject` |
| Idle | Treated as `/run` |

**Examples:**

```
# During active run:
"Add error handling to the API"
→ /inject Add error handling to the API

# When daemon idle:
"Implement feature X"
→ /run Implement feature X

```

**Command Prefix Normalization:**

CJK punctuation is automatically normalized:

- `／` (full-width) → `/`
- `、` (ideographic comma) → `/`

**Examples:**

```
"／status" → /status
"、help" → /help

```

**Sources:**[README.md166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L166-L166)[codex_autoloop/telegram_control.py420-487](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L420-L487)[codex_autoloop/telegram_control.py490-497](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L490-L497)

---

## Command Parsing Reference

**Core Parsing Functions:**

[Flowchart Diagram]

**Command Kind Values:**

| Kind | Trigger | Description |
| --- | --- | --- |
| `run` | `/run <text>` | Start new run |
| `new` | `/new` | Force fresh session |
| `fresh-session` | `/fresh`, `/fresh-session`, `/new-session` | Alias for `new` |
| `inject` | `/inject <text>`, plain text (running) | Add instruction |
| `mode` | `/mode <value>`, mode selection (1/2/3) | Switch planner mode |
| `mode-menu` | `/mode` (no args) | Display mode selection menu |
| `mode-invalid` | Invalid mode selection digit | Invalid mode input |
| `btw` | `/btw <text>` | BTW query |
| `attachments-confirm` | `/confirm-send` | Confirm BTW attachments |
| `attachments-cancel` | `/cancel-send` | Cancel BTW attachments |
| `plan` | `/plan <text>` | Planning direction |
| `review` | `/review <text>` | Review criteria |
| `show-main-prompt` | `/show-main-prompt` | Show main prompt |
| `show-plan` | `/show-plan` | Show plan overview |
| `show-plan-context` | `/show-plan-context` | Show plan context |
| `show-review` | `/show-review [round]` | Show review summary |
| `show-review-context` | `/show-review-context` | Show review context |
| `stop` | `/stop` | Stop run |
| `daemon-stop` | `/daemon-stop` | Stop daemon |
| `status` | `/status` | Get status |
| `help` | `/help` | Show help |
| `plan-run` | Callback `plan_run:<id>` | Execute plan proposal |
| `plan-modify` | Callback `plan_modify:<id>` | Modify and execute |
| `plan-reject` | Callback `plan_reject:<id>` | Reject proposal |

**Sources:**[codex_autoloop/telegram_control.py420-509](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L420-L509)[tests/test_telegram_control.py43-254](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_control.py#L43-L254)

---

## Terminal Command Reference

**`argusbot-daemon-ctl` Subcommands:**

```
# Run control
argusbot-daemon-ctl --bus-dir .argusbot/bus run "objective text"
argusbot-daemon-ctl --bus-dir .argusbot/bus new
argusbot-daemon-ctl --bus-dir .argusbot/bus stop
 
# Execution control
argusbot-daemon-ctl --bus-dir .argusbot/bus inject "instruction text"
argusbot-daemon-ctl --bus-dir .argusbot/bus mode "off|auto|record"
 
# Planning
argusbot-daemon-ctl --bus-dir .argusbot/bus plan "direction text"
 
# Review
argusbot-daemon-ctl --bus-dir .argusbot/bus review "criteria text"
 
# Queries
argusbot-daemon-ctl --bus-dir .argusbot/bus status
argusbot-daemon-ctl --bus-dir .argusbot/bus btw "question text"
argusbot-daemon-ctl --bus-dir .argusbot/bus show-main-prompt
argusbot-daemon-ctl --bus-dir .argusbot/bus show-plan
argusbot-daemon-ctl --bus-dir .argusbot/bus show-plan-context
argusbot-daemon-ctl --bus-dir .argusbot/bus show-review [round]
argusbot-daemon-ctl --bus-dir .argusbot/bus show-review-context
 
# Daemon control
argusbot-daemon-ctl --bus-dir .argusbot/bus help
argusbot-daemon-ctl --bus-dir .argusbot/bus daemon-stop
```

**Bus Directory Default:**`--bus-dir` defaults to `.argusbot/bus` and can be omitted if working in the project root.

**BTW Command Special Behavior:**
Terminal `btw` command waits up to 180 seconds for response in `btw_messages.md` and prints the new content automatically.

**Sources:**[README.md493-499](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L493-L499)[codex_autoloop/daemon_ctl.py18-251](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L18-L251)

---

## Command Comparison Table

| Command | Telegram | Feishu | Terminal | Monitor | When Idle | When Running |
| --- | --- | --- | --- | --- | --- | --- |
| `/run` | ✓ | ✓ | ✓ | ✓ | Start run | Error |
| `/new` | ✓ | ✓ | ✓ | ✓ | Set marker | Set marker |
| `/inject` | ✓ | ✓ | ✓ | ✓ | Auto→run | Queue inject |
| `/mode` | ✓ | ✓ | ✓ | ✓ | Update config | Update + forward |
| `/btw` | ✓ | ✓ | ✓* | ✓ | Query | Query |
| `/plan` | ✓ | ✓ | ✓ | ✓ | Update config | Forward to child |
| `/review` | ✓ | ✓ | ✓ | ✓ | Update config | Forward to child |
| `/show-*` | ✓ | ✓ | ✓ | ✓ | Return artifact | Return artifact |
| `/status` | ✓ | ✓ | ✓ | ✓ | Return status | Return status |
| `/stop` | ✓ | ✓ | ✓ | ✓ | No-op | Stop child |
| `/daemon-stop` | ✓ | ✓ | ✓ | ✓ | Stop daemon | Stop all |
| `/help` | ✓ | ✓ | ✓ | ✓ | Show help | Show help |
| Voice | ✓ | ✗ | ✗ | ✗ | — | — |
| Callbacks | ✓ | ✗ | ✗ | ✗ | — | — |
| Plain text | ✓** | ✓** | ✗ | ✓** | Auto→run | Auto→inject |

* Terminal `btw` waits for response synchronously
** When `plain_text_as_inject=True`

**Sources:**[README.md149-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L149-L166)[codex_autoloop/telegram_control.py165-330](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L165-L330)[codex_autoloop/daemon_ctl.py213-247](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_ctl.py#L213-L247)