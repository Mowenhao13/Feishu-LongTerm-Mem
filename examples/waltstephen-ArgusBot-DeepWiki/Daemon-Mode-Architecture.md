# Daemon Mode Architecture
Relevant source files
- [codex_autoloop/apps/cli_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py)
- [codex_autoloop/apps/daemon_app.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py)
- [codex_autoloop/telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py)
- [tests/test_telegram_daemon.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py)

## Purpose and Scope

This document describes the architecture of ArgusBot's daemon mode, which enables 24/7 operation with persistent supervision of CLI child processes. The daemon acts as a supervisor that accepts remote commands via Telegram, Feishu, or local terminal, spawns CLI instances as child processes, and optionally auto-executes follow-up objectives proposed by the planner.

For information about CLI mode execution (what the daemon spawns as children), see [CLI Mode Architecture](/waltstephen/ArgusBot/3.3-cli-mode-architecture). For the agent loop system that runs inside CLI instances, see [Multi-Agent Loop System](/waltstephen/ArgusBot/3.4-multi-agent-loop-system). For command reference across all modes, see [Command Reference](/waltstephen/ArgusBot/8.1-command-reference).

---

## Daemon Process Lifecycle

The daemon follows a well-defined lifecycle from initialization through shutdown.

[State Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py200-267](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L200-L267)[codex_autoloop/apps/daemon_app.py95-135](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L95-L135)

### Initialization Sequence

The daemon initialization performs several critical setup steps:

| Step | Purpose | Key Code |
| --- | --- | --- |
| **Argument Parsing** | Load configuration from CLI args | [codex_autoloop/telegram_daemon.py201-202](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L201-L202) |
| **Channel Validation** | Ensure at least one control channel (Telegram or Feishu) | [codex_autoloop/telegram_daemon.py212-227](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L212-L227) |
| **Chat ID Resolution** | Auto-detect Telegram chat_id if needed | [codex_autoloop/telegram_daemon.py228-240](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L228-L240) |
| **Token Lock Acquisition** | Prevent multiple daemons on same bot token | [codex_autoloop/telegram_daemon.py252-266](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L252-L266) |
| **Directory Setup** | Create logs_dir and bus_dir | [codex_autoloop/telegram_daemon.py242-249](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L242-L249) |
| **Notifier Initialization** | Set up Telegram/Feishu notifiers | [codex_autoloop/telegram_daemon.py271-294](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L271-L294) |
| **BTW Agent Creation** | Initialize side-agent for read-only queries | [codex_autoloop/telegram_daemon.py324-342](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L324-L342) |
| **Control Channel Start** | Begin polling Telegram/Feishu/local bus | [codex_autoloop/telegram_daemon.py1039-1067](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1039-L1067) |

**Sources:**[codex_autoloop/telegram_daemon.py200-342](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L200-L342)[codex_autoloop/apps/daemon_app.py41-123](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L41-L123)

### Main Loop Structure

The daemon main loop is a single-threaded event loop that multiplexes multiple concerns:

```
while True:
    time.sleep(1)
    # 1. Poll local bus for terminal commands
    for item in daemon_bus.read_new():
        handle_command(TelegramCommand(kind=item.kind, text=item.text), "terminal")
    
    # 2. Check if child process has exited
    if child is None:
        process_planner_timers()  # Auto-execute if countdown elapsed
        update_status()
        continue
    
    # 3. Monitor child process
    rc = child.poll()
    if rc is None:
        # Child still running - check heartbeat timers
        if should_emit_feishu_heartbeat(...):
            feishu_notifier.send_message("[daemon] typing...")
        continue
    
    # 4. Child exited - handle completion
    notify(f"[daemon] run finished\nexit_code={rc}")
    schedule_plan_after_child_finish(...)
    child = None
```

**Sources:**[codex_autoloop/telegram_daemon.py1082-1159](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1082-L1159)[codex_autoloop/apps/daemon_app.py126-134](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L126-L134)

---

## Control Channel Architecture

