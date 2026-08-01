# Memory Extraction: Episodes, Event Logs, and Foresight
Relevant source files
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)
- [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py)
- [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py)
- [methods/evermemos/tests/test_agent_skill_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_skill_extractor.py)

After a `MemCell` is successfully created and its boundaries are defined, the system initiates a parallel extraction pipeline to transform raw data into structured memory types. This process is orchestrated by the `MemoryManager` and involves specialized extractors that utilize Large Language Models (LLMs) to generate narrative summaries, atomic facts, and temporal predictions.

## Extraction Orchestration

The `MemoryManager` serves as the central hub for the extraction lifecycle. Once a `MemCell` (the raw data container) is identified, `MemoryManager.extract_memory` is invoked to dispatch tasks to specific extractors based on the requested `MemoryType`.

### Data Flow and Parallelism

The extraction process typically follows a sequence where the `EpisodeMemory` is generated first (as it provides a narrative summary), followed by `EventLog` and `Foresight` which can be derived from either the `MemCell` or the generated `Episode`.

**Extraction Dispatch Logic**

| Memory Type | Extractor Class | Input Source | Output Entity |
| --- | --- | --- | --- |
| `EPISODIC_MEMORY` | `EpisodeMemoryExtractor` | `MemCell.original_data` | `EpisodeMemory` |
| `EVENT_LOG` | `EventLogExtractor` | `Episode` or `MemCell` | `EventLog` (Atomic Facts) |
| `FORESIGHT` | `ForesightExtractor` | `MemCell` transcript | `List[ForesightRecord]` |
| `AGENT_CASE` | `AgentCaseExtractor` | `MemCell` (OpenAI format) | `AgentCase` (Task/Approach) |
| `AGENT_SKILL` | `AgentSkillExtractor` | `AgentCase` list | `AgentSkill` (Reusable Skill) |
| `PROFILE` | `ProfileExtractor` | `Episode` + `Cluster` | `ProfileMemory` |

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py75-86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L75-L86)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py54-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L54-L63)[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py119-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L119-L130)[methods/evermemos/src/api_specs/memory_types.py133-158](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L133-L158)

---

## Episode Memory Extraction

The `EpisodeMemoryExtractor` focuses on creating a narrative "story" of the interaction. It processes the `original_data` within a `MemCell` to produce a subject and a detailed summary.

### Implementation Details

1. **Text Normalization**: The extractor converts list-based raw data into a structured conversation transcript using `get_text_from_content_items`[methods/evermemos/src/api_specs/memory_types.py73-89](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L73-L89)
2. **LLM Generation**: It utilizes specific prompts to generate a narrative. The system supports multilingual truncation through `SmartTextParser` to ensure inputs fit LLM context windows [methods/evermemos/tests/test_smart_text_parser.py84-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L84-L95)
3. **Vectorization**: Post-extraction, the episode content is sent to the `VectorizeService` to generate embeddings for similarity search.

