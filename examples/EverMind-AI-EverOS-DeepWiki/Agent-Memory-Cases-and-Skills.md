# Agent Memory: Cases and Skills
Relevant source files
- [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py)
- [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py)
- [methods/evermemos/tests/test_agent_search_service.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py)
- [methods/evermemos/tests/test_agent_skill_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_skill_extractor.py)

The Agent Memory pipeline enables self-evolving agents by transforming raw tool-calling trajectories into structured experience records (**AgentCase**) and distilled, reusable procedural knowledge (**AgentSkill**). Unlike standard conversation memory, this pipeline is "tool-aware," ensuring that intermediate reasoning steps and tool execution results are preserved for learning but filtered for clean retrieval.

## 1. Agent Memory Pipeline Overview

The pipeline operates in two primary stages: **Experience Extraction** (Case) and **Skill Distillation** (Skill).

### 1.1 Data Flow Architecture

The following diagram illustrates how raw agent messages are processed into long-term structured memory, bridging raw logs to specialized repositories.

**Agent Memory Extraction Flow**

[Flowchart Diagram]

**Sources:**[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py71-94](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L71-L94)[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py75-86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L75-L86)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py54-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L54-L63)

---

## 2. AgentMemCellExtractor: Tool-Aware Segmentation

The `AgentMemCellExtractor` extends the standard conversation extractor to handle the complexities of agent trajectories, specifically `tool_calls` and `tool` responses.

### 2.1 Key Implementation Details

- **Intermediate Step Guard**: Extraction is skipped if the last message is an intermediate step (role=`tool` or role=`assistant` with `tool_calls`), preventing splits in the middle of a tool execution loop [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py140-150](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L140-L150)
- **Safe Split Logic**: Force-splitting only occurs after a final assistant response (no `tool_calls`) to ensure logical task boundaries are respected [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py159-173](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L159-L173)
- **Index Remapping**: The LLM detects boundaries on a "clean" version of the chat (user/assistant only), which are then remapped back to the original message indices to include the full tool-calling trajectory in the resulting `MemCell`[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py16-40](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L16-L40)

**Sources:**[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py100-152](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L100-L152)[methods/evermemos/src/api_specs/memory_types.py117-129](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L117-L129)

---

## 3. AgentCase: Experience Extraction

The `AgentCaseExtractor` synthesizes a `MemCell` into a single experience record. An `AgentCase` represents a specific instance of problem-solving.

### 3.1 Extraction Pipeline

1. **Pre-compression**: If tool content exceeds `PRE_COMPRESS_CHUNK_SIZE` (default 100k tokens), the extractor uses an LLM to compress tool inputs/outputs into structured summaries [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py50-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L50-L53)
2. **Heuristic Trimming**: Oversized individual messages are truncated to specific token limits (e.g., `MAX_TOOL_OUTPUT_TOKENS` = 1000, `MAX_TOOL_ARGS_TOKENS` = 800) before LLM processing [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py59-62](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L59-L62)
3. **LLM Extraction**: The LLM extracts:

- `task_intent`: The high-level goal (truncated to `MAX_TASK_INTENT_TOKENS`).
- `approach`: The step-by-step logic used.
- `quality_score`: A metric (0.0-1.0) indicating success [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py8-10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L8-L10)
4. **Embedding**: An embedding is computed specifically on the `task_intent` to facilitate semantic retrieval [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py85-86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L85-L86)

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py75-117](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L75-L117)[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py173-183](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L173-L183)[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py64-65](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L64-L65)

---

## 4. AgentSkill: Incremental Skill Distillation

`AgentSkill` represents distilled procedural knowledge. While cases are specific, skills are generalized across multiple similar cases within a `MemScene` (cluster).

### 4.1 Incremental Operations

The `AgentSkillExtractor` does not rebuild the skill library from scratch. Instead, it performs incremental operations based on new `AgentCase` records:

- **ADD**: Create a new skill if the case represents a novel capability.
- **UPDATE**: Refine an existing skill (e.g., improving the "approach" based on a new high-quality case).
- **DELETE**: Retire skills that are no longer valid or have been superseded [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py37-51](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L37-L51)

### 4.2 Maturity and Quality Control

- **Maturity Scoring**: Skills are assigned a `maturity_score`. As more successful cases support a skill, its maturity increases. This is calculated via a specific `maturity_prompt`[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py88-91](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L88-L91)
- **Prompt Selection**: The extractor selects different prompts based on the `quality_score` of the input cases. If quality is below `FAILURE_QUALITY_THRESHOLD` (0.5), a failure-specific extraction prompt is used to learn from mistakes [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py69-70](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L69-L70)
- **Confidence Tracking**: Skills track a `confidence` score. If it falls below `retire_confidence` (default 0.1), the skill is considered for retirement [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py78-79](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L78-L79)

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py54-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L54-L63)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py157-168](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L157-L168)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py82-91](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L82-L91)

---

## 5. Retrieval Flow

Retrieval for agent memory uses a hybrid approach involving vector similarity and keyword search across `AgentCase` and `AgentSkill` repositories.

### 5.1 System Entity Mapping

The following diagram bridges the Natural Language retrieval intent to the specific Code Entities used in the search process.

**Retrieval Entity Mapping**

[Flowchart Diagram]

**Sources:**[methods/evermemos/tests/test_agent_search_service.py110-137](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L110-L137)[methods/evermemos/src/agentic_layer/search_mem_service.py139-160](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/search_mem_service.py#L139-L160)

### 5.2 Retrieval Methods

The `SearchMemoryService` supports multiple retrieval modes for agent memory:

- **Vector**: Semantic search via `AgentCaseMilvusRepository` and `AgentSkillMilvusRepository`.
- **Keyword**: BM25 search via `AgentCaseEsRepository` and `AgentSkillEsRepository`.
- **Hybrid**: Combines Milvus vector hits with Elasticsearch keyword hits, followed by a reranking step.
- **Conversion**: Results are converted into DTOs such as `SearchAgentCaseItem` and `SearchAgentSkillItem`[methods/evermemos/tests/test_agent_search_service.py25-29](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L25-L29)

**Sources:**[methods/evermemos/tests/test_agent_search_service.py5-12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L5-L12)[methods/evermemos/tests/test_agent_search_service.py146-193](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L146-L193)

---

## 6. Data Models

### Agent Memory Record Structure

| Field | Type | Description |
| --- | --- | --- |
| `task_intent` | `str` | Extracted goal of the agent trajectory. |
| `approach` | `str` | Step-by-step summary of how the task was handled. |
| `quality_score` | `float` | Success rating (0.0 to 1.0). |
| `confidence` | `float` | (Skills only) The model's confidence in the distilled skill. |
| `maturity_score` | `float` | (Skills only) Derived from the number of supporting cases. |
| `source_case_ids` | `List[str]` | (Skills only) References to the AgentCases that contributed to this skill. |

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py38-41](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L38-L41)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py141-155](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L141-L155)[methods/evermemos/tests/test_agent_search_service.py87-88](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_search_service.py#L87-L88)