# Orchestrator 设计文档

> **分析来源**: Multica (ref/multica), OpenMultiAgent (ref/open-multi-agent), Repo3 (ref/repo3), Repo1 (ref/repo1), Repo2 (ref/repo2)
> **推荐方案**: OMA Coordinator (规划层) + AgentHub Handoff DAG (统一协作与执行层) + Multica Daemon (执行层)

---

## 1. 分析范围

| 仓库 | 实现 | 关键文件 |
|------|------|---------|
| **open-multi-agent** | TypeScript — Coordinator Goal-First 分解 + TaskQueue DAG + Scheduler | src/orchestrator/orchestrator.ts, task/queue.ts, task/task.ts, orchestrator/scheduler.ts, types.ts, agent/pool.ts |
| **multica** | Go — Daemon poll loop + 任务调度 + 崩溃恢复 | server/internal/daemon/daemon.go, server/pkg/agent/agent.go |
| **repo3** | TypeScript — Planner + Critic + Mention Router | apps/server/src/orchestrator/{planner,critic}.service.ts, conversation/mention-router.ts |
| **repo1** | TypeScript — OrchestratorExecutor | agent-runtime/src/runtime/orchestrator-executor.ts |
| **repo2** | Go — 任务文档 | doc/task/M4-多Agent接入.md, M5-Orchestrator.md |

---

## 2. 方案对比

### 2.1 OpenMultiAgent Coordinator (推荐主方案 — 规划层)

#### 核心哲学: Goal-First, 不是 Graph-First

> "Your engineers describe the goal, not the graph."
> "Graph-first frameworks make you enumerate every node and edge up front. OMA is goal-first: you describe the outcome and the coordinator builds the handoff DAG at runtime."

**三层 API 设计**:

| 模式 | 方法 | 适用场景 |
|------|------|---------|
| 单 Agent | `runAgent()` | 一个 Agent 一个 prompt |
| 自动编配团队 | `runTeam()` | 给 Goal, Coordinator 自动分解执行 |
| 显式管线 | `runTasks()` | 用户手动定义 Handoff Graph 和分配 |

#### runTeam 三部曲

```
Phase 1: Planning — Coordinator Agent 将 Goal 分解为 Handoff DAG
    planOnly=true → 只生成不执行，人类审查
    planOnly=false → 生成后自动执行

Phase 2: Validation — onPlanReady 门禁 (可选)
    返回 false → 整个运行取消
    返回 true → 进入执行

Phase 3: Execution — HandoffQueue + Scheduler + AgentPool
    while (仍有 pending handoff):
        1. Scheduler.autoAssign(queue, agents) ← 每轮自动分配
        2. queue.getByStatus('pending') ← 所有依赖已满足的 handoff
        3. 并行派发到 AgentPool
        4. 完成 → queue 自动解锁依赖者
        5. onApproval 门禁 (可选): 审查每轮结果
        6. 重复直到无 pending handoff
```

#### Handoff DAG 模型 (OMA 原始 Task 概念已融入 Handoff)

在 AgentHub 的统一模型中，OMA 的 Task 实体被直接吸收为 Handoff Packet，不再存在独立的 Task 概念。每个 Handoff Packet 就是一个可调度的工作单元，携带依赖关系、分配目标和输出。

```typescript
// Handoff Packet — 既是任务单元，也是协作消息
interface HandoffPacket {
  id: string                     // 唯一标识
  title: string                  // 任务标题
  description: string            // 任务描述
  status: HandoffStatus          // pending | running | completed | failed | skipped | blocked
  dependencies: string[]         // 依赖的 Handoff ID 列表
  assignee: string               // 分配的 Agent 名称
  output?: string                // 执行输出
  error?: string                 // 错误信息
  metadata?: Record<string, unknown>  // 扩展元数据
}

type HandoffStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'blocked'
```

#### HandoffQueue — 带依赖图/拓扑排序的队列

