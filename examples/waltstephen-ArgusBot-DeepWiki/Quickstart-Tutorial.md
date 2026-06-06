# Quickstart Tutorial
Relevant source files
- [QUICKSTART.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1)
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)

## Purpose and Scope

This tutorial provides a hands-on introduction to using ArgusBot after installation. You will learn how to run your first task, use basic commands, and understand the core workflows. This tutorial assumes you have already completed installation and setup (see [Installation and Initial Setup](/waltstephen/ArgusBot/2.1-installation-and-initial-setup)). For detailed configuration options, see [Configuration Overview](/waltstephen/ArgusBot/2.3-configuration-overview).

By the end of this tutorial, you will:

- Understand the difference between CLI mode and daemon mode
- Run your first automated task with ArgusBot
- Use basic control commands to interact with running tasks
- Read and interpret ArgusBot output
- Know which workflow to use for different scenarios

---

## Prerequisites

Before starting this tutorial:

1. ArgusBot is installed in your environment
2. You have completed `argusbot init` or `argusbot-setup` (see [Installation and Initial Setup](/waltstephen/ArgusBot/2.1-installation-and-initial-setup))
3. Codex CLI is installed and authenticated
4. You are in a project directory where you want ArgusBot to operate

---

## Your First Run

### Using the `argusbot` Command

The simplest way to start is the single-word entrypoint:

```
argusbot
```

**What happens:**

| First Run | Subsequent Runs |
| --- | --- |
| Prompts for control channel (Telegram/Feishu) | Reuses existing config from `.argusbot/daemon_config.json` |
| Collects credentials | Auto-starts daemon if not running |
| Writes `.argusbot/daemon_config.json` | Attaches to live daemon output |
| Starts daemon in background | Ready for commands immediately |

After the first run, you'll see an interactive console where you can type commands directly.

[Flowchart Diagram]

