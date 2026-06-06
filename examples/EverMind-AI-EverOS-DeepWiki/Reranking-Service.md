# Reranking Service
Relevant source files
- [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1)
- [methods/evermemos/tests/test_embedding_reranker_providers.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py)
- [methods/evermemos/tests/test_pickle_size_analysis.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_pickle_size_analysis.py)
- [methods/evermemos/tests/test_rawdata_json_serialization.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py)
- [methods/evermemos/tests/test_smart_text_parser.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py)

The Reranking Service is a critical component of the retrieval pipeline, responsible for re-evaluating and re-ordering memory hits returned by initial keyword or vector searches. It utilizes high-parameter cross-encoders to provide precise relevance scoring, ensuring that the most contextually appropriate memories are presented to the agentic layer.

## HybridRerankService Overview

The `HybridRerankService` implements a dual-strategy approach designed for both cost-efficiency and high availability. It primarily targets a self-hosted `vLLM` instance but can automatically failover to commercial providers like `DeepInfra` if the primary service becomes unavailable.

### Key Characteristics

- **Model**: Standardized on `Qwen3-Reranker-4B` for high-accuracy cross-encoding [methods/evermemos/tests/test_embedding_reranker_providers.py17](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L17-L17)
- **Resilience**: Implements automatic fallback logic with failure tracking to maintain service uptime.
- **Efficiency**: Supports batch processing and concurrent request management via `asyncio.Semaphore`.
- **Observability**: Integrates with Prometheus to track request counts, fallback events, and errors.

### Service Architecture and Data Flow

The following diagram illustrates how the `HybridRerankService` interacts with its providers and the broader system.

**Reranking Service Provider Flow**

[Flowchart Diagram]

Sources: [methods/evermemos/tests/test_embedding_reranker_providers.py5-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L5-L18)

## Implementation Details

### Text Extraction by MemoryType

The reranker does not process raw database objects directly. Instead, it extracts searchable text content from memory "hits" based on their `MemoryType`. This ensures the cross-encoder receives only the narrative or factual data required for scoring. This includes specialized extraction for agent-specific memories.

| Memory Type | Extracted Content Field | Usage in Search |
| --- | --- | --- |
| `EPISODIC_MEMORY` | `episode` | Narrative retrieval [methods/evermemos/tests/test_embedding_reranker_providers.py109](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L109-L109) |
| `AGENT_CASE` | `task_intent` / `approach` | Agent task-solving experience |
| `AGENT_SKILL` | `skill_description` | Tool usage and behavioral patterns |
| `ATOMIC_FACT` | `fact` | Fine-grained knowledge retrieval |

Sources: [methods/evermemos/tests/test_embedding_reranker_providers.py108-112](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L108-L112)[methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md107-116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L107-L116)

### Batch Processing and Concurrency

To handle large volumes of retrieved memories (over-recall), the service implements batching and concurrency limits:

1. **Batching**: Documents are split into chunks to fit model context windows and avoid HTTP timeouts.
2. **Concurrency**: An `asyncio.Semaphore` is used to limit the number of concurrent outgoing HTTP requests to the inference backends, preventing rate-limiting or resource exhaustion.
3. **Integration**: The retrieval system fetches more candidates than requested (top_k) to allow the reranker to find higher-quality matches from a larger pool [methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md107-116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/advanced/RETRIEVAL_STRATEGIES.md?plain=1#L107-L116)

### Prompt and Scoring Logic

The service uses specific instructions to guide the reranker. For example, when checking relevance, an instruction is provided: *"Given a question and a passage, determine if the passage contains information relevant to answering the question."*[methods/evermemos/tests/test_embedding_reranker_providers.py106-107](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L106-L107)

**Natural Language to Code Entity Mapping**

[Flowchart Diagram]

Sources: [methods/evermemos/tests/test_embedding_reranker_providers.py101-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L101-L128)

## Configuration and Fallback Logic

The `HybridRerankService` manages environment-based settings and the runtime state of the fallback mechanism.

### Configuration Parameters

- `RERANK_PROVIDER`: Primary provider, typically set to `vllm`[methods/evermemos/tests/test_embedding_reranker_providers.py15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L15-L15)
- `RERANK_BASE_URL`: The endpoint for the scoring service [methods/evermemos/tests/test_embedding_reranker_providers.py16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L16-L16)
- `RERANK_MODEL`: The specific model identifier, e.g., `Qwen3-Reranker-4B`[methods/evermemos/tests/test_embedding_reranker_providers.py17](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L17-L17)

### Fallback Execution

When the primary service (vLLM) fails or times out, the `HybridRerankService` increments a failure counter. Once a threshold is met, it switches to the `fallback_service` (e.g., DeepInfra) to ensure that memory retrieval does not fail entirely.

## Integration Testing and Correlation

The system includes integration tests to verify that the reranker correctly prioritizes relevant information over noise.

### Test Workflow

1. **Setup**: Configures the `vllm` or `deepinfra` provider via environment variables [methods/evermemos/tests/test_embedding_reranker_providers.py9-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L9-L18)
2. **Execution**: Sends a query (e.g., "苹果" / Apple) along with a mix of relevant ("苹果很好吃") and irrelevant ("汽车很快") documents [methods/evermemos/tests/test_embedding_reranker_providers.py105-112](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L105-L112)
3. **Verification**: The test asserts that the relevance scores produced by the service correctly rank the semantic matches higher than unrelated content [methods/evermemos/tests/test_embedding_reranker_providers.py123-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L123-L128)

### Ranking Correlation Example

| Query | Document | Expected Rank |
| --- | --- | --- |
| "水果" (Fruit) | "香蕉也是水果" (Bananas are also fruit) | 1 [methods/evermemos/tests/test_embedding_reranker_providers.py93-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L93-L95) |
| "水果" (Fruit) | "苹果很好吃" (Apples are delicious) | 2 [methods/evermemos/tests/test_embedding_reranker_providers.py89](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L89-L89) |
| "水果" (Fruit) | "汽车速度很快" (Cars are very fast) | 3 [methods/evermemos/tests/test_embedding_reranker_providers.py91](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L91-L91) |

Sources: [methods/evermemos/tests/test_embedding_reranker_providers.py39-98](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L39-L98)