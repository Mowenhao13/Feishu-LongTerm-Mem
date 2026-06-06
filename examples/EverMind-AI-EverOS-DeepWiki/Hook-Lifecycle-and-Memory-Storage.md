# Hook Lifecycle and Memory Storage
Relevant source files
- [use-cases/claude-code-plugin/hooks/hooks.json](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json)
- [use-cases/claude-code-plugin/hooks/scripts/inject-memories.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/inject-memories.js)
- [use-cases/claude-code-plugin/hooks/scripts/session-context.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js)
- [use-cases/claude-code-plugin/hooks/scripts/session-summary.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-summary.js)
- [use-cases/claude-code-plugin/hooks/scripts/store-memories.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js)
- [use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js)

The EverMem plugin for Claude Code implements a persistent memory system through a series of lifecycle hooks. These hooks manage the flow of data between the local CLI environment and the EverMem Cloud, ensuring that context is both retrieved at the start of a session/prompt and captured at the conclusion of an interaction.

## Lifecycle Hook Overview

The plugin utilizes four primary hooks that map to specific stages of the Claude Code execution lifecycle as defined in `hooks.json`.

| Hook Name | Script | Purpose |
| --- | --- | --- |
| `SessionStart` | `session-context.js` | Dual-fetch of recent cloud memories and local session summaries. |
| `UserPromptSubmit` | `inject-memories.js` | Semantic search and RAG-style prompt injection. |
| `Stop` | `store-memories.js` | Transcript parsing and memory persistence to cloud. |
| `SessionEnd` | `session-summary.js` | Local persistence of session metadata and activity stats. |