**Sources:**[methods/evermemos/src/api_specs/memory_types.py73-114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L73-L114)[methods/evermemos/tests/test_smart_text_parser.py14-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_smart_text_parser.py#L14-L21)

---

## Event Log Extraction (Atomic Facts)

The `EventLogExtractor` decomposes complex episodes into "Atomic Facts." These are independent, granular units of information optimized for precise retrieval and batch embedding.

### Extraction Pipeline

1. **Temporal Context**: The extractor parses timestamps to provide the LLM with temporal grounding.
2. **Atomic Fact Generation**: The LLM is prompted to return a JSON object containing a list of `atomic_fact` strings. Each fact must be a standalone statement.
3. **Parsing & Validation**: The system ensures robustness against LLM formatting inconsistencies by attempting multiple parsing strategies.

**Sources:**[methods/evermemos/src/api_specs/memory_types.py66-71](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L66-L71)[methods/evermemos/tests/test_rawdata_json_serialization.py45-60](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_rawdata_json_serialization.py#L45-L60)

---

## Profile Memory Extraction

The `ProfileExtractor` manages the long-term representation of users and groups. It uses an incremental update strategy rather than full re-generation.

### Incremental Operations

- **Operation Types**: The extractor performs `add`, `update`, or `delete` operations on `explicit_info` (facts like "likes coffee") and `implicit_traits` (behavioral observations like "curious") [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py71-82](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L71-L82)
- **ID Mapping**: To save tokens and prevent LLM hallucination of source IDs, the system uses a short-ID mapper (e.g., `ep1`, `ep2`) during the LLM call and remaps them to real database IDs afterward [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py36-43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L36-L43)
- **Scene Awareness**: Supports both `SOLO` (one user) and `TEAM` (multi-user) scenarios, resolving speaker names to ensure traits are attributed to the correct participant [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py83-96](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L83-L96)

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py119-162](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L119-L162)[methods/evermemos/tests/test_profile_memory.py155-182](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L155-L182)

---

## Agent Experience: Cases and Skills

EverMemOS provides specialized extractors to distill reusable knowledge from agentic tool-calling interactions, specifically `AgentCase` and `AgentSkill`.

### Agent Case Extraction

The `AgentCaseExtractor` processes a `MemCell` to distill a single experience record.

- **Pre-compression**: If tool content exceeds `PRE_COMPRESS_CHUNK_SIZE` (default 100,000 tokens), the extractor uses an LLM to compress tool inputs/outputs [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py50-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L50-L52)
- **Heuristic Trimming**: Per-message limits are applied to tool outputs (`MAX_TOOL_OUTPUT_TOKENS`) and assistant responses to fit context windows [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py59-62](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L59-L62)
- **Attributes**: It extracts `task_intent`, `approach`, and `quality_score`. The `task_intent` is vectorized for retrieval [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py8-10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L8-L10)

### Agent Skill Extraction

The `AgentSkillExtractor` performs incremental skill distillation from one or more `AgentCase` records.

- **Operation-based Updates**: It generates `add`, `update`, or `none` operations on existing cluster skills [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py4-5](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L4-L5)
- **Maturity Scoring**: Skills are assigned a `maturity_score`. The extractor uses a specific prompt to evaluate if a skill has reached the `maturity_threshold` (default 0.6) [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py77-91](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L77-L91)
- **Prompt Selection**: It chooses between `success_extract_prompt` and `failure_extract_prompt` based on the `quality_score` of the input cases [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py69-87](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L69-L87)

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py1-66](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L1-L66)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py1-92](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L1-L92)[methods/evermemos/tests/test_agent_skill_extractor.py78-94](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_skill_extractor.py#L78-L94)

---

## System Architecture Diagrams

### Memory Extraction Flow

This diagram maps the logical extraction process to the specific code entities responsible for the transformation.

[Flowchart Diagram]

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py75-86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L75-L86)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py7-12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L7-L12)[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py119-130](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L119-L130)[methods/evermemos/src/api_specs/memory_types.py171-190](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L171-L190)

### Vectorization and Scoring Pipeline

This diagram illustrates the relationship between extraction, embedding generation, and relevance scoring.

[Flowchart Diagram]

**Sources:**[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py10-11](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L10-L11)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py11-12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L11-L12)[methods/evermemos/tests/test_embedding_reranker_providers.py5-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L5-L18)[methods/evermemos/tests/test_embedding_reranker_providers.py101-121](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_embedding_reranker_providers.py#L101-L121)

---

## Data Models for Extracted Content

| Field | Description | Type | File Reference |
| --- | --- | --- | --- |
| `original_data` | The raw message source (full trajectory for agents) | `List[Dict[str, Any]]` | [methods/evermemos/src/api_specs/memory_types.py146](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L146-L146) |
| `task_intent` | The primary goal of an agent interaction | `str` | [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py65](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L65-L65) |
| `approach` | The methodology used by the agent to solve a task | `str` | [methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py9](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L9-L9) |
| `maturity_score` | Metric indicating the reliability of an agent skill | `float` | [methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py77](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L77-L77) |
| `explicit_info` | Fact-based user profile attributes | `List[Dict[str, Any]]` | [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py55](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L55-L55) |
| `sources` | List of Episode IDs providing evidence for a fact | `List[str]` | [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L52-L52) |

**Sources:**[methods/evermemos/src/api_specs/memory_types.py133-190](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L133-L190)[methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py8-10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_case_extractor.py#L8-L10)[methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py37-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/agent_skill_extractor.py#L37-L52)[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py36-60](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L36-L60)