The daemon accepts commands from three independent sources, all converging on a unified command handler.

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py643-886](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L643-L886)[codex_autoloop/telegram_control.py1-200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L1-L200)[codex_autoloop/feishu_adapter.py1-300](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/feishu_adapter.py#L1-L300)[codex_autoloop/daemon_bus.py1-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py#L1-L100)

### Channel-Specific Features

| Channel | Polling Mechanism | Special Features | Configuration |
| --- | --- | --- | --- |
| **Telegram** | Long-poll `getUpdates` with offset tracking | Voice transcription via Whisper API, inline keyboards, file uploads | `--telegram-bot-token`, `--telegram-chat-id` |
| **Feishu** | Short-poll message API with last message_id | Heartbeat messages for long-running tasks, CN network optimized | `--feishu-app-id`, `--feishu-app-secret`, `--feishu-chat-id` |
| **Local Bus** | File watch on JSONL append | Direct terminal control via `argusbot-daemon-ctl` | `--bus-dir` (auto-created) |

**Sources:**[codex_autoloop/telegram_control.py50-150](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_control.py#L50-L150)[codex_autoloop/feishu_adapter.py200-350](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/feishu_adapter.py#L200-L350)[codex_autoloop/daemon_bus.py1-50](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py#L1-L50)

### Command Handler Dispatch Table

The `handle_command` function routes commands to specific handlers:

| Command Kind | Condition | Action | Handler Location |
| --- | --- | --- | --- |
| `help` | Always | Send help text | [telegram_daemon.py647-648](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L647-L648) |
| `status` | Always | Report daemon + child state | [telegram_daemon.py672-695](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L672-L695) |
| `fresh-session`, `new` | Always | Arm next run for fresh session | [telegram_daemon.py697-719](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L697-L719) |
| `mode` | Always | Update planner mode | [telegram_daemon.py721-741](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L721-L741) |
| `show-main-prompt` | Always | Read and send main prompt markdown | [telegram_daemon.py742-744](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L742-L744) |
| `show-plan` | Always | Read and send plan report markdown | [telegram_daemon.py745-747](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L745-L747) |
| `show-review` | Always | Read and send reviewer summary | [telegram_daemon.py758-771](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L758-L771) |
| `btw` | Always | Start async side-agent query | [telegram_daemon.py783-812](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L783-L812) |
| `run`, `inject` | Child idle | Start new child process | [telegram_daemon.py822-856](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L822-L856) |
| `run`, `inject` | Child running | Forward inject to child control bus | [telegram_daemon.py841-851](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L841-L851) |
| `plan`, `review` | Child running | Forward to child control bus | [telegram_daemon.py813-821](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L813-L821) |
| `stop` | Child running | Forward stop or force-terminate | [telegram_daemon.py857-882](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L857-L882) |
| `daemon-stop` | Always | Raise `SystemExit(0)` | [telegram_daemon.py883-885](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L883-L885) |

**Sources:**[codex_autoloop/telegram_daemon.py643-886](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L643-L886)[codex_autoloop/apps/daemon_app.py187-383](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L187-L383)

---

## Child Process Management

The daemon spawns CLI instances as child processes and supervises their execution.

[Flowchart Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py446-537](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L446-L537)[codex_autoloop/apps/daemon_app.py384-440](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L384-L440)

### Child Command Construction

The `build_child_command` function builds the CLI argument array by:

1. **Resolving the autoloop command**: Typically `argusbot-run` or `python -m codex_autoloop.cli`
2. **Propagating daemon configuration**: Model presets, copilot proxy settings, check commands
3. **Disabling CLI-side control**: `--no-telegram-control` to prevent polling conflicts
4. **Setting up file paths**: Control bus, operator messages, plan report, review summaries
5. **Session management**: `--session-id {resume_session_id}` if resuming

**Key arguments passed to child:**

```
cmd = [
    *resolve_autoloop_command(args.codex_autoloop_bin),
    "--max-rounds", str(args.run_max_rounds),
    "--telegram-bot-token", args.telegram_bot_token,
    "--telegram-chat-id", chat_id,
    "--no-telegram-control",  # Daemon owns polling
    "--control-file", control_path,  # Child reads commands here
    "--operator-messages-file", messages_path,
    "--main-prompt-file", main_prompt_path,
    "--plan-report-file", plan_report_path,
    "--review-summaries-dir", review_summaries_dir,
    "--session-id", resume_session_id,  # if resuming
    objective  # Final positional argument
]
```

**Sources:**[codex_autoloop/telegram_daemon.py470-481](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L470-L481)[tests/test_telegram_daemon.py34-104](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L34-L104)

### Child Process Spawn

Child processes are spawned with specific isolation settings:

```
child = subprocess.Popen(
    cmd,
    stdout=log_file,
    stderr=log_file,
    text=True,
    cwd=run_cwd,
    env=resolve_child_env(),  # Inject PYTHONPATH
    start_new_session=True,   # New process group for clean termination
)
```

**Key environment setup:**

- **`PYTHONPATH`**: Injected with repo root to ensure imports work [telegram_daemon.py91-99](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L91-L99)
- **`cwd`**: Set to `run_cwd` specified by `--run-cd` argument
- **`start_new_session=True`**: Creates new process group for tree termination on Windows/Unix

**Sources:**[codex_autoloop/telegram_daemon.py483-491](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L483-L491)[codex_autoloop/telegram_daemon.py91-99](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L91-L99)

### Control Bus Communication

The daemon communicates with running child processes via a JSONL control bus:

```
# Daemon side: forward command to child
child_control_bus.publish(BusCommand(
    kind="inject",
    text="fix the failing test",
    source="telegram",
    ts=time.time()
))
 
# Child side: read commands in CLI
control_channel = LocalBusControlChannel(
    path=args.control_file,
    source="terminal",
    poll_interval_seconds=1.0
)
control_channel.start(on_control_command)
```

**Supported command kinds:**

- `inject`: Interrupt main agent and resume with new instruction
- `plan`: Send direction to planner only
- `review`: Send criteria to reviewer only
- `stop`: Request graceful shutdown
- `mode`: Update plan_mode (off/auto/record)

**Sources:**[codex_autoloop/telegram_daemon.py634-641](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L634-L641)[codex_autoloop/daemon_bus.py40-70](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py#L40-L70)[codex_autoloop/apps/cli_app.py220-229](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/cli_app.py#L220-L229)

### Child Exit Handling

When a child process exits, the daemon:

1. **Reads exit code**: `rc = child.poll()`
2. **Notifies operators**: Send exit status via all channels
3. **Schedules planner**: If in `auto` mode, prepare follow-up objective
4. **Cleans up references**: `child = None`, `child_control_bus = None`
5. **Updates status file**: Write idle state to `daemon_status.json`

**Sources:**[codex_autoloop/telegram_daemon.py1094-1159](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1094-L1159)[codex_autoloop/apps/daemon_app.py460-481](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L460-L481)

---

## Status and State Tracking

The daemon maintains multiple state files for external observability.

### Status File Schema

The `daemon_status.json` file is continuously updated and readable by `argusbot-daemon-ctl`:

```
{
  "updated_at": "2026-01-15T03:42:17Z",
  "daemon_pid": 12345,
  "daemon_running": true,
  "running": true,
  "child_pid": 12346,
  "child_objective": "implement user authentication",
  "child_log_path": "/path/to/.argusbot/logs/run-20260115-034200.log",
  "child_main_prompt_path": "/path/to/.argusbot/logs/run-20260115-034200-main-prompt.md",
  "child_plan_report_path": "/path/to/.argusbot/logs/run-20260115-034200-plan-report.md",
  "child_review_summaries_dir": "/path/to/.argusbot/logs/run-20260115-034200-review",
  "child_started_at": "2026-01-15T03:42:00Z",
  "last_session_id": "thread_abc123",
  "force_fresh_session": false,
  "run_cwd": "/path/to/project",
  "logs_dir": "/path/to/.argusbot/logs",
  "bus_dir": "/path/to/.argusbot/bus",
  "plan_mode": "auto",
  "btw_busy": false,
  "btw_session_id": null,
  "pending_plan_request": "继续完成目标",
  "pending_plan_auto_execute_at": "2026-01-15T04:00:00Z",
  "scheduled_plan_request_at": null
}
```

**Update locations:**

- After child spawn: [telegram_daemon.py537](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L537-L537)
- After child exit: [telegram_daemon.py1093-1159](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1093-L1159)
- After mode change: [telegram_daemon.py740](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L740-L740)
- After fresh session request: [telegram_daemon.py719](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L719-L719)
- Main loop iteration: [telegram_daemon.py1092](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L1092-L1092)

**Sources:**[codex_autoloop/telegram_daemon.py398-444](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L398-L444)[codex_autoloop/daemon_bus.py10-30](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/daemon_bus.py#L10-L30)

### Events Log

The `daemon-events.jsonl` file maintains a complete audit trail:

```
{"ts": "2026-01-15T03:40:00Z", "type": "daemon.started", "run_cwd": "/path/to/project", "token_hash": "abc123"}
{"ts": "2026-01-15T03:42:00Z", "type": "child.launched", "pid": 12346, "objective": "implement auth", "log_path": "..."}
{"ts": "2026-01-15T03:42:10Z", "type": "command.received", "source": "telegram", "kind": "inject", "text": "use bcrypt"}
{"ts": "2026-01-15T03:42:10Z", "type": "child.command.forwarded", "source": "telegram", "kind": "inject", "text": "use bcrypt"}
{"ts": "2026-01-15T04:15:00Z", "type": "child.finished", "exit_code": 0, "objective": "implement auth", "log_path": "..."}
{"ts": "2026-01-15T04:15:05Z", "type": "plan.scheduled", "mode": "fully-plan", "scheduled_request_at": "2026-01-15T04:25:05Z"}
```

**Event types emitted:**

- `daemon.started`, `daemon.stopped`, `daemon.interrupted`
- `child.launched`, `child.finished`, `child.stop.requested`
- `command.received`, `child.command.forwarded`, `reply.sent`
- `plan.scheduled`, `plan.proposed`, `plan.auto_execute`, `plan.cleared`
- `session.fresh.requested`, `session.fresh.applied`

**Sources:**[codex_autoloop/telegram_daemon.py344-351](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L344-L351)[codex_autoloop/telegram_daemon.py508-521](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L508-L521)

---

## Planning Timers and Follow-up Automation

When running in `auto` planner mode, the daemon can automatically execute follow-up objectives.

### Planning State Machine

[State Diagram]

**Sources:**[codex_autoloop/telegram_daemon.py893-1038](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L893-L1038)[codex_autoloop/telegram_daemon.py975-1038](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L975-L1038)

### Planning State Variables

The daemon maintains several timer-related state variables:

| Variable | Type | Purpose |
| --- | --- | --- |
| `scheduled_plan_context` | `dict` | Objective, exit_code, state_payload for generating plan request |
| `scheduled_plan_request_at` | `datetime` | When to generate plan request (child_exit_time + delay) |
| `pending_plan_request` | `str` | Generated follow-up objective waiting for auto-execute |
| `pending_plan_generated_at` | `datetime` | When the plan request was generated |
| `pending_plan_auto_execute_at` | `datetime` | When to auto-execute if no manual override |

**Sources:**[codex_autoloop/telegram_daemon.py312-317](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L312-L317)

### Plan Request Generation

After child exit, if conditions are met, a plan request is scheduled:

```
def schedule_plan_after_child_finish(objective, exit_code, log_path, plan_report_path):
    # Check mode
    if plan_mode == PLAN_MODE_EXECUTE_ONLY:
        return
    
    if plan_mode == PLAN_MODE_RECORD_ONLY:
        append_plan_record_row(...)
        return
    
    # Check if we should schedule follow-up
    should_schedule, skip_reason = should_schedule_plan_follow_up(
        exit_code=exit_code,
        state_payload=read_status(args.run_state_file)
    )
    if not should_schedule:
        notify(build_plan_skip_message(skip_reason, state_payload))
        return
    
    # Schedule plan request generation
    scheduled_plan_context = {
        "objective": objective,
        "exit_code": exit_code,
        "state_payload": state_payload,
        "plan_report_path": str(plan_report_path)
    }
    scheduled_plan_request_at = now + timedelta(seconds=plan_request_delay_seconds)
```

**Conditions to schedule follow-up:**

1. `exit_code == 0` (run succeeded)
2. Latest review status is `done` (not `blocked` or `continue`)
3. Latest plan has `follow_up_required: true`

**Sources:**[codex_autoloop/telegram_daemon.py893-974](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L893-L974)[tests/test_telegram_daemon.py412-450](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_telegram_daemon.py#L412-L450)

### Auto-Execute Countdown

The planner timers are processed in the main loop:

```
def process_planner_timers():
    now = dt.datetime.utcnow()
    
    # Check for auto-execute countdown elapsed
    if (pending_plan_request is not None and
        pending_plan_auto_execute_at is not None and
        now >= pending_plan_auto_execute_at):
        notify("[daemon] auto executing planned request")
        start_child(pending_plan_request)
        clear_planner_state(reason="auto_execute")
        return
    
    # Check for plan generation time
    if (scheduled_plan_context is not None and
        scheduled_plan_request_at is not None and
        now >= scheduled_plan_request_at):
        request = build_plan_request(...)
        pending_plan_request = request
        pending_plan_auto_execute_at = now + timedelta(seconds=plan_auto_execute_delay_seconds)
        notify(f"[daemon] planner request generated\nAuto execute in {delay}s")
```

**Default timings:**

- `plan_request_delay_seconds`: 600 (10 minutes) - Wait before generating plan
- `plan_auto_execute_delay_seconds`: 600 (10 minutes) - Wait before auto-executing

**Sources:**[codex_autoloop/telegram_daemon.py975-1038](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L975-L1038)[codex_autoloop/telegram_daemon.py310-311](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L310-L311)

### Git Checkpoint Before Follow-up

Before auto-executing a follow-up, the daemon creates a git checkpoint if the workspace is dirty:

```
def create_git_checkpoint(run_cwd, plan_id, auto_triggered):
    result = subprocess.run(
        ["git", "diff", "--quiet"],
        cwd=run_cwd,
        capture_output=True
    )
    if result.returncode == 0:
        # Clean workspace
        return GitCheckpointResult(ok_to_continue=True, message="[daemon] workspace clean")
    
    # Dirty workspace - create checkpoint
    commit_message = f"argusbot checkpoint before follow-up {plan_id}"
    subprocess.run(["git", "add", "-A"], cwd=run_cwd)
    subprocess.run(["git", "commit", "-m", commit_message], cwd=run_cwd)
    
    return GitCheckpointResult(
        ok_to_continue=True,
        message=f"[daemon] created git checkpoint: {commit_hash}",
        commit_hash=commit_hash
    )
```

**Sources:**[codex_autoloop/telegram_daemon.py581-607](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L581-L607) referenced in high-level diagram

---

## Token Lock Mechanism

The token lock prevents multiple daemon instances from polling the same Telegram bot token, which would cause 409 Conflict errors from the getUpdates API.

### Lock File Structure

Lock files are stored in `/tmp/argusbot-token-locks/` (configurable via `--token-lock-dir`):

```
/tmp/argusbot-token-locks/
└── token-{sha256_hash}.lock

```

**Lock file contents:**

```
{
  "token_hash": "abc123...",
  "acquired_at": "2026-01-15T03:40:00Z",
  "pid": 12345,
  "hostname": "server.example.com",
  "owner_info": {
    "pid": 12345,
    "chat_id": "123456789",
    "run_cwd": "/path/to/project",
    "bus_dir": "/path/to/.argusbot/bus",
    "started_at": "2026-01-15T03:40:00Z"
  }
}
```

**Sources:**[codex_autoloop/token_lock.py1-150](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/token_lock.py#L1-L150)[codex_autoloop/telegram_daemon.py252-266](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L252-L266)

### Lock Acquisition Flow

[Flowchart Diagram]

**Stale lock detection:**

- On Unix: `os.kill(pid, 0)` to check if process exists
- On Windows: Parse `tasklist` output for PID

**Sources:**[codex_autoloop/token_lock.py50-120](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/token_lock.py#L50-L120)[codex_autoloop/telegram_daemon.py252-266](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L252-L266)

### Lock Release

The lock is released during daemon shutdown:

```
def _shutdown(self) -> None:
    # ... stop control channels, terminate child ...
    if self.token_lock is not None:
        self.token_lock.release()  # Deletes lock file
```

The `TokenLock` object also implements `__del__` for automatic cleanup on daemon crash.

**Sources:**[codex_autoloop/apps/daemon_app.py527-546](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L527-L546)[codex_autoloop/token_lock.py130-150](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/token_lock.py#L130-L150)

---

## Implementation Variants

There are two implementations of daemon mode in the codebase:

### Legacy Implementation: telegram_daemon.py

The original monolithic implementation with procedural style:

- **Entry point**: `main()` function at [telegram_daemon.py200](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/telegram_daemon.py#L200-L200)
- **All state**: Module-level variables in `main()` closure
- **Command handling**: Single `handle_command()` function with nested logic
- **Planning**: Inline timer processing in main loop
- **Used by**: `argusbot-daemon` CLI entrypoint

**Advantages**: Complete feature set, battle-tested, includes planning automation

**Sources:**[codex_autoloop/telegram_daemon.py1-1463](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/telegram_daemon.py#L1-L1463)

### Refactored Implementation: daemon_app.py

Object-oriented refactoring with cleaner architecture:

- **Entry point**: `TelegramDaemonApp.run()` method at [daemon_app.py95](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/daemon_app.py#L95-L95)
- **State management**: Instance variables on `TelegramDaemonApp` class
- **Command handling**: Method dispatch with smaller functions
- **Control channels**: Abstracted via adapter interfaces
- **Used by**: Newer code paths, potentially future default

**Advantages**: More testable, cleaner separation of concerns, easier to extend

**Missing features**: Planning automation not yet implemented in this variant

**Sources:**[codex_autoloop/apps/daemon_app.py1-929](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/apps/daemon_app.py#L1-L929)

Both implementations share common utilities for child command building, status formatting, and session resolution.

---

## Summary

The daemon mode architecture provides:

1. **Persistent supervision** via a single-threaded event loop
2. **Multi-channel control** from Telegram, Feishu, and local terminal
3. **Child process isolation** with control bus communication
4. **Automated follow-up** via planning timers and git checkpoints
5. **Token lock coordination** to prevent polling conflicts
6. **Complete observability** via status files and event logs

The daemon acts as a thin supervision layer that spawns and monitors CLI instances, forwards commands, and optionally chains objectives together for autonomous operation.