```typescript
// 核心职责:
//   1. 依赖图管理 — 支持任意深度嵌套的依赖
//   2. 拓扑排序 — 按依赖顺序决定执行优先级
//   3. 自动解锁 — handoff 完成时自动标记依赖满足
//   4. 级联失败 — 关键路径失败 → 标记下游为 blocked
//   5. 执行追踪 — 完整记录每 handoff 执行状态和时间

class HandoffQueue {
  handoffs: Map<string, HandoffPacket>

  add(handoff: HandoffPacket): void           // 添加 handoff
  addAll(handoffs: HandoffPacket[]): void     // 批量添加
  getByStatus(status: HandoffStatus): HandoffPacket[]  // 按状态查询
  getPending(): HandoffPacket[]               // 获取所有可执行 handoff (依赖已满足)
  markCompleted(id: string, output: string): void   // 自动解锁下游
  markFailed(id: string, error: string): void       // 级联标记失败
  skipRemaining(reason: string): void               // 跳过全部余下 handoff
  isEmpty(): boolean
  size(): number

  // 事件系统 — onProgress 实时回调
  on(event: 'handoff:completed' | 'handoff:failed' | 'handoff:skipped', cb: Function): void

  // 拓扑排序 (内部实现)
  private topologicalSort(): string[]  // 按拓扑序排列所有 handoff
}
```

#### Scheduler — 4 种调度策略

```typescript
type SchedulingStrategy = 'dependency-first' | 'round-robin' | 'least-busy' | 'capability-match'

class Scheduler {
  // 核心: 自动为每个 pending handoff 选择最优 Agent
  autoAssign(queue: HandoffQueue, agents: AgentConfig[]): void

  // 模式 1: dependency-first (默认)
  //   优先执行阻塞最多后续 handoff 的 handoff
  //   减少总执行时间的最优策略

  // 模式 2: round-robin
  //   轮流分配给 Agent，适合简单、同质的 handoff 集

  // 模式 3: least-busy
  //   分配给当前最空闲的 Agent (负载最小)
  //   适合 handoff 执行时间差异大的场景

  // 模式 4: capability-match
  //   按 Agent 的 tools/systemPrompt 语义匹配 handoff
  //   适合需要特定技能的复杂 handoff
}
```

#### AgentPool — 并行执行引擎

```typescript
class AgentPool {
  availableRunSlots: number      // 剩余可用槽位

  // 核心: 在池中并行运行 handoff
  async run(handoff: HandoffPacket, opts: RunOptions): Promise<AgentRunResult>
  async runEphemeral(agent: Agent, prompt: string, opts: RunOptions): Promise<AgentRunResult>

  // 并行执行方法
  async runAll(handoffs: HandoffPacket[]): Promise<Map<string, AgentRunResult>>
}
```

#### 生命周期钩子

```typescript
interface OrchestratorConfig {
  // 进度事件 (每 handoff/agent 状态变化触发)
  onProgress?: (event: OrchestratorEvent) => void

  // 计划批准门禁 — 在首次执行前触发
  onPlanReady?: (handoffs: HandoffPacket[]) => boolean | Promise<boolean>

  // 每轮完成后的批准门禁
  onApproval?: (completed: HandoffPacket[], next: HandoffPacket[]) => boolean | Promise<boolean>

  // 追踪 span (LLM 调用/工具调用/任务执行)
  onTrace?: (span: TraceSpan) => void

  // Agent 流式输出
  onAgentStream?: (chunk: AgentStreamChunk) => void
}
```

#### 团队上下文注入 (revealCoordinator)

```typescript
// 当 revealCoordinator=true 时, 每个 Worker prompt 自动注入:
//
// ## Team context
// Goal: 实现电商支付系统
// Team: Architect, Backend, Frontend, Reviewer
// Your role in this team: Architect
// Assignment: You are responsible for the handoff below in this team run.
```

#### Delegation 机制

```typescript
// 通过 delegate_to_agent 工具实现嵌套委派
// 安全机制:
//   - 最大委派深度 (maxDelegationDepth): 防无限递归
//   - 委派链追踪 (delegationChain): 检测循环委派 (A→B→A)
//   - 池满检测: 槽位不足时直接返回错误而非死锁

async function runDelegatedAgent(targetAgent: string, prompt: string): Promise<AgentRunResult> {
  if (pool.availableRunSlots < 1) {
    return { success: false, output: '池满，无可用并发槽位' }
  }
  // ... 创建临时 Agent, 注入团队上下文, 执行
}
```

### 2.2 Multica Daemon (推荐主方案 — 执行层)

#### 核心架构

