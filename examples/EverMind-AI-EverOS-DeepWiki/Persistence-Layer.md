# Persistence Layer
Relevant source files
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)
- [methods/evermemos/src/core/oxm/milvus/async_collection.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py)
- [methods/evermemos/src/core/oxm/mongo/mongo_utils.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py)
- [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py)

The EverOS persistence layer employs a "Three-Database" strategy to manage the diverse storage requirements of a high-performance memory system. This architecture separates concerns between transactional document storage, full-text search, and high-dimensional vector similarity.

## Storage Strategy Overview

EverOS utilizes three distinct storage backends, each optimized for specific memory retrieval patterns:

| Backend | Technology | Role in EverOS | Key Features |
| --- | --- | --- | --- |
| **Document Store** | **MongoDB** | Primary source of truth and metadata. | ACID transactions, Beanie ODM, soft-delete support. |
| **Search Engine** | **Elasticsearch** | BM25 keyword-based retrieval. | Tokenization (jieba for Chinese), dynamic mapping templates. |
| **Vector Store** | **Milvus** | Semantic similarity retrieval. | High-speed ANN search, multi-tenant collection isolation. |

### Data Flow and OXM Layer

The **OXM (Object-X Mapping)** abstraction layer ensures consistent data handling across these backends. It provides utility functions for consistent `ObjectId` generation [methods/evermemos/src/core/oxm/mongo/mongo_utils.py14-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py#L14-L31) and robust filtering that handles both string and `ObjectId` types [methods/evermemos/src/core/oxm/mongo/mongo_utils.py48-62](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py#L48-L62)

#### Persistence Architecture Mapping

The following diagram bridges the Natural Language concepts to the specific Code Entities used in the persistence layer.

"Persistence Architecture Mapping"

[Flowchart Diagram]

Sources: [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py16-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L16-L18)[methods/evermemos/src/core/oxm/mongo/mongo_utils.py48-54](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py#L48-L54)[methods/evermemos/src/core/oxm/milvus/async_collection.py51-56](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L51-L56)[methods/evermemos/docs/OVERVIEW.md68-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L68-L76)

## Core Storage Components

### MongoDB: The Source of Truth

MongoDB serves as the authoritative store for all memory entities. It uses the **Beanie ODM** (built on motor) to provide asynchronous document mapping.

- **Base Classes**: Models inherit from common base classes to ensure consistent ID generation and timezone management [methods/evermemos/src/core/oxm/mongo/mongo_utils.py14-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py#L14-L31)
- **Soft Delete**: Repositories implement soft-delete logic by setting a `deleted_at` timestamp and a unique `deleted_id`[methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py165-172](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L165-L172)
- **Repositories**: CRUD operations are encapsulated in repository classes like `AgentSkillRawRepository`[methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py23-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L23-L24) which handle cluster-scoped queries (e.g., fetching skills by `MemScene` cluster ID) [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py86-101](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L86-L101)

For details, see [MongoDB Document Models and Repositories](/EverMind-AI/EverOS/6.1-mongodb-document-models-and-repositories).

### Elasticsearch: Keyword Retrieval

Elasticsearch provides the BM25 search capability necessary for finding specific terms or entities.

- **Tenant Awareness**: Multi-tenancy is supported by routing queries to specific indices based on organization/space IDs.
- **Mapping**: Uses dynamic templates to handle various content types, including specialized tokenization for Chinese text using `jieba`.
- **Sync Logic**: Memories are synchronized from MongoDB to Elasticsearch to ensure keyword searchability [methods/evermemos/docs/OVERVIEW.md73-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L73-L76)

For details, see [Elasticsearch Index Schemas and Repositories](/EverMind-AI/EverOS/6.2-elasticsearch-index-schemas-and-repositories).

### Milvus: Semantic Retrieval

Milvus stores high-dimensional vectors for semantic similarity search.

- **Async Support**: The system uses an `AsyncCollection` wrapper [methods/evermemos/src/core/oxm/milvus/async_collection.py51-56](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L51-L56) that utilizes a dedicated pre-warmed thread pool (`_milvus_executor`) [methods/evermemos/src/core/oxm/milvus/async_collection.py19-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L19-L25) to execute synchronous `pymilvus` calls without blocking the main event loop [methods/evermemos/src/core/oxm/milvus/async_collection.py39-47](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L39-L47)
- **Core Operations**: Supports asynchronous `insert`, `search`, `query`, and `delete` operations [methods/evermemos/src/core/oxm/milvus/async_collection.py85-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L85-L147)
- **Context Propagation**: Uses `contextvars.copy_context()` to ensure tenant information is preserved across thread boundaries [methods/evermemos/src/core/oxm/milvus/async_collection.py35-43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L35-L43)

For details, see [Milvus Vector Collections and Repositories](/EverMind-AI/EverOS/6.3-milvus-vector-collections-and-repositories).

## Persistence Layer Class Hierarchy

This diagram illustrates the relationship between repository abstractions and the asynchronous storage wrappers.

"Persistence Layer Class Hierarchy"

[Class Diagram]

Sources: [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py23-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L23-L33)[methods/evermemos/src/core/oxm/milvus/async_collection.py51-58](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L51-L58)[methods/evermemos/src/core/oxm/milvus/async_collection.py19-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L19-L21)

## Sub-Pages

- [MongoDB Document Models and Repositories](/EverMind-AI/EverOS/6.1-mongodb-document-models-and-repositories) — Detailed Beanie ODM implementation, soft-delete logic, and the core document models (`MemCell`, `UserProfile`, `AgentSkillRecord`, etc.).
- [Elasticsearch Index Schemas and Repositories](/EverMind-AI/EverOS/6.2-elasticsearch-index-schemas-and-repositories) — Configuration for BM25 search, jieba tokenization, and ES repository patterns.
- [Milvus Vector Collections and Repositories](/EverMind-AI/EverOS/6.3-milvus-vector-collections-and-repositories) — Vector collection schemas, `AsyncCollection` wrapper implementation, and similarity search logic.