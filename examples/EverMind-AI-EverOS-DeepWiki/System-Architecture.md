# System Architecture
Relevant source files
- [README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1)
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)

The EverOS architecture is designed around **Clean Architecture** and **Hexagonal Architecture** principles, ensuring a strict separation between business logic and infrastructure concerns. The system is built as a modular, event-driven framework that supports multi-tenancy and high-performance memory processing across multiple storage backends.

## Layered Architecture Overview

EverOS is organized into several functional layers where dependencies strictly flow downwards or towards the core business logic, enforced by a custom Dependency Injection (DI) system [methods/evermemos/docs/ARCHITECTURE.md13-108](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L13-L108)

### 1. Agentic Layer

The top-level orchestration layer providing a unified memory interface. It handles complex reasoning workflows, such as the two-round agentic retrieval loop, vectorization management, and reranking operations [methods/evermemos/docs/ARCHITECTURE.md17-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L17-L31)

- **Key Components**: `MemoryManager`, `FetchMemoryServiceImpl`, `HybridVectorizeService`, `HybridRerankService`[methods/evermemos/docs/AGENTS.md66-77](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/AGENTS.md?plain=1#L66-L77)

### 2. Memory Layer

Handles the lifecycle of memory extraction. It manages the transition from raw message ingestion to structured episodic, semantic, and agent-specific storage [methods/evermemos/docs/ARCHITECTURE.md33-46](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L33-L46)

- **Key Components**: `MemCellExtractor`, `EpisodeMemoryExtractor`, `ProfileManager`, `ClusterManager`, `AgentCaseExtractor`, `AgentSkillExtractor`[methods/evermemos/docs/AGENTS.md80-90](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/AGENTS.md?plain=1#L80-L90)

### 3. Retrieval Layer

Implements multi-modal retrieval (Semantic, Keyword, Hybrid) and result ranking logic using the Reciprocal Rank Fusion (RRF) algorithm [methods/evermemos/docs/ARCHITECTURE.md48-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L48-L63)

### 4. Business Layer

Contains the core domain logic and API endpoint implementations. It enforces business rules, handles data validation/transformation via DTOs, and manages conversation metadata [methods/evermemos/docs/ARCHITECTURE.md65-78](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L65-L78)

### 5. Infrastructure Layer

The outermost layer containing concrete adapters for external services [methods/evermemos/docs/ARCHITECTURE.md80-94](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L80-L94)

- **Persistence**: MongoDB (Beanie ODM), Milvus (Vector Search), Elasticsearch (BM25) [methods/evermemos/docs/ARCHITECTURE.md153-158](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L153-L158)
- **Communication**: FastAPI (REST), Kafka (MQ), Redis (Caching) [methods/evermemos/docs/ARCHITECTURE.md84-88](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L84-L88)

### 6. Core Framework

The foundation providing cross-cutting concerns like DI, lifecycle management, multi-tenancy, and the event system [methods/evermemos/docs/ARCHITECTURE.md96-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L96-L111)

**Sources**: [methods/evermemos/docs/ARCHITECTURE.md13-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L13-L111)[methods/evermemos/docs/AGENTS.md19-155](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/AGENTS.md?plain=1#L19-L155)[methods/evermemos/docs/OVERVIEW.md56-106](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L56-L106)

---

## Core Architectural Patterns

### Hexagonal & Clean Architecture

The system enforces a strict separation of concerns. Business logic in `src/core` never imports from `src/infra_layer` directly.

- **Data Access Standards**: All storage operations must converge to repository methods in the infra layer. Direct database calls in the business layer are prohibited [methods/evermemos/docs/dev_docs/development_standards.md52-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/development_standards.md?plain=1#L52-L53)
- **Async First**: The entire system operates on a single event loop using `async/await` for all I/O operations [methods/evermemos/docs/dev_docs/development_standards.md22-23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/development_standards.md?plain=1#L22-L23)

### Dependency Injection (DI) Backbone

EverOS uses a custom DI framework to manage component lifecycles and enable implementation swapping (e.g., Mock vs. Real).

- **Decorators**: Components are registered using `@service`, `@repository`, and `@component`[methods/evermemos/docs/dev_docs/development_guide.md54-55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/development_guide.md?plain=1#L54-L55)
- **Mocking**: A global `MOCK_MODE` allows the system to swap real infrastructure for in-memory mocks using `@mock_impl`[methods/evermemos/src/run.py105-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/run.py#L105-L111)[methods/evermemos/docs/dev_docs/development_guide.md133-138](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/dev_docs/development_guide.md?plain=1#L133-L138)

For details, see [Dependency Injection and Addon System](/EverMind-AI/EverOS/2.2-dependency-injection-and-addon-system).

### Event-Driven Backbone

The system uses an internal event publisher to decouple message ingestion from heavy memory extraction tasks.

- **Pattern**: `ApplicationEventPublisher` dispatches `BaseEvent` types to listeners [methods/evermemos/docs/AGENTS.md106](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/AGENTS.md?plain=1#L106-L106)
- **Task Infrastructure**: Background lifecycles are managed via FastAPI lifespan providers and the `LongJob` consumer mode [methods/evermemos/src/run.py53-56](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/run.py#L53-L56)

For details, see [Event System and Async Task Infrastructure](/EverMind-AI/EverOS/2.4-event-system-and-async-task-infrastructure).

---

## Technical Mapping: Space to Code

The following diagrams bridge the gap between high-level architectural concepts and the actual code entities within the EverOS repository.

### Application Lifecycle and Entry Points

This diagram shows how the `run.py` entrypoint initializes the system, starting from environment loading to the FastAPI server.

[Flowchart Diagram]

**Sources**: [methods/evermemos/src/run.py65-161](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/run.py#L65-L161)[methods/evermemos/src/application_startup.py127-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/application_startup.py#L127-L130)[methods/evermemos/src/core/oxm/mongo/migration/manager.py133-135](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/migration/manager.py#L133-L135)

### Multi-Tenant Persistence Layer

This diagram illustrates how business repositories interact with tenant-aware infrastructure proxies to ensure data isolation.

[Flowchart Diagram]

**Sources**: [methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py54-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py#L54-L63)[methods/evermemos/src/core/lifespan/mongodb_lifespan.py59-75](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/mongodb_lifespan.py#L59-L75)[methods/evermemos/src/core/tenants/tenantize/oxm/milvus/tenant_aware_collection.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/milvus/tenant_aware_collection.py)

---

## Detailed Architectural Components

### Application Bootstrap and Server Startup

The startup sequence is orchestrated by `LifespanProvider` components. These providers handle the ordered initialization of MongoDB (via Beanie ODM), Milvus collections, and Elasticsearch indices [methods/evermemos/src/core/lifespan/mongodb_lifespan.py22-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/mongodb_lifespan.py#L22-L33)
For details, see [Application Bootstrap and Server Startup](/EverMind-AI/EverOS/2.1-application-bootstrap-and-server-startup).

### Multi-Tenancy Architecture

EverOS implements isolation at the database level. MongoDB uses separate databases per tenant [methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py54](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py#L54-L54) while Milvus uses collection-name suffixing. The `TenantAware` proxies intercept calls and inject the `tenant_id` from the `TenantContext`.
For details, see [Multi-Tenancy Architecture](/EverMind-AI/EverOS/2.3-multi-tenancy-architecture).

### Persistence and OXM

The system utilizes an Object-X-Mapping (OXM) layer to abstract different storage backends.

- **MongoDB**: Primary document store for `MemCell`, `EpisodicMemory`, `AgentCase`, and profiles using Beanie ODM [methods/evermemos/src/core/lifespan/mongodb_lifespan.py59-74](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/mongodb_lifespan.py#L59-L74)
- **Milvus**: High-performance vector storage for semantic search across all memory types [methods/evermemos/docs/ARCHITECTURE.md157](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L157-L157)
- **Elasticsearch**: Keyword search engine for BM25 retrieval, specifically tuned for multi-lingual content [methods/evermemos/docs/ARCHITECTURE.md156](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1#L156-L156)

**Sources**: [methods/evermemos/src/run.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/run.py)[methods/evermemos/docs/ARCHITECTURE.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/ARCHITECTURE.md?plain=1)[methods/evermemos/docs/AGENTS.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/AGENTS.md?plain=1)[methods/evermemos/src/core/lifespan/mongodb_lifespan.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/mongodb_lifespan.py)[methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenantize/oxm/mongo/config_utils.py)