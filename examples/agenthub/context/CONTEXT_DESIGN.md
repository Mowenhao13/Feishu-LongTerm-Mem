# Context 设计文档

## 1. 分析范围

- **context隔离机制.md**: MS Agent Framework 的 source_id 归属机制、SessionContext 隔离（input_messages 只读 + context_messages 按 source_id 键入 + instructions/tools 可追加）、消息按 source_id 过滤；Jido 的 Plugin state isolation（state_key 独立命名空间）、Instance-scoped architecture（非全局单例）、InstanceManager（键控单例注册表）
- **OpenAI-agent-python上下文策略.md**: RunContextWrapper 本地上下文 vs LLM 可见上下文、context 对象不发给 LLM（纯本地）、会话状态与上下文分离、ToolContext（工具级元数据）
- **SANDBOX_DESIGN.md**: work_dir 隔离机制、每任务独立工作目录、路径互斥锁
- **MULTI_SESSION_DESIGN.md**: Session Poisoning 检测（三侧检测：output/error/timeout）、session 生命周期管理、并发控制

## 2. 多层 Context 隔离体系

### 2.1 Agent 级 vs Session 级

Agent 拥有 provider 实例（共享），所有 session 共享这些实例；Session 拥有状态数据，每个 session 的状态完全隔离。Provider 实例在 session 间共享，但通过 state 参数传递 provider-scoped 的 mutable state dict，确保每个 session 的状态独立。这种所有权模型将计算资源（Provider）与状态数据（Session）解耦，是实现多层隔离的基础前提。

### 2.2 三层隔离模型（AgentHub 设计）

AgentHub 设计了三个层级的上下文隔离，分别对应不同的隔离粒度和生命周期：

- **L1: Agent 级** — Provider 实例在 Agent 层面共享，包含配置级上下文。Agent 启动时加载的 provider 实例（如 LLM 客户端、工具注册表）在同一 Agent 的所有 session 间复用。此层级提供计算资源的共享，不携带任何会话状态。

- **L2: Session 级** — 单次 Agent 执行会话，互不干扰的 SessionContext。每次 agent.run() 调用创建独立的 SessionContext 实例，包含 input_messages（只读）、context_messages（按 source_id 键入的消息字典）、instructions 和 tools（provider 可追加的列表）。session 之间的上下文完全隔离，一个 session 的崩溃或 poison 不会影响其他 session。

- **L3: Task/Handoff 级** — 单次 Handoff 执行的 work_dir 文件系统隔离。每个 Handoff 任务获得独立的 work_dir（形如 {workspace}/{task_id}/），包含任务元数据、session_id 和 Agent 产出的文件。当任务绑定到本地目录时，路径互斥锁确保同一目录不会同时被多个任务写入。

三层隔离模型从内存中的配置共享（L1），到会话状态隔离（L2），再到文件系统级别的物理隔离（L3），逐层递进，覆盖了 Agent 执行全生命周期的上下文管理需求。

### 2.3 Source-based 消息过滤

借鉴 MS Agent Framework 的 source_id 机制，每个 ContextProvider 拥有唯一的 source_id，用于消息和工具的归属标记。SessionContext.context_messages 使用 dict[str, list[ChatMessage]] 结构，以 source_id 为键存储各 provider 添加的消息。

框架支持按 source_id 过滤消息，provider 可以获取特定来源的消息（get_messages(sources=[...])），也可以排除特定来源的消息（get_messages(exclude_sources=[...])）。这种设计使得不同 provider 产生的消息可以精确路由到需要它们的组件，避免无关消息污染 LLM 的输入窗口，同时为审计和调试提供了清晰的归属链。

### 2.4 Plugin State 隔离

借鉴 Jido 的 state_key 机制，每个插件在 agent.state 中获得独立的命名空间。插件通过 state_key 选项在 agent 的状态中注册自己的命名空间，防止插件之间互相干扰状态。例如，ChatPlugin 使用 state_key: :chat 获得 agent.state.chat 命名空间，DatabasePlugin 使用 state_key: :database 获得 agent.state.database 命名空间。插件只能访问和修改自己命名空间下的状态，不能越界读写其他插件的状态数据。

