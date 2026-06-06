# Models and AI Configuration
Relevant source files
- [codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py)
- [codex_autoloop/setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py)

This document explains how ArgusBot configures AI models for its multi-agent execution system. It covers model selection strategies, reasoning effort levels, predefined presets, and integration with the Codex CLI backend.

For detailed preset definitions and the model catalog, see [Model Catalog and Presets](/waltstephen/ArgusBot/6.1-model-catalog-and-presets). For GitHub Copilot quota routing, see [Copilot Proxy Integration](/waltstephen/ArgusBot/6.2-copilot-proxy-integration). For configuration file structure and persistence, see [Configuration Files](/waltstephen/ArgusBot/6.3-configuration-files).

---

## Purpose and Scope

ArgusBot executes tasks using a multi-agent architecture where different agents (Main Agent, Reviewer Agent, Planner Agent) require AI model configuration. This page documents:

- **Model selection mechanisms**: presets, custom configuration, and Codex defaults
- **Reasoning effort levels**: how to control model inference depth
- **Configuration resolution**: how setup wizard choices become runtime parameters
- **Backend integration**: how model settings are passed to Codex CLI

This page does **not** cover:

- Individual agent behavior (see [Agent System](/waltstephen/ArgusBot/4.2-reviewer-sub-agent))
- Execution loops (see [Multi-Agent Loop System](/waltstephen/ArgusBot/3.4-multi-agent-loop-system))
- Command-line arguments (see [Configuration Reference](/waltstephen/ArgusBot/8.2-cli-arguments-reference))

---

## Configuration Architecture

The model configuration system has three layers: definition (catalog), selection (setup/daemon config), and execution (runtime parameter passing).

[Flowchart Diagram]

**Sources:**[codex_autoloop/model_catalog.py1-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L1-L166)[codex_autoloop/setup_wizard.py1-1037](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L1-L1037)[codex_autoloop/codex_runner.py1-359](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L1-L359)

---

## Model Selection Strategies

ArgusBot supports three configuration strategies, resolved in order of precedence:

### Strategy 1: Predefined Presets

Users select a named preset (e.g., `"quality"`, `"balanced"`, `"copilot"`) which configures all agents consistently. Presets are defined in `MODEL_PRESETS` and resolved via `get_preset()`.

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py775-798](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L775-L798)[codex_autoloop/model_catalog.py156-161](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L156-L161)

### Strategy 2: Custom Per-Agent Configuration

Users specify individual models and reasoning efforts for each agent. This allows asymmetric configurations (e.g., expensive main agent, cheap reviewer).

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py121-134](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L121-L134)[codex_autoloop/setup_wizard.py916-999](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L916-L999)

### Strategy 3: Inherit Codex Defaults

If no preset and no custom models are specified, ArgusBot omits model configuration arguments, allowing Codex CLI to use its own defaults. This is represented by `None` values in configuration.

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py116-120](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L116-L120)[codex_autoloop/codex_runner.py276-279](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L276-L279)

---

## Reasoning Effort Levels

Reasoning effort controls the depth of model inference, trading latency and cost for quality. ArgusBot supports four levels:

| Level | Flag Value | Typical Use Case | Relative Cost |
| --- | --- | --- | --- |
| `low` | `low` | Fast iterations, cheap agents | 1x |
| `medium` | `medium` | Balanced reviewer checks | 2x |
| `high` | `high` | Production main agent runs | 4x |
| `xhigh` | `xhigh` | Complex reasoning tasks | 8x |

Reasoning effort is passed to Codex CLI via the `-c model_reasoning_effort="<level>"` flag. The Codex CLI interprets this according to its internal model routing logic.

**Sources:**[codex_autoloop/codex_runner.py278-279](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L278-L279)[codex_autoloop/setup_wizard.py128-134](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L128-L134)[codex_autoloop/setup_wizard.py801-808](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L801-L808)

---

## Agent-Specific Model Configuration

Each agent in the multi-agent loop can have distinct model settings:

[Flowchart Diagram]

**Sources:**[codex_autoloop/model_catalog.py8-17](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L8-L17)[codex_autoloop/setup_wizard.py110-134](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L110-L134)

---

## Configuration Resolution Flow

The following diagram shows how model configuration flows from user input through setup to runtime execution:

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py75-135](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L75-L135)[codex_autoloop/model_catalog.py156-161](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L156-L161)[codex_autoloop/codex_runner.py271-298](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L271-L298)

---

## ModelPreset Data Structure

The `ModelPreset` dataclass defines a complete configuration for all agents:

```
@dataclass(frozen=True)
class ModelPreset:
    name: str                          # e.g., "quality", "balanced", "copilot"
    main_model: str                    # Main agent model
    main_reasoning_effort: str         # Main agent reasoning level
    reviewer_model: str                # Reviewer agent model
    reviewer_reasoning_effort: str     # Reviewer agent reasoning level
    plan_model: str                    # Planner agent model
    plan_reasoning_effort: str         # Planner agent reasoning level
    note: str                          # Human-readable description
```

Available presets in `MODEL_PRESETS`:

