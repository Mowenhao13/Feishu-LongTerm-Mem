# Profile and Group Profile Management
Relevant source files
- [methods/evermemos/src/api_specs/memory_types.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py)
- [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py)
- [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py)
- [methods/evermemos/tests/test_agent_memcell_extractor.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_agent_memcell_extractor.py)
- [methods/evermemos/tests/test_profile_memory.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py)

This page details the extraction and management of long-term user and group profiles within EverMemOS. Unlike episodic memories which capture specific events, profiles represent consolidated, structural information about entities—including behavioral traits, professional roles, and group dynamics.

## Profile Management Lifecycle

The `ProfileExtractor` is the core component responsible for orchestrating profile extraction from conversation episodes [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py119-122](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L119-L122) It abstracts the complexity of LLM-based extraction, incremental updates, and multi-scenario logic (e.g., Solo vs. Team).

### Extraction Flow

Profile extraction is typically triggered during the memory consolidation phase. The system processes a `new_episode` in the context of `cluster_episodes` to update a user's long-term profile [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py131-134](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L131-L134)

1. **Input Gathering**: The system receives a `ProfileExtractRequest` containing the latest episode, historical cluster context, and the current `old_profile`[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py84-90](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L84-L90)
2. **Scenario Routing**: The extractor handles different scenarios via `ScenarioType`:

- `SOLO`: Focuses on personal traits and explicit information for a single user [methods/evermemos/src/api_specs/memory_types.py17](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L17-L17)
- `TEAM`: Focuses on professional roles and contributions, requiring speaker disambiguation via `target_user_name`[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py93-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L93-L95)
3. **LLM Operations**: The `_llm_update_profile` method invokes the LLM to perform incremental updates (Add/Update/Delete) based on the new conversation data [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py188-195](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L188-L195)
4. **Consolidation**: The system parses the LLM's operational JSON response and applies changes to the `ProfileMemory` object [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py197-215](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L197-L215)

### Profile Persistence and Storage

Profiles are represented by the `ProfileMemory` class, which inherits from `BaseMemory`[methods/evermemos/src/api_specs/memory_types.py19](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L19-L19) These objects are persisted in MongoDB and synchronized to vector databases like Milvus for retrieval [methods/evermemos/src/api_specs/memory_types.py228-231](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L228-L231)

**Profile Data Flow Diagram**

[Flowchart Diagram]

Sources: [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py84-215](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L84-L215)[methods/evermemos/src/api_specs/memory_types.py19-231](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L19-L231)

---

## ProfileMemory: Explicit Info vs. Implicit Traits

The profile system distinguishes between hard facts and soft behavioral traits to build a comprehensive user model [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py1-7](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L1-L7)

### Taxonomy of Profile Items

The system categorizes information into two primary buckets defined in `ProfileItemType`[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py78-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L78-L80):

- **Explicit Info**: Objective data points including `category`, `description`, and `evidence`. Examples include "Lives in Beijing" or "Uses Python" [methods/evermemos/tests/test_profile_memory.py45-47](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L45-L47)
- **Implicit Traits**: Behavioral patterns and psychological characteristics like "Curious" or "Detail-oriented," supported by a `basis` and `evidence`[methods/evermemos/tests/test_profile_memory.py49-51](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L49-L51)

### LLM Operations-based Updates

Instead of simple overwrites, the system performs targeted operations defined in `ProfileAction`[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py71-75](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L71-L75):

- **ADD**: Insert new information discovered in the current episode.
- **UPDATE**: Modify existing items if new evidence refines or changes the information.
- **DELETE**: Remove items that are no longer true or were extracted in error.
- **Compaction**: The system enforces a `max_items` limit (default 25) to ensure the profile remains concise and token-efficient [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py102-122](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L102-L122)

### ID Aliasing for Token Efficiency

To handle context window constraints and reduce LLM hallucinations, the system implements **ID Aliasing**. Long episode IDs are mapped to short aliases (e.g., `ep1`, `ep2`) during the prompt construction phase [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py36-37](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L36-L37) The `_replace_sources` utility handles the mapping and re-mapping of these IDs within the profile's source metadata [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py40-60](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L40-L60)

Sources: [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py36-122](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L36-L122)[methods/evermemos/tests/test_profile_memory.py45-51](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L45-L51)

---

## Agent and Group Profile Context

### Agent Conversation Handling

For agentic workflows, the `AgentMemCellExtractor` ensures that profile extraction only occurs after a complete agent turn. It uses `is_intermediate_agent_step` to filter out tool calls and tool responses, providing the profile extractor with a clean narrative of the interaction [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py100-152](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L100-L152)[methods/evermemos/src/api_specs/memory_types.py117-129](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L117-L129)

### Team Scenario Disambiguation

In `ScenarioType.TEAM`, the `ProfileExtractor` must identify which user the traits belong to. It uses `_resolve_user_name` to map the `user_id` to a display name found within the conversation episodes, ensuring that traits are attributed to the correct participant [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py180-186](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L180-L186)

**Agent and Profile Interaction Logic**

[Flowchart Diagram]

Sources: [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py100-152](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L100-L152)[methods/evermemos/src/api_specs/memory_types.py117-129](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/api_specs/memory_types.py#L117-L129)[methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py180-186](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L180-L186)

---

## Implementation Details

### Source Tracking and Evidence

Every item in a profile maintains a `sources` list. These sources are often formatted as `YYYY-MM-DD|episode_id` to provide both a timestamp and a direct link back to the raw conversation [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py49-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L49-L53) The `get_all_source_ids` method allows the system to quickly identify which episodes contributed to a user's current profile [methods/evermemos/tests/test_profile_memory.py106-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L106-L113)

### Data Model Structure

The `ProfileMemory` dataclass includes several utility methods for management:

- `total_items()`: Returns the sum of explicit info and implicit traits [methods/evermemos/tests/test_profile_memory.py59-61](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L59-L61)
- `to_readable_profile()`: Generates a human-readable string representation of the profile for injection into LLM prompts [methods/evermemos/tests/test_profile_memory.py127-131](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L127-L131)
- `processed_episode_ids`: Tracks which episodes have already been distilled into the profile to prevent redundant processing [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py165-168](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L165-L168)

### Agent Turn Boundaries

The `AgentMemCellExtractor` provides critical turn-boundary logic to ensure `MemCell` creation respects the completion of agent actions. It checks `is_intermediate_agent_step` to skip boundary detection if the last message is a `tool_call` or `tool` response [methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py140-151](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L140-L151) This ensures that the downstream `ProfileExtractor` receives a coherent set of messages where the agent has finished its thought process.

Sources: [methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py49-168](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memory_extractor/profile_extractor.py#L49-L168)[methods/evermemos/tests/test_profile_memory.py59-131](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/tests/test_profile_memory.py#L59-L131)[methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py140-151](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/memory_layer/memcell_extractor/agent_memcell_extractor.py#L140-L151)