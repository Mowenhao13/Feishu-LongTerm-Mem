# AutoLoopOrchestrator
Relevant source files
- [codex_autoloop/orchestrator.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py)
- [codex_autoloop/reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py)
- [tests/test_reviewer.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_reviewer.py)

The **AutoLoopOrchestrator** is the core execution engine that implements ArgusBot's continuous loop behavior. It coordinates the main agent, reviewer sub-agent, and acceptance checks across multiple rounds until an objective is completed or safety limits are reached.

For information about the multi-agent system architecture, see [Multi-Agent Loop System](/waltstephen/ArgusBot/3.4-multi-agent-loop-system). For details on state persistence mechanisms, see [State Management and Persistence](/waltstephen/ArgusBot/3.5-state-management-and-persistence). For command injection and control mechanisms, see [Command System Overview](/waltstephen/ArgusBot/5.1-command-system-overview).

**Sources:**[codex_autoloop/orchestrator.py1-640](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L1-L640)

---

## Core Responsibilities

The orchestrator manages the following responsibilities:

| Responsibility | Implementation |
| --- | --- |
| **Round Management** | Executes up to `max_rounds` iterations, tracking round index and session continuity |
| **Main Agent Execution** | Invokes `CodexRunner.run_exec()` with appropriate prompts and session resumption |
| **Acceptance Checks** | Runs shell commands via `run_checks()` to verify objective completion |
| **Reviewer Gating** | Delegates completion decision to `Reviewer.evaluate()` after each round |
| **Interrupt Handling** | Processes external interrupts and operator-injected instructions mid-loop |
| **Session Continuity** | Maintains `session_id` across rounds, with recovery from `invalid_encrypted_content` errors |
| **No-Progress Detection** | Tracks repeated identical outputs to prevent infinite loops |
| **Stall Detection** | Monitors agent inactivity via `InactivitySnapshot` callbacks |
| **State Persistence** | Writes state to `state_file` after each round for cross-run continuity |
| **Event Emission** | Publishes structured events for monitoring and UI updates |

**Sources:**[codex_autoloop/orchestrator.py62-74](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L62-L74)[codex_autoloop/orchestrator.py75-371](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L75-L371)

---

## Configuration Schema

The orchestrator is configured via the `AutoLoopConfig` dataclass:

### AutoLoopConfig Fields

```
@dataclass
class AutoLoopConfig:
    objective: str                          # Primary objective to achieve
    max_rounds: int = 500                   # Maximum loop iterations
    max_no_progress_rounds: int = 3         # Consecutive no-progress limit
    check_commands: list[str] | None        # Acceptance check shell commands
    check_timeout_seconds: int = 1200       # Timeout per check command
    
    # Model configuration (per-agent)
    main_model: str | None
    main_reasoning_effort: str | None
    reviewer_model: str | None
    reviewer_reasoning_effort: str | None
    planner_model: str | None
    planner_reasoning_effort: str | None
    
    # Execution flags
    skip_git_repo_check: bool = False
    full_auto: bool = False
    dangerous_yolo: bool = False
    
    # State persistence
    state_file: str | None
    plan_report_file: str | None
    plan_todo_file: str | None
    initial_session_id: str | None
    
    # Stall detection thresholds
    stall_soft_idle_seconds: int = 1200     # Soft watchdog (20 min)
    stall_hard_idle_seconds: int = 10800    # Hard watchdog (3 hours)
    
    # Callback hooks
    loop_event_callback: LoopEventCallback | None
    external_interrupt_reason_provider: Callable[[], str | None] | None
    pending_instruction_consumer: Callable[[], str | None] | None
    stop_requested_checker: Callable[[], bool] | None
    operator_messages_provider: Callable[[], list[str]] | None
```

**Key callback hooks:**

- `loop_event_callback`: Receives all `loop.*` and `round.*` events
- `external_interrupt_reason_provider`: Checks for external interrupts (e.g., `/inject` commands)
- `pending_instruction_consumer`: Retrieves and consumes pending operator instructions
- `stop_requested_checker`: Checks if `/stop` command was issued
- `operator_messages_provider`: Provides historical operator messages for reviewer context

