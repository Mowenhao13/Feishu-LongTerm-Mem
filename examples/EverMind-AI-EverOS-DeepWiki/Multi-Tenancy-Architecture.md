# Multi-Tenancy Architecture
Relevant source files
- [methods/evermemos/docs/advanced/METADATA_CONTROL.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/METADATA_CONTROL.md?plain=1)
- [methods/evermemos/src/core/oxm/milvus/async_collection.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py)
- [methods/evermemos/src/core/oxm/mongo/mongo_utils.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py)
- [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py)

The Multi-Tenancy Architecture in EverOS provides strict data isolation between different organizations and spaces. It is implemented through a combination of dynamic connection proxies, context-aware database routing, and naming conventions for search indices and vector collections. This ensures that a single deployment can serve multiple independent clients without data leakage.

### Core Concepts and Tenant Context

Tenant isolation relies on the `TenantInfo` and `TenantDetail` models [methods/evermemos/src/core/tenants/tenant_models.py46-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_models.py#L46-L113) These models encapsulate tenant-specific identifiers and storage configurations (e.g., dedicated MongoDB URIs or Milvus settings).

The system manages the "Current Tenant" using `ContextVar`, ensuring that asynchronous tasks maintain their tenant identity throughout the request lifecycle [methods/evermemos/src/core/tenants/tenant_contextvar.py20-22](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_contextvar.py#L20-L22)

- **`TenantInfo`**: The primary data model containing `tenant_id` and `tenant_detail`[methods/evermemos/src/core/tenants/tenant_models.py96-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_models.py#L96-L113)
- **`tenant_info_patch`**: A runtime cache within the `TenantInfo` object used to store computed values like active database names or connection aliases to avoid redundant overhead [methods/evermemos/src/core/tenants/tenant_models.py113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_models.py#L113-L113)
- **Tenant Context**: Managed via `set_current_tenant` and `get_current_tenant`, which interface with the global `current_tenant_contextvar`[methods/evermemos/src/core/tenants/tenant_contextvar.py25-92](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_contextvar.py#L25-L92)

### Request Identification (Headers)

Tenants are identified in incoming HTTP requests via specific headers. The system typically expects:

- `X-Organization-Id`: Identifies the high-level organization.
- `X-Space-Id`: Identifies the specific workspace or environment within an organization.

These are processed by the `RequestTenantProvider` and validated using the `@require_tenant` decorator [methods/evermemos/src/core/interface/decorator/require_tenant.py16-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/interface/decorator/require_tenant.py#L16-L48) If a request lacks a tenant context and the system is not in single-tenant mode, it raises an `HTTPException` with status code 400 [methods/evermemos/src/core/interface/decorator/require_tenant.py42-43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/interface/decorator/require_tenant.py#L42-L43)

**Diagram: Request to Tenant Context Flow**

[Flowchart Diagram]

Sources: [methods/evermemos/src/core/tenants/tenant_contextvar.py20-92](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_contextvar.py#L20-L92)[methods/evermemos/src/core/interface/decorator/require_tenant.py16-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/interface/decorator/require_tenant.py#L16-L48)[methods/evermemos/src/core/tenants/tenant_models.py96-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_models.py#L96-L113)

---

### Database Isolation Implementation

EverOS implements isolation across three primary storage backends: MongoDB, Elasticsearch, and Milvus.

#### 1. MongoDB Isolation

Isolation is achieved through `TenantAwareMongoClient` and `TenantAwareDatabase` proxies. These proxies intercept database calls and dynamically route them based on the tenant's `storage_info`[methods/evermemos/src/core/tenants/tenantize/oxm/mongo/tenant_aware_mongo_client.py15-102](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/mongo/tenant_aware_mongo_client.py#L15-L102)

- **Database Naming**: If a specific database is not provided in the tenant config, the system generates one using the `generate_tenant_database_name` utility [methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py19-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py#L19-L100)
- **Client Reuse**: Clients are cached using a key generated from connection parameters (host, port, user) via `get_mongo_client_cache_key` to ensure that tenants sharing the same infrastructure reuse the same connection pool [methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py103-132](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py#L103-L132)
- **Repository Pattern**: Repositories like `AgentSkillRawRepository` inherit from `BaseRepository`, which utilizes these proxies to ensure all `find`, `insert`, and `update` operations are scoped to the correct tenant [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py24-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L24-L33)

#### 2. Elasticsearch Isolation

Elasticsearch isolation is managed by the `TenantAwareAsyncDocument` class [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py29-55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L29-L55)

- **Dynamic Indexing**: It overrides `_get_connection` and `_get_using` to return a tenant-specific connection alias [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py64-98](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L64-L98)
- **Alias/Index Prefixing**: Index names are dynamically computed using `get_tenant_aware_index_name`, which applies tenant-specific prefixes to standard index names [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py20-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L20-L21)
- **Connection Registration**: Upon first access, `_ensure_connection_registered` checks if the tenant's connection alias exists and registers it if necessary using configuration from `get_tenant_es_config`[methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py135-185](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L135-L185)

#### 3. Milvus Isolation

Milvus uses a collection suffix/alias mechanism implemented in `TenantAwareCollection` and `TenantAwareCollectionWithSuffix`[methods/evermemos/src/core/tenants/tenantize/oxm/milvus/tenant_aware_collection.py18-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/milvus/tenant_aware_collection.py#L18-L45)[methods/evermemos/src/core/tenants/tenantize/oxm/milvus/tenant_aware_collection_with_suffix.py15-60](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/milvus/tenant_aware_collection_with_suffix.py#L15-L60)

- **Suffix Logic**: Every collection name is appended with a tenant-specific hash or ID to ensure physical separation of vector data.
- **Async Wrapping**: The `AsyncCollection` class wraps synchronous `pymilvus` calls into asynchronous ones using a dedicated thread pool `_milvus_executor`[methods/evermemos/src/core/oxm/milvus/async_collection.py19-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L19-L21) It ensures that `contextvars` (like tenant context) are preserved across threads via `contextvars.copy_context()` and `ctx.run()`[methods/evermemos/src/core/oxm/milvus/async_collection.py43-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L43-L45)
- **Initialization**: Tenant-specific collections are initialized on-demand or via the `init_tenant_all` utility [methods/evermemos/src/core/tenants/init_tenant_all.py10-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/init_tenant_all.py#L10-L50)

**Diagram: Code Entity Mapping for Multi-Tenancy**

[Class Diagram]

Sources: [methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py29-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/es/tenant_aware_async_document.py#L29-L100)[methods/evermemos/src/core/tenants/tenant_models.py96-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_models.py#L96-L113)[methods/evermemos/src/core/oxm/milvus/async_collection.py51-75](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L51-L75)

---

### Tenant Initialization and Tooling

New tenants must be initialized before they can store data. This process creates the necessary database schemas, Elasticsearch indices, and Milvus collections.

- **`init_tenant_all`**: A comprehensive script that triggers the initialization sequence for all supported backends for a specific tenant [methods/evermemos/src/core/tenants/init_tenant_all.py10-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/init_tenant_all.py#L10-L50)
- **Lifespan Providers**: During application startup, the `MongoDBLifespanProvider` and `MilvusLifespanProvider` handle the initial connection setup for the "default" tenant. They use `get_all_subclasses` to find and initialize all `DocumentBase` and `MilvusCollectionBase` models [methods/evermemos/src/core/lifespan/mongodb_lifespan.py60-75](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/mongodb_lifespan.py#L60-L75)[methods/evermemos/src/core/lifespan/milvus_lifespan.py51-93](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/milvus_lifespan.py#L51-L93)
- **Metadata Control**: Users can control tenant-specific behavior (like `user_details` or `timezone`) via the Settings API. Metadata such as `scene` (e.g., `solo` or `team`) and `user_details` (including `full_name` and `role`) are used to distinguish between speakers and organizations [methods/evermemos/docs/advanced/METADATA_CONTROL.md20-117](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/METADATA_CONTROL.md?plain=1#L20-L117)

### Configuration Modes

The multi-tenancy behavior is governed by `TenantConfig` and the `TenantInfoService` implementation [methods/evermemos/src/core/tenants/tenant_info_provider.py17-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_info_provider.py#L17-L42)

| Mode | Environment Variable | Behavior |
| --- | --- | --- |
| **Non-Tenant Mode** | `TENANT_NON_TENANT_MODE=true` | System behaves as a single-tenant application using "default" connections. |
| **Multi-Tenant Mode** | `TENANT_NON_TENANT_MODE=false` | Requires tenant context for all operations; uses `X-Organization-Id`. |
| **Single-Tenant Mode** | `TENANT_SINGLE_TENANT_ID=xyz` | Automatically activates the specified tenant ID for all requests via `get_current_tenant` fallback logic [methods/evermemos/src/core/tenants/tenant_contextvar.py74-92](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_contextvar.py#L74-L92) |

Sources: [methods/evermemos/src/core/tenants/tenant_contextvar.py74-92](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_contextvar.py#L74-L92)[methods/evermemos/src/core/tenants/tenant_info_provider.py44-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_info_provider.py#L44-L83)[methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py135-180](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py#L135-L180)[methods/evermemos/docs/advanced/METADATA_CONTROL.md150-180](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/METADATA_CONTROL.md?plain=1#L150-L180)[methods/evermemos/src/core/oxm/milvus/async_collection.py14-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py#L14-L48)