这种设计确保了插件的可组合性：多个插件可以安全地共存于同一个 Agent 中，而不必担心状态键名冲突或意外篡改。

### 2.5 实例作用域

借鉴 Jido 的 Instance-scoped architecture，AgentHub 采用非全局单例架构，每 Agent 运行时实例拥有独立的 Registry 和 Supervisor。每个 Agent 实例被显式定义并添加到监督树中，拥有独立的组件注册表、任务监督器和 Agent 监督器。

这种架构带来的关键能力包括：
- 多个隔离的 Agent 实例可以在同一应用中运行，互不干扰
- 清晰的所有权和监督边界，每个实例的生命周期独立管理
- 更容易的测试隔离，测试实例不影响生产实例
- InstanceManager 提供键控单例注册表，每个键对应一个 Agent 实例，按需查找或启动，支持空闲超时和附件跟踪

不同于传统的全局单例模式，实例作用域架构将"一个 Agent 实例"作为最小隔离单元，从架构层面杜绝了全局状态的意外共享。

### 2.6 本地上下文 vs LLM 上下文（借鉴 OpenAI Agents）

借鉴 OpenAI Agents Python SDK 的上下文分离策略，AgentHub 将上下文严格区分为两类：

- **本地上下文（RunContextWrapper）**：不发给 LLM，用于依赖注入、日志、状态查询。本地上下文是一个纯本地对象，工具函数运行时、on_handoff 回调、生命周期钩子等可以通过 RunContextWrapper 访问它。常见用途包括：用户身份信息、日志记录器、数据库连接、辅助函数等。本地上下文还包含运行时元数据，如聚合的 token 用量（usage）、工具输入（tool_input）、审批状态（approve_tool/reject_tool）。对于需要工具级元数据的场景，ToolContext 扩展了 RunContextWrapper，额外提供 tool_name、tool_call_id、tool_arguments 等字段。

- **LLM 上下文**：仅通过 system prompt + messages + tools 暴露给 LLM。LLM 唯一能看到的数据来自对话历史。数据注入 LLM 上下文的途径包括：添加到 instructions（系统提示词，可以是静态字符串或接收上下文并输出字符串的动态函数）、添加到 input 消息（在指令链中层级较低）、通过工具调用按需公开（LLM 决定何时调用工具获取数据）、使用检索或网络检索工具从外部源获取数据。

**两者的严格分离**是核心设计原则。本地上下文中可能包含密钥、内部状态、实现细节等不应暴露给 LLM 的敏感信息。通过将本地上下文与 LLM 上下文严格分离，AgentHub 在保证功能完整性的同时，最大程度降低了信息泄露风险。

## 3. AgentHub Context 模型

### 3.1 Context 传递链

Agent 执行 Handoff 时携带的上下文由以下四个部分组成，每个部分承担不同的职责：

- **handoff_context**: 父任务的 summary + metadata + prior_attempts。当 Agent A 将任务 handoff 给 Agent B 时，Agent A 将当前任务的执行摘要、关键元数据（如已完成步骤、关键决策）和先前尝试记录打包为 handoff_context 传递给 Agent B。这使得接收方 Agent 能够理解任务的来龙去脉，避免从头推理。

- **session_context**: 当前 session 的状态 + 历史。包含会话级别的运行时状态，如消息历史、token 消耗统计、已执行工具列表等。session_context 在 session 的整个生命周期内持续累积，跨 Handoff 传递但不会跨 session 共享。

- **work_dir**: 文件系统隔离目录。每个任务获得独立的 work_dir，路径格式为 {workspace}/{task_id}/。work_dir 包含 .agenthub.meta（任务元数据）、.session_id（会话 ID）以及 Agent 产出的所有文件。当 Handoff 发生时，子任务可以选择继承父任务的 work_dir 或创建新的子目录。

