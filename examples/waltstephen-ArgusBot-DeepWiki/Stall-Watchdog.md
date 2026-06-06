# Stall Watchdog
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py)

The Stall Watchdog is a safety mechanism that detects when the main agent has become unresponsive or stuck, and takes corrective action. It implements a two-tier intervention system: soft idle detection triggers a diagnostic sub-agent to assess whether intervention is needed, while hard idle detection forces an immediate restart as a fail-safe.

For information about the main agent execution loop that the watchdog monitors, see [AutoLoopOrchestrator](/waltstephen/ArgusBot/4.1-autolooporchestrator). For details about session resumption after forced restarts, see [Session Management and Resumption](/waltstephen/ArgusBot/7.1-session-management-and-resumption).

---

## Purpose and Scope

The Stall Watchdog addresses a common failure mode in long-running AI agent sessions: the agent may become stuck waiting for user input, enter an infinite loop, or otherwise stop making progress without explicitly exiting. Without intervention, such stalls would waste compute resources and require manual monitoring.

The watchdog operates independently of the main execution loop, tracking output activity and triggering escalating interventions based on configured idle thresholds.

**Sources:**[README.md71](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L71-L71)[README.md225-226](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L225-L226)[README.md400-403](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L400-L403)

---

## Two-Tier Detection System

### Stall Detection Flow

[Flowchart Diagram]

**Sources:**[README.md400-403](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L400-L403)

---

## Soft Idle Detection

### Threshold and Purpose

The soft idle threshold (default: **3600 seconds** / 1 hour) triggers a diagnostic assessment without forcing immediate action. When crossed, a dedicated diagnosis sub-agent analyzes recent output to determine whether the stall is recoverable or requires intervention.

### Diagnosis Sub-Agent

The diagnosis sub-agent is a separate Codex execution that inspects:

- The latest message content from the main agent
- Recent output tail/logs
- Current execution context

Based on this analysis, it outputs a decision on whether to restart the main agent or continue waiting.

**Key characteristics:**

- **Non-destructive**: Does not automatically terminate the main agent
- **Context-aware**: Analyzes actual output patterns, not just time elapsed
- **Single decision**: Runs once per soft threshold crossing

**Sources:**[README.md225-226](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L225-L226)[README.md402](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L402-L402)

---

## Hard Idle Detection

### Threshold and Purpose

The hard idle threshold (default: **10800 seconds** / 3 hours) is a fail-safe that forces a restart regardless of any diagnostic assessment. This prevents indefinite hangs in cases where the diagnosis sub-agent cannot make a determination or fails to run.

### Forced Restart Mechanism

When the hard threshold is exceeded:

1. The main agent process is **immediately terminated**
2. The orchestrator discards the current round
3. Execution resumes in the next round with a fresh `codex exec resume` call

This mechanism prioritizes system availability over preserving potentially corrupted state.

**Sources:**[README.md226](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L226-L226)[README.md403](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L403-L403)

---

## Configuration Parameters

### Command-Line Arguments

| Argument | Default | Purpose |
| --- | --- | --- |
| `--stall-soft-idle-seconds` | `3600` | Seconds of idle time before diagnosis sub-agent runs |
| `--stall-hard-idle-seconds` | `10800` | Seconds of idle time before forced restart |

**Sources:**[codex_autoloop/cli.py226-242](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L226-L242)

### Validation Rules

The CLI argument parser enforces the following constraints:

[Flowchart Diagram]

Validation logic from [codex_autoloop/cli.py38-47](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L38-L47):

- Both thresholds must be non-negative
- Hard threshold must be greater than or equal to soft threshold
- Setting either to `0` effectively disables that tier

**Sources:**[codex_autoloop/cli.py38-47](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L38-L47)

---

## Integration with Orchestrator

### Monitoring Points

The Stall Watchdog monitors output activity from the main agent during `codex exec` and `codex exec resume` invocations. Activity is tracked at the granularity of:

- Standard output lines
- Standard error lines
- Codex CLI event emissions

### State Transitions

[State Diagram]

**Sources:**[README.md71](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L71-L71)

---

## Relationship to Other Safety Mechanisms

The Stall Watchdog operates in parallel with other loop safety mechanisms:

| Mechanism | Trigger Condition | Action |
| --- | --- | --- |
| **Stall Watchdog (Soft)** | No output for 1 hour | Run diagnosis sub-agent |
| **Stall Watchdog (Hard)** | No output for 3 hours | Force restart |
| **Max Rounds** | Round count exceeds limit | Stop loop entirely |
| **Max No-Progress Rounds** | Identical summaries N times | Stop loop entirely |
| **Reviewer Blocking** | Reviewer returns `blocked` | Stop loop entirely |

The watchdog is unique in that it can **restart within a round** rather than stopping the entire loop, making it suitable for transient stalls rather than fundamental task completion issues.

**Sources:**[README.md622-626](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L622-L626)

---

## Daemon Mode Behavior

In daemon mode, the Stall Watchdog operates within each child CLI process. When a child is force-restarted:

1. The daemon detects the child exit
2. Session state is preserved in `last_state.json`
3. The next round (or next daemon-triggered run) attempts to resume from the saved `session_id`

This ensures continuity across watchdog interventions in 24/7 operation scenarios.

For details on daemon child process lifecycle, see [Daemon Mode Architecture](/waltstephen/ArgusBot/3.2-daemon-mode-architecture).

**Sources:**[README.md482-483](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L482-L483)

---

## Disabling the Watchdog

To disable specific tiers:

```
# Disable soft diagnosis (only use hard fail-safe)
argusbot-run --stall-soft-idle-seconds 0 --stall-hard-idle-seconds 10800 "objective"
 
# Disable both tiers (not recommended for production)
argusbot-run --stall-soft-idle-seconds 0 --stall-hard-idle-seconds 0 "objective"
```

Setting a threshold to `0` disables that tier entirely. Disabling both tiers removes all automatic stall recovery, requiring manual intervention if the agent hangs.

**Sources:**[codex_autoloop/cli.py38-41](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L38-L41)

---

## Summary

The Stall Watchdog provides tiered protection against agent hangs:

- **Soft idle (1hr)**: Intelligent diagnosis before intervention
- **Hard idle (3hr)**: Guaranteed fail-safe restart
- **Configurable**: Adjustable thresholds for different use cases
- **Non-blocking**: Operates independently of the main execution loop

This design balances aggressive recovery (preventing wasted compute) with conservative intervention (avoiding premature termination of slow but legitimate work).

**Sources:**[README.md71](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L71-L71)[README.md225-226](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L225-L226)[README.md400-403](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L400-L403)[codex_autoloop/cli.py226-242](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py#L226-L242)