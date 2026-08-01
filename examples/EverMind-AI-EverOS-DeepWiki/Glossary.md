# Glossary
Relevant source files
- [README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1)
- [methods/evermemos/demo/utils/simple_memory_manager.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py)
- [methods/evermemos/env.template](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template)
- [methods/evermemos/src/agentic_layer/get_mem_service.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py)
- [methods/evermemos/src/agentic_layer/search_mem_service.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py)
- [methods/evermemos/src/api_specs/memory_types.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py)
- [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py)
- [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py)
- [methods/evermemos/tests/test_agent_memcell_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_memcell_extractor.py)
- [methods/evermemos/tests/test_profile_memory.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py)
- [use-cases/openher/.env.example](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/.env.example)
- [use-cases/openher/README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/README.md?plain=1)
- [use-cases/openher/demo/evermemos_demo.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/demo/evermemos_demo.py)
- [use-cases/openher/integration/context_features.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py)
- [use-cases/openher/integration/evermemos_mixin.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py)
- [use-cases/openher/integration/memory_types.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/memory_types.py)

This page provides technical definitions and code-level references for the core concepts, data entities, and domain-specific terminology used in EverMemOS and the broader EverOS repository.

## Core Data Entities

The following entities form the backbone of the memory representation in EverMemOS, including specialized entities for agent-specific memory and self-evolution.

### MemCell

The **MemCell** (Memory Cell) is the fundamental unit of storage for raw ingested data. It represents a "segment" of a conversation or stream that has been bounded by logical topic shifts or hard limits.

- **Implementation:** Defined as a business object in `api_specs.memory_types.MemCell`[methods/evermemos/src/api_specs/memory_types.py133-164](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L133-L164) and used in persistence logic via `infra_layer.adapters.out.persistence.document.memory.memcell.MemCell`.
- **Data Flow:** Raw messages are accumulated until a boundary is detected [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py100-112](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L100-L112) Once a boundary is hit, a `MemCell` is persisted to MongoDB.

### Episode (Episodic Memory)

A narrative summary of a `MemCell`. It transforms raw logs into a human-readable and LLM-friendly story format, capturing the "what happened" of a specific interaction segment.

- **Implementation:**`api_specs.memory_types.EpisodeMemory`[methods/evermemos/src/api_specs/memory_types.py23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L23-L23)
- **Retrieval:** Handled by `SearchMemoryService` using `EpisodicMemoryEsRepository` and `EpisodicMemoryMilvusRepository`[methods/evermemos/src/agentic_layer/search_mem_service.py141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L141-L147)

### AtomicFact

Discrete, high-precision factual units extracted from memory segments. These represent atomic pieces of knowledge (e.g., "User likes black coffee") that can be independently retrieved.

- **Implementation:**`api_specs.dtos.memory.SearchAtomicFactItem`[methods/evermemos/src/agentic_layer/search_mem_service.py25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L25-L25)
- **Parent Mapping:** Linked to parent memories via `ParentType` (either `MEMCELL` or `EPISODE`) [methods/evermemos/src/api_specs/memory_types.py66-71](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L66-L71)

### AgentCase

A specialized memory type for agents that captures a complete "problem-solving trajectory." It includes the task intent, the approach taken, and the quality of the result.

- **Implementation:**`infra_layer.adapters.out.persistence.document.memory.agent_case.AgentCaseRecord`[methods/evermemos/src/agentic_layer/search_mem_service.py64-66](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L64-L66)
- **Extraction:** Uses `AgentMemCellExtractor` which filters out intermediate tool calls for LLM analysis but retains the full trajectory in the final `MemCell`[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py12-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L12-L40)

### AgentSkill

A distilled, reusable "capability" or "pattern" extracted from multiple `AgentCase` instances. Skills evolve over time through incremental updates and represent the "self-evolution" of the agent.

- **Implementation:**`infra_layer.adapters.out.persistence.document.memory.agent_skill.AgentSkillRecord`[methods/evermemos/src/agentic_layer/search_mem_service.py67-69](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L67-L69)
- **Retrieval:** Searched via `AgentSkillEsRepository` and `AgentSkillMilvusRepository`[methods/evermemos/src/agentic_layer/search_mem_service.py149-152](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L149-L152)

### Profile (User & Group)

Long-term representations of users or groups containing `ExplicitInfo` (facts like name, birthday) and `ImplicitTraits` (behavioral patterns like "prefers concise answers").

- **Implementation:**`api_specs.memory_types.ProfileMemory`[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py27](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L27-L27)
- **ID Mapping:** Uses a short-ID mapper (e.g., `ep1`, `ep2`) to reduce token consumption during LLM profile updates [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py36-38](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L36-L38)

