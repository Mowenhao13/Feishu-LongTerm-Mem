# HyperMem Construction Pipeline
Relevant source files
- [.gitignore](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.gitignore)
- [README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1)

The **HyperMem Construction Pipeline** is the process by which raw conversation streams are transformed into a structured, three-level hypergraph. Unlike traditional RAG systems that rely on linear chunking, HyperMem organizes information into **Topic**, **Episode**, and **Fact** nodes, connected by hyperedges that capture high-order semantic associations [README.md74-77](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L74-L77)

## 1. Pipeline Overview

The construction process follows a hierarchical flow, moving from temporal segmentation to semantic abstraction. The pipeline ensures that memory is not just stored as isolated snippets but as part of a continuous narrative with thematic clustering.

### Data Flow Diagram: Raw Stream to Hypergraph

The following diagram illustrates the transformation of a message stream into the `HyperMem` structure, bridging natural language inputs to code-level persistence entities.

"HyperMem Construction Logic"

[Flowchart Diagram]

Sources: [README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[README.md74-77](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L74-L77)

---

## 2. Episode Detection and Boundary Segmentation

The first stage of the pipeline is **Episode Detection**. An "Episode" represents a continuous segment of conversation focused on a specific event or interaction.

### LLM-Driven Boundary Detection

HyperMem utilizes an LLM to analyze the conversation flow and identify transition points. The system evaluates:

1. **Temporal Gaps**: Significant pauses between messages that suggest a change in context.
2. **Semantic Shifts**: Changes in the intent or subject matter of the participants.
3. **Task Completion**: The conclusion of a specific request or problem-solving sequence.

When a boundary is detected, the preceding messages are bundled into a `MemCell` (the fundamental unit of episodic memory) for further processing [README.md63-65](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L65)

---

## 3. The Three-Level Node Structure

The HyperMem architecture is defined by three distinct node types, each representing a different level of granularity.

| Node Level | Entity Name | Description |
| --- | --- | --- |
| **Level 1** | `TopicNode` | High-level thematic clusters (e.g., "Project X Development", "Travel Planning"). |
| **Level 2** | `EpisodeNode` | Narrative summaries of specific conversation segments (represented by `EpisodicMemory`). |
| **Level 3** | `FactNode` | Atomic, verifiable pieces of information (represented by `AtomicFactRecord`). |

### Topic Aggregation

As new episodes are created, the system performs **Streaming Topic Matching**. If an episode aligns with an existing `TopicNode`, a hyperedge is created linking them. If no match is found, a new `TopicNode` is instantiated. This allows the memory to grow dynamically without predefined categories.

---

## 4. Fact Extraction and Hyperedge Assignment

Once an episode is defined, HyperMem extracts atomic facts to populate the third level of the graph.

### Extraction Logic

For every `EpisodeNode`, the system triggers an `AtomicFactExtractor`. Each `FactNode` contains:

- **Subject/Predicate/Object** structure or a short declarative statement.
- **Temporal Metadata**: When the fact was established.
- **Contextual Pointer**: A reference back to the source `EpisodicMemory` record.

### Hyperedge Weight Assignment

Hyperedges in HyperMem are not just binary connections; they carry weights that influence retrieval.

- **Episode-Fact Weights**: Based on the importance of the fact to the episode's narrative summary.
- **Topic-Episode Weights**: Based on the semantic similarity between the topic's global embedding and the episode's local embedding.

"Node and Edge Association"

[Class Diagram]

Sources: [README.md74-77](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L74-L77)[README.md130-137](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L130-L137)

---

## 5. Implementation in EverOS

The construction pipeline is integrated into the broader `EverCore` memory lifecycle. While `EverCore` handles the infrastructure (MongoDB, Milvus, Elasticsearch), the `HyperMem` module provides the logic for hypergraph organization.

### Key Classes and Functions

- **`ConvMemCellExtractor`**: Identifies boundaries and segments raw message streams into `MemCell` objects [README.md63-65](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L65)
- **`EpisodeMemoryExtractor`**: Generates narrative summaries and metadata for `EpisodicMemory` nodes.
- **`AtomicFactExtractor`**: An LLM-based component that decomposes episodic summaries into `AtomicFactRecord` nodes [README.md100-101](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L100-L101)
- **`MemorySyncService`**: Orchestrates the synchronization of extracted nodes and their embeddings to search backends like `Milvus` and `Elasticsearch`.

### Construction Flow

1. **Ingestion**: Raw messages are received via the `POST /api/v1/memories` endpoint.
2. **Segmentation**: The `ConvMemCellExtractor` identifies boundaries based on time-gaps and semantic content.
3. **Abstraction**: `EpisodicMemory` and `AtomicFactRecord` nodes are generated by their respective extractors.
4. **Indexing**: Nodes are vectorized and stored in `Milvus`, while the hypergraph structure (edges) and metadata are persisted in `MongoDB`[README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)

Sources: [README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[README.md63-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L67)[README.md74-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L74-L80)