# REST API Reference
Relevant source files
- [methods/evermemos/docs/api_docs/memory_api.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1)
- [methods/evermemos/docs/dev_docs/api_usage_guide.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/api_usage_guide.md?plain=1)

The EverOS REST API provides a unified interface for managing the lifecycle of conversational memories. It exposes endpoints for high-speed message ingestion, multi-modal memory retrieval (keyword, vector, and agentic), and the management of conversation-specific metadata.

The API is built using FastAPI and follows a controller-based architecture, where the `MemoryController`[methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py74-78](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L74-L78) serves as the primary entry point for all memory operations.

### Authentication and Headers

All API requests require tenant context to ensure data isolation. This is handled via custom HTTP headers that identify the organization and logical space. These headers are essential for the `TenantAwareMongoClient` and other multi-tenant infrastructure to route data correctly.

| Header | Required | Description |
| --- | --- | --- |
| `X-Organization-Id` | Yes | Unique identifier for the organization/tenant. |
| `X-Space-Id` | Yes | Identifier for the specific memory space (e.g., "prod", "testing"). |
| `X-Hash-Key` | No | Optional key for secure ID generation or verification. |

Sources: [methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py82-85](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L82-L85)[methods/evermemos/docs/api_docs/memory_api.md9-11](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L9-L11)

---

### API Surface Overview

The API is primarily versioned under `/api/v0/memories` and `/api/v1/memories`. Below is a high-level summary of the available endpoint groups.

#### Memory Ingestion

- **POST `/api/v0/memories`**: Ingests a single message via `memorize_single_message`[methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py162-182](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L162-L182) If the message triggers a "boundary" (e.g., a natural break in conversation detected by the `ConvMemCellExtractor`), the system extracts structured memories like Episodes, Event Logs, and Foresight.
- **Response Status**: Returns `extracted` if memories were immediately processed, or `accumulated` if the message was queued for future extraction [methods/evermemos/docs/api_docs/memory_api.md95-119](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L95-L119)

For details on ingestion flow and status logic, see [Memory Ingestion and Fetch Endpoints](/EverMind-AI/EverOS/5.1-memory-ingestion-and-fetch-endpoints).

#### Memory Retrieval and Search

- **GET `/api/v0/memories`**: Fetches raw memory records by type (e.g., `episodic_memory`, `atomic_fact`, `foresight`, `profile`) with support for time-range and pagination [methods/evermemos/docs/api_docs/memory_api.md122-148](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L122-L148)
- **POST/GET `/api/v0/memories/search`**: Performs semantic or keyword search. Supports `retrieve_method` options like `keyword`, `vector`, `hybrid`, `rrf`, and `agentic`[methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py341-365](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L341-L365)

For details on search strategies and multi-modal retrieval, see [Memory Search and Conversation Meta Endpoints](/EverMind-AI/EverOS/5.2-memory-search-and-conversation-meta-endpoints).

#### Conversation Metadata and Settings

- **GET/POST/PATCH `/api/v1/memories/conversation-meta`**: Manages the context of a conversation, including the `scene` (e.g., `group_chat` vs `assistant`), `user_details`, and `default_timezone`[methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py441-580](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L441-L580)
- **GET/PUT `/api/v1/settings`**: Accesses and updates global system settings [methods/evermemos/docs/api_docs/memory_api.md18-19](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L18-L19)

For details on metadata management and fallback logic, see [Memory Search and Conversation Meta Endpoints](/EverMind-AI/EverOS/5.2-memory-search-and-conversation-meta-endpoints).

---

### Request Normalization and Data Flow

The API uses a robust conversion layer to transform external JSON payloads into internal Data Transfer Objects (DTOs). This ensures that the business logic in the `MemoryManager`[methods/evermemos/src/agentic_layer/memory_manager.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/memory_manager.py) remains decoupled from HTTP-specific details.

#### API Data Mapping

The following diagram illustrates how external requests are mapped to internal system entities:

**Request Mapping Architecture**

```

```

Sources: [methods/evermemos/src/api_specs/request_converter.py31-35](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/request_converter.py#L31-L35)[methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py74-92](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L74-L92)[methods/evermemos/docs/dev_docs/api_usage_guide.md103-116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/api_usage_guide.md?plain=1#L103-L116)

#### Internal Request Pipeline

When a request enters the `MemoryController`, it is processed through a pipeline of decorators for logging, backgrounding, and metrics before reaching the `MemoryManager`.

**Controller Processing Pipeline**

```

```

Sources: [methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py160-162](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L160-L162)[methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py367-369](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/memory/memory_controller.py#L367-L369)

#### Core Response Convention

All endpoints return a standardized `BaseApiResponse`[methods/evermemos/src/api_specs/dtos/base.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/dtos/base.py) structure, typically including a `status`, `message`, and `result` payload.

```
{
  "status": "ok",
  "message": "Description of the result",
  "result": { 
    "count": 1,
    "status_info": "extracted"
  }
}
```

Sources: [methods/evermemos/docs/api_docs/memory_api.md95-119](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L95-L119)[methods/evermemos/docs/dev_docs/api_usage_guide.md133-148](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/api_usage_guide.md?plain=1#L133-L148)

---

### Child Pages

Detailed documentation for specific API groups can be found in the following sub-pages:

- **[Memory Ingestion and Fetch Endpoints](/EverMind-AI/EverOS/5.1-memory-ingestion-and-fetch-endpoints)**: Deep dive into `POST /memories` and `GET /memories`. Covers `MemorizeRequest` fields, `MemoryRequestLogService`, and soft-delete via `DELETE /memories`.
- **[Memory Search and Conversation Meta Endpoints](/EverMind-AI/EverOS/5.2-memory-search-and-conversation-meta-endpoints)**: Covers search parameters (`top_k`, `radius`, `retrieve_method`) and the `ConversationMetaService` which handles group-level configuration and the `MAGIC_ALL`[methods/evermemos/src/core/oxm/constants.py9](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/constants.py#L9-L9) filter bypass.
- **[Request Conversion and API Data Models](/EverMind-AI/EverOS/5.3-request-conversion-and-api-data-models)**: Technical reference for `request_converter.py` logic, including `generate_single_user_group_id`[methods/evermemos/src/api_specs/request_converter.py24-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/request_converter.py#L24-L41) hashing and the `GroupChatFormat`[methods/evermemos/src/data_format/group_chat/group_chat_format.py138-150](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/data_format/group_chat/group_chat_format.py#L138-L150) schema used for batch imports.