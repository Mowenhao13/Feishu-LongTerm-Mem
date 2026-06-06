Runtime 是 Multica 系统中代表 Agent 执行环境的核心概念，它连接了云端服务器和本地机器上的 AI 编程工具 CLI。 [1](#10-0) 

---

## Runtime 核心概念

### 定义
Runtime 是一个计算环境（本地机器或云端实例），能够执行 Agent 任务。它通过本地 Daemon 进程连接到 Multica 服务器，上报可用的 AI 编程工具（Claude Code、Codex、Gemini 等）。 [2](#10-1) 

### 数据库模型
`agent_runtime` 表存储 Runtime 的完整信息： [1](#10-0) 

| 字段 | 说明 |
|------|------|
| `id` | Runtime UUID |
| `workspace_id` | 所属工作区 |
| `daemon_id` | Daemon 进程标识 |
| `provider` | AI 工具类型（claude/codex/gemini 等） |
| `status` | online/offline |
| `last_seen_at` | 最后心跳时间 |
| `visibility` | private/public |

## Runtime 生命周期

### 注册
Daemon 启动时通过 `UpsertAgentRuntime` 注册 Runtime，使用 `(workspace_id, daemon_id, provider)` 作为唯一约束 [3](#10-2) 。

```sql
INSERT INTO agent_runtime (workspace_id, daemon_id, name, runtime_mode, provider, ...)
VALUES ($1, $2, $3, $4, $5, ...)
ON CONFLICT (workspace_id, daemon_id, provider)
DO UPDATE SET last_seen_at = now()
```

### 心跳与离线检测
- Daemon 每 15 秒发送一次心跳更新 `last_seen_at` [4](#10-3) 
- Runtime Sweeper 每 30 秒巡检，超过 150 秒未心跳的 Runtime 标记为 `offline` [5](#10-4) 
- 离线 Runtime 的任务自动标记为失败（`runtime_offline`） [6](#10-5) 

### 垃圾回收
- 7 天未心跳且无活跃 Agent 的 Runtime 会被删除 [7](#10-6) 
- 删除前通过 `DeleteStaleOfflineRuntimes` 确保无 Agent 引用 [8](#10-7) 

## Runtime 与 Agent 的关系

### 绑定关系
每个 Agent 必须绑定到一个 Runtime，通过 `agent.runtime_id` 外键关联 [9](#10-8) 。

### Provider 映射
一个 Daemon 可以检测多个 CLI，每个 CLI 注册为一个独立的 Runtime：

| Provider | CLI 命令 |
|----------|----------|
| claude | `claude` |
| codex | `codex` |
| gemini | `gemini` |
| cursor-agent | `cursor-agent` |
| kimi | `kimi` |
| kiro-cli | `kiro-cli` |

### 访问控制
Runtime 有 `visibility` 字段控制访问权限 [10](#10-9) ：
- `private`：仅 owner/admin 可绑定 Agent
- `public`：任何工作区成员可绑定

## Runtime 管理 UI

### Runtimes 页面
前端在 `Settings → Runtimes` 提供 Runtime 管理界面 [11](#10-10) ：

- **Machine 分组**：按 Local/Remote/Cloud 分组展示
- **状态监控**：在线/离线状态、last_seen 时间
- **Usage 图表**：每日 token 消耗统计
- **Activity 图表**：任务活动情况
- **CLI 版本**：显示可用更新

### 时区覆盖
Runtime 支持时区覆盖，确保用量图表与用户本地时间对齐 [12](#10-11) 。

## Runtime Sweeper 机制

Runtime Sweeper 是后台守护进程，负责维护系统健康 [13](#10-12) ：

```go
func runRuntimeSweeper(ctx context.Context, db *sql.DB) {
    ticker := time.NewTicker(30 * time.Second)
    for {
        select {
        case <-ticker.C:
            // 1. 标记离线 Runtime
            staleRuntimes := SelectStaleOnlineRuntimes(150s)
            MarkRuntimesOfflineByIDs(staleRuntimes)
            
            // 2. 失败孤儿任务
            FailTasksForOfflineRuntimes(staleRuntimes)
            
            // 3. 删除长期离线 Runtime
            DeleteStaleOfflineRuntimes(7 days)
        }
    }
}
```

## 会话恢复与 Runtime

### Session Resumption
Chat Session 通过 `runtime_id` 和 `session_id` 维护执行上下文 [14](#10-13) ：

- `chat_session.runtime_id` 记录最后使用的 Runtime
- `chat_session.session_id` 记录 CLI 的会话 ID
- `chat_session.work_dir` 记录工作目录路径

### Runtime Guard
系统有 Runtime Guard 机制防止跨 Runtime 的会话恢复 [15](#10-14) ：

- 如果 Issue 的上一个任务在不同 Runtime 上执行
- 新任务不会恢复旧的 `session_id`，只恢复 `work_dir`
- 这确保了会话上下文的一致性

## Notes

Runtime 是 Multica 分布式执行架构的核心，它让 Agent 在用户控制的本地环境中运行，而不是在云端服务器。这种设计保证了代码安全、工具链隔离和成本可控。Daemon 作为 Runtime 的本地代理，负责 CLI 探测、任务认领和结果流式传输。

Wiki pages you might want to explore:
- [Runtimes and Agent Providers (multica-ai/multica)](/wiki/multica-ai/multica#10)
- [Glossary (multica-ai/multica)](/wiki/multica-ai/multica#15)

Wiki pages you might want to explore:
- [Runtimes and Agent Providers (multica-ai/multica)](/wiki/multica-ai/multica#10)
- [Glossary (multica-ai/multica)](/wiki/multica-ai/multica#15)

### Citations

**File:** server/pkg/db/generated/models.go (L49-65)
```go
type AgentRuntime struct {
	ID             pgtype.UUID        `json:"id"`
	WorkspaceID    pgtype.UUID        `json:"workspace_id"`
	DaemonID       pgtype.Text        `json:"daemon_id"`
	Name           string             `json:"name"`
	RuntimeMode    string             `json:"runtime_mode"`
	Provider       string             `json:"provider"`
	Status         string             `json:"status"`
	DeviceInfo     string             `json:"device_info"`
	Metadata       []byte             `json:"metadata"`
	LastSeenAt     pgtype.Timestamptz `json:"last_seen_at"`
	CreatedAt      pgtype.Timestamptz `json:"created_at"`
	UpdatedAt      pgtype.Timestamptz `json:"updated_at"`
	OwnerID        pgtype.UUID        `json:"owner_id"`
	LegacyDaemonID pgtype.Text        `json:"legacy_daemon_id"`
	Visibility     string             `json:"visibility"`
}
```

**File:** docs/product-overview.md (L284-300)
```markdown
### 3.5 Runtime 运行时 & Daemon 守护进程

> **角色**：Agent 真正跑起来的物理/虚拟机器。

这是 Multica **分布式执行架构**的核心设计：**agent 不在 server 上运行，而在用户自己的机器上运行**。Server 只做任务调度、状态同步、数据存储。

#### Daemon 是什么

`multica` CLI 在用户的机器上启动一个后台进程（macOS launchd / Linux systemd / Windows 服务风格），它：

1. **自动探测** `$PATH` 上安装的 coding CLI（`claude`, `codex`, `opencode`, `openclaw`, `hermes`, `gemini`, `pi`, `cursor-agent`, `kimi`, `kiro-cli`）
2. 向 server **注册** 为一组 runtime（一个 CLI = 一个 runtime）
3. 每 3 秒 **轮询** 一次 server，有任务就认领
4. 每 15 秒 **心跳**（keepalive），报告自己还活着
5. 认领任务后，在本机的隔离工作目录里**启动 agent CLI**，把 agent 的输出流**实时推回 server**
6. 任务完成后上报结果、token 用量、session id 和工作目录（用于下次恢复）

```

**File:** server/pkg/db/queries/runtime.sql (L32-60)
```sql
-- name: UpsertAgentRuntime :one
-- (xmax = 0) AS inserted distinguishes a fresh insert (true) from an upsert
-- that updated an existing row (false). Analytics reads this to fire
-- runtime_registered/runtime_ready only on first-time registration.
INSERT INTO agent_runtime (
    workspace_id,
    daemon_id,
    name,
    runtime_mode,
    provider,
    status,
    device_info,
    metadata,
    owner_id,
    last_seen_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
ON CONFLICT (workspace_id, daemon_id, provider)
DO UPDATE SET
    name = EXCLUDED.name,
    runtime_mode = EXCLUDED.runtime_mode,
    status = EXCLUDED.status,
    device_info = EXCLUDED.device_info,
    metadata = EXCLUDED.metadata,
    owner_id = COALESCE(EXCLUDED.owner_id, agent_runtime.owner_id),
    last_seen_at = now(),
    updated_at = now()
RETURNING *, (xmax = 0) AS inserted;

-- name: UpdateAgentRuntimeVisibility :one
```

**File:** server/pkg/db/queries/runtime.sql (L62-70)
```sql
-- 'public' (any workspace member can). Default for new rows is 'private'
-- (see migration 083). Gated at the handler layer to owner / workspace
-- admin only.
UPDATE agent_runtime
SET visibility = @visibility, updated_at = now()
WHERE id = @id
RETURNING *;


```

**File:** server/pkg/db/queries/runtime.sql (L268-276)
```sql
-- name: DeleteStaleOfflineRuntimes :many
-- Deletes runtimes that have been offline for longer than the TTL and have
-- no agents bound (active or archived). The FK constraint on agent.runtime_id
-- is ON DELETE RESTRICT, so we must exclude all agent references.
DELETE FROM agent_runtime
WHERE status = 'offline'
  AND last_seen_at < now() - make_interval(secs => @stale_seconds::double precision)
  AND id NOT IN (SELECT DISTINCT runtime_id FROM agent)
RETURNING id, workspace_id;
```

**File:** CLI_AND_DAEMON.md (L169-171)
```markdown
| Poll interval | `--poll-interval` | `MULTICA_DAEMON_POLL_INTERVAL` | `3s` |
| Heartbeat interval | `--heartbeat-interval` | `MULTICA_DAEMON_HEARTBEAT_INTERVAL` | `15s` |
| Agent timeout | `--agent-timeout` | `MULTICA_AGENT_TIMEOUT` | `2h` |
```

**File:** server/pkg/db/generated/runtime.sql.go (L182-191)
```go
			&i.Priority,
			&i.DispatchedAt,
			&i.StartedAt,
			&i.CompletedAt,
			&i.Result,
			&i.Error,
			&i.CreatedAt,
			&i.Context,
			&i.RuntimeID,
			&i.SessionID,
```

**File:** server/internal/handler/daemon_test.go (L2589-2652)
```go
func TestClaimTask_IssuePriorSessionRuntimeGuard(t *testing.T) {
	if testHandler == nil {
		t.Skip("database not available")
	}

	ctx := context.Background()

	agentID, runtimeID, daemonID := createRuntimeGuardAgent(t, ctx)
	oldRuntimeID := createRuntimeGuardRuntime(t, ctx, "kimi")

	var skipIssueID string
	if err := testPool.QueryRow(ctx, `
		INSERT INTO issue (workspace_id, title, status, priority, creator_id, creator_type, number, position)
		VALUES ($1, 'runtime-session-skip fixture', 'in_progress', 'none', $2, 'member', 81203, 0)
		RETURNING id
	`, testWorkspaceID, testUserID).Scan(&skipIssueID); err != nil {
		t.Fatalf("setup: create skip issue: %v", err)
	}
	t.Cleanup(func() { testPool.Exec(ctx, `DELETE FROM issue WHERE id = $1`, skipIssueID) })

	if _, err := testPool.Exec(ctx, `
		INSERT INTO agent_task_queue (
			agent_id, runtime_id, issue_id,
			status, priority, started_at, completed_at,
			session_id, work_dir
		)
		VALUES ($1, $2, $3, 'completed', 0, now(), now(), 'old-runtime-session', '/tmp/old-runtime-workdir')
	`, agentID, oldRuntimeID, skipIssueID); err != nil {
		t.Fatalf("setup: create old-runtime prior task: %v", err)
	}
	if _, err := testPool.Exec(ctx, `
		INSERT INTO agent_task_queue (
			agent_id, runtime_id, issue_id,
			status, priority
		)
		VALUES ($1, $2, $3, 'queued', 0)
	`, agentID, runtimeID, skipIssueID); err != nil {
		t.Fatalf("setup: create current-runtime task: %v", err)
	}

	task := claimTaskForRuntimeGuard(t, runtimeID, daemonID)
	if task.PriorSessionID != "" {
		t.Fatalf("runtime mismatch: expected empty PriorSessionID, got %q", task.PriorSessionID)
	}
	if task.PriorWorkDir != "/tmp/old-runtime-workdir" {
		t.Fatalf("runtime mismatch: expected PriorWorkDir='/tmp/old-runtime-workdir', got %q", task.PriorWorkDir)
	}
	if _, err := testPool.Exec(ctx, `
		UPDATE agent_task_queue
		SET status = 'completed', completed_at = now()
		WHERE issue_id = $1 AND status IN ('dispatched', 'running')
	`, skipIssueID); err != nil {
		t.Fatalf("setup: complete claimed skip task: %v", err)
	}

	var resumeIssueID string
	if err := testPool.QueryRow(ctx, `
		INSERT INTO issue (workspace_id, title, status, priority, creator_id, creator_type, number, position)
		VALUES ($1, 'runtime-session-resume fixture', 'in_progress', 'none', $2, 'member', 81204, 0)
		RETURNING id
	`, testWorkspaceID, testUserID).Scan(&resumeIssueID); err != nil {
		t.Fatalf("setup: create resume issue: %v", err)
	}
	t.Cleanup(func() { testPool.Exec(ctx, `DELETE FROM issue WHERE id = $1`, resumeIssueID) })
```

