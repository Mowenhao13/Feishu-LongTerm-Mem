# OpenHer: Persona Memory Integration (Use-Case)
Relevant source files
- [use-cases/openher/.env.example](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/.env.example)
- [use-cases/openher/README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/README.md?plain=1)
- [use-cases/openher/demo/evermemos_demo.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/demo/evermemos_demo.py)
- [use-cases/openher/integration/context_features.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py)
- [use-cases/openher/integration/evermemos_mixin.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py)
- [use-cases/openher/integration/memory_types.py](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/memory_types.py)

The **OpenHer** persona engine represents a primary use-case for EverMemOS, demonstrating how persistent, structured memory can transform a standard chatbot into an "AI Being" with emergent personality and evolving relationships. By integrating EverMemOS, OpenHer moves beyond short-term context windows to maintain a long-term story across sessions, allowing the persona to naturally recall user preferences, past conflicts, and shared history [use-cases/openher/README.md1-28](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/README.md?plain=1#L1-L28)

### Purpose and Scope

This page provides a high-level overview of the integration between the OpenHer persona engine and the EverMemOS memory infrastructure. It details how memory data is mapped into neural network features and how the `EverMemosMixin` lifecycle incorporates asynchronous memory retrieval to ensure fluid conversation.

---

### Memory Architecture Layers

OpenHer utilizes a three-layer memory strategy where EverMemOS serves as the foundation for long-term episodic and declarative memory [use-cases/openher/README.md32-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/README.md?plain=1#L32-L42)

| Layer | Implementation | Function | Analogy |
| --- | --- | --- | --- |
| **Style Memory** | Local Neural State | Behavioral habits, tone, and expression patterns. | Muscle memory |
| **Local Facts** | SQLite (SoulMem) | Immediate user preferences and short-term info. | Short-term memory |
| **Long-Term Memory** | **EverMemOS** | Episodic history, user profiles, and foresight. | **Episodic memory** |

**Sources:**[use-cases/openher/README.md32-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/README.md?plain=1#L32-L42)[use-cases/openher/integration/memory_types.py1-14](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/memory_types.py#L1-L14)

---

### Neural Network Integration (12D Context)

OpenHer's core is a living neural network that processes a 25D input vector to produce 8D behavioral signals [use-cases/openher/integration/context_features.py55-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py#L55-L63) EverMemOS expands the persona's perception from 8D (per-turn LLM perception) to 12D by providing a 4D relationship vector derived from long-term memory [use-cases/openher/integration/context_features.py37-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py#L37-L53)

**The 4D Relationship Vector:**

1. **Relationship Depth:** (0=Stranger $\to$ 1=Old Friend)
2. **Emotional Valence:** (-1=Negative history $\to$ 1=Positive history)
3. **Trust Level:** (0=No trust $\to$ 1=Deep trust)
4. **Pending Foresight:** (0=Nothing pending $\to$ 1=Unresolved concern)

**Sources:**[use-cases/openher/integration/context_features.py48-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py#L48-L53)[use-cases/openher/README.md44-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/README.md?plain=1#L44-L67)

---

### Data Flow: From Memory to Behavior

The following diagram illustrates how EverMemOS entities (Code Space) map to the Persona's internal perception (Natural Language Space).

**Memory-to-Persona Mapping**

[Flowchart Diagram]

**Sources:**[use-cases/openher/integration/memory_types.py36-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/memory_types.py#L36-L67)[use-cases/openher/integration/context_features.py37-67](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py#L37-L67)

---

### The EverMemosMixin Lifecycle

Integration is managed via the `EverMemosMixin`, which hooks into the `ChatAgent` lifecycle to perform non-blocking memory operations [use-cases/openher/integration/evermemos_mixin.py1-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L1-L15)

1. **Session Initialization:**`_evermemos_gather()` loads the `SessionContext` (profile, episodes, foresight) at the start of a session [use-cases/openher/integration/evermemos_mixin.py25-47](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L25-L47)
2. **Relationship Evolution:**`_apply_relationship_ema()` blends the EverMemOS prior with per-turn LLM "Critic" feedback using an Exponential Moving Average (EMA) [use-cases/openher/integration/evermemos_mixin.py61-104](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L61-L104)
3. **Async Search Pattern:** To prevent UI freezing, OpenHer uses a "look-ahead" search. Turn $N$ triggers an async search for Turn $N+1$. Results are collected with a 500ms timeout fallback [use-cases/openher/integration/evermemos_mixin.py128-182](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L128-L182)
4. **Background Storage:**`_evermemos_store_bg()` fires a fire-and-forget task to persist the current turn into EverMemOS [use-cases/openher/integration/evermemos_mixin.py106-126](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L106-L126)

For details, see [EverMemosMixin and Session Context](/EverMind-AI/EverOS/14.1-evermemosmixin-and-session-context).

---

### Relationship EMA and Neural Pipeline

The relationship between the user and persona is not static. It evolves using a semi-emergent update pattern where the **Critic LLM** judges the current turn's sentiment and trust, which is then smoothed against the EverMemOS baseline using a depth-modulated alpha [use-cases/openher/demo/evermemos_demo.py151-179](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/demo/evermemos_demo.py#L151-L179)

**Neural Pipeline Summary:**

- **Input (25D):** 5D Drives + 12D Context (8D Turn + 4D EverMemOS) + 8D Recurrent State [use-cases/openher/integration/context_features.py60](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py#L60-L60)
- **Hidden (24D):** Tanh activation layer [use-cases/openher/integration/context_features.py61-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py#L61-L63)
- **Output (8D):** Sigmoid behavioral signals (Directness, Vulnerability, Warmth, etc.) [use-cases/openher/integration/context_features.py22-31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/context_features.py#L22-L31)

For details, see [Neural Network Pipeline and Relationship Evolution](/EverMind-AI/EverOS/14.2-neural-network-pipeline-and-relationship-evolution).

---

### Implementation Summary

The integration is designed for high performance and graceful degradation within the `EverMemosMixin`[use-cases/openher/integration/evermemos_mixin.py17-23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L17-L23)

| Feature | Logic | File Reference |
| --- | --- | --- |
| **Timeout Fallback** | 500ms limit on memory retrieval | [use-cases/openher/integration/evermemos_mixin.py177-182](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L177-L182) |
| **Concurrency Guard** | Turn-ID validation for async tasks | [use-cases/openher/integration/evermemos_mixin.py167-174](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L167-L174) |
| **Alpha Modulation** | Depth-based EMA smoothing ($\alpha \in [0.15, 0.65]$) | [use-cases/openher/integration/evermemos_mixin.py94-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L94-L95) |
| **Client** | `EverMemOSClient` (httpx-based) | [use-cases/openher/demo/evermemos_demo.py38-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/demo/evermemos_demo.py#L38-L128) |

**Sources:**[use-cases/openher/integration/evermemos_mixin.py1-182](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/integration/evermemos_mixin.py#L1-L182)[use-cases/openher/demo/evermemos_demo.py38-179](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/openher/demo/evermemos_demo.py#L38-L179)