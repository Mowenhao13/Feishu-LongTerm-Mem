# EverMemBench: Multi-Person Group Chat Benchmark
Relevant source files
- [.gitignore](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.gitignore)
- [README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1)

EverMemBench is a standalone evaluation framework designed to measure the quality of long-term memory systems in the context of multi-person group chats. It provides a unified standard for evaluating factual recall, applied reasoning, and personalized generalization across different memory architectures and Large Language Models (LLMs) [README.md96-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L100) Unlike static benchmarks, EverMemBench focuses on the dynamic nature of group interactions, supporting a four-stage pipeline to assess how memory systems ingest, retrieve, and utilize information over time [README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)

### Core Pipeline Architecture

The benchmark operates through a strictly defined four-stage pipeline. This structure ensures that every memory system, whether it is an external service like Zep or an internal method like EverMemOS, is evaluated under identical conditions.

1. **Add Stage**: Raw conversation data from the dataset is ingested into the memory system. For systems like EverMemOS, this triggers the encoding and consolidation processes.
2. **Search Stage**: The framework generates queries based on the benchmark questions and retrieves relevant memory segments from the system.
3. **Answer Stage**: An LLM (the "Answerer") uses the retrieved context to generate responses to the benchmark questions.
4. **Evaluate Stage**: The generated answers are scored against ground truth using either exact matching (for multiple-choice) or LLM-as-a-judge (for open-ended questions).

#### EverMemBench Pipeline Data Flow

The following diagram illustrates the flow of data through the `EverMemBench` framework and its interaction with the memory adapter layer.

[Flowchart Diagram]

**Sources:**[README.md96-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L100)[README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)

---

### Supported Memory Systems and Adapters

EverMemBench is designed to be extensible through an adapter pattern. Each supported memory system implements a specific adapter class that translates the benchmark's standard commands into system-specific API calls.

| System | Adapter Class | Description |
| --- | --- | --- |
| **EverMemOS** | `EverMemosAdapter` | Integrates with the EverMemOS REST API, utilizing MemCells and Episodes [README.md63-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L67) |
| **Mem0** | `Mem0Adapter` | Interfaces with the Mem0 library for fact-based memory storage [README.md134](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L134-L134) |
| **Memobase** | `MemobaseAdapter` | Connects to the Memobase cloud/local service. |
| **Zep** | `ZepAdapter` | Evaluates the Zep long-term memory store [README.md136](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L136-L136) |
| **Memos** | `MemosAdapter` | A baseline implementation for simple document-based memory [README.md135](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L135-L135) |
| **LLM Long-Context** | `LongContextAdapter` | A special mode where the entire conversation history is passed in the prompt window without a retrieval system. |

#### EverMemosAdapter Implementation

The `EverMemosAdapter` serves as the bridge between the benchmark and the `evermemos` core. It handles the conversion of `GroupChatFormat` data into the internal `RawData` format required by the EverMemOS ingestion pipeline [README.md43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L43-L43)

**Sources:**[README.md130-137](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L130-L137)[README.md43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L43-L43)[README.md63-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L67)

---

### Question Types and Evaluation Modes

The benchmark evaluates memory systems using two distinct question formats to capture different aspects of memory utility:

- **Multiple Choice (Objective)**: Tests factual recall and specific detail retrieval. These are evaluated using strict accuracy metrics.
- **Open-Ended (Subjective)**: Tests reasoning and the ability to synthesize information from multiple conversation segments. These are evaluated using an "LLM-as-a-judge" approach, where a strong model (e.g., GPT-4o) scores the answer based on completeness and correctness relative to the ground truth [README.md96-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L100)

#### LLM Long-Context Evaluation Mode

This mode serves as the "Gold Standard" or upper bound for performance. Instead of using a memory system to retrieve snippets, the entire conversation history is fed into a long-context LLM. This measures how well a model can reason over raw data when no information loss occurs during retrieval.

**Sources:**[README.md96-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L96-L100)[README.md130-137](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L130-L137)

---

### Dataset Format and CLI Usage

EverMemBench uses a standardized JSONL format for its datasets, specifically optimized for multi-person interactions [README.md100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L100-L100)

#### Dataset Structure

Each entry in the dataset includes:

- `conversation_history`: A list of messages with `sender`, `content`, and `timestamp`.
- `questions`: A list of question objects containing the `question_text`, `options` (for multiple choice), and `ground_truth`.

#### CLI Usage

The benchmark is executed via a command-line interface, allowing users to specify the system, the stage, and the model to be used.

```
# Example: Running the full pipeline for EverMemOS
python run_bench.py --system evermemos --stage all --dataset group_chat_v1.jsonl --model gpt-4o
```

**Key CLI Arguments:**

- `--system`: The target memory system (e.g., `evermemos`, `mem0`, `zep`).
- `--stage`: The specific stage to run (`add`, `search`, `answer`, `evaluate`, or `all`).
- `--model`: The LLM used for answering and evaluation.

**Sources:**[README.md100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L100-L100)[README.md43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L43-L43)

---

### Result Structure and Metrics

The output of a benchmark run is stored in a structured format, typically a JSON file containing detailed logs for every question, followed by a summary report.

#### Metrics Tracked

1. **Recall Accuracy**: The percentage of factual questions answered correctly.
2. **Reasoning Score**: The average score (1-10) assigned by the LLM judge for complex queries.
3. **Retrieval Latency**: The time taken by the memory system to return context during the Search stage.
4. **Token Efficiency**: The number of context tokens retrieved versus the relevance of the answer.

#### Code Entity Mapping: Benchmark to System

The following diagram bridges the benchmark's conceptual stages to the specific code entities in the `EverMemOS` implementation that they exercise.

[Flowchart Diagram]

**Sources:**[README.md38-48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L38-L48)[README.md63-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/README.md?plain=1#L63-L67)