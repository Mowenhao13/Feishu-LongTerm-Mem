# Model Catalog and Presets
Relevant source files
- [README.md](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1)
- [codex_autoloop/cli.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/cli.py)
- [codex_autoloop/setup_wizard.py](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py)

This page documents the available AI models, predefined model presets, reasoning effort levels, and the mechanisms for selecting and applying models across ArgusBot's multi-agent system. For runtime provider configuration and GitHub Copilot integration, see [Copilot Proxy Integration](/waltstephen/ArgusBot/6.2-copilot-proxy-integration). For the complete structure of daemon configuration files, see [Configuration Files](/waltstephen/ArgusBot/6.3-configuration-files).

---

## Overview

ArgusBot uses separate model configurations for three distinct agents:

- **Main Agent**: Executes tasks via Codex CLI (`codex exec` / `codex exec resume`)
- **Reviewer Agent**: Evaluates completion status with structured JSON output
- **Planner Agent**: Maintains strategic overview and proposes follow-up objectives

Each agent can be assigned a specific model name and reasoning effort level. Model presets provide convenient bundles that configure all three agents simultaneously with balanced settings for different use cases (quality vs cost vs speed).

**Sources:**[codex_autoloop/model_catalog.py1-166](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L1-L166)[README.md524-547](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L524-L547)

---

## Model Catalog

The system maintains a catalog of available models, categorized by purpose. These entries provide reference documentation but do not enforce availability—actual model support depends on your Codex CLI configuration and backend provider.

### Available Models

[Flowchart Diagram]

| Model | Category | Description |
| --- | --- | --- |
| `gpt-5.4` | general | Current strongest general model available in local Codex cache |
| `gpt-5.3-codex` | codex | Current strongest codex-optimized model in local cache |
| `gpt-5.2-codex` | codex | Previous codex-optimized model |
| `gpt-5.1-codex` | codex | Balanced codex model |
| `gpt-5.1-codex-max` | codex | Long-running high-cost coding model |
| `gpt-5-codex` | codex | Older codex-optimized model |
| `gpt-5.1-codex-mini` | cheap | Cheaper codex-focused model |
| `gpt-5-codex-mini` | cheap | Older cheaper codex-focused model |

**Sources:**[codex_autoloop/model_catalog.py27-36](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L27-L36)

---

## Reasoning Effort Levels

Each model can be paired with a reasoning effort parameter that controls the depth of inference processing. This parameter is passed to Codex CLI as `-c model_reasoning_effort="<level>"`.

### Valid Effort Levels

| Level | Use Case | Token Cost Impact |
| --- | --- | --- |
| `low` | Fast iteration, simple tasks | Minimal |
| `medium` | Balanced quality/cost, recommended for 24/7 daemon operation | Moderate |
| `high` | Default for quality presets, strong reasoning | Significant |
| `xhigh` | Maximum reasoning depth, complex tasks | Maximum |

**Note:** For always-on daemon operation, `medium` reasoning provides a safer cost/quality tradeoff compared to `high` or `xhigh` which can accumulate substantial token usage over extended runs.

**Sources:**[README.md37-40](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L37-L40)[codex_autoloop/setup_wizard.py801-808](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L801-L808)

---

## Model Presets

Presets are predefined bundles that configure all three agents (main, reviewer, planner) with coordinated model and reasoning effort settings. Each preset is represented by the `ModelPreset` dataclass:

[Class Diagram]

**Sources:**[codex_autoloop/model_catalog.py8-24](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L8-L24)[codex_autoloop/model_catalog.py42-123](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L42-L123)

---

## Preset Catalog

### Available Presets

| Preset Name | Main Agent | Reviewer Agent | Planner Agent | Use Case |
| --- | --- | --- | --- | --- |
| **quality** | `gpt-5.4/high` | `gpt-5.4/high` | `gpt-5.4/high` | Highest-quality default with high reasoning for all agents |
| **copilot** | `gpt-5.4/high` | `gpt-5.4/high` | `gpt-5.4/high` | Copilot proxy-friendly preset using GPT-5.4 (routes via GitHub quota) |
| **codex52-xhigh** | `gpt-5.2-codex/xhigh` | `gpt-5.2-codex/xhigh` | `gpt-5.2-codex/xhigh` | Codex 5.2 with maximum reasoning for all agents |
| **quality-xhigh** | `gpt-5.4/xhigh` | `gpt-5.4/xhigh` | `gpt-5.4/xhigh` | Highest-quality preset with maximum reasoning on all agents |
| **balanced** | `gpt-5.3-codex/high` | `gpt-5.1-codex/medium` | `gpt-5.1-codex/medium` | Strong coding quality with cheaper reviewer and planner |
| **codex-xhigh** | `gpt-5.3-codex/xhigh` | `gpt-5.3-codex/xhigh` | `gpt-5.3-codex/xhigh` | Pure codex-focused preset with maximum reasoning on all agents |
| **cheap** | `gpt-5.1-codex-mini/medium` | `gpt-5-codex-mini/low` | `gpt-5-codex-mini/low` | Lower-cost pairing for long background loops |
| **max** | `gpt-5.1-codex-max/xhigh` | `gpt-5.3-codex/high` | `gpt-5.3-codex/high` | Most expensive long-horizon pairing |