```
Daemon (常驻进程)
│
├── CLI 探测 & 注册 (启动时)
│   ├── exec.LookPath("claude"), exec.LookPath("codex"), ...
│   ├── 检测版本
│   └── POST /api/daemon/register → 为每个 workspace 注册 runtime
│
├── 心跳 (持续运行)
│   ├── WebSocket 主心跳: 15s/次
│   └── HTTP 降级: 15s/次 (WS 断开时启用)
│
├── 任务轮询 (每 runtime 独立 goroutine)
│   ├── slot-before-claim 并发控制
│   │   └── 首次获取 slot → 然后 ClaimTask → 成功则执行
│   ├── 默认最大并发: 20
│   └── 每 3s 轮询一次 (强制休眠)
│
├── 任务执行 (handleTask)
│   ├── 路径锁 → 解锁或等待
│   ├── StartTask(taskID) → 状态: running
│   ├── spawn 子进程 (agent.Backend.Execute)
│   ├── 5s/次 检测取消
│   └── CompleteTask / FailTask (重试机制)
│
├── 崩溃恢复
│   ├── runtime 消失 → 重新注册 + RecoverOrphans
│   ├── 孤儿任务 → 标记失败
│   └── 优雅关闭 (SIGTERM, 30s 等待)
│
├── GC 循环 (1h/次)
│   └── 过期 work_dir 清理
│
├── Session 管理
│   ├── session_id + work_dir 持久化
│   ├── Session Poisoning 检测
│   │   └── 输出侧: 已知 fallback marker
│   │   └── 错误侧: LLM API 400 (恢复必然重现)
│   │   └── 超时侧: Codex 语义不活跃
│   └── GetLastTaskSession 过滤 poisoned session
│
└── 自动更新 (6h/次)
    └── 检查新版 → 下载 → 替换二进制 → 重启
```

#### 关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| PollInterval | 30s | 任务轮询间隔 |
| HeartbeatInterval | 15s | 心跳间隔 |
| AgentTimeout | 2h | Agent 执行超时 |
| AgentIdleWatchdog | 30min | 静默强制停止 |
| MaxConcurrentTasks | 20 | 最大并发数 |
| GCInterval | 1h | GC 间隔 |
| GCTTL | 24h | 完成任务目录保留时间 |
| GCOrphanTTL | 72h | 孤儿目录保留时间 |
| GCArtifactTTL | 12h | 制品保留时间 |

#### Poll Loop 设计

```go
// 每个 runtime 一个 poller goroutine
func (d *Daemon) runRuntimePoller(ctx context.Context, runtimeID string, provider string) {
    for {
        select {
        case <-ctx.Done(): return
        default:
            slot := <-d.taskSlots         // 1. 获取 slot
            d.tryEnterClaim()             // 2. auto-update barrier
            task, err := d.client.ClaimTask(ctx, runtimeID)  // 3. 认领
            if task == nil {
                d.taskSlots <- slot       // 归还 slot
                sleepWithContext(ctx, d.cfg.PollInterval)
                continue
            }
            go d.handleTask(ctx, task, slot, provider, runtimeID)  // 4. 异步执行
        }
    }
}
```

### 2.3 Repo3 Planner + Critic + Mention Router (参考)

#### Planner: 将 Goal → Plan (DAG)
#### Critic: 评估 Plan 和执行结果质量
#### Mention Router: 解析 @mention → 路由到指定 Agent

---

## 3. 推荐方案 — 统一 Handoff DAG

### 3.1 为什么一个 DAG 就够了

现有设计包含两个 DAG 概念：

- **Task DAG** — OMA Coordinator 在 Planning 阶段输出的逻辑任务分解图
- **Handoff DAG** — AgentHub 协作层定义的 Agent 间消息传递与依赖关系图

这两者在本质上描述的是同一件事：**"为了达成目标，需要哪些工作单元，以及它们之间的依赖关系"**。Task DAG 是"what"，Handoff DAG 是"how"——但在实际系统中，what 和 how 从来不需要分开建模。

**统一为一个 Handoff DAG 的理由：**

1. **工作单元即消息**：每个 Handoff Packet 本身就是一份完整的工作描述（title + description + dependencies + assignee），无需额外的 Task 实体来包装它。Handoff Packet 的 `status` 字段天然承载任务生命周期，`dependencies` 字段天然承载 DAG 拓扑。

