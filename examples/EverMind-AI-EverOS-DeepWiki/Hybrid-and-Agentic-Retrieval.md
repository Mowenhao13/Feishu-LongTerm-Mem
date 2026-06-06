# Hybrid and Agentic Retrieval
Relevant source files
- [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1)
- [methods/evermemos/src/agentic_layer/search_mem_service.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py)
- [methods/evermemos/tests/test_agent_search_service.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py)

This page provides a technical deep dive into the retrieval architecture of EverOS. The system employs a multi-layered approach combining traditional keyword search, vector similarity, and an LLM-guided "agentic" loop to ensure high precision and recall across diverse memory types.

## Retrieval Architecture Overview

The retrieval system is orchestrated by the `SearchMemoryService`[methods/evermemos/src/agentic_layer/search_mem_service.py132](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L132-L132) and `MemoryManager`[methods/evermemos/src/agentic_layer/memory_manager.py87](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/memory_manager.py#L87-L87) in the agentic layer. It dispatches requests to various backends based on the `RetrieveMethod` specified in the `RetrieveMemRequest`[methods/evermemos/src/api_specs/memory_models.py88](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_models.py#L88-L88)

### Supported Retrieval Methods

| Method | Implementation | Backend |
| --- | --- | --- |
| `KEYWORD` | BM25 Algorithm | Elasticsearch [methods/evermemos/src/agentic_layer/search_mem_service.py9](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L9-L9) |
| `VECTOR` | Vector Similarity | Milvus [methods/evermemos/src/agentic_layer/search_mem_service.py10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L10-L10) |
| `HYBRID` | Keyword + Vector + Rerank | ES + Milvus + Rerank Service [methods/evermemos/src/agentic_layer/search_mem_service.py11](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L11-L11) |
| `RRF` | Reciprocal Rank Fusion | Fusion of keyword + vector results [methods/evermemos/src/agentic_layer/search_mem_service.py12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L12-L12) |
| `AGENTIC` | Two-round LLM loop | Sufficiency check + Query refinement [methods/evermemos/src/agentic_layer/search_mem_service.py13](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L13-L13) |

**Sources:**[methods/evermemos/src/agentic_layer/search_mem_service.py1-14](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L1-L14)[methods/evermemos/src/api_specs/memory_models.py88-89](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_models.py#L88-L89)

---

## Core Retrieval Components

### 1. Vector Similarity

Vector retrieval involves computing the distance between a query embedding and stored document embeddings.

- **Process**: The input query is vectorized via the `vectorize_service` obtained from the bean registry [methods/evermemos/src/agentic_layer/search_mem_service.py182-183](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L182-L183)
- **Metrics**: The system records the duration of the embedding stage using `record_retrieve_stage`[methods/evermemos/src/agentic_layer/search_mem_service.py184-189](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L184-L189)
- **Radius Search**: For agent-specific memories, a distance radius defined by `AGENT_MEMORY_MILVUS_RADIUS` is applied to filter irrelevant results [methods/evermemos/src/agentic_layer/search_mem_service.py105](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L105-L105)

### 2. Keyword Search (BM25)

Keyword search utilizes Elasticsearch's BM25 implementation, which is effective for exact term matching.

- **Tokenization**: For Chinese content, the system uses `jieba.cut_for_search` to generate query words [methods/evermemos/src/agentic_layer/search_mem_service.py174](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L174-L174)
- **Stopwords**: Words are filtered via `filter_stopwords` with a minimum length of 2 to improve precision [methods/evermemos/src/agentic_layer/search_mem_service.py175](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L175-L175)

### 3. RRF Fusion and Reranking

When `RetrieveMethod.RRF` or `HYBRID` is selected, the system merges results from different backends.

- **RRF**: Fuses keyword and vector results based on their ranks [methods/evermemos/src/agentic_layer/search_mem_service.py12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L12-L12)
- **Vector Anchored Fusion**: A utility `vector_anchored_fusion` is used to combine multi-source results while maintaining vector relevance anchors [methods/evermemos/src/agentic_layer/retrieval_utils.py84](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/retrieval_utils.py#L84-L84)
- **Reranking**: The `HybridRerankService` scores the relevance of retrieved memories against the query [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md107-116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L107-L116)
- **Recall Multiplier**: To improve rerank quality, the system often over-recalls by a factor (default 2) using `_compute_recall_limit`[methods/evermemos/src/agentic_layer/search_mem_service.py115-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L115-L128)

**Sources:**[methods/evermemos/src/agentic_layer/search_mem_service.py115-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L115-L128)[methods/evermemos/src/agentic_layer/search_mem_service.py170-175](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L170-L175)[methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md107-116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L107-L116)[methods/evermemos/src/agentic_layer/retrieval_utils.py84](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/retrieval_utils.py#L84-L84)

---

## Agentic Retrieval Loop

Agentic retrieval is an intelligent, multi-round process using an LLM for query expansion and sufficiency validation [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md120-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L120-L130)

### The Two-Round Process

1. **Query Analysis**: LLM analyzes the user query to understand intent [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md126](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L126-L126)
2. **Query Expansion**: Generates 2-3 complementary queries to cover different aspects [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md127](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L127-L127)
3. **Parallel Retrieval**: Executes RRF retrieval for each expanded query in parallel [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L128-L128)
4. **Fusion**: Merges results using multi-path RRF and context integration [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md129-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L129-L130)

### Agentic Logic Flow

The following diagram illustrates the internal logic of the agentic retrieval process.

**Agentic Retrieval Flow**

[Flowchart Diagram]

**Sources:**[methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md120-145](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L120-L145)[methods/evermemos/src/agentic_layer/search_mem_service.py13](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L13-L13)

---

## Code Entity Space: Search Service Components

The `SearchMemoryService` acts as the primary coordinator for retrieval, interacting with multiple specialized repositories across episodic, profile, and agent-specific memory types.

**Search Component Architecture**

[Flowchart Diagram]

**Sources:**[methods/evermemos/src/agentic_layer/search_mem_service.py139-164](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L139-L164)

---

## Routing and Filtering Logic

### Repository Routing

The service initializes both search (ES/Milvus) and raw (MongoDB) repositories to handle the full lifecycle of a search request, from recall to document hydration [methods/evermemos/src/agentic_layer/search_mem_service.py141-157](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L141-L157)

| MemoryType | ES Repository | Milvus Repository | Raw Repository |
| --- | --- | --- | --- |
| `episodic_memory` | `EpisodicMemoryEsRepository` | `EpisodicMemoryMilvusRepository` | `EpisodicMemoryRawRepository` |
| `agent_case` | `AgentCaseEsRepository` | `AgentCaseMilvusRepository` | `AgentCaseRawRepository` |
| `agent_skill` | `AgentSkillEsRepository` | `AgentSkillMilvusRepository` | `AgentSkillRawRepository` |
| `profile` | N/A | `UserProfileMilvusRepository` | N/A |

### Filtering and DSL Parsing

The service handles complex filters (e.g., `user_id`, `group_id`, `time_range`) and parses them into backend-specific DSLs. It uses constants like `MAGIC_ALL`[methods/evermemos/src/core/oxm/constants.py104](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/constants.py#L104-L104) to handle broad searches across all scopes.

### Document Conversion

Search results are converted into DTOs such as `SearchEpisodeItem`, `SearchAgentCaseItem`, and `SearchAgentSkillItem`[methods/evermemos/src/api_specs/dtos/memory.py28-36](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/dtos/memory.py#L28-L36) The conversion logic handles null fields, ensures string ID consistency, and applies score normalization [methods/evermemos/tests/test_agent_search_service.py149-183](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L149-L183)

**Sources:**[methods/evermemos/src/agentic_layer/search_mem_service.py139-164](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L139-L164)[methods/evermemos/tests/test_agent_search_service.py149-183](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L149-L183)[methods/evermemos/src/api_specs/dtos/memory.py28-36](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/dtos/memory.py#L28-L36)[methods/evermemos/src/core/oxm/constants.py104](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/oxm/constants.py#L104-L104)