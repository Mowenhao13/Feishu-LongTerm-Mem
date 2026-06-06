# HyperMem Retrieval and Embedding Propagation
Relevant source files
- [.gitignore](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.gitignore)
- [README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1)

HyperMem implements a hierarchical, coarse-to-fine retrieval strategy designed to navigate its three-level hypergraph structure: Topics, Episodes, and Facts. By leveraging the structural relationships and attention-weighted embedding propagation, HyperMem achieves high-accuracy retrieval for long-term conversations, significantly outperforming traditional RAG and flat graph-based baselines.

## Retrieval Strategy: Coarse-to-Fine Traversal

The retrieval process in HyperMem is a top-down traversal of the hypergraph. Instead of searching all facts simultaneously, the system filters the search space through successive layers of abstraction.

### 1. Topic-Level Filtering

The system first identifies relevant high-level themes. Topic nodes act as the primary entry points for the retrieval pipeline.

- **Input:** User query vector.
- **Process:** Vector similarity search against the Topic node embeddings.
- **Output:** A candidate set of Topic nodes.

### 2. Episode-Level Ranking

Once topics are identified, the system traverses hyperedges to find specific conversation episodes associated with those topics.

- **Mechanism:** The system follows the connections from selected Topic nodes to their member Episode nodes.
- **Ranking:** Episodes are ranked based on their relevance to the query, often incorporating temporal weights to prioritize recent context if applicable.

### 3. Fact-Level Retrieval

The final stage retrieves atomic facts from within the ranked episodes.

- **Mechanism:** Direct retrieval of Fact nodes that are members of the selected Episode hyperedges.
- **Result:** A set of precise information units used to augment the LLM's context.

Sources: [README.md74-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L74-L80)[README.md133](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L133-L133)

## Hyperedge Embedding Propagation

HyperMem utilizes an attention-weighted aggregation mechanism to ensure that embeddings at higher levels (Topics/Episodes) accurately represent the semantic richness of their constituent lower-level nodes (Facts).

### Attention-Weighted Aggregation

Rather than simple averaging, HyperMem propagates embeddings upwards through the hypergraph. A Topic node's embedding is a weighted sum of its Episodes, and an Episode's embedding is a weighted sum of its Facts.

**The Propagation Logic:**

1. **Fact to Episode:** Fact embeddings are aggregated using an attention mechanism where the weights are determined by the semantic importance of each fact within the episode's narrative context.
2. **Episode to Topic:** Episode embeddings are similarly aggregated into the parent Topic node.

### System Mapping: Retrieval Data Flow

The following diagram illustrates how the retrieval logic bridges the natural language query to the underlying hypergraph entities stored in the system.

**HyperMem Retrieval Flow**

[Flowchart Diagram]

Sources: [README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[README.md74-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L74-L80)

## Performance and Benchmarks

HyperMem has been rigorously evaluated against the **LoCoMo** (Long-Context Memory) benchmark, which tests an agent's ability to recall and reason over extremely long conversation histories.

### LoCoMo Benchmark Results

HyperMem demonstrates superior performance compared to both standard RAG (Retrieval-Augmented Generation) and existing memory frameworks. It achieves a 92.73% accuracy on the LoCoMo benchmark.

| System | LoCoMo Accuracy |
| --- | --- |
| **HyperMem** | **92.73%** |
| EverCore (EverOS) | 93.05% |
| Mem0 | 78.4% |
| MemOS | 74.2% |
| Zep | 71.6% |

### Comparison with Baselines

- **Standard RAG:** Often fails in long conversations because it lacks the hierarchical context (Topics/Episodes), leading to "fact fragmentation" where retrieved chunks lack the necessary narrative background.
- **Graph-based Baselines:** While better than flat RAG, standard graphs often struggle with "high-order associations." HyperMem's use of **hyperedges** (which can connect multiple nodes simultaneously) allows it to capture complex relationships that binary edges in standard graphs miss.

Sources: [README.md76-78](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L76-L78)[README.md130-136](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L130-L136)

## Implementation Architecture

The retrieval engine is integrated into the broader EverOS ecosystem, utilizing the infrastructure layer for vector operations and persistence.

**Retrieval Component Diagram**

[Flowchart Diagram]

### Key Components

- **TopicFilter:** Interfaces with the `Milvus` collection containing Topic node embeddings to perform the initial coarse search.
- **EpisodeRanker:** Uses metadata stored in `MongoDB` (such as `EpisodicMemory` records) to traverse hyperedges and rank conversation segments.
- **FactRetriever:** Performs the final granular search, often utilizing `Elasticsearch` for hybrid keyword/vector matching on `AtomicFactRecord` entities to ensure factual precision.

Sources: [README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[README.md74-80](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L74-L80)