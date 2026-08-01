# SimpleMemoryManager and Chat Demo
Relevant source files
- [methods/evermemos/demo/agent_clustering_test_demo.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/agent_clustering_test_demo.py)
- [methods/evermemos/demo/chat_agent_demo.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/chat_agent_demo.py)
- [methods/evermemos/demo/utils/agent_demo_helpers.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py)
- [methods/evermemos/demo/utils/simple_memory_manager.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py)
- [methods/evermemos/env.template](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template)
- [methods/evermemos/src/agentic_layer/get_mem_service.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py)

This page describes the high-level client utilities and the interactive chat demonstration system within EverOS. These components provide a simplified interface for developers to interact with the memory system and reference implementations of memory-augmented chat agents.

## SimpleMemoryManager

The `SimpleMemoryManager` is a high-level Python client designed to encapsulate the complexities of HTTP API calls to the EverOS server [methods/evermemos/demo/utils/simple_memory_manager.py67-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L67-L76) It allows developers to store and search memories with minimal configuration by wrapping the REST API.

### Key Methods and Logic

| Method | Description | Implementation Details |
| --- | --- | --- |
| `store()` | Ingests a single message into the system. | Generates a unique `message_id`, attaches metadata (sender, role, timestamp), and posts to `/api/v1/memories`[methods/evermemos/demo/utils/simple_memory_manager.py104-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L104-L140) |
| `search()` | Performs a multi-modal search. | Sends a query to `/api/v1/memories/search` and returns formatted results [methods/evermemos/demo/utils/simple_memory_manager.py228-255](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L228-L255) |
| `wait_for_index()` | Pauses execution for background indexing. | Simple `asyncio.sleep` to allow the background extraction pipeline (MemCells to Episodes/Event Logs) to complete [methods/evermemos/demo/utils/simple_memory_manager.py217-226](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L217-L226) |
| `_init_settings()` | Initializes session metadata. | Triggered on the first `store()` call; ensures the server has the correct settings via `/api/v1/settings`[methods/evermemos/demo/utils/simple_memory_manager.py172-196](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L172-L196) |

### Message ID Generation

The manager generates IDs using the pattern `msg_{counter}_{timestamp_ms}` to ensure uniqueness and chronological ordering within the ingestion pipeline [methods/evermemos/demo/utils/simple_memory_manager.py118-123](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L118-L123)

### Event Time Extraction

The utility `extract_event_time_from_memory` parses memory dictionaries to find the actual time of an event rather than its storage time. It uses a prioritized regex search:

1. ISO dates in parentheses in the `subject` field [methods/evermemos/demo/utils/simple_memory_manager.py32-36](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L32-L36)
2. Chinese date formats in the `subject`[methods/evermemos/demo/utils/simple_memory_manager.py38-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L38-L42)
3. ISO or Chinese date formats within the `episode` content [methods/evermemos/demo/utils/simple_memory_manager.py45-61](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L45-L61)

**Sources:**[methods/evermemos/demo/utils/simple_memory_manager.py14-162](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L14-L162)[methods/evermemos/demo/utils/simple_memory_manager.py172-255](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L172-L255)

---

## ChatSession Orchestrator

The chat demonstration system (facilitated by `AgentDemoRunner` and scripts like `chat_agent_demo.py`) manages the state and execution flow for a conversation thread. It orchestrates memory retrieval, prompt construction, and LLM interaction.

### Parallel Memory Retrieval

When a user provides input, the demo scripts perform retrieval across multiple memory types to build context. The `GetMemoryService` provides the backend logic for fetching these structured memories from the persistence layer [methods/evermemos/src/agentic_layer/get_mem_service.py58-69](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L58-L69)

1. **Episodic Memory:** Narrative summaries of past events [methods/evermemos/src/agentic_layer/get_mem_service.py189-192](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L189-L192)
2. **User Profile:** Long-term user traits and preferences [methods/evermemos/src/agentic_layer/get_mem_service.py91-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L91-L100)
3. **Agent Skills/Cases:** Specialized experience and reasoning patterns for task-oriented agents [methods/evermemos/src/agentic_layer/get_mem_service.py182-185](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L182-L185)

### LLM Provider Integration

The system integrates with various LLM backends (OpenRouter, OpenAI, vLLM) via the `.env` configuration [methods/evermemos/env.template17-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L17-L48) The demo environment supports specific configurations for:

- **Vectorization:** Primary and fallback embedding providers (e.g., vLLM with DeepInfra fallback) [methods/evermemos/env.template63-88](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L63-L88)
- **Reranking:** Primary and fallback rerankers for quality filtering [methods/evermemos/env.template108-133](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L108-L133)

**Sources:**[methods/evermemos/src/agentic_layer/get_mem_service.py58-188](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L58-L188)[methods/evermemos/env.template17-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L17-L140)[methods/evermemos/demo/utils/agent_demo_helpers.py139-178](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L139-L178)

