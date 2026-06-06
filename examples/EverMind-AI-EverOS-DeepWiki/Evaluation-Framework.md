# Evaluation Framework
Relevant source files
- [README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1)
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)

The **Evaluation Framework** in EverOS is a unified system designed to benchmark memory quality and agent self-evolution. It provides a consistent methodology for comparing EverMemOS with other memory systems (such as Mem0, Zep, and Memobase) and measuring the longitudinal growth of agents as they acquire new skills [README.md86-89](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L86-L89)

The framework is split into two primary standalone benchmarks and an internal adapter system:

1. **EverMemBench**: Focuses on memory quality (recall, reasoning, generalization) [README.md96-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L100)
2. **EvoAgentBench**: Focuses on agent self-evolution and skill acquisition curves [README.md107-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L107-L111)
3. **EverMemOS Internal Adapter**: The bridge within the `methods/evermemos` codebase that allows the core system to be plugged into these benchmarks.

### Evaluation Architecture

The framework follows a decoupled architecture where dataset loaders, system adapters, and evaluators are orchestrated to measure performance across different domains [README.md38-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L45)

#### System Components to Code Mapping

The following diagram illustrates how high-level evaluation concepts map to specific code entities across the benchmarks and core methods.

**Evaluation Framework Entity Map**

[Flowchart Diagram]

Sources: [README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[README.md96-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L111)

---

### EverMemOS Evaluation Adapter (Internal)

The internal evaluation adapter provides the necessary glue to run EverMemOS against memory benchmarks. It implements a multi-stage pipeline:

- **Extraction & Indexing**: Converting raw messages into `MemCell` entities and building indices via `MemorySyncService`.
- **Agentic Retrieval**: Using a two-round retrieval loop (sufficiency check and query refinement) to ensure high recall for complex queries.
- **Response Generation**: Combining retrieved episodes, profiles, and foresight into a coherent context for the LLM.

For details, see [EverMemOS Evaluation Adapter (Internal)](/EverMind-AI/EverOS/9.1-evermemos-evaluation-adapter-(internal)).

---

### EverMemBench: Memory Quality Benchmark

**EverMemBench** is a standalone framework designed to evaluate memory systems under a unified standard. It measures three layers of memory quality:

1. **Factual Recall**: Ability to retrieve specific facts from history.
2. **Applied Reasoning**: Using retrieved memories to solve multi-step problems.
3. **Personalized Generalization**: Understanding user traits and habits over time.

It supports a variety of backends including EverMemOS, Mem0, Memobase, and Zep, providing a "fair-play" environment where each system uses its native retrieval logic but is judged by a common LLM-as-a-judge [README.md96-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L100)

For details, see [EverMemBench: Multi-Person Group Chat Benchmark](/EverMind-AI/EverOS/9.2-evermembench:-multi-person-group-chat-benchmark).

---

### EvoAgentBench: Agent Self-Evolution Benchmark

**EvoAgentBench** shifts the focus from static memory snapshots to **longitudinal growth**. It measures how an agent improves over time by:

- **Skill Extraction**: Identifying successful patterns from past task executions via `AgentSkillExtractor`.
- **Transfer Efficiency**: Applying learned skills to new, unseen problems.
- **Error Avoidance**: Recalling past failures to prevent regressions.

The benchmark covers five domains: Information Retrieval, Reasoning, Software Engineering, Code Implementation, and Knowledge Work [README.md107-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L107-L111)

For details, see [EvoAgentBench: Agent Self-Evolution Benchmark](/EverMind-AI/EverOS/9.3-evoagentbench:-agent-self-evolution-benchmark).

---

### Performance Overview

EverMemOS and its underlying architectures (like HyperMem) consistently achieve high scores on these benchmarks due to their structured approach to memory.

| Metric | EverMemOS / HyperMem | Baseline (RAG) |
| --- | --- | --- |
| **LoCoMo Accuracy** | **92.73%**[README.md76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L76-L76) | ~78% |
| **Self-Evolution Delta (Code)** | **+21% to +26%**[README.md143-144](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L143-L144) | N/A |
| **Self-Evolution Delta (General)** | **+20% to +40%**[README.md145-146](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L145-L146) | N/A |

#### Evaluation Bridge: Natural Language to Code

This diagram shows how natural language evaluation requests flow into specific code-level search and retrieval functions.

**Natural Language to Code Entity Bridge**

[Flowchart Diagram]

Sources: [README.md141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L141-L147)[README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[methods/evermemos/docs/OVERVIEW.md84-106](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L84-L106)

---

### Usage Summary

Evaluations for memory systems are typically launched via the benchmark-specific CLI tools:

```
# Example for EverMemBench
python -m EverMemBench.cli --dataset locomo --system evermemos --stages add search answer evaluate
```

The framework handles checkpointing, allowing developers to resume evaluations from intermediate stages (e.g., re-running the `evaluate` stage without re-ingesting data).

Sources: [README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[README.md96-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L111)