**Sources:**[codex_autoloop/codexloop.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codexloop.py#L1-L100)[codex_autoloop/setup_wizard.py1-50](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L1-L50)[README.md129-183](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L129-L183)

---

## Running Your First Task

### CLI Mode: Single Run

For a one-time task without daemon overhead, use `argusbot-run`:

```
argusbot-run \
  --max-rounds 10 \
  --check "pytest -q" \
  "Implement the get_user function and make sure all tests pass"
```

**Command Breakdown:**

| Argument | Purpose |
| --- | --- |
| `--max-rounds 10` | Stop after 10 agent iterations |
| `--check "pytest -q"` | Run this command each round; must pass for completion |
| Final string | The objective given to the main agent |

**What you'll see:**

```
[loop.started] session_id=abc123, max_rounds=10
[round.started] round=1
[main_agent.message] Planning implementation strategy...
[main_agent.tool_use] edit: src/user.py
[round.review.started] round=1
[round.review.completed] status=continue, message="Tests still failing, need to fix validation"
[round.started] round=2
...

```

The loop continues until:

1. Reviewer returns `status=done` AND all `--check` commands pass
2. OR `max_rounds` is reached
3. OR reviewer returns `status=blocked`
4. OR you manually send `/stop`

[Flowchart Diagram]

**Sources:**[codex_autoloop/run_loop.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/run_loop.py#L1-L100)[codex_autoloop/loop_engine.py1-200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/loop_engine.py#L1-L200)[README.md192-229](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L192-L229)

---

### Daemon Mode: Persistent Operation

For ongoing work with Telegram/Feishu control, use daemon mode:

```
# If not already started by 'argusbot'
argusbot init
```

Then from your Telegram bot (or terminal):

```
/run Implement the authentication module and write comprehensive tests

```

The daemon spawns a child process that runs the task. You can:

- Send `/inject` to modify the objective mid-execution
- Send `/status` to see current progress
- Send `/stop` to halt execution
- Let it complete and automatically propose the next task (if planner mode is `auto`)

**Daemon Command Flow:**

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py1-300](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1-L300)[codex_autoloop/loop_state_store.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/loop_state_store.py#L1-L100)[README.md423-453](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L423-L453)

---

## Basic Commands Reference

### In Terminal (Direct or Attach Mode)

When running `argusbot` or `argusbot-run` with terminal control:

| Command | Purpose | Example |
| --- | --- | --- |
| `/run <objective>` | Start new task | `/run Add logging to all API endpoints` |
| `/inject <instruction>` | Modify current task | `/inject Focus on error handling first` |
| `/status` | Check progress | `/status` |
| `/stop` | Halt execution | `/stop` |
| `/new` | Force fresh session (no resume) | `/new` |
| `/mode <off\|auto\|record>` | Set planner behavior | `/mode record` |
| `/plan <direction>` | Give planner guidance | `/plan Focus on performance optimization` |
| `/review <criteria>` | Update review criteria | `/review Must handle edge cases` |
| `/btw <question>` | Ask question without interrupting | `/btw What's the current test coverage?` |
| `/daemon-stop` | Shutdown daemon | `/daemon-stop` |
| Plain text | Auto-routes to `/run` or `/inject` | `Add input validation` |

**Plain text auto-routing:**

- If daemon is **idle**: treated as `/run <text>`
- If daemon has **active child**: treated as `/inject <text>`

### From Telegram/Feishu

Same commands work in Telegram/Feishu with these additions:

| Feature | Telegram | Feishu |
| --- | --- | --- |
| Voice messages | Auto-transcribed via Whisper API | Not supported |
| Inline buttons | Plan approval/rejection | Not supported |
| Media attachments | Photos, videos, documents (via `/btw`) | Photos, files |
| Long-poll interval | 20s timeout, 2s interval | 2s interval |

**Example Telegram interaction:**

```
You: /run Create a user registration endpoint with validation

Bot: ▶️ Started run abc123
     Round 1/500
     Main agent: Analyzing requirements...

[30 seconds later]
Bot: 📝 Round 1 complete
     Reviewer: continue - "Need to add password hashing"

You: /inject Use bcrypt for password hashing

Bot: ✅ Injected instruction
     Will apply in next round

[2 minutes later]
Bot: ✅ Loop completed
     Reviewer: done - "All tests passing, validation complete"

```

**Sources:**[codex_autoloop/telegram_notifier.py1-200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_notifier.py#L1-L200)[codex_autoloop/telegram_command_poller.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_command_poller.py#L1-L100)[README.md364-422](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L364-L422)

---

## Understanding Execution Output

### Terminal Output Structure

When you run a task, you'll see event-driven output:

```
[2024-01-15 10:23:45] loop.started session_id=abc123 max_rounds=500
[2024-01-15 10:23:46] round.started round=1
[2024-01-15 10:23:50] main_agent.thinking "Analyzing codebase structure..."
[2024-01-15 10:24:10] main_agent.tool_use tool=edit file=src/api.py
[2024-01-15 10:24:15] acceptance_checks.started checks=["pytest -q"]
[2024-01-15 10:24:20] acceptance_checks.completed all_passed=true
[2024-01-15 10:24:21] round.review.started round=1
[2024-01-15 10:24:30] round.review.completed status=done message="Implementation complete"
[2024-01-15 10:24:30] loop.completed exit_code=0 total_rounds=1

```

### Key Event Types

| Event Type | Meaning |
| --- | --- |
| `loop.started` | New execution session began |
| `round.started` | Main agent starting iteration |
| `main_agent.message` | Agent reasoning or status update |
| `main_agent.tool_use` | Agent executing a tool (edit, bash, etc.) |
| `acceptance_checks.*` | Running `--check` commands |
| `round.review.started` | Reviewer evaluating round |
| `round.review.completed` | Reviewer decision: `done`, `continue`, or `blocked` |
| `loop.completed` | Session finished (success or failure) |
| `planner.sweep.completed` | Background planner updated reports |

**Sources:**[codex_autoloop/event_types.py1-50](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/event_types.py#L1-L50)[codex_autoloop/loop_engine.py200-400](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/loop_engine.py#L200-L400)

---

### State Artifacts Created

During execution, ArgusBot creates several files in `.argusbot/`:

[Flowchart Diagram]

**File Usage:**

| File | Purpose | Used By |
| --- | --- | --- |
| `last_state.json` | Current session snapshot | Session resumption logic |
| `operator_messages.md` | Input history for reviewer context | Reviewer agent prompts |
| `plan_report.md` | Latest strategic plan | Planner follow-up proposals |
| `plan_todo.md` | Mirrored TODO board | CLI display (`/show-plan`) |
| `review_summaries/index.md` | Latest review | Status commands |
| `argusbot-run-archive.jsonl` | Audit trail | Session resolution |

**Sources:**[codex_autoloop/loop_state_store.py100-300](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/loop_state_store.py#L100-L300)[codex_autoloop/session_utils.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/session_utils.py#L1-L100)[README.md481-489](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L481-L489)

---

## Common Workflows

### Workflow 1: Single Task Execution

**Use case:** Run one specific task and exit.

```
argusbot-run \
  --max-rounds 20 \
  --check "npm test" \
  "Add error handling to the payment processing module"
```

**When to use:**

- One-off tasks
- Scripts/automation that don't need persistence
- Quick experiments
- CI/CD integration

**Lifecycle:**

1. Process starts
2. Executes main → check → review loop
3. Completes or hits max rounds
4. Process exits

---

### Workflow 2: Continuous Daemon Operation

**Use case:** Ongoing development with remote control.

```
# One-time setup
argusbot init
 
# Then use forever via Telegram or terminal
/run Build the authentication system
# [waits for completion]
/run Add rate limiting to all endpoints
# [etc.]
```

**When to use:**

- 24/7 project operation
- Remote control from phone/Telegram
- Automatic follow-up task proposals
- Long-running projects

**Lifecycle:**

1. Daemon starts once
2. Waits for `/run` commands
3. Spawns child process per run
4. Monitors child, logs results
5. Optionally proposes next task (if `planner_mode=auto`)
6. Returns to idle, repeat

**Sources:**[README.md32-83](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L32-L83)[QUICKSTART.md90-143](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L90-L143)

---

### Workflow 3: Iterative Development with Injections

**Use case:** Refine objectives during execution.

```
# Terminal or Telegram
/run Implement the data export feature

# [Observes execution]
# [Sees agent going in wrong direction]

/inject Actually, export to JSON format, not CSV

# [Later]
/inject Add compression before export

# [Task completes with both modifications]

```

**When to use:**

- Requirements clarify during execution
- Need to course-correct
- Want to add constraints mid-run

**How it works:**

- Injection appended to `operator_messages.md`
- Next round, main agent receives updated context
- Reviewer sees full history when evaluating

**Sources:**[codex_autoloop/loop_state_store.py200-250](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/loop_state_store.py#L200-L250)[README.md387-392](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L387-L392)

---

### Workflow 4: Using the Planner for Follow-ups

**Use case:** Let ArgusBot propose next tasks automatically.

```
# Setup with auto planner mode
argusbot init
# [Choose mode 2: Auto Planner]
 
/run Build the initial API structure
 
# [Task completes]
# Daemon sends Telegram message:
# "Planner suggests: Add input validation and error handling to all endpoints"
# [Execute] [Reject] [Modify]
 
# [Click Execute or wait 10 minutes for auto-execution]
```

**Planner modes:**

| Mode | Behavior |
| --- | --- |
| `off` | No planner background sweeps |
| `auto` | Planner proposes follow-up, auto-executes after delay |
| `record` | Planner writes reports but no auto-execution |

**Follow-up flow:**

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py300-500](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L300-L500)[README.md441-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L441-L444)[QUICKSTART.md118-124](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L118-L124)

---

## Troubleshooting Quick Reference

| Issue | Solution |
| --- | --- |
| "daemon.pid exists but process not running" | Run `argusbot init` to clean up and restart |
| Telegram bot not responding | Verify token format: `123456789:ABC...`, check network access |
| Session won't resume | Use `/new` to force fresh session |
| Agent loops without progress | Check objective clarity, add `/review` criteria, lower max_rounds |
| `invalid_encrypted_content` error | Will auto-trigger fresh session on next run |
| Stuck at max_rounds | Increase limit or refine objective to be more specific |
| Commands not recognized in terminal | Ensure you're in attach mode (`argusbot`) or daemon-ctl |

**Sources:**[README.md417-422](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L417-L422)[codex_autoloop/telegram_daemon.py400-450](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L400-L450)

---

## Next Steps

Now that you understand basic ArgusBot operation:

1. **Configure for your needs:** See [Configuration Overview](/waltstephen/ArgusBot/2.3-configuration-overview) for model selection, preset customization, and advanced options
2. **Explore daemon architecture:** See [Daemon Mode Architecture](/waltstephen/ArgusBot/3.2-daemon-mode-architecture) for process management details
3. **Understand the multi-agent system:** See [Multi-Agent Loop System](/waltstephen/ArgusBot/3.4-multi-agent-loop-system) for how main, reviewer, and planner agents coordinate
4. **Master commands:** See [Command Reference](/waltstephen/ArgusBot/8.1-command-reference) for complete command documentation
5. **Set up remote control:** See [Telegram Integration](/waltstephen/ArgusBot/5.2-telegram-integration) or [Feishu Integration](/waltstephen/ArgusBot/5.3-feishu-integration) for advanced notification and control features

**Sources:**[README.md1-638](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L1-L638)[QUICKSTART.md1-183](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/QUICKSTART.md?plain=1#L1-L183)