---

## Data Flow: From Input to Memory-Augmented Response

The following diagrams illustrate how the demo utilities bridge the gap between user input and the underlying memory entities.

### Logic Flow: Chat Interaction

```

```

### Memory Retrieval Logic (GetMemoryService)

```

```

**Sources:**[methods/evermemos/src/agentic_layer/get_mem_service.py127-187](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L127-L187)[methods/evermemos/demo/utils/simple_memory_manager.py104-140](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L104-L140)[methods/evermemos/env.template21-28](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L21-L28)

---

## Agent and Clustering Demos

The demo suite includes specialized scripts and helpers for testing complex agentic behaviors:

### Agent Clustering (`agent_clustering_test_demo.py`)

This demo simulates multiple agent trajectories (e.g., code debugging, data analysis, infrastructure provisioning) to verify that the memory system correctly:

- **Merges** similar reasoning patterns into the same cluster [methods/evermemos/demo/agent_clustering_test_demo.py1-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/agent_clustering_test_demo.py#L1-L15)
- **Separates** distinct task intents into different clusters [methods/evermemos/demo/agent_clustering_test_demo.py37-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/agent_clustering_test_demo.py#L37-L170)

### Chat Agent (`chat_agent_demo.py`)

Demonstrates memory extraction from casual chitchat without tool calls. It verifies that the system can still extract:

- **Episodic Memories** from conversational topics like weekend plans [methods/evermemos/demo/chat_agent_demo.py36-79](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/chat_agent_demo.py#L36-L79)
- **Agent Experiences** from the assistant's own conversational strategies [methods/evermemos/demo/chat_agent_demo.py1-13](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/chat_agent_demo.py#L1-L13)

### Agent Demo Helpers (`agent_demo_helpers.py`)

Provides the `AgentDemoRunner` class, which handles session management and v1 API interactions for all agent demos [methods/evermemos/demo/utils/agent_demo_helpers.py139-172](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L139-L172) It includes specialized printers for different memory types:

- `print_episodic_memories`[methods/evermemos/demo/utils/agent_demo_helpers.py31-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L31-L42)
- `print_agent_cases`[methods/evermemos/demo/utils/agent_demo_helpers.py70-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L70-L83)
- `print_agent_skills`[methods/evermemos/demo/utils/agent_demo_helpers.py85-98](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L85-L98)

**Sources:**[methods/evermemos/demo/agent_clustering_test_demo.py1-167](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/agent_clustering_test_demo.py#L1-L167)[methods/evermemos/demo/chat_agent_demo.py1-156](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/chat_agent_demo.py#L1-L156)[methods/evermemos/demo/utils/agent_demo_helpers.py1-133](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L1-L133)

---

## Entity Mapping: Code to Concept

This table maps the conceptual "Natural Language" elements to the specific "Code Entities" used in the demo applications and retrieval services.

| Conceptual Space | Code Entity (Identifier) | File Path |
| --- | --- | --- |
| **Memory Client** | `SimpleMemoryManager` | [methods/evermemos/demo/utils/simple_memory_manager.py67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L67-L67) |
| **Memory Retrieval** | `GetMemoryService` | [methods/evermemos/src/agentic_layer/get_mem_service.py58](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L58-L58) |
| **Search Endpoint** | `/api/v1/memories/search` | [methods/evermemos/demo/utils/simple_memory_manager.py99](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L99-L99) |
| **Memory Ingestion** | `/api/v1/memories` | [methods/evermemos/demo/utils/simple_memory_manager.py98](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L98-L98) |
| **Environment Config** | `.env` | [methods/evermemos/env.template1](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/env.template#L1-L1) |
| **Clustering Test** | `agent_clustering_test_demo.py` | [methods/evermemos/demo/agent_clustering_test_demo.py1](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/agent_clustering_test_demo.py#L1-L1) |
| **Chat Agent Demo** | `chat_agent_demo.py` | [methods/evermemos/demo/chat_agent_demo.py1](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/chat_agent_demo.py#L1-L1) |
| **Demo Orchestrator** | `AgentDemoRunner` | [methods/evermemos/demo/utils/agent_demo_helpers.py139](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L139-L139) |

**Sources:**[methods/evermemos/demo/utils/simple_memory_manager.py67-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/simple_memory_manager.py#L67-L100)[methods/evermemos/src/agentic_layer/get_mem_service.py58-69](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/get_mem_service.py#L58-L69)[methods/evermemos/demo/agent_clustering_test_demo.py1-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/agent_clustering_test_demo.py#L1-L34)[methods/evermemos/demo/utils/agent_demo_helpers.py139-172](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/demo/utils/agent_demo_helpers.py#L139-L172)