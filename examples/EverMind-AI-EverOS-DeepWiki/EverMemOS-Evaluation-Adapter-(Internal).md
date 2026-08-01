# EverMemOS Evaluation Adapter (Internal)
Relevant source files
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)
- [methods/evermemos/tests/test_llm_switching_e2e.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_llm_switching_e2e.py)

The EverMemOS Evaluation Adapter is a specialized bridge between the EverOS memory engine and the benchmark evaluation framework. It replicates the core production memory pipeline—including boundary detection, extraction, and agentic retrieval—using specialized in-memory storage and offline utilities to facilitate rapid testing against datasets like LoCoMo, LongMemEval, and PersonaMem.

## Overview and Purpose

The adapter is designed to evaluate the effectiveness of the EverMemOS architecture in a controlled, reproducible environment. It decomposes the memory lifecycle into five distinct stages, mirroring the system's internal logic while allowing for experimental configuration (e.g., toggling Foresight extraction or Agentic Retrieval).

### Key Responsibilities

- **Data Normalization**: Converts benchmark-specific formats (e.g., LoCoMo JSON) into the internal `RawData` and `Message` models used by EverOS [methods/evermemos/evaluation/src/adapters/evermemos_adapter.py164-201](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos_adapter.py#L164-L201)
- **Pipeline Simulation**: Executes the full extraction suite including `ConvMemCellExtractor`, `EpisodeMemoryExtractor`, and `EventLogExtractor`[methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py33-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py#L33-L45)
- **Agentic Retrieval**: Implements the multi-round retrieval logic, including sufficiency checks and query refinement, to test the "Agentic Layer" capabilities [methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py1-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py#L1-L8)
- **Offline Storage**: Uses `InMemoryClusterStorage` and `InMemoryProfileStorage` to maintain state across evaluation rounds without requiring a full MongoDB/Milvus infrastructure during the "Add" phase [methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py18-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py#L18-L32)[methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py18-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py#L18-L45)

**Sources:**[methods/evermemos/evaluation/src/adapters/evermemos_adapter.py164-201](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos_adapter.py#L164-L201)[methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py33-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py#L33-L45)[methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py1-8](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py#L1-L8)[methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py18-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py#L18-L32)[methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py18-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py#L18-L45)

---

## Evaluation Pipeline Architecture

The following diagram illustrates the flow from raw dataset ingestion to final scoring, mapping evaluation stages to their corresponding code entities.

### Data Flow: From Dataset to Score

[Flowchart Diagram]

**Sources:**[methods/evermemos/evaluation/src/adapters/evermemos_adapter.py42-58](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos_adapter.py#L42-L58)[methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py1-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py#L1-L45)[methods/evermemos/evaluation/src/adapters/evermemos/stage3_memory_retrivel.py22-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage3_memory_retrivel.py#L22-L25)

---

## Stage 1: MemCell and Memory Extraction

In Stage 1, the adapter processes raw conversation strings into structured `MemCell` objects. It utilizes the production `ConvMemCellExtractor` to perform boundary detection.

### Extraction Workflow

1. **Boundary Detection**: The `ConvMemCellExtractor` uses LLM-based reasoning or hard limits (token/message count) to determine where a memory segment ends.
2. **Parallel Extraction**: Once a `MemCell` is formed, the adapter triggers `EpisodeMemoryExtractor` for narrative summaries and `EventLogExtractor` for atomic fact extraction [methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py170-195](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py#L170-L195)
3. **Clustering & Profiling**: Based on `ExperimentConfig`, the adapter may trigger the `ClusterManager` to group related MemCells and the `ProfileManager` to update user/group traits [methods/evermemos/evaluation/src/adapters/evermemos/config.py16-29](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L16-L29)

**Sources:**[methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py170-200](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage1_memcells_extraction.py#L170-L200)[methods/evermemos/evaluation/src/adapters/evermemos/config.py16-29](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L16-L29)

---

## Stage 2: Index Building

Stage 2 focuses on creating searchable representations of the extracted memories. It builds two types of indices for each conversation to support hybrid retrieval [methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py114-116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py#L114-L116)

### Indexing Components

- **BM25 Index**: Uses `BM25Okapi` to index tokenized text. It prioritizes fields by weighting the "subject" (title) 3x and "summary" 2x compared to the narrative "episode" [methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py52-93](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py#L52-L93)
- **Embedding Index**: Generates vector representations using `VectorizeService`. It processes documents in batches (default size 256) with controlled concurrency to avoid API timeouts [methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py185-190](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py#L185-L190)

**Sources:**[methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py52-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py#L52-L111)[methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py170-190](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage2_index_building.py#L170-L190)

---

## Stage 3: Agentic and Hybrid Retrieval

The retrieval stage supports multiple modes of finding relevant information, controlled by the `retrieval_mode` toggle in `ExperimentConfig`[methods/evermemos/evaluation/src/adapters/evermemos/config.py30-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L30-L33)

### Retrieval Strategies

- **Lightweight**: Fast retrieval using `bm25_only`, `emb_only`, or `hybrid` modes without LLM intervention [methods/evermemos/evaluation/src/adapters/evermemos/config.py41-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L41-L48)
- **Agentic**: A multi-round process using LLM-guided refinement to improve recall [methods/evermemos/evaluation/src/adapters/evermemos/config.py31-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L31-L33)

### Agentic Retrieval Logic

The agentic loop utilizes `agentic_utils.py` to perform:

1. **Sufficiency Check**: Uses `SUFFICIENCY_CHECK_PROMPT` to evaluate if the current Top-K results can answer the user query [methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py172-210](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py#L172-L210)
2. **Query Refinement**: If insufficient, an LLM generates a `MULTI_QUERY_GENERATION_PROMPT` to expand temporal references and identify missing components [methods/evermemos/evaluation/src/adapters/evermemos/prompts/multi_query_prompts.py3-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/prompts/multi_query_prompts.py#L3-L24)
3. **RRF Fusion**: Combines results from BM25 and Vector search using Reciprocal Rank Fusion (RRF) to normalize scores across different search methods [methods/evermemos/evaluation/src/adapters/evermemos/stage3_memory_retrivel.py193-215](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage3_memory_retrivel.py#L193-L215)

### Retrieval Component Mapping

[Flowchart Diagram]

**Sources:**[methods/evermemos/evaluation/src/adapters/evermemos/stage3_memory_retrivel.py193-215](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage3_memory_retrivel.py#L193-L215)[methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py172-210](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/agentic_utils.py#L172-L210)[methods/evermemos/evaluation/src/adapters/evermemos/prompts/multi_query_prompts.py3-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/prompts/multi_query_prompts.py#L3-L24)

---

## Stage 5: Evaluation and Scoring

The final stage uses an "LLM-as-a-Judge" approach to score the generated answers against ground truth (gold) answers.

### Grading Logic

- **locomo_grader**: A specialized function that prompts an LLM to compare a generated answer with a gold answer. It is instructed to be "generous," focusing on whether the answer touches on the same topic or temporal period rather than exact string matching [methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py26-57](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py#L26-L57)
- **Concurrency**: The evaluator processes responses in parallel using `asyncio.gather` with a configurable number of concurrent workers (default 10) [methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py114-157](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py#L114-L157)

**Sources:**[methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py26-71](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py#L26-L71)[methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py110-157](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/stage5_eval.py#L110-L157)

---

## Configuration and Storage

The adapter is highly configurable via `ExperimentConfig` and utilizes in-memory storage for offline execution.

### Key Configuration Parameters

| Parameter | Description | Source |
| --- | --- | --- |
| `use_agentic_retrieval` | Toggles the multi-round LLM loop. | [methods/evermemos/evaluation/src/adapters/evermemos/config.py12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L12-L12) |
| `enable_clustering` | Toggles semantic grouping of MemCells. | [methods/evermemos/evaluation/src/adapters/evermemos/config.py18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L18-L18) |
| `hybrid_rrf_k` | The constant `k` used in Reciprocal Rank Fusion (default 40). | [methods/evermemos/evaluation/src/adapters/evermemos/config.py53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L53-L53) |
| `retrieval_mode` | Switches between `agentic` and `lightweight`. | [methods/evermemos/evaluation/src/adapters/evermemos/config.py33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L33-L33) |

### In-Memory Storage

To support evaluation without a full database stack, the adapter provides:

- **InMemoryClusterStorage**: Maintains `event_id` to `cluster_id` mappings and cluster states [methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py18-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py#L18-L32)
- **InMemoryProfileStorage**: Stores user and group profiles with optional versioning and JSON file persistence [methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py18-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py#L18-L45)

**Sources:**[methods/evermemos/evaluation/src/adapters/evermemos/config.py7-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/config.py#L7-L53)[methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py1-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_cluster_storage.py#L1-L40)[methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py1-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/evaluation/src/adapters/evermemos/tools/in_memory_profile_storage.py#L1-L45)