# MongoDB Document Models and Repositories
Relevant source files
- [methods/evermemos/src/core/oxm/milvus/async_collection.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/milvus/async_collection.py)
- [methods/evermemos/src/core/oxm/mongo/mongo_utils.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/mongo/mongo_utils.py)
- [methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py)
- [methods/evermemos/tests/test_get_mem_service_e2e.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_get_mem_service_e2e.py)

This page details the persistence layer implementation for MongoDB within EverOS. The system utilizes the **Beanie ODM** (Object Document Mapper) to provide an asynchronous, schema-enforced interface to MongoDB, integrated with a repository pattern for clean data access.

## Base Document Architecture

The persistence layer is built upon a hierarchy of base classes that provide auditing, timezone safety, and soft-delete capabilities across all memory models.

### DocumentBase and AuditBase

`DocumentBase` extends Beanie's `Document` to ensure all `datetime` objects are "aware" (containing timezone information) before persistence [src/core/oxm/mongo/document_base.py21-27](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base.py#L21-L27) It uses a recursive validator `check_datetimes_are_aware` to traverse nested models and convert naive datetimes to the system default timezone [src/core/oxm/mongo/document_base.py144-159](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base.py#L144-L159) It also manages database binding via `Settings.bind_database`[src/core/oxm/mongo/document_base.py28-43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base.py#L28-L43)