2. **消除转换开销**：Task → Handoff 转换是一个纯机械的映射步骤（Task.title → Handoff.title, Task.dependencies → Handoff.dependencies, ...），没有信息增益，只有运行时开销和额外的出错面。

3. **单一事实来源**：一个 DAG 意味着 Planning 阶段产出的结构直接进入执行，不存在"Plan DAG"和"Execution DAG"可能产生分歧的问题。人类审查 DAG 时看到的就是实际执行的 DAG。

4. **简化编程模型**：使用者只需理解 Handoff DAG 这一个概念。生命周期钩子、调度策略、持久化、可观测性——所有机制都围绕同一个实体构建。

### 3.2 统一后的架构：双层而非三层

统一 Handoff DAG 后，原三层架构（Planning → Collaboration → Execution）压缩为双层：

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: Planning Layer (Coordinator Agent — 参照 OMA)             │
│                                                                      │
│  runTeam(goal) 三部曲:                                               │
│    Phase 1: Planning                                                 │
│      Coordinator Agent (LLM) 将 Goal → Handoff DAG                  │
│      planOnly → 展示 DAG, 等人类审查                                 │
│                                                                      │
│    Phase 2: Validation (Optional)                                    │
│      onPlanReady: 人类/程序审查 DAG → 批准/拒绝                       │
│      onApproval:  每轮结果审查                                        │
│                                                                      │
│    Phase 3: Execution                                                │
│      HandoffQueue.autoAssign(agents) → 拓扑排序 → 并行派发           │
│      4 调度策略: dependency-first / round-robin / least-busy /       │
│                  capability-match                                    │
│      Dependency-first (默认): 优先执行阻塞最多下游的 handoff          │
│      AgentPool 并行执行 → queue 自动解锁 → 再次派发                  │
│      全部完成 → Coordinator 结果合成                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: Execution Layer (Daemon — 参照 Multica)                    │
│                                                                      │
│  Handoff Dispatcher → POST /api/daemon/runtimes/.../tasks/claim     │
│  Daemon 轮询 → slot-before-claim → spawn Claude/Codex CLI           │
│  流式输出 → 进度事件 → 任务完成/失败                                 │
│  崩溃恢复 + Session Poisoning + GC                                   │
└─────────────────────────────────────────────────────────────────────┘
```

关键变化：原 Collaboration Layer 被消除，其职责（Handoff 状态管理、依赖解析、Event Store 持久化）并入 Planning Layer 的 HandoffQueue 和 Execution Layer 的 Dispatcher。Handoff DAG 不再是一个"中间转换层"，而是贯穿 Planning 到 Execution 的唯一数据结构。

### 3.3 统一 Handoff DAG 的执行流程

```
用户: "实现电商支付系统"
    │
    ▼
Phase 1 — Planning (Coordinator Agent)
    │
    ├── Coordinator Agent (LLM) 分解 Goal
    │   └── 输出 Handoff DAG:
    │       ├── Handoff#1: 设计 API 契约   → assignee=Architect, deps=[]
    │       ├── Handoff#2: 实现支付网关    → assignee=Backend,  deps=[Handoff#1]
    │       ├── Handoff#3: 实现前端支付页  → assignee=Frontend, deps=[Handoff#1]
    │       └── Handoff#4: 安全审查       → assignee=Review,   deps=[Handoff#2, Handoff#3]
    │
    ├── onPlanReady (可选) — 人类确认 DAG
    │
    ▼
Phase 2 — Validation (依赖解析 + 门禁)
    │
    ├── HandoffQueue.topologicalSort() 校验依赖无环
    ├── onPlanReady 门禁: 展示 Handoff DAG, 等待批准
    │
    ▼
Phase 3 — Execution (HandoffQueue + Scheduler + Daemon)
    │
    ├── 首轮: Handoff#1 (Architect) → Daemon 轮询认领 → 执行
    ├── Handoff#1 完成 → queue 自动解锁 Handoff#2、Handoff#3
    ├── 次轮: Handoff#2 (Backend) + Handoff#3 (Frontend) 并行
    ├── 两者完成后 → 解锁 Handoff#4 (Review)
    └── 全部完成 → Coordinator 结果合成
        └── "支付系统已完成: API + 前端 + 审查通过"
