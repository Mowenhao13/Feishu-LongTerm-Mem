# Elasticsearch Index Schemas and Repositories
Relevant source files
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)
- [methods/evermemos/src/core/oxm/milvus/async_collection.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py)
- [methods/evermemos/src/core/oxm/mongo/mongo_utils.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py)
- [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py)

Elasticsearch (ES) serves as the primary engine for **BM25 keyword-based retrieval** within EverOS. It complements the vector-based search provided by Milvus by offering precise term matching, which is essential for retrieving specific entities, names, or technical terms that semantic embeddings might miss. The system employs a tenant-aware architecture, custom Chinese tokenization via `jieba`, and an Object-XML Mapping (OXM) layer to synchronize data from MongoDB.

## Architecture Overview

The ES persistence layer is built upon `elasticsearch-dsl` but heavily customized to support multi-tenancy and specific memory requirements.

### Core Components

- **`TenantAwareAsyncDocument`**: The base class for all ES models, providing dynamic index and connection routing based on the current tenant context [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py29-55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L29-L55)
- **OXM Layer**: Defines the mapping between application-level memory models and ES document structures via `DocBase` and `AliasSupportDoc`[methods/evermemos/src/core/oxm/es/doc_base.py14-43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/doc_base.py#L14-L43)
- **Converters**: Specialized classes (e.g., `EventLogConverter`, `EpisodicMemoryConverter`) that transform MongoDB records into ES documents, including custom tokenization logic [methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py23-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py#L23-L30)
- **Repositories**: Provide async CRUD and search operations, abstracting the underlying ES client through `BaseRepository`[methods/evermemos/src/core/oxm/es/base_repository.py20-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/base_repository.py#L20-L31)

### Data Flow: MongoDB to Elasticsearch

The synchronization typically follows this path:

1. **Extraction**: A background worker extracts an `Episode`, `Foresight`, or `EventLog` and saves it to MongoDB.
2. **Conversion**: A converter (e.g., `EventLogConverter.from_mongo`) is invoked to transform the MongoDB record [methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py32-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py#L32-L41)
3. **Tokenization**: During conversion, `jieba` is used to segment Chinese text into space-separated tokens stored in `search_content` fields [methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py87-101](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py#L87-L101)
4. **Persistence**: The resulting `AsyncDocument` is saved to a tenant-specific ES index using the `create` or `create_batch` methods in the repository [methods/evermemos/src/core/oxm/es/base_repository.py67-81](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/base_repository.py#L67-L81)

Sources: [methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py23-78](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py#L23-L78)[methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py29-55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L29-L55)[methods/evermemos/src/core/oxm/es/base_repository.py177-213](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/base_repository.py#L177-L213)

## Tenant Awareness and Index Isolation

EverOS implements strict tenant isolation at the Elasticsearch level. Each tenant can have its own ES connection or share a cluster while using prefixed indices.

### Connection and Index Routing

The `TenantAwareAsyncDocument` overrides standard `elasticsearch-dsl` methods to inject tenant context:

- **`_get_connection`**: Dynamically retrieves the ES client based on the current tenant's configuration [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py80-97](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L80-L97)
- **`_get_tenant_aware_using`**: Computes a unique connection alias for the tenant, caching it to avoid redundant lookups [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py100-132](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L100-L132)
- **Index Naming**: Indices are generated with tenant-specific prefixes to prevent cross-tenant data leakage [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py38-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L38-L40)

### Document Class Hierarchy

| Class | Role |
| --- | --- |
| `DocBase` | Extends `AsyncDocument` with index name generation utilities [methods/evermemos/src/core/oxm/es/doc_base.py14-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/doc_base.py#L14-L40) |
| `AliasSupportDoc` | Adds timezone-aware date field processing and `meta.id` synchronization [methods/evermemos/src/core/oxm/es/doc_base.py42-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/doc_base.py#L42-L170) |
| `TenantAwareAsyncDocument` | Core multi-tenancy logic for connection and index routing [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py29-55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L29-L55) |

Sources: [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py100-132](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L100-L132)[methods/evermemos/src/core/oxm/es/doc_base.py42-110](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/doc_base.py#L42-L110)

## Index Schemas

EverOS maintains primary indices for memory retrieval, such as episodic memory, foresight, and event logs. Each uses a `search_content` field designed for BM25 optimization.

### 1. Episodic Memory Index (`episodic-memory`)

Stores narrative summaries of conversations.

- **Key Fields**: `event_id` (PK), `user_id`, `timestamp`, `title`, `episode`, `search_content`[methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py57-86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py#L57-L86)
- **Tokenization**: `title` and `episode` use the `whitespace_lowercase_trim_stop_analyzer`[methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py65-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py#L65-L80)
- **BM25 Core**: `search_content` is a multi-value field containing pre-tokenized keywords with an `original` sub-field for exact matches [methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py84-105](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py#L84-L105)

### 2. Event Log Index (`event-log`)

Stores atomic facts and discrete events.

- **Key Fields**: `id` (PK), `timestamp`, `atomic_fact`, `search_content`[methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/event_log.py28-55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/event_log.py#L28-L55)
- **Structure**: Uses `lower_keyword_analyzer` for exact matching in `search_content.original`[methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/event_log.py44-47](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/event_log.py#L44-L47)

### 3. Agent Memory Indices

EverOS also supports specialized indices for agent-specific data:

- **Agent Case Index**: Stores specific agent interaction cases for keyword search [methods/evermemos/src/agentic_layer/search_mem_service.py47-49](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L47-L49)
- **Agent Skill Index**: Stores extracted agent skills, managed via `AgentSkillEsRepository`[methods/evermemos/src/agentic_layer/search_mem_service.py50-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L50-L52)

Sources: [methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py14-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/episodic_memory.py#L14-L50)[methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/event_log.py14-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/memory/event_log.py#L14-L21)[methods/evermemos/src/agentic_layer/search_mem_service.py47-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L47-L52)

## Tokenization and Converters

Since Elasticsearch's standard analyzer does not handle Chinese word boundaries well, EverOS performs **client-side tokenization** during the conversion process using the `jieba` library.

### Jieba Integration

The `SearchMemoryService` and various converters use `jieba.cut_for_search` to segment text before it reaches ES [methods/evermemos/src/agentic_layer/search_mem_service.py171-175](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L171-L175)

- **Stopword Filtering**: Words are filtered using `filter_stopwords` with a minimum length of 2 to remove noise [methods/evermemos/src/agentic_layer/search_mem_service.py175](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L175-L175)
- **Space Separation**: The resulting tokens are joined by spaces or stored as a list in the `search_content` field, allowing ES to treat them as individual terms.

### Dynamic Mapping Templates

To simplify schema management, `DYNAMIC_TEMPLATES` define type inference based on field suffixes:

- `*_ts`, `*_date` → `date`[methods/evermemos/src/core/oxm/es/mapping_templates.py19-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/mapping_templates.py#L19-L34)
- `*_desc` → `text` (tokenized) [methods/evermemos/src/core/oxm/es/mapping_templates.py45-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/mapping_templates.py#L45-L50)
- `*_id` → `keyword` (exact match) [methods/evermemos/src/core/oxm/es/mapping_templates.py77-82](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/mapping_templates.py#L77-L82)

Sources: [methods/evermemos/src/agentic_layer/search_mem_service.py171-176](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L171-L176)[methods/evermemos/src/core/oxm/es/mapping_templates.py18-90](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/mapping_templates.py#L18-L90)

## Search Repository Implementation

The `BaseRepository` provides a generic interface for ES operations, while specific implementations handle complex queries.

### Retrieval Logic

The retrieval system uses a `search` method that accepts a raw ES query dict [methods/evermemos/src/core/oxm/es/base_repository.py217-220](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/base_repository.py#L217-L220)

- **BM25 Search**: Typically targets the `search_content` field using a `match` or `multi_match` query.
- **Batch Operations**: Supports `create_batch` using `elasticsearch.helpers.async_bulk` for high-throughput synchronization [methods/evermemos/src/core/oxm/es/base_repository.py177-213](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/base_repository.py#L177-L213)

### System Data Flow Diagram

Title: "Elasticsearch Retrieval and Sync Flow"

[Flowchart Diagram]

Sources: [methods/evermemos/src/agentic_layer/search_mem_service.py171-175](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L171-L175)[methods/evermemos/src/core/oxm/es/base_repository.py20-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/base_repository.py#L20-L31)[methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py32-78](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/search/elasticsearch/converter/event_log_converter.py#L32-L78)

## Migration and Utilities

EverOS provides tools for index maintenance, rebuilding, and data clearing.

### Index Rebuilding

The `rebuild_index` utility allows for zero-downtime schema updates by:

1. Finding the document class by index name [methods/evermemos/src/core/oxm/es/migration/utils.py20-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/migration/utils.py#L20-L34)
2. Creating a new index with a timestamped name via `document_class.dest()`[methods/evermemos/src/core/oxm/es/migration/utils.py114-129](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/migration/utils.py#L114-L129)
3. Using the ES `reindex` API to migrate data [methods/evermemos/src/core/oxm/es/migration/utils.py132-137](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/migration/utils.py#L132-L137)
4. Updating aliases to point to the new index [methods/evermemos/src/core/oxm/es/migration/utils.py143](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/migration/utils.py#L143-L143)

### Migration Entity Mapping

Title: "ES Migration and Document Mapping"

[Flowchart Diagram]

Sources: [methods/evermemos/src/core/oxm/es/migration/utils.py78-145](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/migration/utils.py#L78-L145)[methods/evermemos/src/core/oxm/es/doc_base.py171-180](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/doc_base.py#L171-L180)[methods/evermemos/src/core/oxm/es/base_repository.py33-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/es/base_repository.py#L33-L41)