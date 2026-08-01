# Handoff 设计文档

> **分析来源**: Hermes kanban handoff、AutoGen/Swarm HandoffMessage、ref/handoff.md（OMA/AdaptOrch 事件驱动编排）、AgentHub Orchestrator Handoff DAG
> **状态**: 设计阶段

---

## 1. 分析范围

| 来源 | 核心机制 | 关键贡献 |
|------|---------|---------|
| **Hermes handoff** | `kanban_complete(summary, metadata)` 结构化输出；review-required 阻塞模式；`kanban_show()` 读取父任务与历史尝试 | 结构化工作结果传递、人类审查门禁、历史失败路径回溯 |
| **AutoGen / Swarm HandoffMessage** | `HandoffMessage` 特殊消息类型；Handoff 类转工具函数触发交接；Swarm 团队通过 HandoffMessage 选择发言者 | 工具化触发交接、上下文自动注入 |
| **ref/handoff.md (OMA/AdaptOrch)** | 宏观编排层：事件驱动状态机硬交接（Exit Code 拦截、Git commit、worktree 生命周期）；微观执行层：Function Calling 本地原语 | 分层设计原则："外部靠图，内部靠喊" |
| **AgentHub Orchestrator Handoff DAG** | Handoff Packet 即工作单元；DAG 依赖图拓扑排序；Scheduler 四种调度策略 | DAG 编排引擎、依赖解析与级联失败 |

---

## 2. 核心设计原则：两层 Handoff

Handoff 机制必须严格区分为两个层面，每个层面采用完全不同的交接方式：

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: 宏观 DAG 编排层                                │
│                                                         │
│  交接方式: 事件驱动 + 状态机                              │
│  执行者: 平台适配层 (Engine/Orchestrator)                │
│  触发信号: Exit Code / Git commit / Worktree 变化       │
│  Token 消耗: 零                                          │
│  Agent 感知: Agent 不知道其他 Agent 存在                  │
│                                                         │
│  ┌─────┐  exit 0  ┌─────────┐  deps met  ┌─────┐       │
│  │Task1│ ────────► │ State   │ ──────────► │Task2│       │
│  │Done │  事件拦截  │ Machine │  状态机决策  │激活 │       │
│  └─────┘           └─────────┘            └─────┘       │
└─────────────────────────────────────────────────────────┘
                            │
                            平台内部决策，不经过 LLM
                            │
┌─────────────────────────────────────────────────────────┐
│  Layer 2: 微观子任务内部                                  │
│                                                         │
│  交互方式: Function Calling (仅 3 个本地原语工具)          │
│  执行者: Worker Agent (被关在 Worktree 沙箱里)            │
│  可用工具: complete / block / show                        │
│  禁止工具: delegate / review / handover / query / notify  │
│                                                         │
│  Agent 在 Worktree 内:                                    │
│    ┌─────────────────────────────────┐                   │
│    │ handoff_show() → 读取上下文      │                   │
│    │   ... 修改文件、跑测试 ...       │                   │
│    │ handoff_complete() → 提交成果    │                   │
│    │   exit 0 → 平台拦截 → 状态机      │                   │
│    └─────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

### 2.1 为什么宏观编排不能用 Function Calling

如果让 Worker Agent 内部通过 Function Calling 决定传给谁，会带来三个致命缺陷：

1. **非确定性** — Agent 执行完代码后可能报错、产生幻觉、乱调函数传错人。LLM 的输出不可控，不能作为编排层的决策依据
2. **破坏 DAG 解耦** — 如果 Agent A 必须知道 Agent B 的存在才能调用 handoff 函数，就违背了高隔离原则。Agent 之间应该不知道彼此存在
3. **浪费 Token** — 每次跨 Agent 交接都经过 LLM 的 function_calling，Token 消耗呈线性增长，Agent 越多浪费越大

### 2.2 工业级做法：事件驱动与状态机硬交接

宏观编排层的交接完全由平台适配层的工程代码控制，LLM 处于被动接受状态：

```text
1. [Claude Code CLI 在 Worktree-A 中执行完毕，进程正常退出 (Exit Code 0)]
                             │
                             ▼ (物理信号拦截)
2. [平台适配层 Engine 捕获到退出信号] ──► 自动执行: git commit & merge
                             │
                             ▼ (更新看板状态机)
3. [状态机检测 Task-1 完成] ──► 标记 Task-1 为 DONE
                             │
                             ▼ (检查依赖图)
4. [Task-2 的依赖全部解除] ──► 自动激活 Task-2
                             │
                             ▼ (拉起新 Worktree)
5. [平台拉起 Worktree-B，唤醒 Codex CLI 进驻] ──► 注入 Task-2 上下文
```

在这个过程中，Claude 根本不知道自己把接力棒传给了谁，Codex 也不知道是谁帮它开的路。交接完全是平台利用 Exit Code、Git 和状态机硬编码实现的，**没有消耗任何 Function Calling 的 Token**。