Sources: [use-cases/claude-code-plugin/hooks/hooks.json1-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/hooks.json#L1-L52)[use-cases/claude-code-plugin/hooks/scripts/session-context.js1-7](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js#L1-L7)[use-cases/claude-code-plugin/hooks/scripts/inject-memories.js1-16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/inject-memories.js#L1-L16)[use-cases/claude-code-plugin/hooks/scripts/store-memories.js1-12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L1-L12)[use-cases/claude-code-plugin/hooks/scripts/session-summary.js1-7](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-summary.js#L1-L7)

## Data Flow and Turn Boundary Detection

EverMem relies on parsing the Claude Code transcript (a JSONL file) to identify "Turns." A turn is defined as the sequence starting from a user message and ending with the final assistant response.

### Turn Boundary Logic

In `store-memories.js`, the system detects turn boundaries using the `turn_duration` marker.

- **Turn Start**: Immediately follows the last `{"type":"system","subtype":"turn_duration"}` entry [use-cases/claude-code-plugin/hooks/scripts/store-memories.js120-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L120-L128)
- **Turn End**: The current end of the transcript file during the `Stop` hook execution [use-cases/claude-code-plugin/hooks/scripts/store-memories.js114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L114-L114)

### Transcript Parsing Diagram

The following diagram illustrates how `extractLastTurn` filters the transcript to isolate meaningful text from tool invocations and internal reasoning.

**Transcript Parsing and Filtering**

[Flowchart Diagram]

Sources: [use-cases/claude-code-plugin/hooks/scripts/store-memories.js96-109](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L96-L109)[use-cases/claude-code-plugin/hooks/scripts/store-memories.js151-181](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L151-L181)

## Hook Implementations

### SessionStart: `session-context.js`

This hook performs a "dual-fetch" strategy to prepare the environment:

1. **Cloud Fetch**: Calls `getMemories` from `evermem-api.js` to retrieve the `RECENT_MEMORY_COUNT` (default 5) most recent items [use-cases/claude-code-plugin/hooks/scripts/session-context.js31-135](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js#L31-L135)
2. **Local Fetch**: Reads `sessions.jsonl` via `getLastSessionSummary` to find the previous session's summary for the current `groupId`[use-cases/claude-code-plugin/hooks/scripts/session-context.js46-68](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js#L46-L68)
3. **Injection**: Injects a `<session-context>` block into the `systemPrompt` to orient Claude and displays a summary via `systemMessage`[use-cases/claude-code-plugin/hooks/scripts/session-context.js168-204](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js#L168-L204)
4. **Group Tracking**: Calls `saveGroup(getGroupId(), hookInput.cwd)` to track the project in the local store [use-cases/claude-code-plugin/hooks/scripts/session-context.js116-123](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js#L116-L123)

### UserPromptSubmit: `inject-memories.js`

Triggered when a user submits a prompt. It performs semantic retrieval:

- **Validation**: Skips prompts shorter than `MIN_WORDS` (3) using `countWords` which supports CJK character counting by regex matching `[\u4E00-\u9FFF...]`[use-cases/claude-code-plugin/hooks/scripts/inject-memories.js38-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/inject-memories.js#L38-L80)
- **Retrieval**: Calls `searchMemories` with `retrieveMethod: 'hybrid'` and a `topK` of 15 [use-cases/claude-code-plugin/hooks/scripts/inject-memories.js93-96](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/inject-memories.js#L93-L96)
- **Context Injection**: Formats results into a `<relevant-memories>` block via `buildContext()`, sorted by recency (most recent first) to ensure Claude prioritizes the latest information [use-cases/claude-code-plugin/hooks/scripts/inject-memories.js197-210](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/inject-memories.js#L197-L210)

### Stop: `store-memories.js`

Responsible for saving the interaction. It includes a `readTranscriptWithRetry` function with 5 retries and a 100ms delay to ensure the `turn_duration` marker or final lines are written by the host process [use-cases/claude-code-plugin/hooks/scripts/store-memories.js37-74](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L37-L74) It extracts the last turn's text (filtering out `thinking` and `tool_use` blocks) and pushes it to the cloud via `addMemory()`[use-cases/claude-code-plugin/hooks/scripts/store-memories.js167-206](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L167-L206)

### SessionEnd: `session-summary.js`

Handles deferred display and local logging. It uses `extractTranscriptContent` to parse the JSONL transcript, identifying the `firstUserPrompt` and calculating session duration [use-cases/claude-code-plugin/hooks/scripts/session-summary.js25-78](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-summary.js#L25-L78) It appends a record to the local `sessions.jsonl` store via `saveSummary`[use-cases/claude-code-plugin/hooks/scripts/session-summary.js83-90](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-summary.js#L83-L90)

## Local Storage and Data Models

The plugin maintains two local JSONL files for performance and the Memory Hub dashboard.

### `sessions.jsonl`

Stores session metadata. Each entry includes:

- `sessionId`: Unique Claude session ID.
- `groupId`: Project identifier (usually a hash of the CWD).
- `summary`: Truncated first user prompt used as the session title.
- `turnCount`: Total interactions (calculated by counting `turn_duration` markers).
- `startTime` / `endTime`: ISO timestamps extracted from transcript entries.

Sources: [use-cases/claude-code-plugin/hooks/scripts/session-summary.js51-74](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-summary.js#L51-L74)[use-cases/claude-code-plugin/hooks/scripts/session-summary.js177-187](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-summary.js#L177-L187)

### `groups.jsonl`

Tracks which local directories have been used with the plugin to populate the "Projects" view in the Memory Hub. It maps `groupId` to the local `path` (CWD) and stores a `keyId` (SHA-256 hash of the API key) to separate accounts [use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js4-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js#L4-L8)

**Local Store Entry (groups.jsonl)**

| Field | Description |
| --- | --- |
| `keyId` | First 12 chars of hashed API key [use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js7-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js#L7-L8) |
| `groupId` | Unique project hash |
| `name` | Base name of the CWD [use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js#L67-L67) |
| `path` | Full local filesystem path [use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js68](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js#L68-L68) |

Sources: [use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js55-77](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/utils/groups-store.js#L55-L77)[use-cases/claude-code-plugin/hooks/scripts/session-context.js116-123](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js#L116-L123)

## System Architecture: Hook to Cloud Bridge

The following diagram maps the plugin's natural language interaction hooks to the underlying code entities and API calls.

**Hook to API Mapping**

[Flowchart Diagram]

Sources: [use-cases/claude-code-plugin/hooks/scripts/session-context.js31-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-context.js#L31-L33)[use-cases/claude-code-plugin/hooks/scripts/inject-memories.js18-19](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/inject-memories.js#L18-L19)[use-cases/claude-code-plugin/hooks/scripts/store-memories.js7-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/store-memories.js#L7-L8)[use-cases/claude-code-plugin/hooks/scripts/session-summary.js12-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/claude-code-plugin/hooks/scripts/session-summary.js#L12-L18)