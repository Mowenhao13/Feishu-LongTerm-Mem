# CLI Adapter 设计文档

> **分析来源**: Multica (ref/multica), Repo2 (ref/repo2), Repo3 (ref/repo3), Repo1 (ref/repo1)
> **推荐方案**: Multica (主) + Repo2 Adapter 接口 (简化参考)

---

## 1. 分析范围

从 ref/ 的 4+ 个仓库中提取 CLI Adapter 相关的实现，对比后选择最优方案。

| 仓库 | 语言 | CLI 实现 | 设计文档 |
|------|------|---------|---------|
| **multica** | Go | server/pkg/agent/{agent,claude,codex,thinking,models}.go | 生产级，12 个 Agent 后端 |
| **repo2** | Go | src/daemon/adapter/{adapter,claude,codex,command}.go | 简化适配器模式 |
| **repo3** | TypeScript | apps/server/src/adapter/adapter.factory.ts | 工厂 + 中间件链 |
| **repo1** | TypeScript | agent-runtime/src/runtime/ | 运行时抽象 |

---

## 2. 方案对比

### 2.1 Multica (推荐主方案)

**设计定位**: 统一接口执行 prompt，通过子进程管理 CLI 生命周期

**核心接口**:

```go
// agent.go
type Backend interface {
    Execute(ctx context.Context, prompt string, opts ExecOptions) (*Session, error)
}

type ExecOptions struct {
    Cwd                        string
    Model                      string
    SystemPrompt               string
    MaxTurns                   int
    Timeout                    time.Duration
    SemanticInactivityTimeout  time.Duration
    ResumeSessionID            string
    ExtraArgs                  []string
    CustomArgs                 []string
    McpConfig                  json.RawMessage
    ThinkingLevel              string
}

type Session struct {
    Messages <-chan Message     // 流式事件
    Result   <-chan Result      // 最终结果
}

type Message struct {
    Type      MessageType       // text | thinking | tool-use | tool-result | status | error | log
    Content   string
    Tool      string
    CallID    string
    Input     map[string]any
    Output    string
    Status    string
    SessionID string
}
```

**设计特点**:
1. **Channel 架构** — `Messages` 提供流式事件，`Result` 提供最终结果，goroutine-safe
2. **Session 恢复** — `ResumeSessionID` 支持跨对话上下文恢复，`resolveSessionID()` 检测恢复是否真正生效（失败时返回空字符串，让 daemon fallback 创建新 session）
3. **Args 安全过滤** — `filterCustomArgs()` 过滤协议级关键参数（`--output-format`, `--permission-mode`, `--mcp-config` 等），防止用户 custom_args 覆盖 daemon 协议
4. **Env 安全过滤** — `isFilteredChildEnvKey()` 过滤 `CLAUDECODE_*` 环境变量，防止子进程继承父进程的 claude session
5. **MCP Config 管理** — 写入临时文件并通过 `--mcp-config` 传递，确保受控的 MCP Server 集
6. **Thinking Level** — 注入 `--effort` 参数，支持 low/medium/high/xhigh/max

### 2.2 Claude CLI 适配器 (multica)

```go
// claude.go 核心流程
func (b *claudeBackend) Execute(ctx context.Context, prompt string, opts ExecOptions) (*Session, error) {
    // 1. 探测 execPath，设置 Timeout (默认 20min)
    execPath := b.cfg.ExecutablePath // default: "claude"
    exec.LookPath(execPath)
    runCtx, cancel := context.WithTimeout(ctx, timeout)

    // 2. 构建参数: buildClaudeArgs()
    args := []string{
        "-p",                                                                // 非交互模式
        "--output-format", "stream-json",                                    // 流式 JSON 协议
        "--input-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",                            // 自动批准工具调用
        "--disallowedTools", "AskUserQuestion",                              // 禁止交互式问题
    }

    // 3. 启动子进程
    cmd := exec.CommandContext(runCtx, execPath, args...)
    cmd.Dir = opts.Cwd
    cmd.Env = buildEnv(b.cfg.Env)                                           // 过滤子进程环境变量
    stdout, _ := cmd.StdoutPipe()
    stdin, _ := cmd.StdinPipe()

    // 4. 异步写入 prompt (goroutine，防 stdout 阻塞死锁)
    go writeClaudeInput(stdin, prompt)

    // 5. 异步读取 stdout (goroutine)
    scanner := bufio.NewScanner(stdout)
    for scanner.Scan() {
        line := scanner.Text()
        var msg claudeSDKMessage
        json.Unmarshal([]byte(line), &msg)
        switch msg.Type {
        case "assistant": handleAssistant(msg, msgCh, &output, usage)
        case "user":      handleUser(msg, msgCh)
        case "system":    handleSystem(msg, msgCh)
        case "result":    // 最终结果，包含 token usage
        case "log":       handleLog(msg)
        }
    }

    // 6. 等待退出 -> 分类最终状态
    switch {
    case runCtx.Err() == context.DeadlineExceeded: // timeout
    case runCtx.Err() == context.Canceled:          // aborted
    case exitErr != nil:                             // failed (含 stderr tail)
    }

    // 7. 返回 Result
    resCh <- Result{Status, Output, Error, DurationMs, SessionID, Usage}
}
```

### 2.3 Codex CLI 适配器 (multica)

**核心差异**: Codex 使用 JSON-RPC (MCP 风格) 而非 stdin/stdout stream-json