```

关键变化：不再有"Task → Handoff 转换"步骤。Coordinator 输出的就是最终执行的 Handoff DAG，直接进入 Validation 和 Execution 阶段。

### 3.4 OMA 调度策略在统一 Handoff DAG 中的运用

| 策略 | 说明 | AgentHub 映射 |
|------|------|--------------|
| **dependency-first** (默认) | `topologicalSort()` → 优先执行阻塞最多下游的 handoff | HandoffQueue 拓扑排序，同 OMA |
| **round-robin** | 同层级 Agent 轮流分配 | 在 Role Pool 内轮询 |
| **least-busy** | 选池中最空闲 Agent | 统计 Daemon 当前负载 + slot 使用率 |
| **capability-match** | 按 Agent tools 语义匹配 handoff | 按 Agent capability_tags 精确匹配 |

### 3.5 生命周期钩子

| OMA 钩子 | 触发时机 | AgentHub 映射 |
|----------|---------|--------------|
| `onProgress` | 每 handoff/agent 状态变化 | → WebSocket Room 广播 |
| `onPlanReady` | Handoff DAG 生成后, 执行前 | → Room Board 展示 DAG, 人类确认 |
| `onApproval` | 每轮完成后 | → Handoff REVIEW 或人类审查 |
| `onAgentStream` | Agent 流式输出 | → WS message.streaming 事件 |
| `onTrace` | LLM/工具/任务 span | → Event Store 持久化 + DAG dashboard |

### 3.6 统一 Handoff DAG 的关键设计决策

| 特性 | OMA 方案 | 统一 Handoff DAG 方案 |
|------|---------|---------------------|
| **规划输出** | Task DAG | Handoff DAG (直接可执行) |
| **工作单元** | Task → 再转换为 Handoff | Handoff Packet 即工作单元 |
| **转换步骤** | Task→Handoff 映射 | 不存在 |
| **DAG 数量** | 2 个 (Task DAG + Handoff DAG) | 1 个 (Handoff DAG) |
| **目标分解** | Coordinator Agent (LLM) | Coordinator Agent (LLM) — 不变 |
| **调度策略** | 4 种 | 4 种 — 不变 |
| **计划门禁** | onPlanReady 审查 Handoff DAG | onPlanReady 审查 Handoff DAG |
| **执行引擎** | AgentPool (LLM API) | Daemon (CLI spawn) — 不变 |
| **任务轮询** | — | Multica 3s polling — 不变 |
| **并发控制** | pool semaphore | slot-before-claim — 不变 |
| **崩溃恢复** | — | 孤儿回收 + 重新注册 — 不变 |
| **Delegation** | delegate_to_agent | @mention / 结构化委派 — 不变 |
| **结果合成** | Coordinator 汇总 | Coordinator 汇总 — 不变 |
| **DAG 持久化** | 内存 | Event Store (AgentHub) — 不变 |
| **可观测性** | onProgress+onTrace | Event Store + Dashboard — 不变 |

---

## 4. 方案对比总表

| 维度 | OMA (原方案) | Multica | Repo3 | AgentHub (统一 Handoff DAG) |
|------|-------------|---------|-------|---------------------------|
| **规划能力** | Coordinator Agent 分解 Goal | 无 | Planner + Critic | Coordinator Agent 分解 Goal |
| **DAG 模型** | Task DAG | 无独立 DAG | Plan DAG | **单一 Handoff DAG** |
| **Task 实体** | Task (独立类型) | Task (Daemon 级别) | Step | **无** — Handoff Packet 即任务 |
| **Task→Handoff 转换** | 需要 | 不涉及 | 不涉及 | **不需要** |
| **调度策略** | 4 种 | 无 (FIFO) | 无 | 4 种 — 直接调度 Handoff |
| **执行模型** | AgentPool (in-process) | Daemon (CLI spawn) | Express 服务 | Daemon (CLI spawn) |
| **计划门禁** | onPlanReady | 无 | Critic 评估 | onPlanReady |
| **持久化** | 内存 | 文件系统 | 数据库 | Event Store |
| **崩溃恢复** | 无 | 孤儿回收 + Session Poisoning | 无 | 孤儿回收 + Session Poisoning |
| **可观测性** | onProgress + onTrace | Activity Log | 日志 | Event Store + Dashboard |