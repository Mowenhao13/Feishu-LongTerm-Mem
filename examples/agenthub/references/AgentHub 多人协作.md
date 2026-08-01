# AgentHub 多人协作

## TODO

[TODO](https://tcn400cp6243.feishu.cn/wiki/GPuvwVANUiLelJkE26DcmrginnT)

## 协作

### Light\-agent

[LightAgent/README\.zh\-CN\.md at main](https://github.com/wanxingai/LightAgent/blob/main/README.zh-CN.md)

特点：

- 内置带反思的思维树（ToT）模块，支持复杂任务分解和多步推理，提升任务处理能力。

    - 阶段1：初始规划

使用 ToT 模型生成初始的工具使用计划

system\_prompt 包含工具列表和当前时间信息

\- 阶段2：反思优化

要求模型反思初始回答，严格按照工具列表重新规划

不可以创造新的工具，只输出新的任务规划

\- 阶段3：工具提取

强制 JSON 格式输出，仅提取工具名称

使用 response\_format=\{\&\#34;type\&\#34;: \&\#34;json\_object\&\#34;\} 确保结构化输出

\- 自适应工具过滤：如果启用 filter\_tools，使用 ToolRegistry\.filter\_tools 过滤工具 支持从大量工具中智能筛选相关工具，降低 Token 消耗

- 比Swarm更简单的多智能体协同，内置的LightSwarm实现意图判断和任务转移功能，能够更智能地处理用户输入，并根据需要将任务转移给其他代理。

- 清晰地展示了如何为 Agent 注入“持久化记忆（Memory）

    

### Openai\-agents\-python

https://github\.com/openai/openai\-agents\-python

- REPL 快速验证智能体行为 用于调试

- 上下文策略：本地上下文，llm上下文 [OpenAI\-agent\-python上下文策略](https://tcn400cp6243.feishu.cn/wiki/KDRlwvQTeiS16bkz4P4cghCRnNf)

- agent控制权交接：当 LLM 决定将任务委派给另一个智能体时，它会调用相应的 handoff 工具（默认命名为 transfer\_to\_\&lt;agent\_name\&gt;），控制权随即转移到目标智能体

    

### Deerflow

https://github\.com/bytedance/deer\-flow/blob/main/README\_zh\.md

- Harness与app分离 Harness负责智能体编排、工具集、沙箱环境、模型工厂、记忆管理 app负责API 接口封装、身份验证、第三方平台（飞书/Slack等）集成

- 状态管理：扩展了 LangGraph 的 AgentState，增加了 sandbox（沙箱信息）、artifacts（制品路径）、todos（任务清单）等字段，用于在节点间传递复杂上下文

- 中间件链：

|顺序|中间件名称|核心职责|
|---|---|---|
|1\-3|基础基础设施|`ThreadData` 初始化线程目录，`Uploads` 注入上传文件，`Sandbox` 分配执行环境 `CLAUDE\.md:158\-160`。|
|4\-5|错误处理|`DanglingToolCall` 补全缺失的工具响应，`LLMErrorHandling` 规范化模型调用失败 `CLAUDE\.md:161\-162`。|
|6\-8|安全与审计|`Guardrail` 进行工具调用鉴权，`SandboxAudit` 记录安全日志 `CLAUDE\.md:163\-164`。|
|9\-11|上下文管理|`Summarization` 进行长文本摘要，`TodoList` 管理规划模式任务，`Memory` 异步更新持久化记忆 `CLAUDE\.md:166\-170`。|
|12\-14|视觉与限制|`ViewImage` 注入图片数据，`SubagentLimit` 限制并行子智能体数量 `CLAUDE\.md:171\-173`。|
|15\-18|循环与拦截|`LoopDetection` 阻断死循环，`Clarification` 拦截澄清请求并中断执行（必须最后） `CLAUDE\.md:174\-175`。|

- 沙箱机制：多智能体协作通过共享 thread\_id 来实现对同一个沙箱实例的并发访问和状态同步。[DeerFlow沙箱机制](https://tcn400cp6243.feishu.cn/wiki/K4mUwihodiTUaFkUcMSc4s57nod)

- 上下文工程流：

    - 上下文过长时，SummarizationMiddleware 会压缩历史对话

    - 记忆注入: Memory Middleware 将跨会话的持久化记忆注入到系统提示词中

    - 文件卸载: 中间结果被写入沙箱文件系统，而非保留在上下文窗口中

        

### AI\-Scientist\-v2

[AI\-scientist\-v2](https://tcn400cp6243.feishu.cn/wiki/NFibwIFvUiV8VYk2IQQcxC9vnOc)

#### 核心协作范式的飞跃：从“工作流”到“代理树搜索 \(Agentic Tree Search\)”

传统的项目（如 LangGraph）极其依赖人类预设的有向无环图（DAG）或状态机。Agent 该怎么走第一步、报错了怎么退回，全靠人类工程师在代码里写死。

- **AI Scientist\-v2 的突破**：它抛弃了死板的工作流，引入了 **Agentic Tree Search（代理树搜索）** 算法。

- **它是怎么做的**：系统在面对“提出科学假设并验证”这种长周期、高模糊度的任务时，会将每一步决策（比如：选择方案 A 还是方案 B？代码这样改还是那样改？）看作树的一个分叉。Agent 团队会进行并行探索、回溯（Backtracking）和蒙特卡洛式的路径评估。它允许 Agent **自己发现死胡同、自己斩断错误分支并主动调头**，具有极高的探索自由度。

#### 代码生成的本质改变：脱离“模板依赖”，实现真正的“代码泛化”

在旧版本（v1）或 ChatDev 等传统的多 Agent 编码项目中，Agent 之所以能写出代码，很大程度上依赖于人类提前喂给它的“代码模板”（Code Templates）和严格的脚手架限制。一旦脱离这个特定领域，Agent 就会抓瞎。

- **AI Scientist\-v2 的突破**：实现了**端到端的多阶段实验闭环**。它不需要人类给模板，而是分为四个严密的科学实验阶段：

    1. **初始实现**（自主搭建基础代码与验证）

    2. **基线调优**（超参数多维搜索与测试）

    3. **创新研究**（探索新方法）

    4. **消融实验**（评估各组件贡献度）

- **亮点**：它能有效泛化到完全不同的机器学习和科学领域。Agent 不仅仅是在“写代码”，而是在“通过写代码和跑实验来验证它自己提出的科学假设”。

#### 闭环评测的进化：集成“视觉\-语言模型（VLM）反馈循环”

普通的多 Agent 框架（如 AutoGen），Agent 之间的反馈局限于“纯文本的报错（Traceback）”或 **“JSON 数据对齐”**。

- **AI Scientist\-v2 的突破**：深度集成了 **VLM（视觉\-语言模型）反馈循环**。



### Kanban

#### Kanban 多 agent 调度

[https://www\.xiaohongshu\.com/discovery/item/69f9a0df0000000038037336?source=webshare\&amp;xhsshare=pc\_web\&amp;xsec\_token=ABAOVvZlJ\_SyGqUTFNIY6\_7jLRi76L5WRLNilBmDl6wo8=\&amp;xsec\_source=pc\_share](https://www.xiaohongshu.com/discovery/item/69f9a0df0000000038037336?source=webshare&xhsshare=pc_web&xsec_token=ABAOVvZlJ_SyGqUTFNIY6_7jLRi76L5WRLNilBmDl6wo8=&xsec_source=pc_share)

#### Vibe Kanban

[https://github\.com/BloopAI/vibe\-kanban](https://github.com/BloopAI/vibe-kanban)

### Kanban描述

[https://www\.xiaohongshu\.com/discovery/item/69fe7bdd0000000035031997?source=webshare\&amp;xhsshare=pc\_web\&amp;xsec\_token=ABcGfUuNatlaUGKyK\-9Y9hU3EX4DUYKwKWj5wZYZcdVN4=\&amp;xsec\_source=pc\_share](https://www.xiaohongshu.com/discovery/item/69fe7bdd0000000035031997?source=webshare&xhsshare=pc_web&xsec_token=ABcGfUuNatlaUGKyK-9Y9hU3EX4DUYKwKWj5wZYZcdVN4=&xsec_source=pc_share)

### Kanban机制

[Kanban机制](https://tcn400cp6243.feishu.cn/wiki/MrqCwbMKJiLP9Rk5rZ8cASaYnMc)

#### Hermess Kanban

[Hermes agent Kanban](https://tcn400cp6243.feishu.cn/wiki/LjlYwJzwLi4bDEk5QOicB9PEnjd)

[Hermes handoff 机制](https://tcn400cp6243.feishu.cn/wiki/JIuswVmIliRpxUk7rjbcOvcxnzd)



### Microsoft AutoGen

[https://github\.com/microsoft/autogen](https://github.com/microsoft/autogen)

Agentic AI 沟通框架

#### Multi\-Agent Team

##### 预定义的多智能体团队模式：

|团队类型|描述|使用场景|
|---|---|---|
|`RoundRobinGroupChat`|代理按轮询顺序轮流发言|简单的协作任务，如反思模式|
|`SelectorGroupChat`|使用 LLM 根据上下文动态选择下一个发言者|需要动态协调的复杂任务|
|`Swarm`|代理通过 `HandoffMessage` 主动移交任务控制权|基于工具调用的本地决策|
|`MagenticOneGroupChat`|基于账本协调的通用多智能体系统|复杂的网页和文件任务|
|`GraphFlow`|基于有向图的结构化工作流|需要严格执行顺序的任务|

- 共享上下文：参与者通过向所有其他参与者广播消息来共享上下文

- 发言者选择：不同团队使用不同策略选择下一个发言者（轮询、LLM选择、工具调用等）

#### AgentChat

- **`AssistantAgent`**: 使用语言模型并具有工具调用内置代理，主要用于原型设计和教育目的 

- **`CodeExecutorAgent`**: 专门用于代码生成和执行的代理

- **`UserProxyAgent`**: 用于人工交互的代理

- **`SocietyOfMindAgent`**: 将团队包装为单个代理



## Context隔离

### microsoft/agent\-framework

框架通过以下机制实现context隔离：

[context隔离机制](https://tcn400cp6243.feishu.cn/wiki/A0KkwBVkziyXP8k0o8Yc9N9fnnh)





## Memory

### Benchmarks

- EverMemBench\(评估记忆质量\)

- EvoAgentBench\(评估智能体自我进化能力\)

### Memory结构

#### HyperMem（超图记忆构建）



## AI Observability



## 插件

### Mcp\-ssh\-manager

https://deepwiki\.com/search/\_a0c1208c\-2152\-4a74\-9469\-749bff409326?mode=fast







