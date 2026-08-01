# Request Conversion and API Data Models
Relevant source files
- [methods/evermemos/docs/api_docs/memory_api.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1)
- [methods/evermemos/tests/test_embedding_reranker_providers.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py)
- [methods/evermemos/tests/test_pickle_size_analysis.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py)
- [methods/evermemos/tests/test_rawdata_json_serialization.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py)
- [methods/evermemos/tests/test_smart_text_parser.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py)

This page details the mechanisms by which external HTTP requests are transformed into internal domain objects within EverMemOS. It covers the normalization of raw message data, the deterministic generation of group identifiers for single-user scenarios, and the structured DTOs (Data Transfer Objects) used for memory ingestion, retrieval, and search.

## Overview of Request Normalization

The system acts as a bridge between diverse external input formats and a standardized internal memory representation. This process is primarily handled by the API controllers and a set of specialized conversion utilities.

### Key Components

- **`MemoryController`**: The entry point for RESTful requests, responsible for initial parameter extraction and routing to business services.
- **`request_converter.py`**: A utility module that transforms raw dictionaries and query parameters into validated DTOs like `MemorizeRequest`, `FetchMemRequest`, or `RetrieveMemRequest`.
- **`RawData`**: A container class used to wrap original message content and its associated metadata before it enters the processing pipeline. It includes heuristic logic for serializing and deserializing datetime fields [methods/evermemos/tests/test_rawdata_json_serialization.py8-9](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L8-L9)
- **`GroupChatFormat`**: A specialized specification for batch ingestion that includes session metadata and a list of messages [methods/evermemos/docs/api_docs/memory_api.md243-252](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L243-L252)

## Data Flow: From Request to Domain Object

The following diagram illustrates how a raw HTTP POST request is transformed into internal entities.

**Request Transformation Pipeline**

[Flowchart Diagram]

Sources: [methods/evermemos/docs/api_docs/memory_api.md24-90](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L24-L90)[methods/evermemos/tests/test_rawdata_json_serialization.py18-29](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L18-L29)

## Single-User Group ID Generation

When a `group_id` is not provided in a request, EverMemOS defaults to "single-user mode". To maintain consistency in memory extraction (which requires a group context), the system generates a deterministic `group_id` based on the sender's ID [methods/evermemos/docs/api_docs/memory_api.md58-60](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L58-L60)

The system ensures that all messages from the same sender are routed to the same logical memory container even if the client does not manage group IDs. This enables simpler use cases like persona/profile building for a single user without multi-party context [methods/evermemos/docs/api_docs/memory_api.md62-66](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L62-L66)

## API Data Models (DTOs)

EverMemOS utilizes Pydantic-based DTOs to enforce strict typing and validation at the API boundary.

### Ingestion Models

- **`MemorizeRequest`**: The internal schema for a single message, containing fields like `message_id`, `sender`, `content`, and `create_time`[methods/evermemos/docs/api_docs/memory_api.md30-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L30-L41)
- **`RawData`**: Handles complex content serialization. It includes internal logic to identify and restore timestamp fields (e.g., `create_time`, `update_time`, `sent_timestamp`) for proper ISO format restoration during JSON deserialization [methods/evermemos/tests/test_rawdata_json_serialization.py45-73](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L45-L73)

### Retrieval and Search Models

The system distinguishes between "Fetching" (direct database queries) and "Retrieving" (intelligent/semantic search).

| Model | Purpose | Key Fields |
| --- | --- | --- |
| `FetchMemRequest` | Basic filtered retrieval from MongoDB | `user_id`, `group_id`, `memory_type`, `limit`, `offset` |
| `RetrieveMemRequest` | Advanced search (Vector, Hybrid, Agentic) | `query`, `retrieve_method`, `top_k`, `memory_types`, `radius` |

Sources: [methods/evermemos/docs/api_docs/memory_api.md122-148](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L122-L148)[methods/evermemos/docs/api_docs/memory_api.md184-219](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L184-L219)

## Enums and Constants

The system uses enumerations to standardize behavior across the memory pipeline:

- **`MemoryType`**: Defines the target memory store: `profile`, `episodic_memory`, `foresight`, `atomic_fact`, `agent_case`, or `agent_skill`[methods/evermemos/docs/api_docs/memory_api.md140-148](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L140-L148)
- **`RetrieveMethod`**: Specifies the search algorithm: `keyword`, `vector`, `hybrid`, `rrf`, or `agentic`[methods/evermemos/docs/api_docs/memory_api.md212](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L212-L212)
- **`MAGIC_ALL`**: A special string constant (`"__all__"`) used to bypass filtering and search across all entities.

## Mapping Natural Language to Code Entities

This diagram maps the concepts used in API documentation to the specific implementation classes and logic in the codebase.

**Entity Mapping**

[Flowchart Diagram]

Sources: [methods/evermemos/docs/api_docs/memory_api.md30-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L30-L41)[methods/evermemos/docs/api_docs/memory_api.md147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L147-L147)[methods/evermemos/tests/test_rawdata_json_serialization.py8-29](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L8-L29)

## Batch Ingestion: GroupChatFormat

For large-scale data imports, the system uses the `GroupChatFormat`. This structure maps a list of messages and conversation metadata into the internal ingestion pipeline.

**GroupChatFormat Structure**

[Class Diagram]

Sources: [methods/evermemos/docs/api_docs/memory_api.md30-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L30-L41)[methods/evermemos/tests/test_rawdata_json_serialization.py121-146](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L121-L146)

Sources:

- [methods/evermemos/docs/api_docs/memory_api.md1-220](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/api_docs/memory_api.md?plain=1#L1-L220)
- [methods/evermemos/tests/test_rawdata_json_serialization.py1-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L1-L170)
- [methods/evermemos/tests/test_smart_text_parser.py24-70](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L24-L70)