**Sources:**[methods/evermemos/src/api_specs/memory_types.py23-164](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L23-L164)[methods/evermemos/src/agentic_layer/search_mem_service.py25-152](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L25-L152)[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py12-112](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L12-L112)[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py27-38](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L27-L38)

---

## Memory Pipeline Concepts

### Agent Boundary Detection

The logic for determining when an agent's task-solving session is complete. Standard conversation splitting might break in the middle of a tool-call sequence.

- **Guard Logic:** The `AgentMemCellExtractor` skips boundary detection if the last message is an intermediate step (e.g., `tool_call` or `tool` response) [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py140-150](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L140-L150)
- **Intermediate Step:** Defined as any message with `role="tool"` or `role="assistant"` containing `tool_calls`[methods/evermemos/src/api_specs/memory_types.py117-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L117-L130)

### MemScene

A clustering concept where related `MemCells` or `AgentCases` are grouped based on semantic similarity and time-gaps to form a coherent "scene" for high-level reasoning and profile extraction.

### Hybrid Retrieval & Reranking

A multi-stage process to find the most relevant memories using both keyword and vector search.

- **Vectorization:** Converting text to embeddings using `HybridVectorizeService`[methods/evermemos/env.template60-101](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L60-L101)
- **Reranking:** Using cross-encoders (e.g., `Qwen3-Reranker-4B`) via `HybridRerankService` to score the relevance of retrieved candidates against the query [methods/evermemos/env.template105-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L105-L140)

**Sources:**[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py140-150](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L140-L150)[methods/evermemos/src/api_specs/memory_types.py117-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L117-L130)[methods/evermemos/env.template60-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L60-L140)

---

## Technical Architecture Diagrams

### Agent Memory Extraction Flow

This diagram bridges the agent conversation space to the specific code entities that handle trajectory-aware extraction.

[Flowchart Diagram]

**Sources:**[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py12-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L12-L40)[methods/evermemos/src/api_specs/memory_types.py117-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L117-L130)[methods/evermemos/src/agentic_layer/search_mem_service.py156-157](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L156-L157)

### Multi-Modal Search Routing

This diagram shows how the `SearchMemoryService` routes queries across different memory types and storage backends using different retrieval methods.

[Flowchart Diagram]

**Sources:**[methods/evermemos/src/agentic_layer/search_mem_service.py131-160](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L131-L160)[methods/evermemos/src/agentic_layer/search_mem_service.py141-152](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L141-L152)

---

## Abbreviations and Domain Terms

| Term | Definition | Code Reference |
| --- | --- | --- |
| **RawDataType** | Enum distinguishing between standard `CONVERSATION` and tool-aware `AGENTCONVERSATION`. | `api_specs.memory_types.RawDataType`[methods/evermemos/src/api_specs/memory_types.py26-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L26-L31) |
| **ScenarioType** | Distinguishes between `SOLO` (1 user) and `TEAM` (multi-user) interaction modes. | `api_specs.memory_types.ScenarioType`[methods/evermemos/src/api_specs/memory_types.py14-19](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L14-L19) |
| **StatusResult** | Object indicating the outcome of a memorization attempt (e.g., `should_wait=True` for more context). | `memory_layer.memcell_extractor.base_memcell_extractor.StatusResult`[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py124](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L124-L124) |
| **RawData** | A generic container for ingested content before it is processed into a `MemCell`. | `api_specs.dtos.RawData`[methods/evermemos/tests/test_agent_memcell_extractor.py22](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_memcell_extractor.py#L22-L22) |
| **DI** | Dependency Injection. The system uses a custom bean registry (`@service`, `get_bean`) for decoupled service management. | `core.di`[methods/evermemos/src/agentic_layer/search_mem_service.py24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L24-L24) |
| **OXM** | Object-X-Mapping. The abstraction layer for multi-database persistence (MongoDB, ES, Milvus). | `core.oxm`[methods/evermemos/src/agentic_layer/search_mem_service.py104](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L104-L104) |
| **SimpleMemoryManager** | A high-level Python client wrapper that simplifies the HTTP API for demo and testing purposes. | `demo.utils.simple_memory_manager.SimpleMemoryManager`[methods/evermemos/demo/utils/simple_memory_manager.py67-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L67-L76) |

**Sources:**[methods/evermemos/src/api_specs/memory_types.py14-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L14-L31)[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py124](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L124-L124)[methods/evermemos/src/agentic_layer/search_mem_service.py24-104](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L24-L104)[methods/evermemos/demo/utils/simple_memory_manager.py67-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L67-L76)