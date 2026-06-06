# Claude Code Plugin (Use-Case)
Relevant source files
- [use-cases/claude-code-plugin/README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1)
- [use-cases/claude-code-plugin/assets/dashboard-preview.html](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard-preview.html)
- [use-cases/claude-code-plugin/assets/dashboard.html](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html)
- [use-cases/claude-code-plugin/commands/ask.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/ask.md?plain=1)
- [use-cases/claude-code-plugin/install.sh](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/install.sh)
- [use-cases/claude-code-plugin/plugin.json](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/plugin.json)

The **EverMem Plugin for Claude Code** provides persistent memory capabilities for the Anthropic Claude Code CLI. It automatically captures coding context, architectural decisions, and session history to ensure continuity across development sessions. The plugin leverages the EverOS backend to transform raw CLI transcripts into structured, retrievable memory units.

## Plugin Architecture

The plugin is built on a hook-based architecture defined in `hooks.json`[use-cases/claude-code-plugin/hooks/hooks.json1-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json#L1-L53) that integrates directly with the Claude Code lifecycle. It operates by intercepting user prompts and model responses to perform context injection and memory storage. The plugin is distributed via the Claude marketplace and managed as a user-scoped plugin [use-cases/claude-code-plugin/README.md51-56](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L51-L56)

### System Interaction Flow

The following diagram illustrates how the plugin bridges the **Natural Language Space** (User/Claude interaction) with the **Code Entity Space** (EverOS API and Local Storage).

**Diagram: Claude Code Lifecycle Integration**

```

```

Sources: [use-cases/claude-code-plugin/README.md200-240](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L200-L240)[use-cases/claude-code-plugin/README.md82-107](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L82-L107)[use-cases/claude-code-plugin/hooks/hooks.json1-51](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json#L1-L51)

## Core Features

| Feature | Description |
| --- | --- |
| **Automatic Save** | Conversations are parsed and sent to EverOS when Claude finishes a response turn [use-cases/claude-code-plugin/README.md103-106](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L103-L106) |
| **Context Injection** | Relevant past memories are retrieved via vector search and injected into the current prompt [use-cases/claude-code-plugin/README.md92-101](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L92-L101) |
| **Session Persistence** | Summaries of the previous session are loaded upon startup to provide immediate continuity [use-cases/claude-code-plugin/README.md86-90](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L86-L90) |
| **Memory Hub** | A local proxy server provides a web-based dashboard for visualizing memory growth and project activity [use-cases/claude-code-plugin/README.md108-119](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L108-L119) |

## Implementation Modules

The plugin functionality is divided into two primary domains: the lifecycle hooks that handle real-time interaction, and the management layer that provides visualization and manual control.

### Hook Lifecycle and Memory Storage

The plugin utilizes four primary hooks to manage the memory lifecycle:

- `SessionStart`: Executes `session-context-wrapper.sh` to fetch recent cloud memories and local session history [use-cases/claude-code-plugin/hooks/hooks.json3-14](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json#L3-L14)
- `UserPromptSubmit`: Runs `inject-memories.js` to trigger semantic search and prompt augmentation [use-cases/claude-code-plugin/hooks/hooks.json15-26](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json#L15-L26)
- `Stop`: Triggers `store-memories.js` to capture the conversation transcript [use-cases/claude-code-plugin/hooks/hooks.json27-38](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json#L27-L38)
- `SessionEnd`: Runs `session-summary.js` to generate a deferred summary for the next session [use-cases/claude-code-plugin/hooks/hooks.json39-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json#L39-L50)

For technical details on transcript parsing and local storage formats, see **[Hook Lifecycle and Memory Storage](/EverMind-AI/EverOS/13.1-hook-lifecycle-and-memory-storage)**.

### Memory Hub and Commands

Beyond automatic behavior, the plugin provides a suite of tools for manual memory management:

- **Memory Hub**: A local dashboard served via `proxy.js` on port `3456`, featuring heatmaps and project-based grouping [use-cases/claude-code-plugin/assets/dashboard.html156-222](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html#L156-L222)
- **Slash Commands**: Direct CLI commands like `/evermem:search` and `/evermem:ask` for explicit retrieval [use-cases/claude-code-plugin/README.md71-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L71-L80) The `/evermem:ask` command specifically combines memory search with current context [use-cases/claude-code-plugin/commands/ask.md9-11](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/ask.md?plain=1#L9-L11)
- **Project Context**: Support for `.claude/evermem.local.md` to define project-specific `group_id` mappings [use-cases/claude-code-plugin/README.md129-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L129-L140)

For details on the proxy server and command implementation, see **[Memory Hub Dashboard and Commands](/EverMind-AI/EverOS/13.2-memory-hub-dashboard-and-commands)**.

## Technical Components Mapping

This diagram maps the high-level plugin features to the specific files and data structures used in the implementation.

**Diagram: Component to File Mapping**

```

```

Sources: [use-cases/claude-code-plugin/README.md71-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L71-L80)[use-cases/claude-code-plugin/commands/ask.md1-58](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/ask.md?plain=1#L1-L58)[use-cases/claude-code-plugin/assets/dashboard.html1-150](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html#L1-L150)

## Configuration and Setup

The plugin requires an `EVERMEM_API_KEY` environment variable to communicate with the EverOS backend [use-cases/claude-code-plugin/README.md123-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L123-L128) Installation is automated via a shell script that detects the user's shell profile and configures the environment [use-cases/claude-code-plugin/install.sh38-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/install.sh#L38-L52)

- **Environment Variable**: `export EVERMEM_API_KEY="your-api-key-here"`[use-cases/claude-code-plugin/README.md39-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L39-L40)
- **Project Config**: `.claude/evermem.local.md` for overriding the `group_id`[use-cases/claude-code-plugin/README.md131-139](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L131-L139)
- **Debug Mode**: `export EVERMEM_DEBUG=1` redirects logs to `/tmp/evermem-debug.log`[use-cases/claude-code-plugin/README.md165-180](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L165-L180)
- **Dependencies**: The installation process automatically triggers `npm install` within the plugin's cache directory to ensure lifecycle hooks have necessary runtime packages [use-cases/claude-code-plugin/install.sh153-159](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/install.sh#L153-L159)

Sources: [use-cases/claude-code-plugin/README.md15-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L15-L24)[use-cases/claude-code-plugin/README.md123-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L123-L140)[use-cases/claude-code-plugin/README.md165-180](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L165-L180)[use-cases/claude-code-plugin/install.sh38-160](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/install.sh#L38-L160)