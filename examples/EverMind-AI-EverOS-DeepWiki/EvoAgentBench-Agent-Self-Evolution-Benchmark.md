# EvoAgentBench: Agent Self-Evolution Benchmark
Relevant source files
- [.gitignore](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.gitignore)
- [README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1)

EvoAgentBench is a longitudinal evaluation framework designed to measure the **self-evolution** capabilities of AI agents. Unlike static benchmarks that provide a snapshot of performance, EvoAgentBench tracks growth curves across five distinct domains, measuring how agents improve through skill extraction and persistent memory integration. It specifically evaluates transfer efficiency, error avoidance, and the quality of extracted skills using a "train/extract/evaluate" protocol [README.md107-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L107-L113)

### Core Architecture and Runner Logic

The benchmark is structured around a central runner that orchestrates the lifecycle of an agent's evolution. It abstracts the interaction between the evaluation tasks and the underlying agent implementations through pluggable adapters [README.md141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L141-L147)

#### Evolution Lifecycle

The framework follows a three-stage protocol to measure evolution:

1. **Train (Experience Accumulation):** The agent performs tasks in a specific domain, generating raw interaction logs and execution traces.
2. **Extract (Skill Consolidation):** The system uses EverMemOS (EverCore) logic to extract "skills" or "experiences" from the training traces. These are stored as structured memories [README.md63-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L67)
3. **Evaluate (Longitudinal Testing):** The agent is tested on new, unseen tasks within the same domain. Performance is compared between a "Baseline" (no memory) and an "Evolved" state (with extracted skills).

#### Runner Architecture

The `Runner` is the primary execution engine. It manages domain-specific configurations, initializes the selected agent adapter, and handles the data flow between the agent and the evaluation metrics.

**Evolution Runner Data Flow**

[Flowchart Diagram]

Sources: [README.md107-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L107-L113)[README.md141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L141-L147)

---

### Evaluation Domains

EvoAgentBench categorizes agent capabilities into five high-level domains, each with specific success criteria and environmental abstractions [README.md107-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L107-L113)

| Domain | Description | Primary Metric |
| --- | --- | --- |
| **Information Retrieval** | Navigating complex documentation and extracting relevant facts. | Retrieval Precision / Recall |
| **Reasoning** | Multi-step logical deduction and planning. | Step-wise Accuracy |
| **Software Engineering** | Large-scale codebase modification and bug fixing (e.g., Django). | Pass@k / Unit Test Rate |
| **Code Implementation** | Writing atomic functions or scripts from specifications. | Execution Success |
| **Knowledge Work** | General productivity tasks like data analysis (e.g., GDPVAL). | Goal Completion Rate |

Sources: [README.md107-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L107-L113)[README.md141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L141-L147)

---

### Pluggable Agent Adapters

The framework supports multiple agent architectures through an adapter pattern, allowing different frameworks to be benchmarked under identical conditions [README.md141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L141-L147)

- **Nanobot Adapter:** Integrates the Nanobot agent framework, focusing on lightweight, tool-use-centric evolution [README.md144](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L144-L144)
- **OpenClaw Adapter:** Integrates the OpenClaw framework, which utilizes a more complex multi-agent orchestration and sub-agent assembly logic [README.md143](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L143-L143)

**Agent-to-Code Mapping**

[Class Diagram]

Sources: [README.md141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L141-L147)[README.md25-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L25-L30)

---

### Skill Extraction and EverMemOS Integration

The "Self-Evolution" aspect is powered by the integration with **EverMemOS (EverCore)**. During the evolution phase, the benchmark triggers specific memory extraction pipelines to convert raw logs into reusable agent skills [README.md63-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L67)

1. **Trace Parsing:** Raw agent actions (tool calls, LLM thoughts, environment feedback) are ingested.
2. **MemCell Creation:** Interaction sequences are segmented into `MemCell` entities.
3. **Skill Extraction:** The system identifies successful patterns and error-correction sequences, distilling them into structured `AgentSkill` memories.
4. **Retrieval-Augmented Evolution:** During evaluation, the agent retrieves relevant past experiences (skills) before deciding on its next action, allowing it to avoid previous mistakes or reuse successful code patterns.

### Performance Gains

The effectiveness of the self-evolution is measured by the "Delta" (improvement) between the baseline agent and the evolved agent [README.md139-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L139-L147)

| Task Type | Agent + LLM | Baseline | Evolved (+Skills) | Delta |
| --- | --- | --- | --- | --- |
| **Code (Django)** | OpenClaw + Qwen3.5-397B | 37% | 58% | **+21%** |
| **Code (Django)** | Nanobot + Qwen3.5-397B | 21% | 47% | **+26%** |
| **General (GDPVAL)** | OpenClaw + Qwen3.5-397B | 29% | 69% | **+40%** |
| **General (GDPVAL)** | OpenClaw + Qwen3.5-27B | 41% | 61% | **+20%** |

Sources: [README.md141-147](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L141-L147)[README.md63-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L67)