| Preset Name | Main Model | Main Effort | Reviewer Model | Reviewer Effort | Use Case |
| --- | --- | --- | --- | --- | --- |
| `quality` | `gpt-5.4` | `high` | `gpt-5.4` | `high` | Highest quality, symmetric config |
| `copilot` | `gpt-5.4` | `high` | `gpt-5.4` | `high` | Copilot proxy-optimized |
| `codex52-xhigh` | `gpt-5.2-codex` | `xhigh` | `gpt-5.2-codex` | `xhigh` | Maximum codex reasoning |
| `quality-xhigh` | `gpt-5.4` | `xhigh` | `gpt-5.4` | `xhigh` | Maximum general reasoning |
| `balanced` | `gpt-5.3-codex` | `high` | `gpt-5.1-codex` | `medium` | Strong main, cheaper reviewer |
| `codex-xhigh` | `gpt-5.3-codex` | `xhigh` | `gpt-5.3-codex` | `xhigh` | Pure codex maximum effort |
| `cheap` | `gpt-5.1-codex-mini` | `medium` | `gpt-5-codex-mini` | `low` | Cost-optimized |
| `max` | `gpt-5.1-codex-max` | `xhigh` | `gpt-5.3-codex` | `high` | Long-horizon expensive |

**Sources:**[codex_autoloop/model_catalog.py8-123](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L8-L123)

---

## RunnerOptions Integration

The `CodexRunner` class accepts `RunnerOptions` which encapsulate model configuration:

```
@dataclass
class RunnerOptions:
    model: str | None = None                      # Model override
    reasoning_effort: str | None = None           # Reasoning effort override
    dangerous_yolo: bool = False
    full_auto: bool = False
    skip_git_repo_check: bool = False
    extra_args: list[str] | None = None
    working_dir: str | None = None
    output_schema_path: str | None = None
    watchdog_soft_idle_seconds: int | None = None
    watchdog_hard_idle_seconds: int | None = None
    # ... additional fields
```

When `CodexRunner.run_exec()` builds the command, it conditionally includes model flags:

```
# From _build_command()
if options.model:
    command.extend(["-m", options.model])
if options.reasoning_effort:
    command.extend(["-c", f'model_reasoning_effort="{options.reasoning_effort}"'])
```

This design allows each agent invocation to specify its own model without global configuration pollution.

**Sources:**[codex_autoloop/codex_runner.py36-48](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L36-L48)[codex_autoloop/codex_runner.py271-298](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L271-L298)

---

## Setup Wizard Model Selection

The interactive setup wizard prompts users to select a model configuration strategy:

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py75-135](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L75-L135)[codex_autoloop/setup_wizard.py775-798](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L775-L798)

---

## Command Construction Example

Given configuration `{"run_main_model": "gpt-5.3-codex", "run_main_reasoning_effort": "xhigh"}`, the CodexRunner builds:

```
codex exec --json -m gpt-5.3-codex -c model_reasoning_effort="xhigh" --full-auto -
```

Given configuration `{"run_main_model": None, "run_main_reasoning_effort": None}`, the CodexRunner builds:

```
codex exec --json --full-auto -
```

The model and reasoning effort flags are omitted when configuration values are `None`, allowing Codex CLI to apply its own defaults.

**Sources:**[codex_autoloop/codex_runner.py271-298](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L271-L298)

---

## Copilot Proxy Override Mechanism

When copilot proxy is enabled, additional configuration overrides are injected at runtime to route requests through the local proxy. This is handled by the `copilot_proxy` module (referenced in setup wizard).

The setup wizard detects proxy availability:

1. Checks `--run-copilot-proxy-dir` argument
2. Auto-detects proxy in standard locations via `resolve_proxy_dir()`
3. Offers to bootstrap install if not found and preset is `"copilot"`

Configuration is stored in `daemon_config.json`:

- `run_copilot_proxy`: boolean enable flag
- `run_copilot_proxy_dir`: path to proxy checkout
- `run_copilot_proxy_port`: local proxy port (default 18080)

At execution time, the daemon ensures the proxy is running and injects provider overrides via `codex_config_overrides()` into `CodexRunner.default_extra_args`.

**Sources:**[codex_autoloop/setup_wizard.py85-99](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L85-L99)[codex_autoloop/setup_wizard.py389-432](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L389-L432)

---

## Configuration Persistence

Model configuration is persisted in two primary locations:

### daemon_config.json

Written by setup wizard, read by daemon on startup:

```
{
  "run_model_preset": "quality",
  "run_main_model": "gpt-5.4",
  "run_main_reasoning_effort": "high",
  "run_reviewer_model": "gpt-5.4",
  "run_reviewer_reasoning_effort": "high",
  "run_copilot_proxy": false,
  "run_copilot_proxy_dir": null,
  "run_copilot_proxy_port": 18080
}
```

### Daemon Command Line

The setup wizard builds the daemon launch command with explicit flags mirroring the config:

```
argusbot-daemon \
  --run-model-preset quality \
  --run-main-model gpt-5.4 \
  --run-main-reasoning-effort high \
  --run-reviewer-model gpt-5.4 \
  --run-reviewer-reasoning-effort high \
  --run-copilot-proxy-port 18080
```

This dual persistence ensures the daemon can be launched either by reading config or via explicit arguments.

**Sources:**[codex_autoloop/setup_wizard.py169-277](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L277)