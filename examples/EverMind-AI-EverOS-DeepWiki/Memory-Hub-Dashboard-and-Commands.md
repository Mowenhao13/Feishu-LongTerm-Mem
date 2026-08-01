# Memory Hub Dashboard and Commands
Relevant source files
- [use-cases/claude-code-plugin/README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1)
- [use-cases/claude-code-plugin/assets/dashboard-preview.html](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard-preview.html)
- [use-cases/claude-code-plugin/assets/dashboard.html](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html)
- [use-cases/claude-code-plugin/commands/ask.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/ask.md?plain=1)
- [use-cases/claude-code-plugin/commands/help.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/help.md?plain=1)
- [use-cases/claude-code-plugin/commands/hub.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/hub.md?plain=1)
- [use-cases/claude-code-plugin/commands/projects.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/projects.md?plain=1)
- [use-cases/claude-code-plugin/commands/scripts/search-memories.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/scripts/search-memories.js)
- [use-cases/claude-code-plugin/commands/search.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/search.md?plain=1)
- [use-cases/claude-code-plugin/mcp/server.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/mcp/server.js)
- [use-cases/claude-code-plugin/server/proxy.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js)

The Memory Hub serves as the central management and visualization interface for the EverMem Claude Code plugin. It consists of a local proxy server that facilitates communication between the browser-based dashboard and the EverMem Cloud API, alongside a suite of slash commands that allow users to interact with their persistent memory directly from the Claude Code CLI.

## Memory Hub Proxy Server

The proxy server, implemented in `proxy.js`, runs locally on port `3456`[use-cases/claude-code-plugin/server/proxy.js20](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L20-L20) It performs three primary roles:

1. **Dashboard Hosting**: Serves the `dashboard.html` file to the user's browser [use-cases/claude-code-plugin/server/proxy.js173-184](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L173-L184)
2. **Local Data Aggregation**: Exposes a `/api/groups` endpoint that reads from local `groups.jsonl` to provide a project-centric view of memory [use-cases/claude-code-plugin/server/proxy.js152-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L152-L170)
3. **API Forwarding**: Proxies `POST` requests (specifically `/api/v1/memories/search` and `/api/v1/memories/get`) to the EverMem Cloud API [use-cases/claude-code-plugin/server/proxy.js107-143](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L107-L143) This bypasses browser limitations regarding GET requests with bodies and handles CORS headers [use-cases/claude-code-plugin/server/proxy.js85-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L85-L95)

### Data Flow: Dashboard to Cloud

The following diagram illustrates how the Dashboard retrieves data through the local proxy.

**Memory Hub Data Retrieval Flow**

```

```

Sources: [use-cases/claude-code-plugin/server/proxy.js97-188](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L97-L188)

## Dashboard Features and Local Data

The Memory Hub provides a visual interface for managing persistent memory across different projects. It leverages a local data file `groups.jsonl` to track project metadata [use-cases/claude-code-plugin/server/proxy.js22](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L22-L22)

### Local Data Structure (`groups.jsonl`)

