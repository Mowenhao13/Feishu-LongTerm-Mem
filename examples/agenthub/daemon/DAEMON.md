# Claude Code CLI 构建参数

## 核心构建参数

`buildClaudeArgs` 函数在 `server/pkg/agent/claude.go` 中定义，构建传递给 Claude Code CLI 的参数列表： [1](#15-0) 

### 基础参数（硬编码）

```go
args := []string{
    "-p",                                    // 非交互模式
    "--output-format", "stream-json",        // 输出格式
    "--input-format", "stream-json",         // 输入格式
    "--verbose",                             // 详细日志
    "--strict-mcp-config",                  // 严格 MCP 配置
    "--permission-mode", "bypassPermissions", // 绕过权限
    "--disallowedTools", "AskUserQuestion",  // 禁用交互式提问工具
}
```

### 条件参数

| 参数 | 触发条件 | 说明 |
|------|----------|------|
| `--model <value>` | `opts.Model != ""` | 指定模型 |
| `--effort <value>` | `opts.ThinkingLevel != ""` | 思考级别（xhigh/high/medium/low） |
| `--max-turns <value>` | `opts.MaxTurns > 0` | 最大轮次 |
| `--append-system-prompt <value>` | `opts.SystemPrompt != ""` | 附加系统提示 |
| `--resume <value>` | `opts.ResumeSessionID != ""` | 恢复会话 |

### 自定义参数

- `opts.ExtraArgs` - 额外参数（经过过滤）
- `opts.CustomArgs` - 用户自定义参数（经过过滤） [2](#15-1) 

## 参数过滤机制

### 被阻塞的参数

以下参数被硬编码阻塞，用户无法通过 `custom_args` 覆盖： [3](#15-2) 

```go
var claudeBlockedArgs = map[string]blockedArgMode{
    "-p":                blockedStandalone,      // 非交互模式
    "--output-format":   blockedWithValue,       // stream-json 协议
    "--input-format":    blockedWithValue,       // stream-json 协议
    "--permission-mode": blockedWithValue,       // bypassPermissions
    "--mcp-config":      blockedWithValue,       // 由 daemon 设置
    "--effort":          blockedWithValue,       // 由 daemon 注入
}
```

### 过滤逻辑

`filterCustomArgs` 函数会移除被阻塞的协议关键参数，防止破坏 daemon↔agent 通信协议 [4](#15-3) 。

---

# Daemon 工作原理

## Daemon 架构

Daemon 是本地守护进程，负责在用户机器上执行 agent 任务。核心文件在 `server/internal/daemon/` 目录 [5](#15-4) 。

## 启动流程

### 1. 配置加载与 CLI 探测

Daemon 启动时探测 PATH 中可用的 agent CLI： [6](#15-5) 

```go
if e, ok := probe("MULTICA_CLAUDE_PATH", "claude", "MULTICA_CLAUDE_MODEL"); ok {
    agents["claude"] = e
}
// 探测其他 CLI：codex, opencode, openclaw, hermes, gemini, pi, cursor-agent, kimi, kiro-cli
```

### 2. Runtime 注册

向 server 注册每个检测到的 CLI 为一个 runtime： [7](#15-6) 

- 调用 `/api/daemon/register` 端点
- 每个 workspace 注册一组 runtime
- 获取 runtime ID 用于后续任务认领

### 3. 心跳维持

后台 `heartbeatLoop` 每 15 秒发送心跳，保持 runtime 在线状态 [8](#15-7) 。

## 任务执行流程

### 1. 任务轮询

`pollLoop` 每 3 秒轮询 server 认领任务 [9](#15-8) 。

### 2. 原子认领

使用 `FOR UPDATE SKIP LOCKED` 确保多个 daemon 不会认领同一任务 [10](#15-9) 。

### 3. 执行环境准备

`execenv.Prepare` 创建隔离工作目录： [11](#15-10) 

- 创建 `workdir/` 子目录
- 注入元技能文件（CLAUDE.md / AGENTS.md）
- 注入 skills 到 provider 原生路径

### 4. Agent 启动

通过 `agent.New` 创建 provider backend，调用 `Execute` 启动 CLI 进程 [12](#15-11) 。

```go
backend, err := agent.New(provider, agent.Config{
    ExecutablePath: entry.Path,
    Env:            agentEnv,
    Logger:         d.logger,
})
```

### 5. 实时进度上报

- `StartTask` - 标记任务为 running
- `ReportProgress` - 上报步骤和摘要
- `ReportTaskMessages` - 批量上报消息
- `PinTaskSession` - 中途保存 session_id 和 work_dir
- `CompleteTask` / `FailTask` - 完成或失败 [13](#15-12) 

## 并发控制

### 执行槽位

Daemon 使用执行槽位机制控制并发任务数，在认领任务前先获取槽位 [14](#15-13) 。

### 配置参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| Poll interval | `MULTICA_DAEMON_POLL_INTERVAL` | 3s | 轮询间隔 |
| Heartbeat interval | `MULTICA_DAEMON_HEARTBEAT_INTERVAL` | 15s | 心跳间隔 |
| Agent timeout | `MULTICA_AGENT_TIMEOUT` | 2h | Agent 超时 |
| Max concurrent tasks | `MULTICA_DAEMON_MAX_CONCURRENT_TASKS` | 20 | 最大并发任务数 [15](#15-14)  |

## Notes

构建参数的设计确保了 daemon 与 Claude Code CLI 之间的稳定通信协议，通过阻塞关键参数防止用户配置破坏协议。Daemon 采用拉式架构，通过轮询认领任务、原子锁保证唯一性、隔离环境执行、实时上报进度的机制实现可靠的分布式任务执行 [16](#15-15) 。

Wiki pages you might want to explore:
- [Agent Provider Implementations (multica-ai/multica)](/wiki/multica-ai/multica#10.2)
- [Daemon and Task Execution (multica-ai/multica)](/wiki/multica-ai/multica#5.2)

### Citations

**File:** server/pkg/agent/claude.go (L463-479)
```go
// claudeBlockedArgs are flags hardcoded by the daemon that must not be
// overridden by user-configured custom_args. Overriding these would break
// the daemon↔Claude communication protocol.
var claudeBlockedArgs = map[string]blockedArgMode{
	"-p":                blockedStandalone, // non-interactive mode
	"--output-format":   blockedWithValue,  // stream-json protocol
	"--input-format":    blockedWithValue,  // stream-json protocol
	"--permission-mode": blockedWithValue,  // bypassPermissions for autonomous operation
	"--mcp-config":      blockedWithValue,  // set by daemon from agent.mcp_config
	// `--effort` is owned by the per-agent thinking_level picker so a
	// user-supplied custom_arg cannot silently outvote it. The daemon
	// injects --effort only when opts.ThinkingLevel is set; if a user
	// nevertheless writes it in custom_args we drop the duplicate and
	// log a warning rather than letting the CLI receive two conflicting
	// --effort values.
	"--effort": blockedWithValue,
}
```

**File:** server/pkg/agent/claude.go (L481-519)
```go
func buildClaudeArgs(opts ExecOptions, logger *slog.Logger) []string {
	args := []string{
		"-p",
		"--output-format", "stream-json",
		"--input-format", "stream-json",
		"--verbose",
		"--strict-mcp-config",
		"--permission-mode", "bypassPermissions",
		// AskUserQuestion is Claude Code's built-in interactive question tool.
		// The daemon runs Claude in non-interactive stream-json mode and has
		// no UI for the prompt to render in, so a call returns an empty
		// answer and the agent ends up "inferring" silently — the user
		// never sees the question (see GitHub #2588). User-facing
		// clarification belongs in an issue comment instead.
		"--disallowedTools", "AskUserQuestion",
	}
	if opts.Model != "" {
		args = append(args, "--model", opts.Model)
	}
	if opts.ThinkingLevel != "" {
		// Slotted right after --model so the per-session effort runs
		// against the same model selection the args advertise; the CLI
		// itself accepts the flag in any order but this ordering makes
		// the launch line readable in `agent command` logs.
		args = append(args, "--effort", opts.ThinkingLevel)
	}
	if opts.MaxTurns > 0 {
		args = append(args, "--max-turns", fmt.Sprintf("%d", opts.MaxTurns))
	}
	if opts.SystemPrompt != "" {
		args = append(args, "--append-system-prompt", opts.SystemPrompt)
	}
	if opts.ResumeSessionID != "" {
		args = append(args, "--resume", opts.ResumeSessionID)
	}
	args = append(args, filterCustomArgs(opts.ExtraArgs, claudeBlockedArgs, logger)...)
	args = append(args, filterCustomArgs(opts.CustomArgs, claudeBlockedArgs, logger)...)
	return args
}
```

**File:** server/pkg/agent/claude.go (L599-635)
```go
// filterCustomArgs removes protocol-critical flags from user-configured custom
// args to prevent breaking daemon↔agent communication. Each backend defines its
// own blocked set (the flags it hardcodes). This is intentionally narrow — we
// only block args that would break the communication protocol, not every
// possible dangerous flag. Workspace members are trusted to configure agents
// sensibly, same as with custom_env.
func filterCustomArgs(args []string, blocked map[string]blockedArgMode, logger *slog.Logger) []string {
	if len(args) == 0 {
		return args
	}
	filtered := make([]string, 0, len(args))
	skip := false
	for _, arg := range args {
		if skip {
			skip = false
			continue
		}
		// Check if this arg is a blocked flag or starts with "blockedFlag=".
		flag := arg
		hasInlineValue := false
		if idx := strings.Index(arg, "="); idx > 0 {
			flag = arg[:idx]
			hasInlineValue = true
		}
		mode, isBlocked := blocked[flag]
		if isBlocked {
			logger.Warn("custom_args: blocked protocol-critical flag, skipping", "flag", flag)
			if mode == blockedWithValue && !hasInlineValue {
				// The next arg is the value for this flag — skip it too.
				skip = true
			}
			continue
		}
		filtered = append(filtered, arg)
	}
	return filtered
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

**File:** docs/product-overview.md (L735-785)
```markdown
## 4. 系统架构全景

```
┌─────────────────────┐        ┌────────────────────┐        ┌──────────────────┐
│  Next.js Web App    │        │  Electron Desktop  │        │  multica CLI     │
│  apps/web           │        │  apps/desktop      │        │  server/cmd/     │
└──────────┬──────────┘        └──────────┬─────────┘        └────────┬─────────┘
           │  HTTP + WebSocket             │                           │  HTTP
           │                               │                           │
           └──────────────┬────────────────┴───────────────┬───────────┘
                          │                                │
                          ▼                                ▼
              ┌─────────────────────────────────────────────────┐
              │               Go Backend (server/)              │
              │  • Chi HTTP router  • gorilla/websocket hub      │
              │  • sqlc generated queries                        │
              │  • In-process event bus                          │
              │  • Background workers (sweeper / scheduler)      │
              └──────────────────┬──────────────────────────────┘
                                 │
                                 ▼
                      ┌──────────────────────┐
                      │  PostgreSQL 17       │
                      │  + pgcrypto          │
                      │  (28 tables)         │
                      └──────────────────────┘

                                 ▲
                                 │ HTTPS poll + heartbeat
                                 │
              ┌─────────────────────────────────────────────────┐
              │         Local Daemon (用户机器上运行)            │
              │  • 每 3s 认领任务  • 每 15s 心跳                 │
              │  • 探测并启动 agent CLI 子进程                   │
              │  • 为任务准备隔离工作目录                        │
              └───────────────┬─────────────────────────────────┘
                              │ spawns
              ┌───────────────┼─────────────────────────────────┐
              ▼               ▼              ▼              ▼
         Claude Code      Codex         OpenCode      …其他 CLI
         (子进程)         (子进程)      (子进程)
```

### 分层职责

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| **Web / Desktop 客户端** | UI、本地客户端状态（Zustand）、服务器状态缓存（TanStack Query）、WebSocket 订阅 | 业务规则、AI 调用 |
| **Server** | 持久化、权限、任务编排、事件广播、Autopilot 调度、Runtime 健康监测 | 不直接执行 agent、不调 LLM |
| **Daemon** | 探测并启动本地 CLI、管理任务工作目录、流式上报消息、session 恢复 | 不做业务决策、只认 server 给它的任务 |
| **Agent CLI（Claude Code 等）** | 实际调用 LLM、执行工具调用、写文件、跑测试 | 不感知 Multica 的数据模型（所有上下文通过 `multica` CLI 命令读回） |
```

**File:** server/internal/daemon/daemon.go (L277-318)
```go
	d.logger.Info("runtime deleted server-side; pruned from local state",
		"runtime_id", runtimeID, "workspace_id", workspaceID)
	d.notifyRuntimeSetChanged()

	if !d.tryClaimRegisterSlot(workspaceID, entryAt, time.Now()) {
		d.logger.Debug("skip re-register: coalescing with recent attempt",
			"workspace_id", workspaceID)
		return
	}

	err := d.reregisterWorkspaceAfterRuntimeGone(d.recoveryContext(), workspaceID)
	d.recordRegisterCompletion(workspaceID, time.Now(), err)
	if err != nil {
		// Logged at Warn (not Error) because workspaceSyncLoop retries
		// independently every DefaultWorkspaceSyncInterval, so a transient
		// failure here is not a stuck state — just an extra wait.
		d.logger.Warn("re-register after runtime gone failed",
			"workspace_id", workspaceID, "error", err)
	}
}

// tryClaimRegisterSlot atomically decides whether the calling goroutine should
// run registerRuntimesForWorkspace. Returns true and claims the in-flight slot
// when the caller may proceed; returns false (without mutating state) when the
// call must be coalesced with a peer.
//
// Two gates are checked under runtimeGoneMu:
//
//  1. reregisterNextAttempt: a future timestamp means a peer holds the slot or
//     a previous attempt failed and we are inside the failure backoff window.
//  2. reregisterLastCompletedAt: a timestamp at or after our entryAt means a
//     peer's register SUCCEEDED after we entered handleRuntimeGone, so the
//     workspace state is already covered for our wave and we can bail.
//     Failures intentionally don't stamp this field (see
//     recordRegisterCompletion), so a same-wave straggler whose entryAt
//     predates a failed sibling can still retry once the failure backoff
//     expires — failures don't cover anything.
//
// entryAt is the wall-clock captured at the top of handleRuntimeGone. now is
// passed in (rather than read inside) so tests can drive the gate
// deterministically without sleeping.
func (d *Daemon) tryClaimRegisterSlot(workspaceID string, entryAt, now time.Time) bool {
```

**File:** server/internal/daemon/daemon.go (L456-492)
```go
	}
	for _, rt := range resp.Runtimes {
		d.runtimeIndex[rt.ID] = rt
	}
	// Response is authoritative — replace, do not append. Replacing also
	// catches the rare case where UpsertAgentRuntime returns a different ID
	// for a surviving provider (e.g. schema change); the daemon converges on
	// what the server says without leaving stale heartbeat goroutines.
	ws.runtimeIDs = newIDs
	if resp.ReposVersion != "" {
		ws.reposVersion = resp.ReposVersion
		ws.allowedRepoURLs = repoAllowlist(resp.Repos)
	}
	if len(resp.Settings) > 0 {
		ws.settings = resp.Settings
	}
	d.mu.Unlock()

	for _, rid := range newIDs {
		d.logger.Info("re-registered runtime after server-side deletion",
			"workspace_id", workspaceID, "runtime_id", rid)
	}
	d.notifyRuntimeSetChanged()

	// Tell the server about any tasks the previous (now-deleted) runtime
	// was working on, mirroring the registration path's recover-orphans call.
	for _, rid := range newIDs {
		if err := d.client.RecoverOrphans(ctx, rid); err != nil {
			d.logger.Warn("recover-orphans after re-register failed",
				"runtime_id", rid, "error", err)
		}
	}
	return nil
}

// runtimeSetWatcher is a tiny pub/sub for runtime-set changes. It exists
// because more than one supervisor (taskWakeupLoop, heartbeatLoop, pollLoop)
```

**File:** server/internal/daemon/daemon.go (L630-669)
```go
	}

	// Deregister runtimes on shutdown (uses a fresh context since ctx will be cancelled).
	defer d.deregisterRuntimes()

	// Start workspace sync loop to discover newly created workspaces.
	go d.workspaceSyncLoop(ctx)

	taskWakeups := make(chan struct{}, 1)
	go d.taskWakeupLoop(ctx, taskWakeups)
	go d.heartbeatLoop(ctx)
	go d.gcLoop(ctx)
	go d.autoUpdateLoop(ctx)
	go d.serveHealth(ctx, healthLn, time.Now())
	d.logger.Debug("background loops launched (workspace-sync, task-wakeup, heartbeat, gc, auto-update, health)")
	err = d.pollLoop(ctx, taskWakeups)
	d.logger.Debug("daemon main loop returning", "error", err)
	return err
}

// RestartBinary returns the path to the new binary if the daemon needs to restart
// after a successful update, or empty string if no restart is needed.
func (d *Daemon) RestartBinary() string {
	return d.restartBinary
}

// deregisterRuntimes notifies the server that all runtimes are going offline.
func (d *Daemon) deregisterRuntimes() {
	runtimeIDs := d.allRuntimeIDs()
	if len(runtimeIDs) == 0 {
		d.logger.Debug("deregister: no runtimes to deregister")
		return
	}

	d.logger.Debug("deregistering runtimes on shutdown", "count", len(runtimeIDs), "runtime_ids", runtimeIDs)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := d.client.Deregister(ctx, runtimeIDs); err != nil {
		d.logger.Warn("failed to deregister runtimes on shutdown", "error", err)
```

**File:** server/internal/daemon/daemon.go (L1839-1862)
```go
// runRuntimePoller is the per-runtime claim+dispatch loop. It owns its own
// poll cadence and wakeup channel so that a slow HTTP claim for this runtime
// cannot delay any other runtime's claims.
//
// The execution slot is acquired BEFORE ClaimTask. The alternative —
// claiming first and then waiting for a slot — would let claimed tasks pile
// up in the server-side `dispatched` state without a corresponding
// StartTask, and the server's sweeper would fail them as `failed/timeout`
// after dispatchTimeoutSeconds=300s (runtime_sweeper.go:25). That is the
// exact user-visible failure this issue is fixing, so we cannot risk
// recreating it under load.
//
// Slot-before-claim does mean a slow claim holds a slot during its HTTP
// roundtrip; the upper bound is `client.Timeout = 30s` (client.go:59), well
// below the 300s dispatch timeout, so other runtimes' tasks stay in
// server-side `queued` state (which has no timeout) rather than entering
// `dispatched` and racing the sweeper.
//
// pollerCtx is cancelled when this runtime is removed from the watched set
// (e.g. workspace de-registered). parentCtx is the daemon's root ctx and is
// passed to handleTask so an in-flight task is not killed just because the
// runtime set changed mid-flight — the task continues to run until the
// daemon itself shuts down (or the server cancels it).
func (d *Daemon) runRuntimePoller(
```

**File:** server/internal/daemon/daemon.go (L2575-2582)
```go
	backend, err := agent.New(provider, agent.Config{
		ExecutablePath: entry.Path,
		Env:            agentEnv,
		Logger:         d.logger,
	})
	if err != nil {
		return TaskResult{}, fmt.Errorf("create agent backend: %w", err)
	}
```

**File:** apps/docs/content/docs/cli/reference.zh.mdx (L112-120)
```text
Daemon behavior is configured via flags or environment variables:

| Setting | Flag | Env Variable | Default |
|---------|------|--------------|---------|
| Poll interval | `--poll-interval` | `MULTICA_DAEMON_POLL_INTERVAL` | `3s` |
| Heartbeat interval | `--heartbeat-interval` | `MULTICA_DAEMON_HEARTBEAT_INTERVAL` | `15s` |
| Agent timeout | `--agent-timeout` | `MULTICA_AGENT_TIMEOUT` | `2h` |
| Max concurrent tasks | `--max-concurrent-tasks` | `MULTICA_DAEMON_MAX_CONCURRENT_TASKS` | `20` |
| Daemon ID | `--daemon-id` | `MULTICA_DAEMON_ID` | hostname |
```
