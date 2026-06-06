# Testing Infrastructure
Relevant source files
- [methods/evermemos/tests/integration/test_delete_api_integration.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py)
- [methods/evermemos/tests/test_agent_search_service.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py)
- [methods/evermemos/tests/test_embedding_reranker_providers.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py)
- [methods/evermemos/tests/test_get_mem_service_e2e.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_get_mem_service_e2e.py)
- [methods/evermemos/tests/test_llm_switching_e2e.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py)
- [methods/evermemos/tests/test_pickle_size_analysis.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py)
- [methods/evermemos/tests/test_rawdata_json_serialization.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py)
- [methods/evermemos/tests/test_smart_text_parser.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py)

The EverOS testing infrastructure is designed to ensure the reliability of the agentic memory pipeline, spanning from raw message ingestion to complex hybrid retrieval. The system employs a multi-tiered testing strategy including unit tests for data models, repository-level integration tests for persistence backends (MongoDB, Elasticsearch, Milvus), and end-to-end integration tests for AI services like vectorization and reranking.

## Test Organization and Configuration

All tests are located in the `tests/` directory. The project uses `pytest` as the primary test runner, configured to handle asynchronous execution and environment-specific setups.

### Key Test Categories

| Category | Description | Key Files |
| --- | --- | --- |
| **Unit Tests** | Logic verification for utilities, data models, and tokenizers. | `tests/test_rawdata_json_serialization.py`[methods/evermemos/tests/test_rawdata_json_serialization.py1-12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L1-L12)`tests/test_smart_text_parser.py`[methods/evermemos/tests/test_smart_text_parser.py1-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L1-L8) |
| **Repository Tests** | Integration tests for the persistence layer (CRUD and search). | `tests/test_agent_search_service.py`[methods/evermemos/tests/test_agent_search_service.py1-16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L1-L16)`tests/integration/test_delete_api_integration.py`[methods/evermemos/tests/integration/test_delete_api_integration.py1-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L1-L15) |
| **Service Integration** | Validation of external AI providers (vLLM, DeepInfra) and retrieval logic. | `tests/test_embedding_reranker_providers.py`[methods/evermemos/tests/test_embedding_reranker_providers.py1-28](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L1-L28)`tests/test_llm_switching_e2e.py`[methods/evermemos/tests/test_llm_switching_e2e.py1-22](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py#L1-L22) |
| **Performance/Size** | Analysis of serialization overhead and memory usage. | `tests/test_pickle_size_analysis.py`[methods/evermemos/tests/test_pickle_size_analysis.py1-11](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py#L1-L11) |
| **E2E/API** | Full system flow tests against running servers. | `tests/test_get_mem_service_e2e.py`[methods/evermemos/tests/test_get_mem_service_e2e.py1-27](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_get_mem_service_e2e.py#L1-L27) |

### Mocking and Dependency Injection

Tests extensively use `unittest.mock` to isolate business logic from infrastructure. For instance, `SearchMemoryService` tests mock out `EpisodicMemoryEsRepository`, `MilvusRepository`, and `MemoryManager` to focus on search result processing and DTO conversion [methods/evermemos/tests/test_agent_search_service.py107-138](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L107-L138)

**Sources:**`methods/evermemos/tests/test_agent_search_service.py`[methods/evermemos/tests/test_agent_search_service.py1-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L1-L140)`methods/evermemos/tests/test_embedding_reranker_providers.py`[methods/evermemos/tests/test_embedding_reranker_providers.py1-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L1-L30)

## Repository and API Integration Testing

Integration tests verify the "Code Entity Space" interaction with the "Infrastructure Space" (Databases and HTTP Endpoints).

### Delete API Integration

The system includes specialized integration tests for the `POST /api/v1/memories/delete` endpoint. These tests interact with a live MongoDB instance to verify cascading soft-deletes across `v1_memcells`, `v1_episodic_memories`, and `v1_atomic_fact_records`[methods/evermemos/tests/integration/test_delete_api_integration.py49-62](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L49-L62)

**Data Flow: Integration Test Lifecycle**

1. **Setup**: `mongo_client`[methods/evermemos/tests/integration/test_delete_api_integration.py109-116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L109-L116) and `db`[methods/evermemos/tests/integration/test_delete_api_integration.py118-121](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L118-L121) fixtures establish connections using environment variables like `MONGODB_HOST` and `TENANT_SINGLE_TENANT_ID`[methods/evermemos/tests/integration/test_delete_api_integration.py40-47](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L40-L47)
2. **Injection**: Fixture data (MemCells and child records) is inserted directly into MongoDB via `_make_memcell`[methods/evermemos/tests/integration/test_delete_api_integration.py145-172](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L145-L172) and `_make_child`[methods/evermemos/tests/integration/test_delete_api_integration.py175-216](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L175-L216)
3. **Execution**: An `httpx.Client`[methods/evermemos/tests/integration/test_delete_api_integration.py124-129](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L124-L129) sends a request to the local API server defined by `DELETE_URL`[methods/evermemos/tests/integration/test_delete_api_integration.py38](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L38-L38)
4. **Verification**: The test queries MongoDB to ensure `deleted_at` is populated and `deleted_id` is updated [methods/evermemos/tests/integration/test_delete_api_integration.py152-162](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L152-L162)

### Agent Memory Search

Tests for `SearchMemoryService` validate the retrieval of `AgentCaseRecord` and `AgentSkillRecord`[methods/evermemos/tests/test_agent_search_service.py37-88](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L37-L88) They ensure that search results from Elasticsearch or Milvus are correctly transformed into `SearchAgentCaseItem`[methods/evermemos/tests/test_agent_search_service.py146-168](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L146-L168) and `SearchAgentSkillItem`[methods/evermemos/tests/test_agent_search_service.py175-193](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L175-L193) DTOs, including score normalization.

**Sources:**`methods/evermemos/tests/integration/test_delete_api_integration.py`[methods/evermemos/tests/integration/test_delete_api_integration.py1-220](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L1-L220)`methods/evermemos/tests/test_agent_search_service.py`[methods/evermemos/tests/test_agent_search_service.py1-200](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L1-L200)

## AI Service and Retrieval Infrastructure

These tests validate the `VectorizeService`, `RerankService`, and the dynamic switching of LLM providers.

### Vectorization and Rerank Verification

The `test_embedding_reranker_providers.py` file contains functional tests for `Qwen3-Embedding-4B` and `Qwen3-Reranker-4B` models [methods/evermemos/tests/test_embedding_reranker_providers.py9-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L9-L18)

**System Component Interaction**
Title: Vectorize and Rerank Integration Flow

[Flowchart Diagram]

### LLM Dynamic Switching

The `LLMSwitchingE2ETest` class [methods/evermemos/tests/test_llm_switching_e2e.py33-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py#L33-L40) validates the system's ability to switch providers (e.g., OpenRouter to OpenAI) or models within the same provider between messages. It uses the `PUT /api/v1/settings` endpoint to update `llm_custom_setting`[methods/evermemos/tests/test_llm_switching_e2e.py59-64](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py#L59-L64) and verifies that subsequent memory extractions utilize the new configuration [methods/evermemos/tests/test_llm_switching_e2e.py91-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py#L91-L170)

**Sources:**`methods/evermemos/tests/test_embedding_reranker_providers.py`[methods/evermemos/tests/test_embedding_reranker_providers.py31-133](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L31-L133)`methods/evermemos/tests/test_llm_switching_e2e.py`[methods/evermemos/tests/test_llm_switching_e2e.py1-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py#L1-L170)

## Data Processing and Serialization

### RawData Integrity

`RawData`[methods/memory_layer/memcell_extractor/base_memcell_extractor.py8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/memory_layer/memcell_extractor/base_memcell_extractor.py#L8-L8) serialization tests ensure that complex nested structures, including `datetime` objects, survive JSON conversion without precision loss [methods/evermemos/tests/test_rawdata_json_serialization.py45-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L45-L76) This is critical for data types like `Email`[methods/evermemos/tests/test_rawdata_json_serialization.py119-165](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L119-L165) or `LinkDoc`[methods/evermemos/tests/test_rawdata_json_serialization.py166-176](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L166-L176) where timestamps are essential for chronological memory ordering.

**Data Mapping: RawData to JSON**
Title: RawData Serialization Mapping

[Class Diagram]

### Smart Text Parsing

The `SmartTextParser`[methods/common_utils/text_utils.py15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/common_utils/text_utils.py#L15-L15) is tested for its ability to tokenize CJK characters, English words, and punctuation [methods/evermemos/tests/test_smart_text_parser.py84-163](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L84-L163) Tests verify that the parser correctly assigns scores to different token types (e.g., `CJK_CHAR` score vs `ENGLISH_WORD` score) [methods/evermemos/tests/test_smart_text_parser.py59-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L59-L83) which informs the `smart_truncate_text` utility.

### Pickle Size Analysis

The `test_pickle_size_analysis.py` module evaluates the binary size of objects after serialization [methods/evermemos/tests/test_pickle_size_analysis.py1-11](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py#L1-L11) It compares `JSON` vs `Pickle` serialization for basic types and complex objects like `ComplexTestObject`[methods/evermemos/tests/test_pickle_size_analysis.py37-74](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py#L37-L74) which is used to benchmark the `RedisDataProcessor`[methods/evermemos/tests/test_pickle_size_analysis.py140-155](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py#L140-L155)

**Sources:**`methods/evermemos/tests/test_rawdata_json_serialization.py`[methods/evermemos/tests/test_rawdata_json_serialization.py12-168](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L12-L168)`methods/evermemos/tests/test_smart_text_parser.py`[methods/evermemos/tests/test_smart_text_parser.py24-205](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L24-L205)`methods/evermemos/tests/test_pickle_size_analysis.py`[methods/evermemos/tests/test_pickle_size_analysis.py1-200](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py#L1-L200)

## Key Test Files Summary

| File Path | Purpose |
| --- | --- |
| `tests/test_agent_search_service.py` | Validates agent case/skill search and DTO conversion [methods/evermemos/tests/test_agent_search_service.py1-12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L1-L12) |
| `tests/integration/test_delete_api_integration.py` | Integration tests for memory deletion across MongoDB collections [methods/evermemos/tests/integration/test_delete_api_integration.py1-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L1-L8) |
| `tests/test_embedding_reranker_providers.py` | Functional tests for embedding and reranking similarity [methods/evermemos/tests/test_embedding_reranker_providers.py1-6](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L1-L6) |
| `tests/test_llm_switching_e2e.py` | End-to-end verification of dynamic LLM provider switching [methods/evermemos/tests/test_llm_switching_e2e.py1-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py#L1-L8) |
| `tests/test_rawdata_json_serialization.py` | Ensures data integrity for complex RawData structures [methods/evermemos/tests/test_rawdata_json_serialization.py1-4](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L1-L4) |
| `tests/test_smart_text_parser.py` | Validates tokenization and scoring for text truncation [methods/evermemos/tests/test_smart_text_parser.py4-7](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L4-L7) |
| `tests/test_pickle_size_analysis.py` | Benchmarks serialization overhead for the cache layer [methods/evermemos/tests/test_pickle_size_analysis.py1-10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py#L1-L10) |
| `tests/test_get_mem_service_e2e.py` | Tests `POST /api/v1/memories/get` with various filters [methods/evermemos/tests/test_get_mem_service_e2e.py1-27](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_get_mem_service_e2e.py#L1-L27) |

**Sources:**`methods/evermemos/tests/test_agent_search_service.py`[methods/evermemos/tests/test_agent_search_service.py1-16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L1-L16)`methods/evermemos/tests/integration/test_delete_api_integration.py`[methods/evermemos/tests/integration/test_delete_api_integration.py1-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/integration/test_delete_api_integration.py#L1-L15)`methods/evermemos/tests/test_embedding_reranker_providers.py`[methods/evermemos/tests/test_embedding_reranker_providers.py1-28](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L1-L28)`methods/evermemos/tests/test_llm_switching_e2e.py`[methods/evermemos/tests/test_llm_switching_e2e.py1-22](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py#L1-L22)`methods/evermemos/tests/test_rawdata_json_serialization.py`[methods/evermemos/tests/test_rawdata_json_serialization.py1-12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L1-L12)`methods/evermemos/tests/test_smart_text_parser.py`[methods/evermemos/tests/test_smart_text_parser.py1-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L1-L8)`methods/evermemos/tests/test_pickle_size_analysis.py`[methods/evermemos/tests/test_pickle_size_analysis.py1-11](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py#L1-L11)`methods/evermemos/tests/test_get_mem_service_e2e.py`[methods/evermemos/tests/test_get_mem_service_e2e.py1-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_get_mem_service_e2e.py#L1-L30)