# Codex Runner Integration
Relevant source files
- [codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py)
- [codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py)
- [codex_autoloop/reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py)
- [tests/test_reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_reviewer.py)

## Overview

The Codex Runner Integration layer provides the bridge between ArgusBot's orchestration logic and the underlying Codex CLI execution engine. This integration abstracts the invocation of `codex exec` and `codex exec resume` commands, handles model selection and configuration, manages session continuity, and routes requests through optional proxy layers.

This page documents the `CodexRunner` abstraction, execution modes, model configuration hierarchy, copilot-proxy integration, and result processing. For details on how the orchestrator uses these primitives to implement the multi-round loop, see [AutoLoopOrchestrator](/waltstephen/ArgusBot/4.1-autolooporchestrator). For model preset definitions and the model catalog, see [Model Catalog and Presets](/waltstephen/ArgusBot/6.1-model-catalog-and-presets). For copilot-proxy setup and installation, see [Copilot Proxy Integration](/waltstephen/ArgusBot/6.2-copilot-proxy-integration).

---

## CodexRunner Architecture

The `CodexRunner` class serves as the primary abstraction for invoking Codex CLI commands. It is instantiated once and reused across all agent invocations (main agent, reviewer, planner, BTW side-agent, stall sub-agent).

### Invocation Flow

[Flowchart Diagram]