**Sources:**[codex_autoloop/orchestrator.py18-51](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L18-L51)

---

## Loop Execution Flow

### High-Level State Machine

[State Diagram]

**Sources:**[codex_autoloop/orchestrator.py75-371](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L75-L371)

---

## Round Execution Details

Each round follows this detailed sequence:

[Flowchart Diagram]

**Sources:**[codex_autoloop/orchestrator.py90-371](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L90-L371)

---

## Prompt Building Strategy

The orchestrator constructs different prompts based on context:

### Prompt Selection Decision Tree

[Flowchart Diagram]

### Request Style Detection

The `_request_style()` method classifies objectives into two categories:

| Category | Markers | Prompt Behavior |
| --- | --- | --- |
| **"response"** | `?`, `why`, `what`, `how`, `explain`, `analyze`, greetings (`hi`, `hello`, `你好`) | Direct answer, no DONE/REMAINING/BLOCKERS format, inspect repo as needed |
| **"implementation"** | `fix`, `implement`, `add`, `write`, `edit`, `modify`, `refactor`, `修改`, `实现` | Execute concrete work, end-to-end completion, DONE/REMAINING/BLOCKERS summary required |

**Sources:**[codex_autoloop/orchestrator.py558-639](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L558-L639)[codex_autoloop/orchestrator.py402-451](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L402-L451)

---

## Interrupt Handling

### External Interrupt Flow

```

```

**Sources:**[codex_autoloop/orchestrator.py130-206](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L130-L206)[codex_autoloop/orchestrator.py483-499](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L483-L499)

---

## Session Continuity and Recovery

### Session ID Lifecycle

```

```

**Invalid Encrypted Content Detection:**

The orchestrator detects this specific Codex CLI error pattern:

```
@staticmethod
def _looks_like_invalid_encrypted_content(fatal_error: str | None) -> bool:
    if not fatal_error:
        return False
    return (
        "invalid_encrypted_content" in fatal_error.lower() 
        or "invalid encrypted content" in fatal_error.lower()
    )
```

**Recovery Strategy:**

1. **Resumed session fails:** Reset `session_id` to `None`, emit `round.session.reset`, build fresh retry prompt, continue loop
2. **Fresh session fails:** Cannot recover automatically, return `AutoLoopResult(success=False)` immediately

**Sources:**[codex_autoloop/orchestrator.py208-255](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L208-L255)[codex_autoloop/orchestrator.py521-542](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L521-L542)

---

## Safety Mechanisms

### No-Progress Detection

The orchestrator prevents infinite loops by tracking a "progress signature" across rounds:

**Progress Signature Construction:**

```
@staticmethod
def _build_progress_signature(*, main_result: Any) -> str:
    last_message = str(getattr(main_result, "last_agent_message", "") or "").strip()
    if last_message:
        return f"msg:{last_message}"
    
    # Fallback to exit code + status flags
    fatal_error = str(getattr(main_result, "fatal_error", "") or "").strip()
    exit_code = int(getattr(main_result, "exit_code", 0))
    turn_completed = bool(getattr(main_result, "turn_completed", False))
    turn_failed = bool(getattr(main_result, "turn_failed", False))
    return (
        "nomsg:"
        f"exit={exit_code}|completed={int(turn_completed)}|"
        f"failed={int(turn_failed)}|fatal={fatal_error[:240]}"
    )
```

**No-Progress Logic:**

- Compare current signature with previous signature
- If identical: `no_progress_rounds += 1`
- If different: `no_progress_rounds = 0`
- If `no_progress_rounds >= max_no_progress_rounds`: Stop with failure

This prevents scenarios where the reviewer repeatedly says "continue" without the main agent producing new output.

**Sources:**[codex_autoloop/orchestrator.py338-356](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L338-L356)[codex_autoloop/orchestrator.py544-556](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L544-L556)

### Stall Watchdog Integration

The orchestrator delegates stall detection to the stall watchdog system:

```
def inactivity_callback(snapshot: InactivitySnapshot) -> str:
    return self._handle_inactivity(round_index=round_index, snapshot=snapshot)
 
def _handle_inactivity(self, *, round_index: int, snapshot: InactivitySnapshot) -> str:
    decision = analyze_stall(snapshot)
    self._emit({
        "type": "round.watchdog.checked",
        "round_index": round_index,
        "idle_seconds": int(snapshot.idle_seconds),
        "should_restart": decision.should_restart,
        "reason": decision.reason,
        "matched_pattern": decision.matched_pattern,
    })
    if decision.should_restart:
        self._emit({
            "type": "round.watchdog.restart_requested",
            "round_index": round_index,
            "idle_seconds": int(snapshot.idle_seconds),
            "reason": decision.reason,
        })
        return "restart"
    return "continue"
```

For details on stall detection patterns and diagnosis, see [Stall Watchdog](/waltstephen/ArgusBot/4.6-stall-watchdog).

**Sources:**[codex_autoloop/orchestrator.py101-102](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L101-L102)[codex_autoloop/orchestrator.py459-481](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L459-L481)

---

## Event System

The orchestrator emits structured events via the `loop_event_callback`:

### Event Types

| Event Type | Timing | Key Fields |
| --- | --- | --- |
| `loop.started` | Before first round | `objective`, `max_rounds`, `session_id` |
| `round.started` | Start of each round | `round_index`, `session_id` |
| `round.main.completed` | After main agent execution | `exit_code`, `turn_completed`, `interrupted`, `fatal_error`, `last_message` |
| `round.control.injected` | Operator instruction consumed | `instruction` |
| `round.session.reset` | Session reset due to encryption error | `previous_session_id`, `reason` |
| `round.checks.completed` | After acceptance checks | `checks[]` with `command`, `exit_code`, `passed` |
| `round.review.completed` | After reviewer evaluation | `status`, `confidence`, `reason`, `next_action` |
| `round.watchdog.checked` | Stall watchdog evaluation | `idle_seconds`, `should_restart`, `matched_pattern` |
| `round.watchdog.restart_requested` | Watchdog triggers restart | `idle_seconds`, `reason` |
| `loop.completed` | Loop termination | `success`, `stop_reason` |

### Event Emission Pattern

```
def _emit(self, event: dict[str, Any]) -> None:
    callback = self.config.loop_event_callback
    if callback is None:
        return
    callback(event)
```

Events are synchronous and blocking. The callback is invoked inline during execution.

**Sources:**[codex_autoloop/orchestrator.py81-88](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L81-L88)[codex_autoloop/orchestrator.py453-457](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L453-L457)

---

## State Persistence

### State File Structure

The orchestrator persists state to `state_file` (typically `.argusbot/last_state.json`) after each round:

```
{
  "updated_at": "2024-01-15T10:30:45.123456+00:00",
  "objective": "Fix failing tests in test_planner.py",
  "session_id": "thread-abc123",
  "round_count": 3,
  "latest_review_status": "continue",
  "rounds": [
    {
      "round_index": 1,
      "thread_id": "thread-abc123",
      "main_exit_code": 0,
      "main_turn_completed": true,
      "main_turn_failed": false,
      "checks": [
        {
          "command": "pytest tests/test_planner.py",
          "exit_code": 1,
          "passed": false,
          "output": "..."
        }
      ],
      "review": {
        "status": "continue",
        "confidence": 0.8,
        "reason": "Tests still failing",
        "next_action": "Fix assertion in test_evaluate_plan",
        "round_summary_markdown": "...",
        "completion_summary_markdown": ""
      },
      "main_last_message": "DONE: Read test file\nREMAINING: Fix assertions\nBLOCKERS: None"
    }
  ]
}
```

**Persistence Method:**

```
def _persist_state(
    self,
    *,
    rounds: list[RoundSummary],
    session_id: str | None,
    current_review: ReviewDecision,
) -> None:
    if not self.config.state_file:
        return
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "objective": self.config.objective,
        "session_id": session_id,
        "round_count": len(rounds),
        "latest_review_status": current_review.status,
        "rounds": [self._serialize_round(item) for item in rounds],
    }
    path = Path(self.config.state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

This state enables:

- Cross-run continuity (reading `session_id` on restart)
- Daemon status reporting
- Historical round inspection
- Recovery after crashes

**Sources:**[codex_autoloop/orchestrator.py373-399](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L373-L399)

---

## Result Schema

The orchestrator returns an `AutoLoopResult` upon completion:

```
@dataclass
class AutoLoopResult:
    success: bool                    # True if status='done' and checks passed
    session_id: str | None           # Final session_id for resumption
    rounds: list[RoundSummary]       # All round summaries
    stop_reason: str                 # Human-readable termination reason
    plan: Any | None = None          # Planner result (if planner enabled)