- **agent_profile**: Agent 的 instructions + skills + capability_tags。定义了接收方 Agent 的身份和行为边界，包括系统指令集、已注册的技能列表和能力标签。agent_profile 在 Agent 实例化时确定，在 Handoff 传递中作为目标 Agent 的识别和匹配依据。

### 3.2 上下文注入时机

上下文在以下三个关键时机被注入到 Agent 执行流中：

- **Handoff 分配 → 注入 handoff_context**：当 Orchestrator 决定将任务从当前 Agent 移交给另一个 Agent 时，handoff_context 被构造并注入到接收 Agent 的执行环境中。注入时机在接收 Agent 的 before_run 钩子中，确保接收 Agent 在开始执行前就能访问父任务的上下文。

- **Daemon spawn → 注入 agent_profile + work_dir**：当 Daemon 为任务 spawn 新的 Agent 实例时，agent_profile（Agent 的身份和指令集）和 work_dir（隔离的工作目录）被注入到新实例中。注入时机在 Agent 实例初始化阶段，早于任何消息处理。

- **Room 交互 → 注入 session_context**：当 Agent 在 Room（多 Agent 协作空间）中与其他 Agent 交互时，session_context 被注入到交互上下文中。Room 中的每次消息交换都携带当前的 session_context，确保所有参与 Agent 共享一致的会话状态视图。

三个注入时机覆盖了 Agent 执行的完整生命周期：任务分配（Handoff）、实例创建（Daemon spawn）和协作通信（Room），确保上下文在任何执行路径上都能正确传递。

## 4. 对比与选型

| 特性 | MS Agent Framework | OpenAI Agents Python | Jido | AgentHub |
|------|-------------------|-------------------|------|----------|
| 隔离粒度 | source_id | RunContextWrapper | state_key + InstanceManager | 三层隔离（Agent/Session/Task） |
| 消息过滤 | 按 source_id 精确过滤 | 完整对话历史传递 | — | 按 source + session + level 组合过滤 |
| Plugin 隔离 | — | — | state_key 命名空间 | Plugin State 隔离（state_key 命名空间） |
| 实例管理 | — | 单次 run 生命周期 | InstanceManager 键控单例 | Daemon 管理 + InstanceManager |
| 本地/LLM 分离 | 部分（state 参数区分） | 严格分离（RunContextWrapper 不发给 LLM） | — | 严格分离（RunContextWrapper 模式） |
| 文件系统隔离 | — | — | — | work_dir 路径隔离 + GC 循环 |
| Session Poisoning | — | — | — | 三侧检测（output/error/timeout） |

## 5. 推荐方案

AgentHub 的 Context 体系采用组合推荐策略，融合各参考框架的核心优势：

**消息过滤层**采用 MS Agent Framework 的 source_id 机制。每个 ContextProvider 拥有唯一 source_id，消息按 source_id 存储和过滤，支持来源包含和排除两种过滤模式。这为多 Provider 协作场景提供了精确的消息路由能力。

**上下文分层**采用 OpenAI Agents Python SDK 的本地/LLM 严格分离策略。RunContextWrapper 作为纯本地上下文载体，不发给 LLM，用于依赖注入、日志和状态查询；LLM 仅通过 system prompt、messages 和 tools 接触数据。两者之间设定了清晰的边界。

**实例管理**采用 Jido 的 Instance-scoped architecture 和 InstanceManager 键控单例注册表。非全局单例架构确保每个 Agent 运行时实例拥有独立的组件注册表和监督器，InstanceManager 提供按需查找、自动生命周期和可选持久化能力。

**三层隔离模型**是 AgentHub 的核心创新。L1 Agent 级（配置共享）、L2 Session 级（状态隔离）、L3 Task/Handoff 级（文件系统隔离）形成了从内存到磁盘的完整隔离链条。结合 Multica 风格的 work_dir 路径隔离、GC 循环和 Session Poisoning 三侧检测机制，AgentHub 的 Context 体系在借鉴业界最佳实践的基础上，实现了覆盖配置、状态、文件系统和安全性的全面上下文管理方案。