---

## 3. 微观子任务内部：本地原语工具 (Function Calling)

虽然宏观交接不用 Function Calling，但在**单个子任务内部（Worker Agent 的 Worktree 沙箱里）**，Function Calling 是 Agent 与平台进行交互的唯一通道。

Agent 在 Worktree 内被注入一组高度封装的**本地原语工具**，只能操作自己的任务，无法影响其他 Agent。

### 3.1 可用工具

| 工具 | 对应 Hermes | 用途 | 可用时机 |
|------|-----------|------|---------|
| `handoff_complete(summary, metadata)` | kanban_complete | 完成任务，提交结构化工作成果 | running 状态 |
| `handoff_block(reason, context)` | kanban_block + kanban_comment | 阻塞任务等待人工/审查介入 | running 状态 |
| `handoff_show()` | kanban_show | 读取当前任务的上下文、父任务结果、历史尝试 | 始终可用 |

**工具行为说明**：

- **handoff_complete** — Agent 调用此工具声明任务完成。平台收到此调用后，不会立即认为任务结束，而是等待 CLI 进程退出 (exit 0) 作为最终确认。Agent 在调用时需提供 `summary`（人类可读的完成摘要）和 `metadata`（结构化事实数据，如 changed_files、tests_run、decisions 等）
- **handoff_block** — Agent 在遇到无法自行解决的问题时调用（如循环依赖、需要人类决策、需要跨 Agent 信息）。调用时携带 `reason` 和 `context`，平台收到后暂停此任务的执行计时，等待外部介入
- **handoff_show** — Agent 随时调用以获取当前任务的完整上下文。包括任务描述、父任务的完成结果 (summary + metadata)、历史尝试记录 (prior_attempts)、验收标准等

### 3.2 被禁止的工具

Agent **绝不可见**以下涉及跨 Agent 编排的工具：

| 工具 | 原因 |
|------|------|
| `handoff_delegate(target, ...)` | Agent 不能决定谁来做子任务 |
| `handoff_review(target, ...)` | Agent 不能指定审查者 |
| `handoff_handover(target, ...)` | Agent 不能主动交接给其他 Agent |
| `handoff_query(target, ...)` | Agent 不需要知道其他 Agent 的存在 |
| `handoff_notify(target, ...)` | 通知由平台状态机自动广播 |

这些跨 Agent 的操作由宏观编排层的状态机统一决策，Worker Agent 完全不需要关心。

### 3.3 工具注册时机

工具根据任务上下文动态注入：

- **handoff_show()** 始终可用 — Agent 启动时默认注入
- **handoff_complete()** 仅当任务处于 running 状态时可用 — Daemon 在 spawn CLI 时注入
- **handoff_block()** 始终可用 — Agent 启动时默认注入

> 注意：这里没有任何"给其他 Agent 委派"的工具。Agent 在自己的 Worktree 沙箱内是孤立的。

---

## 4. 宏观 DAG 编排：事件驱动状态机

这是整个平台的核心编排机制，完全由平台代码控制，不经过任何 LLM。

### 4.1 状态机模型

每个 Handoff 在 DAG 编排层经历以下状态流转：

```
                  ┌─────────┐
                  │ pending │  ← Coordinator 创建 Handoff 后
                  └────┬────┘
                       │
                  ┌────▼────┐
                  │ ready   │  ← 依赖全部解除，等待调度
                  └────┬────┘
                       │
                  ┌────▼────┐
                  │running  │  ← Daemon 拉起 CLI，Agent 进驻 Worktree
                  └────┬────┘
                       │
              ┌────────┼────────┐
              ▼        ▼        ▼
          ┌──────┐ ┌──────┐ ┌──────┐
          │ done │ │blocked│ │failed│
          └──────┘ └──────┘ └──────┘
```

**状态说明**：

| 状态 | 说明 | 触发方式 |
|------|------|---------|
| **pending** | Handoff 已创建，但依赖尚未全部满足 | Coordinator 生成 DAG 时 |
| **ready** | 所有依赖已解除，等待 Daemon 认领调度 | 状态机检测依赖图自动推进 |
| **running** | Agent 正在 Worktree 中执行 | Daemon 轮询认领后 spawn CLI |
| **done** | 任务完成，成果已提交 | Agent 调用 handoff_complete + exit 0 |
| **blocked** | 等待人工审查或外部介入 | Agent 调用 handoff_block |
| **failed** | 执行过程中发生不可恢复错误 | 进程非零退出 / 超时 |

### 4.2 状态机触发信号

状态转换不依赖 LLM，而是由以下**确定性物理信号**触发：