```

### Possible Stop Reasons

| Scenario | `success` | `stop_reason` |
| --- | --- | --- |
| Reviewer marked done + checks pass | `True` | `"Reviewer marked done and acceptance checks passed."` |
| Operator `/stop` command | `False` | `"Stopped by operator command."` |
| Reviewer status `blocked` | `False` | `f"Reviewer blocked: {review.reason}"` |
| No progress for N rounds | `False` | `"Stopped due to repeated no-progress rounds. Reviewer kept requesting continuation without new output."` |
| Encryption error in fresh session | `False` | `"Main agent failed with invalid_encrypted_content in a fresh session; cannot recover automatically."` |
| Max rounds reached | `False` | `f"Reached max rounds ({self.config.max_rounds})."` |

**Sources:**[codex_autoloop/orchestrator.py53-60](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L53-L60)[codex_autoloop/orchestrator.py92-99](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L92-L99)[codex_autoloop/orchestrator.py319-370](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L319-L370)

---

## Integration with Other Components

### Component Dependencies

```

```

**Initialization Pattern (from CLI/Daemon):**

```
from codex_autoloop.codex_runner import CodexRunner
from codex_autoloop.reviewer import Reviewer
from codex_autoloop.orchestrator import AutoLoopOrchestrator, AutoLoopConfig
 
runner = CodexRunner()
reviewer = Reviewer(runner)
planner = Planner(runner) if planner_enabled else None
 
config = AutoLoopConfig(
    objective="Fix the bug in module X",
    max_rounds=500,
    check_commands=["pytest tests/"],
    state_file=".argusbot/last_state.json",
    loop_event_callback=lambda event: print(event),
    # ... other config
)
 
orchestrator = AutoLoopOrchestrator(runner, reviewer, config, planner)
result = orchestrator.run()
```

**Sources:**[codex_autoloop/orchestrator.py62-74](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/orchestrator.py#L62-L74)

---

## Advanced Topics

### Generic Acknowledgment Detection

The orchestrator includes special logic to detect when the main agent produces a "generic role acknowledgment" without concrete execution. This is handled by the reviewer's coercion logic:

```
def _coerce_decision_against_main_summary(
    decision: ReviewDecision, 
    *, 
    main_summary: str
) -> ReviewDecision:
    normalized = " ".join((main_summary or "").lower().split())
    if any(pattern in normalized for pattern in GENERIC_MAIN_PATTERNS) \
       and not _has_concrete_execution_evidence(main_summary):
        return ReviewDecision(
            status="continue",
            confidence=min(decision.confidence, 0.2),
            reason=(
                "Main agent summary appears to be a generic role acknowledgment "
                "without concrete repository work. Continue and require specific execution evidence."
            ),
            next_action="Perform concrete repository inspection or code changes before the next review.",
            # ...
        )
    return decision
```

**Generic patterns detected:**

- "I am the primary implementation agent"
- "I'll act as the primary implementation agent"
- "I'll handle the main task directly"

**Concrete execution evidence:**

- `DONE:`, `REMAINING:`, `BLOCKERS:` sections
- Command execution patterns: `ran pytest`, `executed git diff`, etc.
- Action verbs: `read`, `inspected`, `edited`, `updated`, `fixed`, etc.

This prevents the reviewer from marking "done" when the agent merely acknowledges the task without performing work.

**Sources:**[codex_autoloop/reviewer.py174-233](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/reviewer.py#L174-L233)[tests/test_reviewer.py28-100](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/tests/test_reviewer.py#L28-L100)

---

**Summary:** The `AutoLoopOrchestrator` implements ArgusBot's core continuous execution loop, coordinating the main agent, reviewer, and acceptance checks while managing session continuity, safety limits, and external interrupts. It serves as the central control flow for both CLI and daemon execution modes.