```go
// codex.go 核心流程
func (b *codexBackend) Execute(...) (*Session, error) {
    // 1. 启动 `codex app-server` (JSON-RPC 服务)
    cmd := exec.CommandContext(runCtx, execPath, codexArgs...)

    // 2. JSON-RPC 交互: 通过 codexClient 封装
    c := &codexClient{
        onMessage: func(msg Message) {
            if msg.Type == MessageText { output.WriteString(msg.Content) }
            trySend(msgCh, msg)
        },
        onSemanticActivity: func(description string) {
            // 语义不活跃检测
            trySendString(semanticActivityCh, description)
        },
        onTurnDone: func(aborted bool) { turnDone <- aborted },
    }

    // 3. 超时: 普通超时 + 语义不活跃超时 (默认 30min)
    semanticInactivityTimeout := opts.SemanticInactivityTimeout // default: 30min

    // 4. MCP Config 写入 CODEX_HOME/config.toml (而非 --mcp-config)
    ensureCodexMcpConfig(filepath.Join(codexHome, "config.toml"), opts.McpConfig)
}
```

### 2.4 Repo2 适配器模式 (推荐简化参考)

**设计定位**: 最小公共接口的 CLI 包装器

```go
// adapter.go
type Adapter interface {
    Name() string
    Start(ctx context.Context, prompt string, systemPrompt string) error
    Stream() <-chan StreamChunk
    Stop() error
    IsRunning() bool
}

type StreamChunk struct {
    Type     string    // "text" | "error" | "done" | "artifact"
    Content  string
    Artifact *Artifact
}

// command.go — 通用 stdin/stdout CLI 包装
type CommandAdapter struct {
    name    string
    command string
    args    []string
    cmd     *exec.Cmd
    stream  chan StreamChunk
}

func NewCommandAdapter(name, command string, args []string) *CommandAdapter

// claude.go / codex.go — 一行工厂函数
func NewClaudeAdapter() *CommandAdapter {
    return NewCommandAdapter("Claude Code", "claude", nil)
}
func NewCodexAdapter() *CommandAdapter {
    return NewCommandAdapter("Codex CLI", "codex", nil)
}
```

**优点**: 接口极简 (5 方法)，CommandAdapter 通用化，适合快速原型
**不足**: 缺少参数安全过滤、MCP 管理、Session 恢复、Token Usage 追踪等生产级特性

### 2.5 Repo3 适配器工厂

```typescript
// adapter.factory.ts
class AgentAdapterFactory {
    // 可插拔适配器注册 + 中间件链
    create(type: string, config: AdapterConfig): AgentAdapter
    // 环境密钥回退: process.env[key] ?? process.env[fallbackKey] ?? null
    // 支持: claude, codex, openai, mock
}
```

**特点**: TypeScript 实现，工厂模式 + 环境密钥回退 + 中间件链嵌入
**不足**: 偏上层抽象，未涉及子进程管理细节

---

## 3. 推荐方案: Multica (主) + Repo2 Adapter 接口 (简化参考)

### 3.1 AgentHub 的 CLI Adapter 设计

```
AgentHub Unified Backend Interface
│
├── ClaudeAdapter (主)
│   ├── spawn → `claude -p --output-format stream-json --input-format stream-json`
│   ├── stdin → JSON stream {type:"user", message:{role:"user", content:[{type:"text", text:prompt}]}}
│   ├── stdout → 行级 JSON 解析 (assistant/user/system/result/log)
│   └── control → 自动批准 stdin 回复控制请求
│
├── CodexAdapter (主)
│   ├── spawn → `codex app-server`
│   ├── JSON-RPC 协议 (MCP 风格)
│   ├── MCP Config → CODEX_HOME/config.toml
│   └── 语义不活跃超时检测
│
├── OpenCodeAdapter (扩展)
│   ├── spawn → `opencode run --json`
│   └── 与 claude 模式类似
│
└── CustomAdapter (扩展)
    └── spawn → 任意自定义 CLI
```

### 3.2 关键设计决策

| 决策 | Multica 方案 | AgentHub 选型理由 |
|------|-------------|-------------------|
| **接口设计** | `Execute(prompt, opts) → Session{Messages, Result}` | ✅ 采纳 — Channel 架构天然适合 CLI 流式输出 |
| **参数安全** | `filterCustomArgs` + `isFilteredChildEnvKey` | ✅ 采纳 — 必须防止 user config 覆盖协议参数 |
| **Session 恢复** | `ResumeSessionID` + `resolveSessionID` | ✅ 采纳 — 关键特性，恢复失败时 fallback 创建 |
| **MCP Config** | 临时文件 `--mcp-config` / `config.toml` | ✅ 采纳 — 受控 MCP 注入 |
| **Thinking Level** | `--effort low|medium|high` | ✅ 采纳 |
| **自动批准** | 控制请求 stdin 回复 `allow` | ✅ 采纳 — daemon 模式必须自动批准 |
| **流式格式** | Claude: line-delimited JSON | Codex: JSON-RPC | ✅ 采纳 — 各自协议 |
| **超时策略** | 总超时 + 语义不活跃超时 (Codex) | ✅ 采纳 |
| **Token 跟踪** | `TokenUsage{Input,Output,CacheRead,CacheWrite}` | ✅ 采纳 |

### 3.3 AgentHub 适配器设计

```go
// 采纳 Multica 的 ExecOptions → Session 架构
// 采纳 Repo2 的 Start/Stop 生命周期 (从 Execute 拆分)

type AgentAdapter interface {
    // 统一执行入口 (采纳 Multica)
    Execute(ctx context.Context, prompt string, opts ExecOptions) (*Session, error)
    // 生命周期控制 (采纳 Repo2)
    Start(ctx context.Context, prompt string, opts ExecOptions) error
    Stop() error
    IsRunning() bool
}

// 其他类型定义 -> 直接复用 multica server/pkg/agent/agent.go 的设计
```