| 信号 | 来源 | 触发转换 |
|------|------|---------|
| **Exit Code 0** | CLI 进程正常退出 | running → done |
| **Exit Code ≠ 0** | CLI 进程异常退出 | running → failed |
| **Git commit** | Agent 或平台自动提交 | running 期间持续记录 |
| **Worktree 创建完成** | Git worktree add 成功 | ready → running |
| **Worktree 清理完成** | Git worktree remove 成功 | done → 清理 |
| **handoff_complete()** | Agent 的 function_call | 触发状态机检查，等待 exit 0 |
| **handoff_block()** | Agent 的 function_call | running → blocked |
| **超时** (AgentIdleWatchdog) | Daemon 计时器 | running → failed |

### 4.3 DAG 依赖解析

状态机内部维护 DAG 的依赖图，自动处理以下逻辑：

```text
Handoff 创建时: 所有 Handoff 初始为 pending

每轮状态变化后:
  1. 检查所有下游 Handoff 的 dependencies 是否全部为 done
  2. 如果全部满足: 该 Handoff 从 pending → ready
  3. ready 的 Handoff 进入 Daemon 轮询队列

并行触发:
  Handoff#2 depends on Handoff#1
  Handoff#3 depends on Handoff#1
  → Handoff#1 done 后, #2 和 #3 同时变为 ready → 并行执行

级联失败:
  Handoff#4 depends on Handoff#2 AND Handoff#3
  → 如果 #2 failed, #4 自动变为 skipped (无需执行)
```

### 4.4 与 Daemon 的对接

Daemon 轮询的是 **ready 状态的 Handoff**（而非 Task），执行流程：

```text
1. Daemon 轮询 → ClaimHandoff(runtimeID) → 拿到一个 ready 的 Handoff
2. 创建独立 Worktree → git worktree add
3. Handoff 状态: ready → running
4. 注入 Agent 上下文 (handoff_show 数据)
5. 注册本地原语工具 (complete / block / show)
6. spawn CLI 子进程
7. 监控 Exit Code
8. Exit 0 → 状态机: running → done
9. Exit ≠ 0 → 状态机: running → failed
```

---

## 5. Handoff 与看板同步

Handoff 状态机的每次状态变化同步反映在看板 Issue 上：

| Handoff 状态 | 看板 Issue 状态 |
|------------|---------------|
| pending | Backlog |
| ready | Todo |
| running | InProgress |
| done | Done |
| blocked | Blocked |
| failed | Cancelled |

**看板作为可视化界面**：看板提供 Handoff DAG 的人类可读视图，每个 Issue 卡片展示 handoff 的 title、assignee、status 以及已完成 handoff 的 summary 和 metadata 摘要。人类可通过看板直观地追踪整个工作流的进展，也可在看板上直接操作状态（如手工将 blocked 的 Issue 解除阻塞）。

---

## 6. Handoff 上下文传递

上下文传递是保证多 Agent 协作连续性的关键机制，分为两个层面独立处理。

### 6.1 宏观层面：状态机自动传递

当 Handoff 从 pending → ready 时，状态机自动完成以下操作：

- 收集所有父 Handoff 的 summary 和 metadata
- 收集 prior_attempts 历史记录
- 打包为结构化上下文，等待注入到即将启动的 Agent

这些操作是平台代码自动执行的，不消耗 Token。

### 6.2 微观层面：Agent 通过 handoff_show 读取

Agent 在 Worktree 启动后，通过 `handoff_show()` 读取：

- **任务描述**：当前 Handoff 的 title、description、acceptance_criteria
- **父任务结果**：上游已完成工作的 summary 和 metadata
- **prior_attempts**：当前任务的历史失败记录（outcome、error），避免重复错误路径
- **context_refs**：指向外部上下文资源的引用（文档、先前输出等）

---

## 7. 推荐方案

AgentHub 的 Handoff 体系采用分层设计："**外部靠图 (DAG)，内部靠喊 (Function Calling)**"

| 层面 | 机制 | 控制方 | 是否经过 LLM | Token 消耗 |
|------|------|--------|------------|-----------|
| 宏观 DAG 编排 | 事件驱动 + 状态机 | 平台适配层代码 | ❌ 不经过 | 零 |
| 微观子任务内部 | Function Calling (3 个本地工具) | Worker Agent | ✅ 经过 LLM | 仅任务内 |
| Coordinator 规划 | LLM 规划输出 DAG | Coordinator Agent | ✅ 仅规划阶段 | 一次性 |

**关键约束**：
- Worker Agent 被关在 Worktree 沙箱里，只能改文件、跑测试、调用 `complete/block/show`
- Worker Agent 绝不可见任何涉及跨 Agent 编排的工具（`delegate/review/handover/query/notify`）
- 跨 Agent 的接力棒传递，由平台状态机通过 Exit Code / Git / Worktree 生命周期硬编码控制
- 这样设计，就用确定性的系统工程代码彻底抽离并控制住了黑盒 LLM 的不确定性