**Default Preset:**`codex-xhigh` is defined as `DEFAULT_MODEL_PRESET` but is typically overridden during setup.

**Sources:**[codex_autoloop/model_catalog.py42-123](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L42-L123)[README.md532-541](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L532-L541)

---

## Model Selection Mechanisms

### Selection Priority

ArgusBot resolves model configuration through the following priority chain:

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py79-135](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L79-L135)[codex_autoloop/codex_runner.py271-298](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/codex_runner.py#L271-L298)

---

## Interactive Setup Selection

During `argusbot init` / `argusbot-setup`, the setup wizard presents an interactive model choice menu:

[Flowchart Diagram]

**Sources:**[codex_autoloop/setup_wizard.py775-798](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L775-L798)[codex_autoloop/setup_wizard.py106-135](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L106-L135)

---

## CLI Arguments

### Direct Model Specification

Models can be specified directly via command-line arguments for single runs:

```
argusbot-run \
  --main-model gpt-5.4 \
  --main-reasoning-effort high \
  --reviewer-model gpt-5.4 \
  --reviewer-reasoning-effort high \
  --planner-model gpt-5.3-codex \
  "implement feature"
```

### Preset Specification

```
argusbot-run \
  --run-model-preset balanced \
  "implement feature"
```

### Daemon Configuration

For daemon mode, presets are stored in `.argusbot/daemon_config.json` and applied to all daemon-launched child runs unless overridden:

```
{
  "run_model_preset": "balanced",
  "run_main_model": "gpt-5.3-codex",
  "run_main_reasoning_effort": "high",
  "run_reviewer_model": "gpt-5.1-codex",
  "run_reviewer_reasoning_effort": "medium"
}
```

**Sources:**[README.md201-204](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L201-L204)[codex_autoloop/setup_wizard.py169-197](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L169-L197)

---

## Listing Available Models and Presets

The `model_catalog` module provides a command-line utility to display the current catalog:

```
# Human-readable format
python -m codex_autoloop.model_catalog
argusbot-models
 
# JSON output
python -m codex_autoloop.model_catalog --json
argusbot-models --json
```

### Example Output

```
Model presets:
- quality: main=gpt-5.4/high, reviewer=gpt-5.4/high, plan=gpt-5.4/high (Highest-quality default with high reasoning for both agents.)
- copilot: main=gpt-5.4/high, reviewer=gpt-5.4/high, plan=gpt-5.4/high (Copilot proxy-friendly preset using GPT-5.4 across main, reviewer, and planner.)
- balanced: main=gpt-5.3-codex/high, reviewer=gpt-5.1-codex/medium, plan=gpt-5.1-codex/medium (Strong coding quality with cheaper reviewer.)
...

Common model names:
- gpt-5.4: [general] Current strongest general model available in local Codex cache.
- gpt-5.3-codex: [codex] Current strongest codex-optimized model in local cache.
...

```

**Sources:**[codex_autoloop/model_catalog.py126-154](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L126-L154)[README.md524-547](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L524-L547)

---

## Code Resolution Flow

### Preset Lookup Function

The `get_preset()` function performs case-insensitive name matching:

[Flowchart Diagram]

**Sources:**[codex_autoloop/model_catalog.py156-161](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/model_catalog.py#L156-L161)

---

## Special Preset Behaviors

### Copilot Preset

When the `copilot` preset is selected or when `--run-model-preset copilot` is specified, the setup wizard automatically offers to install or detect the copilot-proxy integration. This preset is specifically designed to work with models supported by GitHub Copilot's backend.

**Sources:**[codex_autoloop/setup_wizard.py398](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L398-L398)[README.md97-127](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L97-L127)

### Inherit Codex Defaults

Selecting option `0` during interactive setup or omitting both `--run-model-preset` and explicit model arguments causes ArgusBot to inherit model settings from Codex CLI's global configuration file (`~/.codex/config.toml`). This is the recommended approach for users who have already configured Codex CLI with preferred models.

**Sources:**[codex_autoloop/setup_wizard.py81-85](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/codex_autoloop/setup_wizard.py#L81-L85)[README.md21](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L21-L21)

---

## Cost and Reasoning Effort Warnings

The setup wizard and documentation emphasize token cost implications for different reasoning effort levels:

> **From README**: "For 24/7 daemon operation, choosing `high` or `xhigh` reasoning can lead to token usage close to running one Codex session continuously for 24 hours. Plan budget carefully."

> "For always-on daemon use, `medium` is often the safer default for token cost while keeping solid quality."

These warnings appear during interactive setup when higher reasoning effort presets are selected, prompting users to confirm their choice.

**Sources:**[README.md37-40](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L37-L40)[README.md545-547](https://github.com/waltstephen/ArgusBot/blob/6d0ec9f8/README.md?plain=1#L545-L547)