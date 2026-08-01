# Batch Ingestion with run_memorize.py
Relevant source files
- [methods/evermemos/docs/dev_docs/run_memorize_usage.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1)
- [methods/evermemos/docs/usage/BATCH_OPERATIONS.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1)

The `run_memorize.py` script is a specialized CLI tool designed for high-volume ingestion of historical conversation data into EverMemOS. It processes files adhering to the **ConversationFormat** (formerly GroupChatFormat) specification, ensuring that complex multi-user interactions are correctly mapped to the memory system with appropriate metadata and rate control.

## Overview and CLI Usage

The script serves as a bridge between raw JSON conversation logs and the EverMemOS REST API. It supports two primary modes: a **Validation Mode** for schema checking and an **Ingestion Mode** for sequential API posting.

### Command-Line Arguments

The tool is typically invoked via `uv` through the `bootstrap.py` entrypoint to ensure the dependency injection container and environment are correctly initialized [methods/evermemos/docs/dev_docs/run_memorize_usage.md23-27](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L23-L27)[methods/evermemos/docs/usage/BATCH_OPERATIONS.md50-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L50-L53)

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `--input` | Yes | - | Path to the JSON file in `ConversationFormat`. [methods/evermemos/docs/dev_docs/run_memorize_usage.md53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L53-L53) |
| `--api-url` | No* | `http://localhost:1995/api/v0/memories` | The base endpoint for the memory service. [methods/evermemos/docs/dev_docs/run_memorize_usage.md55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L55-L55) |
| `--scene` | Yes | - | Extraction strategy: `solo` (1:1 assistant) or `team` (multi-user group). [methods/evermemos/docs/dev_docs/run_memorize_usage.md54](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L54-L54) |
| `--validate-only` | No | `False` | If set, the script exits after format validation without sending data. [methods/evermemos/docs/dev_docs/run_memorize_usage.md56](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L56-L56) |

**Example Command:**

```
uv run python src/bootstrap.py src/run_memorize.py \
  --input data/team_chat.json \
  --scene team \
  --api-url http://localhost:1995/api/v0/memories
```

**Sources:**[methods/evermemos/docs/dev_docs/run_memorize_usage.md18-58](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L18-L58)[methods/evermemos/docs/usage/BATCH_OPERATIONS.md46-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L46-L76)

---

## Data Flow and Implementation

The script executes a multi-step pipeline to ensure data integrity and metadata synchronization before message ingestion begins.

### Ingestion Pipeline

1. **Format Validation**: The script reads the input JSON and validates it against the `ConversationFormat` specification. It uses `conversation_converter` (from `infra_layer.adapters.input.api.mapper`) to ensure structural correctness [methods/evermemos/docs/dev_docs/run_memorize_usage.md105-108](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L105-L108)[methods/evermemos/docs/dev_docs/run_memorize_usage.md231](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L231-L231)
2. **Metadata Synchronization (Save Settings)**: Before processing messages, it calls the `settings` interface at `{base_url}/api/v1/settings` to save metadata such as the `scene`, `group_id`, and `user_details`[methods/evermemos/docs/dev_docs/run_memorize_usage.md110-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L110-L113)[methods/evermemos/docs/dev_docs/run_memorize_usage.md165-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L165-L170)
3. **Sequential Posting**: Messages are extracted from the `conversation_list` and posted one-by-one to the primary `memorize` API address [methods/evermemos/docs/dev_docs/run_memorize_usage.md115-119](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L115-L119)
4. **Feedback Loop**: The script monitors API responses, distinguishing between successful ingestion and "Waiting for episode boundary" (which indicates the message was cached but hasn't triggered a memory extraction yet) [methods/evermemos/docs/dev_docs/run_memorize_usage.md171-194](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L171-L194)

### Component Interaction Diagram

This diagram maps the CLI script logic to the internal Code Entities and API endpoints.

**CLI to Server Interaction**

[Flowchart Diagram]

**Sources:**[methods/evermemos/docs/dev_docs/run_memorize_usage.md101-124](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L101-L124)[methods/evermemos/docs/dev_docs/run_memorize_usage.md231-240](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L231-L240)[methods/evermemos/docs/usage/BATCH_OPERATIONS.md32-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L32-L40)

---

## Conversation Meta Synchronization

A critical feature of `run_memorize.py` is the automatic synchronization of `session_meta`. This ensures that group context (timezone, user roles, scene type) is established before the first memory cell is created.

### Metadata Mapping

The script maps fields from the `session_meta` block in the JSON file to the system's internal configuration:

- **Scene Control**: The `--scene` CLI argument (`solo` or `team`) specifies the memory extraction strategy, which may differ from internal descriptors like `work` or `social` found in the data files [methods/evermemos/docs/usage/BATCH_OPERATIONS.md79-84](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L79-L84)
- **User Details**: Participant info (e.g., `full_name`, `role`, `nickname`) is persisted, allowing the system to attribute facts and traits to specific users during profile extraction [methods/evermemos/docs/usage/BATCH_OPERATIONS.md101-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L101-L111)
- **Group Identity**: The `group_id` serves as the primary partition key for the conversation's memory space [methods/evermemos/docs/usage/BATCH_OPERATIONS.md133](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L133-L133)

### Entity Association Diagram

This diagram shows how the batch ingestion script populates the internal memory structures.

**Natural Language Space to Code Entity Mapping**

```

```

**Sources:**[methods/evermemos/docs/usage/BATCH_OPERATIONS.md90-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L90-L128)[methods/evermemos/docs/dev_docs/run_memorize_usage.md66-99](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L66-L99)

---

## Key Features and Processing Logic

### Validation Mode

When run with `--validate-only`, the script performs a dry run that:

- Verifies the JSON file exists and is valid JSON [methods/evermemos/docs/dev_docs/run_memorize_usage.md208-225](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L208-L225)
- Checks the data against the `ConversationFormat` schema [methods/evermemos/docs/dev_docs/run_memorize_usage.md140-141](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L140-L141)
- Outputs statistics including the number of users, message count, and time range [methods/evermemos/docs/dev_docs/run_memorize_usage.md143-149](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L143-L149)

### Batch Processing Statistics

Upon completion, the script provides a summary of the operation:

- **Successfully Processed**: The count of messages sent to the API [methods/evermemos/docs/dev_docs/run_memorize_usage.md198](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L198-L198)
- **Total Saved**: The number of persistent memories (Episodes/Facts) actually generated. This number is often lower than the message count because multiple messages are consolidated into single memory units [methods/evermemos/docs/dev_docs/run_memorize_usage.md199](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L199-L199)

### Core Dependencies

- `httpx`: Used for asynchronous HTTP requests to the memory service [methods/evermemos/docs/dev_docs/run_memorize_usage.md232](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L232-L232)
- `conversation_converter`: Handles the transformation and validation of input data [methods/evermemos/docs/dev_docs/run_memorize_usage.md231](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L231-L231)
- `core.observation.logger`: Provides detailed logging of the ingestion progress [methods/evermemos/docs/dev_docs/run_memorize_usage.md233](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L233-L233)

**Sources:**[methods/evermemos/docs/dev_docs/run_memorize_usage.md101-125](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L101-L125)[methods/evermemos/docs/dev_docs/run_memorize_usage.md229-234](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/run_memorize_usage.md?plain=1#L229-L234)[methods/evermemos/docs/usage/BATCH_OPERATIONS.md21-29](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/BATCH_OPERATIONS.md?plain=1#L21-L29)