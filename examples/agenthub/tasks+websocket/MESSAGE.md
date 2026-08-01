用户与 Agent 的通信不是典型的 message_bus 范式，而是**任务队列 + WebSocket 实时推送**的混合模式。 [1](#14-0) [2](#14-1) 

---

## 通信架构概览

Multica 的用户与 Agent 通信采用以下架构：

```
用户操作 → HTTP API → 任务队列 (agent_task_queue) → Daemon 轮询认领 → Agent CLI 执行
                ↓
            WebSocket 实时推送 (task:message, task:completed 等)
```

## 与 Message Bus 范式的对比

| 特性 | Message Bus 范式 | Multica 实现 |
|------|------------------|-------------|
| 通信模式 | 发布/订阅，无直接寻址 | 任务队列 + WebSocket 广播 |
| 消息路由 | 基于主题/路由键 | 基于 workspace 房间 + 任务 ID |
| 消费者 | 多个消费者竞争消费 | 单一 Daemon 认领（FOR UPDATE SKIP LOCKED） [3](#14-2)  |
| 消息持久化 | 通常支持 | PostgreSQL 持久化队列 |
| 实时性 | 异步，可能有延迟 | WebSocket 实时流式推送 |

## Multica 的实际通信机制

### 1. 任务队列层（核心）
用户与 Agent 的交互通过 `agent_task_queue` 表实现 [4](#14-3) ：

- **入队**：分配 issue、@mention、发送 chat 消息都会创建 task
- **认领**：Daemon 通过 `ClaimTask` 使用 `FOR UPDATE SKIP LOCKED` 认领任务 [3](#14-2) 
- **执行**：Daemon 启动 Agent CLI，流式读取输出
- **状态流转**：queued → dispatched → running → completed/failed [5](#14-4) 

### 2. WebSocket 实时推送层
Server 使用 WebSocket hub 推送事件到前端 [1](#14-0) ：

- **房间模型**：按 workspace 分房间，事件只广播给该房间的连接
- **事件类型**：定义了 60+ 种事件类型（`task:message`、`task:completed`、`comment:created` 等） [6](#14-5) 
- **个人定向推送**：`inbox:new` 等个人事件使用 `SendToUser` 定向推送

### 3. 内部事件总线
Go 后端有一个内部 `events.Bus` 用于服务间解耦 [7](#14-6) ，但这主要用于后端服务之间的通信，不是用户与 Agent 的主要通信通道。

## 为什么不是 Message Bus

1. **有明确的生产者-消费者关系**：用户操作产生 task，Daemon 消费 task，不是多对多的广播
2. **任务有状态**：task 有明确的状态机（queued/dispatched/running/completed），需要持久化和追踪 [5](#14-4) 
3. **执行环境隔离**：每个 task 在独立的 Daemon 工作目录执行，不是共享的执行上下文
4. **流式输出**：Agent CLI 的输出通过 stdin/stdout 流式传输，不是离散的消息 [8](#14-7) 

## Notes

Multica 的设计更接近 **任务队列模式**（Task Queue Pattern）而非 Message Bus。WebSocket 提供了实时通知能力，但核心的 Agent 触发和执行是通过数据库任务队列实现的。内部确实有一个事件总线用于后端服务解耦，但这与用户-Agents 通信是两个不同的层面 [7](#14-6) 。

Wiki pages you might want to explore:
- [Tasks (multica-ai/multica)](/wiki/multica-ai/multica#5.3)
- [Daemon and Task Execution (multica-ai/multica)](/wiki/multica-ai/multica#5.2)

Wiki pages you might want to explore:
- [Documentation Site (apps/docs) (multica-ai/multica)](/wiki/multica-ai/multica#13.2)
- [Glossary (multica-ai/multica)](/wiki/multica-ai/multica#15)

### Citations

**File:** docs/product-overview.md (L787-810)
```markdown
### 实时层（WebSocket）

Server 启动一个 WebSocket hub：

- **鉴权**：URL 参数里的 JWT 或 PAT + workspace_slug
- **房间模型**：按 workspace 分房间，一个 workspace 的事件只广播给该房间的连接
- **个人定向推送**：`inbox:new`, `invitation:created` 等个人事件用 `SendToUser`
- **心跳**：server 每 54 秒 ping，客户端 60 秒内必须 pong

**全部事件类型（供文案参考，共约 60+ 个）**：
- `issue:created` / `issue:updated` / `issue:deleted`
- `comment:created` / `comment:updated` / `comment:deleted` / `reaction:added` / `issue_reaction:added`
- `agent:created` / `agent:status` / `agent:archived`
- `task:dispatch` / `task:progress` / `task:message` / `task:completed` / `task:failed` / `task:cancelled`
- `inbox:new` / `inbox:read` / `inbox:archived` / `inbox:batch-*`
- `workspace:updated` / `workspace:deleted` / `member:added` / `member:updated` / `member:removed`
- `invitation:created` / `invitation:accepted` / `invitation:declined` / `invitation:revoked`
- `chat:message` / `chat:done` / `chat:session_read`
- `skill:created` / `skill:updated` / `skill:deleted`
- `project:created` / `project:updated` / `project:deleted`
- `autopilot:created` / `autopilot:updated` / `autopilot:run_start` / `autopilot:run_done`
- `subscriber:added` / `activity:created`
- `daemon:heartbeat` / `daemon:register`

```

**File:** apps/docs/content/docs/assigning-issues.mdx (L46-55)
```text
## What happens after assignment

When a non-Backlog issue is assigned to an agent, Multica immediately does the following in the background:

1. Enqueues a `queued` `task` with priority inherited from the issue, routed to the runtime where the agent lives.
2. The agent's daemon picks up the `task` on its next poll and transitions it to `dispatched`.
3. The agent starts working and the `task` moves to `running`; on completion it becomes `completed` or `failed`.
4. During execution the agent can change the issue's status, post comments, and edit fields — these actions appear under the agent's identity.

**If the agent is offline**, the `task` waits in the queue — **it times out and fails after 5 minutes** with reason `runtime_offline`. For retryable sources (assign, @-mention, chat), Multica automatically re-enqueues it. See [**Tasks**](/tasks) for the full retry rules.
```

**File:** apps/docs/content/docs/tasks.mdx (L9-11)
```text
A **task** is the unit of every [agent](/agents) run — [assigning an issue to an agent](/assigning-issues), [@-mentioning an agent in a comment](/mentioning-agents), sending a message in [chat](/chat), or an [Autopilot](/autopilots) firing on schedule all produce a task. Multica puts it in a queue; a [daemon](/daemon-runtimes) picks it up and hands it off to the corresponding [AI coding tool](/providers), then writes the result back to the server when it finishes.

Tasks and [issues](/issues) are two different objects. A single issue can be assigned, @-mentioned, and manually rerun many times — each produces a **new** task.
```

**File:** apps/docs/content/docs/tasks.mdx (L15-32)
```text
<Mermaid chart={`
graph LR
    Q["Queued<br/>queued"] -->|daemon picks up| D["Dispatched<br/>dispatched"]
    D -->|agent starts| R["Running<br/>running"]
    R -->|success| C["Completed<br/>completed"]
    R -->|error or timeout| F["Failed<br/>failed"]
    Q -->|user cancels| X["Cancelled<br/>cancelled"]
    D -->|user cancels| X
    R -->|user cancels| X
    F -.retryable reason.-> Q
`} />

- **Queued** — the task was just created and is waiting for a daemon to pick it up
- **Dispatched** — a daemon has claimed it and is starting the AI coding tool
- **Running** — the AI coding tool is actually doing the work
- **Completed** — finished successfully; the output (comments, code commits, status changes) is written back to the server
- **Failed** — aborted with an error or timeout; if the failure reason is retryable, the task automatically returns to `queued` for another attempt
- **Cancelled** — the user cancelled it
```

**File:** server/pkg/protocol/events.go (L1-90)
```go
package protocol

// Event types for WebSocket communication between server, web clients, and daemon.
const (
	// Issue events
	EventIssueCreated         = "issue:created"
	EventIssueUpdated         = "issue:updated"
	EventIssueDeleted         = "issue:deleted"
	EventIssueMetadataChanged = "issue_metadata:changed"

	// Comment events
	EventCommentCreated       = "comment:created"
	EventCommentUpdated       = "comment:updated"
	EventCommentDeleted       = "comment:deleted"
	EventCommentResolved      = "comment:resolved"
	EventCommentUnresolved    = "comment:unresolved"
	EventReactionAdded        = "reaction:added"
	EventReactionRemoved      = "reaction:removed"
	EventIssueReactionAdded   = "issue_reaction:added"
	EventIssueReactionRemoved = "issue_reaction:removed"

	// Agent events
	EventAgentStatus   = "agent:status"
	EventAgentCreated  = "agent:created"
	EventAgentArchived = "agent:archived"
	EventAgentRestored = "agent:restored"

	// Task events (server <-> daemon).
	// Each event maps to a status transition on agent_task_queue. Front-end
	// subscribes by `task:` prefix and invalidates the workspace task
	// snapshot, so the granularity here is "what does the user want to see
	// change" — not "every internal status flip".
	EventTaskQueued                  = "task:queued"                    // ∅ → queued (enqueue / retry create)
	EventTaskDispatch                = "task:dispatch"                  // queued → dispatched (daemon claim)
	EventTaskRunning                 = "task:running"                   // dispatched → running (daemon started)
	EventTaskWaitingLocalDirectory   = "task:waiting_local_directory"   // dispatched → waiting_local_directory (daemon parked on a busy local_directory path)
	EventTaskProgress                = "task:progress"
	EventTaskCompleted               = "task:completed"                 // running → completed
	EventTaskFailed                  = "task:failed"                    // running → failed
	EventTaskMessage                 = "task:message"
	EventTaskCancelled               = "task:cancelled"                 // * → cancelled

	// Inbox events
	EventInboxNew           = "inbox:new"
	EventInboxRead          = "inbox:read"
	EventInboxArchived      = "inbox:archived"
	EventInboxBatchRead     = "inbox:batch-read"
	EventInboxBatchArchived = "inbox:batch-archived"

	// Workspace events
	EventWorkspaceUpdated = "workspace:updated"
	EventWorkspaceDeleted = "workspace:deleted"

	// Member events
	EventMemberAdded   = "member:added"
	EventMemberUpdated = "member:updated"
	EventMemberRemoved = "member:removed"

	// Subscriber events
	EventSubscriberAdded   = "subscriber:added"
	EventSubscriberRemoved = "subscriber:removed"

	// Activity events
	EventActivityCreated = "activity:created"

	// Skill events
	EventSkillCreated = "skill:created"
	EventSkillUpdated = "skill:updated"
	EventSkillDeleted = "skill:deleted"

	// Chat events
	EventChatMessage        = "chat:message"
	EventChatDone           = "chat:done"
	EventChatSessionRead    = "chat:session_read"
	EventChatSessionDeleted = "chat:session_deleted"
	EventChatSessionUpdated = "chat:session_updated"

	// Project events
	EventProjectCreated         = "project:created"
	EventProjectUpdated         = "project:updated"
	EventProjectDeleted         = "project:deleted"
	EventProjectResourceCreated = "project_resource:created"
	EventProjectResourceUpdated = "project_resource:updated"
	EventProjectResourceDeleted = "project_resource:deleted"

	// Label events
	EventLabelCreated       = "label:created"
	EventLabelUpdated       = "label:updated"
	EventLabelDeleted       = "label:deleted"
	EventIssueLabelsChanged = "issue_labels:changed"
```