`AuditBase` provides automatic lifecycle tracking by adding `created_at` and `updated_at` fields to inheriting documents [src/infra_layer/adapters/out/persistence/document/memory/event_log_record.py17](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/event_log_record.py#L17-L17) It handles the population of these fields during both single and bulk insertions via `prepare_for_insert_many`[src/core/oxm/mongo/document_base.py186-189](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base.py#L186-L189)

### Soft-Delete Implementation

Soft-deletion is managed via `DocumentBaseWithSoftDelete`. This class introduces `deleted_at`, `deleted_by`, and a unique `deleted_id` trick to allow multiple historical records while enforcing uniqueness for active ones [src/core/oxm/mongo/document_base_with_soft_delete.py33-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base_with_soft_delete.py#L33-L42)

- **Instance Methods**: `delete()`, `restore()`, and `hard_delete()`[src/core/oxm/mongo/document_base_with_soft_delete.py46-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base_with_soft_delete.py#L46-L50)
- **Querying**: `find_one()` and `find_many()` automatically filter out deleted records [src/core/oxm/mongo/document_base_with_soft_delete.py52-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base_with_soft_delete.py#L52-L53)
- **Hard Queries**: `hard_find_one()` and `hard_find_many()` include deleted records [src/core/oxm/mongo/document_base_with_soft_delete.py54-55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base_with_soft_delete.py#L54-L55)

**Sources:**[src/core/oxm/mongo/document_base.py21-189](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base.py#L21-L189)[src/core/oxm/mongo/document_base_with_soft_delete.py21-166](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base_with_soft_delete.py#L21-L166)[src/infra_layer/adapters/out/persistence/document/memory/memcell.py72-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/memcell.py#L72-L83)

---

## Memory Document Models

EverOS defines specific models for different stages of the memory pipeline. All models reside in `src/infra_layer/adapters/out/persistence/document/memory/`.

### Core Memory Entities

| Model | Collection | Purpose | Key Fields |
| --- | --- | --- | --- |
| `MemCell` | `memcells` | Raw scene segmentation results; supports soft-delete [src/infra_layer/adapters/out/persistence/document/memory/memcell.py72-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/memcell.py#L72-L83) | `user_id`, `group_id`, `summary`, `original_data` |
| `EpisodicMemory` | `episodic_memories` | Narrative summaries of events [src/infra_layer/adapters/out/persistence/document/memory/episodic_memory.py11-17](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/episodic_memory.py#L11-L17) | `episode`, `participants`, `memcell_event_id_list` |
| `AtomicFactRecord` | `atomic_fact_records` | Atomic facts extracted from episodes [src/infra_layer/adapters/out/persistence/document/memory/atomic_fact_record.py17-22](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/atomic_fact_record.py#L17-L22) | `atomic_fact`, `parent_id`, `parent_type` |
| `ForesightRecord` | `foresight_records` | Temporal predictions and expectations [src/infra_layer/adapters/out/persistence/document/memory/foresight_record.py18-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/foresight_record.py#L18-L24) | `content`, `start_time`, `end_time`, `evidence` |
| `AgentCase` | `agent_cases` | Specific instances of agent task execution [src/infra_layer/adapters/out/persistence/document/memory/agent_case.py18-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/agent_case.py#L18-L24) | `task_intent`, `approach`, `quality_score` |
| `AgentSkillRecord` | `agent_skill_records` | Skills extracted from AgentCase clusters [src/infra_layer/adapters/out/persistence/document/memory/agent_skill.py16-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/agent_skill.py#L16-L18) | `cluster_id`, `name`, `confidence`, `description` |

### Profile and Meta Entities

| Model | Collection | Purpose |
| --- | --- | --- |
| `UserProfile` | `user_profiles` | Long-term traits and explicit info for individuals [src/infra_layer/adapters/out/persistence/document/memory/user_profile.py10-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/user_profile.py#L10-L15) |
| `GroupProfile` | `group_profiles` | Collective behavior, topic status (`TopicInfo`), and roles (`RoleAssignment`) [src/infra_layer/adapters/out/persistence/document/memory/group_profile.py70-75](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/group_profile.py#L70-L75) |
| `ConversationMeta` | `conversation_meta` | Metadata about conversation scenes and participants [src/infra_layer/adapters/out/persistence/document/memory/conversation_meta.py10-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/conversation_meta.py#L10-L15) |
| `CoreMemory` | `core_memories` | Critical, persistent facts that override standard retrieval [src/infra_layer/adapters/out/persistence/document/memory/core_memory.py10-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/core_memory.py#L10-L15) |

**Sources:**[src/infra_layer/adapters/out/persistence/document/memory/memcell.py72-122](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/memcell.py#L72-L122)[src/infra_layer/adapters/out/persistence/document/memory/episodic_memory.py11-56](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/episodic_memory.py#L11-L56)[src/infra_layer/adapters/out/persistence/document/memory/atomic_fact_record.py17-57](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/atomic_fact_record.py#L17-L57)[src/infra_layer/adapters/out/persistence/document/memory/foresight_record.py18-66](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/foresight_record.py#L18-L66)[src/infra_layer/adapters/out/persistence/document/memory/group_profile.py70-120](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/group_profile.py#L70-L120)[src/infra_layer/adapters/out/persistence/document/memory/agent_skill.py16-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/agent_skill.py#L16-L50)[src/infra_layer/adapters/out/persistence/document/memory/agent_case.py18-70](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/agent_case.py#L18-L70)

---

## Repository Pattern and Data Flow

Repositories abstract the Beanie ODM calls, providing a clean interface for the Business Layer.

### Repository Implementation

Repositories use the `@repository` decorator for dependency injection [src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L23-L23) Most inherit from `BaseRepository[T]`, which provides standard CRUD operations like `insert`, `save`, and `find`[src/core/oxm/mongo/base_repository.py15-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/base_repository.py#L15-L30)

Specialized repositories implement domain-specific logic:

- `AgentSkillRawRepository`: Manages skill items with confidence filtering and cluster-scoped retrieval [src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py24-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L24-L30) It provides methods like `get_by_cluster_id` and `update_skill_by_id`[src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py86-114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L86-L114)
- `MemCellRawRepository`: Handles complex deletion logic and scene-based queries [src/infra_layer/adapters/out/persistence/repository/memcell_raw_repository.py27-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/memcell_raw_repository.py#L27-L41)

### Case Study: MemCell Deletion Flow

The `MemCellDeleteService` orchestrates soft-deletion using the `MemCellRawRepository`[src/service/memcell_delete_service.py21-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/service/memcell_delete_service.py#L21-L31) It provides granular methods:

- `delete_by_event_id`: Deletes a single record [src/service/memcell_delete_service.py34-50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/service/memcell_delete_service.py#L34-L50)
- `delete_by_user_id`: Batch deletes all memories for a user [src/service/memcell_delete_service.py84-101](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/service/memcell_delete_service.py#L84-L101)
- `delete_by_combined_criteria`: Uses complex filters (e.g., user + group) to target records [src/service/memcell_delete_service.py185-214](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/service/memcell_delete_service.py#L185-L214)

### Natural Language to Code Entity Mapping: Persistence

The following diagram bridges the gap between high-level memory concepts and the specific repository classes and methods that handle them.

**Memory Storage Mapping**

[Flowchart Diagram]

**Sources:**[src/service/memcell_delete_service.py84-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/service/memcell_delete_service.py#L84-L130)[src/infra_layer/adapters/out/persistence/repository/memcell_raw_repository.py182-202](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/memcell_raw_repository.py#L182-L202)[src/infra_layer/adapters/out/persistence/document/memory/user_profile.py47-58](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/user_profile.py#L47-L58)[src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py86-112](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L86-L112)

---

## Migration Manager

Database schema changes and index updates are managed by the `MigrationManager`.

### Key Functions

- **`create_migration(migration_name)`**: Generates a timestamped Python file in `migrations/mongodb/` using a predefined template [src/core/oxm/mongo/migration/manager.py152-184](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/migration/manager.py#L152-L184)
- **`run_migration()`**: Wraps the `beanie migrate` CLI command. It supports forward and backward (rollback) migrations and can be configured to use transactions [src/core/oxm/mongo/migration/manager.py186-214](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/migration/manager.py#L186-L214)

### Migration Template

The manager provides a template that supports both `iterative_migration` (document-by-document transformation) and `free_fall_migration` (direct collection access for bulk operations like index creation) [src/core/oxm/mongo/migration/manager.py30-77](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/migration/manager.py#L30-L77)

**Sources:**[src/core/oxm/mongo/migration/manager.py24-214](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/migration/manager.py#L24-L214)

---

## MongoDB Utilities

The system provides specialized utilities for handling MongoDB identifiers and queries outside of the Beanie lifecycle.

### ObjectId Management

The `mongo_utils.py` module provides functions for ID generation and conversion:

- `generate_object_id()`: Returns a tuple of (ObjectId, string, datetime) [src/core/oxm/mongo/mongo_utils.py14-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/mongo_utils.py#L14-L32)
- `build_id_filter(ids)`: A critical utility that converts a list of strings into a MongoDB filter. It handles both `ObjectId`-compliant strings and raw legacy string IDs by constructing an `$or` clause if necessary [src/core/oxm/mongo/mongo_utils.py48-86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/mongo_utils.py#L48-L86)

**Sources:**[src/core/oxm/mongo/mongo_utils.py1-87](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/mongo_utils.py#L1-L87)

---

## Technical Interaction Diagram

The following diagram illustrates the relationship between the Beanie ODM base classes, the specific document models, and the repository layer.

**Persistence Class Hierarchy and Interaction**

[Class Diagram]

**Sources:**[src/core/oxm/mongo/document_base.py21-43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base.py#L21-L43)[src/core/oxm/mongo/document_base_with_soft_delete.py21-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/core/oxm/mongo/document_base_with_soft_delete.py#L21-L31)[src/infra_layer/adapters/out/persistence/document/memory/memcell.py72-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/document/memory/memcell.py#L72-L83)[src/infra_layer/adapters/out/persistence/repository/memcell_raw_repository.py27-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/memcell_raw_repository.py#L27-L41)[src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py24-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/src/infra_layer/adapters/out/persistence/repository/agent_skill_raw_repository.py#L24-L33)