The file uses JSONL format where each line represents a session start event [use-cases/claude-code-plugin/commands/projects.md30-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/projects.md?plain=1#L30-L32)

- `keyId`: SHA-256 hash (first 12 chars) of the API key [use-cases/claude-code-plugin/server/proxy.js27-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L27-L31)
- `groupId`: 9-character identifier based on project name and path hash [use-cases/claude-code-plugin/commands/projects.md35](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/projects.md?plain=1#L35-L35)
- `name`: The project directory name [use-cases/claude-code-plugin/commands/projects.md32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/projects.md?plain=1#L32-L32)
- `path`: The absolute path of the project [use-cases/claude-code-plugin/commands/projects.md32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/projects.md?plain=1#L32-L32)

### Dashboard Visualization

The `dashboard.html` file implements a comprehensive UI for memory exploration [use-cases/claude-code-plugin/assets/dashboard.html1-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html#L1-L15):

- **Activity Heatmap**: A GitHub-style 6-month heatmap showing memory creation frequency [use-cases/claude-code-plugin/assets/dashboard.html156-222](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html#L156-L222)
- **Growth Chart**: A 7-day bar chart showing memory volume trends [use-cases/claude-code-plugin/assets/dashboard.html251-263](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html#L251-L263)
- **Project Cards**: Expandable sections for each project (group) identified in the local `groups.jsonl` file [use-cases/claude-code-plugin/assets/dashboard-preview.html65-112](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard-preview.html#L65-L112)

### Key Local Functions in proxy.js

- `computeKeyId(apiKey)`: Generates a unique identifier for the account to associate projects with specific API keys [use-cases/claude-code-plugin/server/proxy.js27-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L27-L31)
- `getGroupsForKey(keyId)`: Parses `groups.jsonl`, filters by `keyId`, and aggregates statistics including `sessionCount` and `lastSeen` timestamps [use-cases/claude-code-plugin/server/proxy.js36-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L36-L83)

Sources: [use-cases/claude-code-plugin/server/proxy.js24-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/server/proxy.js#L24-L83)[use-cases/claude-code-plugin/commands/projects.md19-35](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/projects.md?plain=1#L19-L35)[use-cases/claude-code-plugin/assets/dashboard.html156-263](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/assets/dashboard.html#L156-L263)

## Slash Commands and MCP Integration

The plugin extends Claude Code via custom slash commands and the Model Context Protocol (MCP).

### Slash Commands

Users interact with the memory system using the following commands defined in the `commands/` directory:

| Command | Script / Logic | Description |
| --- | --- | --- |
| `/evermem:search` | `search-memories.js` | Searches EverMem Cloud with hybrid retrieval and displays scores [use-cases/claude-code-plugin/commands/scripts/search-memories.js34-78](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/scripts/search-memories.js#L34-L78) |
| `/evermem:ask` | `ask.md` | Combines memory search results with current conversation context to answer complex questions [use-cases/claude-code-plugin/commands/ask.md9-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/ask.md?plain=1#L9-L41) |
| `/evermem:hub` | `hub.md` | Starts `proxy.js` and provides the local dashboard URL [use-cases/claude-code-plugin/commands/hub.md7-19](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/hub.md?plain=1#L7-L19) |
| `/evermem:projects` | `projects.md` | Aggregates and displays a table of tracked projects from `groups.jsonl`[use-cases/claude-code-plugin/commands/projects.md42-54](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/projects.md?plain=1#L42-L54) |
| `/evermem:help` | `help.md` | Shows configuration status and available commands [use-cases/claude-code-plugin/commands/help.md31-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/help.md?plain=1#L31-L45) |

### MCP Server (`mcp/server.js`)

The MCP server exposes the `evermem_search` tool to Claude [use-cases/claude-code-plugin/mcp/server.js13-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/mcp/server.js#L13-L32)

- **Tool**: `evermem_search`
- **Logic**: It implements a JSON-RPC loop [use-cases/claude-code-plugin/mcp/server.js186-219](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/mcp/server.js#L186-L219) that handles `tools/call` requests. It uses `searchMemories` from the API utilities to fetch results and formats them into a token-efficient Markdown table for the LLM [use-cases/claude-code-plugin/mcp/server.js84-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/mcp/server.js#L84-L95)

**Command and MCP Execution Flow**

```

```

Sources: [use-cases/claude-code-plugin/mcp/server.js9-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/mcp/server.js#L9-L32)[use-cases/claude-code-plugin/commands/scripts/search-memories.js8-37](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/scripts/search-memories.js#L8-L37)[use-cases/claude-code-plugin/commands/hub.md7-10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/hub.md?plain=1#L7-L10)[use-cases/claude-code-plugin/commands/ask.md18-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/commands/ask.md?plain=1#L18-L24)

## Installation and Setup

The `install.sh` script (referenced in the documentation) automates the deployment and configuration of the plugin environment.

1. **API Key Configuration**: Prompts the user for their EverMem API key and saves it to the shell profile [use-cases/claude-code-plugin/README.md21-23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L21-L23)
2. **Plugin Installation**:

- Adds the EverMem marketplace from GitHub [use-cases/claude-code-plugin/README.md52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L52-L52)
- Installs the `evermem@evermem` plugin with user scope [use-cases/claude-code-plugin/README.md55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L55-L55)
3. **Verification**: Users can run `/evermem:help` to check the configuration status [use-cases/claude-code-plugin/README.md67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L67-L67)

Sources: [use-cases/claude-code-plugin/README.md15-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/README.md?plain=1#L15-L67)