**Sources:**[codex_autoloop/orchestrator.py112-128](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L112-L128)[codex_autoloop/reviewer.py51-64](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py#L51-L64)

### RunnerOptions Configuration

The `RunnerOptions` dataclass encapsulates all configuration parameters for a single Codex CLI invocation:

| Field | Type | Purpose |
| --- | --- | --- |
| `model` | `str \| None` | Model override (e.g., `"gpt-5.4-turbo"`, `"claude-sonnet-4.6"`) |
| `reasoning_effort` | `str \| None` | Reasoning effort level (`"low"`, `"medium"`, `"high"`, `"xhigh"`) |
| `dangerous_yolo` | `bool` | Pass `--dangerously-bypass-approvals-and-sandbox` to Codex CLI |
| `full_auto` | `bool` | Pass `--full-auto` to Codex CLI |
| `skip_git_repo_check` | `bool` | Pass `--skip-git-repo-check` to Codex CLI |
| `extra_args` | `list[str] \| None` | Additional arguments appended to codex command |
| `watchdog_soft_idle_seconds` | `int` | Soft idle threshold triggering stall sub-agent diagnosis |
| `watchdog_hard_idle_seconds` | `int` | Hard idle threshold forcing restart |
| `inactivity_callback` | `Callable` | Function invoked on idle detection, returns `"restart"` or `"continue"` |
| `external_interrupt_reason_provider` | `Callable` | Function polled for external stop/inject commands |
| `output_schema_path` | `str \| None` | Path to JSON schema file for structured output (reviewer only) |

**Sources:**[codex_autoloop/orchestrator.py115-126](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L115-L126)[codex_autoloop/reviewer.py54-62](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py#L54-L62)

### ExecResult Structure

The `run_exec()` method returns an `ExecResult` object containing:

| Field | Type | Description |
| --- | --- | --- |
| `thread_id` | `str \| None` | Session ID for resumption (Codex CLI `--session-id`) |
| `exit_code` | `int` | Process exit code from Codex CLI |
| `turn_completed` | `bool` | Whether the agent completed its turn successfully |
| `turn_failed` | `bool` | Whether the agent turn failed with an error |
| `fatal_error` | `str \| None` | Fatal error message if process crashed or was interrupted |
| `last_agent_message` | `str` | Final message from agent (used as summary) |
| `agent_messages` | `list[str]` | All agent messages captured during execution |

**Sources:**[codex_autoloop/orchestrator.py129-147](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L129-L147)

---

## Execution Modes

The CodexRunner supports two primary execution modes: fresh session creation and session resumption. The mode is determined by the presence of `resume_thread_id` in the `run_exec()` call.

### Execution Mode Decision Flow

[Flowchart Diagram]

**Sources:**[codex_autoloop/orchestrator.py111-129](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L111-L129)

### Fresh Session Creation

When `resume_thread_id` is `None`, the runner invokes `codex exec` without a session ID:

```
codex exec --model {model} --reasoning-effort {effort} {extra_args} -- {prompt}

```

The Codex CLI creates a new session and emits a `thread_id` in its JSONL output stream. The runner captures this value and returns it in `ExecResult.thread_id`.

**First-run scenario:**

- Orchestrator starts with `initial_session_id=None`
- Round 1 calls `run_exec(prompt, resume_thread_id=None, ...)`
- Codex CLI creates fresh session, e.g., `thread-abc123`
- Orchestrator stores `session_id = "thread-abc123"`

**Sources:**[codex_autoloop/orchestrator.py111-129](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L111-L129)

### Session Resumption

When `resume_thread_id` is provided, the runner invokes `codex exec resume`:

```
codex exec resume --session-id {thread_id} --model {model} {extra_args} -- {prompt}

```

This continues the existing conversation context, preserving:

- Previous agent messages and tool calls
- Repository state observed by the agent
- Conversation history and context window

**Multi-round scenario:**

- Round 1 completes with `session_id = "thread-abc123"`
- Round 2 calls `run_exec(prompt, resume_thread_id="thread-abc123", ...)`
- Agent continues from previous context

**Sources:**[codex_autoloop/orchestrator.py111-129](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L111-L129)

### Invalid Encrypted Content Recovery

When resuming a session fails with `invalid_encrypted_content` error, the orchestrator implements automatic recovery:

[Flowchart Diagram]

**Recovery logic:**

1. Detect `invalid_encrypted_content` in `main_result.fatal_error`
2. If resuming session (not fresh), reset `session_id` to `None`
3. Construct special retry prompt explaining the error
4. Continue loop with fresh session on next round

**Non-recoverable case:**

- If fresh session (not resuming) also fails with `invalid_encrypted_content`, the loop terminates with blocking error

**Sources:**[codex_autoloop/orchestrator.py134-255](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L134-L255)

---

## Model Configuration

Model selection follows a three-tier hierarchy: system defaults → preset configurations → explicit overrides.

### Model Selection Hierarchy

[Flowchart Diagram]

**Sources:**[codex_autoloop/cli.py119-121](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L119-L121)[codex_autoloop/orchestrator.py115-117](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L115-L117)[codex_autoloop/reviewer.py54-56](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py#L54-L56)

### Per-Agent Model Overrides

Each agent type accepts separate model overrides via CLI arguments:

| CLI Argument | Agent Target | Purpose |
| --- | --- | --- |
| `--main-model` | Main execution agent | Override model for primary implementation rounds |
| `--reviewer-model` | Reviewer sub-agent | Override model for completion gating |
| `--plan-model` | Planner sub-agent | Override model for planning/follow-up proposals |

**Example usage:**

```
argusbot-run --main-model gpt-5.4-turbo \
             --reviewer-model claude-sonnet-4.6 \
             --plan-model gpt-5.2-turbo \
             "Implement feature X"
```

These overrides are stored in `daemon_config.json` for daemon mode and passed to `RunnerOptions` during invocation.

**Sources:**[codex_autoloop/cli.py119-121](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L119-L121)[codex_autoloop/orchestrator.py116](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L116-L116)[codex_autoloop/reviewer.py55](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py#L55-L55)

### Reasoning Effort Levels

Reasoning effort controls the depth of model thinking/planning before responding. Supported levels:

| Level | Description | Use Case |
| --- | --- | --- |
| `low` | Minimal reasoning overhead | Fast iterations, simple tasks |
| `medium` | Balanced reasoning depth | Default for most tasks |
| `high` | Extended reasoning time | Complex problem-solving |
| `xhigh` | Maximum reasoning depth | Critical decisions, difficult debugging |

**Per-agent reasoning effort overrides:**

- `--main-reasoning-effort` → Main agent
- `--reviewer-reasoning-effort` → Reviewer sub-agent
- `--plan-reasoning-effort` → Planner sub-agent

**Sources:**[codex_autoloop/cli.py123-141](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L123-L141)

---

## Copilot Proxy Integration

ArgusBot can route Codex CLI requests through a local `copilot-proxy` instance running at `localhost:18080`. This enables:

- Using GitHub Copilot quota instead of direct API keys
- Accessing copilot-proxy-specific model routing (e.g., `gpt-5.4`, `gpt-5.2`, `claude-sonnet-4.6`)
- Bypassing rate limits on personal API keys

### Proxy Routing Architecture

[Flowchart Diagram]

**Sources:**[codex_autoloop/cli.py83-99](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L83-L99)

### Auto-Detection and Configuration

When `--copilot-proxy` is enabled, ArgusBot searches for the copilot-proxy directory in standard locations:

1. `~/.copilot-proxy/` (preferred)
2. `~/copilot-proxy/`
3. Explicit path via `--copilot-proxy-dir`

If found, the directory path is passed to Codex CLI, which handles proxy startup and communication.

**CLI Arguments:**

| Argument | Default | Description |
| --- | --- | --- |
| `--copilot-proxy` | `False` | Enable copilot-proxy routing |
| `--copilot-proxy-dir` | Auto-detected | Path to copilot-proxy checkout |
| `--copilot-proxy-port` | `18080` | Local proxy server port |

**Sources:**[codex_autoloop/cli.py83-99](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L83-L99)

### Bootstrap Installation

If using the `copilot` model preset but copilot-proxy is not detected, the setup wizard offers to bootstrap install it. See [Copilot Proxy Integration](/waltstephen/ArgusBot/6.2-copilot-proxy-integration) for installation details.

---

## Extra Arguments and Customization

The `--{agent}-extra-arg` flags allow passing arbitrary arguments to Codex CLI on a per-agent basis.

### Per-Agent Extra Arguments

[Flowchart Diagram]

**Example usage:**

```
argusbot-run \
  --main-extra-arg "--context-size 32000" \
  --reviewer-extra-arg "--temperature 0.3" \
  --reviewer-extra-arg "--max-tokens 2000" \
  "Implement feature X"
```

The extra arguments are appended to the Codex CLI command before the `--` separator that precedes the prompt.

**Sources:**[codex_autoloop/cli.py143-158](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L143-L158)[codex_autoloop/orchestrator.py121](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L121-L121)

---

## Safety and Automation Flags

The Codex Runner respects three primary safety flags that control automation levels and sandbox enforcement:

### Flag Definitions

| CLI Argument | RunnerOptions Field | Codex CLI Flag | Purpose |
| --- | --- | --- | --- |
| `--yolo` | `dangerous_yolo` | `--dangerously-bypass-approvals-and-sandbox` | Skip all approvals, disable sandbox |
| `--full-auto` | `full_auto` | `--full-auto` | Auto-approve safe operations |
| `--skip-git-repo-check` | `skip_git_repo_check` | `--skip-git-repo-check` | Allow running outside git repos |

### Safety Flag Inheritance

All three agents (main, reviewer, planner) inherit these flags from the global configuration:

[Flowchart Diagram]

**Rationale:**

- Reviewer sub-agent needs same safety context as main agent to evaluate results accurately
- Planner sub-agent may perform read-only inspections requiring same repo access
- Consistent safety posture across all agents prevents surprises

**Sources:**[codex_autoloop/orchestrator.py118-120](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L118-L120)[codex_autoloop/reviewer.py57-59](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py#L57-L59)

---

## Result Processing and Exit Codes

The CodexRunner parses JSONL output from Codex CLI and translates it into structured `ExecResult` objects.

### Exit Code Interpretation

| Exit Code | Interpretation | Orchestrator Action |
| --- | --- | --- |
| `0` | Normal completion | Proceed to acceptance checks and reviewer |
| `1` | Turn failed or error | Pass to reviewer for evaluation |
| `130` | SIGINT (Ctrl+C) | Treat as external interrupt |
| Other | Unexpected error | Pass fatal error to reviewer |

**Sources:**[codex_autoloop/orchestrator.py140-147](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L140-L147)

### Thread ID Extraction

The `thread_id` (session ID) is extracted from Codex CLI JSONL output events. This value is:

1. Captured on first successful execution
2. Returned in `ExecResult.thread_id`
3. Stored by orchestrator as `session_id`
4. Used as `resume_thread_id` in subsequent rounds

**Session ID flow:**

```
Round 1: run_exec(prompt, resume_thread_id=None)
         → ExecResult.thread_id = "thread-abc123"
         → orchestrator stores session_id = "thread-abc123"

Round 2: run_exec(prompt, resume_thread_id="thread-abc123")
         → Resumes conversation context
         → ExecResult.thread_id = "thread-abc123" (unchanged)

```

**Sources:**[codex_autoloop/orchestrator.py129](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L129-L129)

### Agent Message Aggregation

The runner collects all agent messages emitted during execution:

- `agent_messages: list[str]` contains full conversation
- `last_agent_message: str` is the final message (used as summary)

The orchestrator uses `last_agent_message` for:

- Reviewer evaluation input
- Progress signature calculation (no-progress detection)
- Round summary persistence

**Sources:**[codex_autoloop/orchestrator.py145-146](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L145-L146)[codex_autoloop/orchestrator.py281](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L281-L281)

### Turn Completion Status

The runner tracks two boolean flags from Codex CLI:

- `turn_completed`: Agent successfully completed its turn
- `turn_failed`: Agent turn failed with error

These are passed to the reviewer for completion gating:

- `turn_completed=True` + acceptance checks passed → candidate for `done` status
- `turn_failed=True` → reviewer typically returns `continue` with error context

**Sources:**[codex_autoloop/orchestrator.py141-142](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L141-L142)[codex_autoloop/reviewer.py28-40](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py#L28-L40)

---

## Codex Binary Path Configuration

The path to the Codex CLI binary is configurable via `--codex-bin`:

```
argusbot-run --codex-bin /usr/local/bin/codex "Implement feature X"
```

**Default:**`codex` (assumes `codex` is in `PATH`)

This allows:

- Using custom Codex CLI builds
- Testing against development versions
- Running from non-standard installation locations

**Sources:**[codex_autoloop/cli.py82](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L82-L82)

---

**Summary:** The Codex Runner Integration layer provides a clean abstraction over Codex CLI invocation, handling session management, model configuration, proxy routing, and result parsing. It enables the orchestrator to focus on high-level loop logic while delegating execution details to the runner. The integration supports both fresh sessions and resumption, automatic error recovery, and fine-grained per-agent customization.