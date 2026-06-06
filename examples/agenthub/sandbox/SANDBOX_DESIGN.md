# Sandbox 设计文档

> **分析来源**: Multica (ref/multica), Repo3 (ref/repo3), Repo1 (ref/repo1)
> **推荐方案**: Multica (主) + Repo3 沙箱抽象层 (参考)

---

## 1. 分析范围

| 仓库 | 实现 | 关键文件 |
|------|------|---------|
| **multica** | Go — GC + work_dir 隔离 + 路径锁 | server/internal/daemon/gc.go, execenv/ |
| **repo3** | TypeScript — 沙箱抽象接口 | apps/server/src/sandbox/sandbox.service.ts |
| **repo1** | TypeScript — workspace sandbox + policy | agent-runtime/src/runtime/workspace/{index,sandbox-policy}.ts |

---

## 2. 方案对比

### 2.1 Multica (推荐主方案)

**设计定位**: 每任务独立 work_dir + 垃圾回收 + local_directory 路径锁

#### GC 循环

```go
// gc.go
func (d *Daemon) gcLoop(ctx context.Context) {
    // 启动 30s 后首次执行
    // 周期性 (默认 1h) 扫描 workspace 目录

    // 清理目标:
    //   1. done/cancelled 任务目录 (TTL: 24h)
    //   2. 孤儿目录 — 缺少 meta 文件或 issue 不可达 (TTL: 72h)
    //   3. 制品目录 — node_modules, target, .next 等 (TTL: 12h)

    stats := &gcStats{
        cleaned:         0,  // 已清理的完整任务目录
        orphaned:        0,  // 孤儿目录数
        artifactRemoved: 0,  // 删除的制品子目录数
        bytesReclaimed:  0,  // 释放的总字节数
        byPattern:       map[string]int{},  // 按模式统计
    }
}

type gcStats struct {
    cleaned         int
    orphaned        int
    skipped         int
    artifactDirs    int
    artifactRemoved int
    bytesReclaimed  int64
    byPattern       map[string]int
}
```

**关键设计**: `shouldCleanTaskDir()` 根据 task 状态决定 action (clean/skip/artifact-only)，避免误删正在运行的任务。

#### Work Dir 隔离

每个任务有独立的 work_dir:

```
~/.multica/workspaces/{workspace_id}/
├── {task_id}/                # 每个任务独立目录
│   ├── .multica.meta         # 任务元数据
│   ├── .session_id           # 会话 ID (用于恢复)
│   └── ...                   # Agent 产出的文件
│
└── .repos/                   # 共享仓库缓存 (bare worktree 引用)
```

**local_directory 路径锁**: 当任务绑定到本地目录且另一个任务正在使用该路径时，任务进入 `waiting_local_directory` 状态，使用 Go 的 sync.Mutex + map[string]*sync.Mutex 实现路径级锁定。

### 2.2 Repo3 沙箱抽象层 (参考)

```typescript
// sandbox.service.ts
type SandboxProvider = 'mock' | 'e2b' | 'docker' | 'webcontainer';

interface StartSandboxInput {
  conversationId: string;
  snapshotId: string;
  provider?: SandboxProvider;
}

interface SandboxHandle {
  id: string;
  url: string;
  expiresAt: string;
}

class SandboxService {
  async start(input: StartSandboxInput): Promise<SandboxHandle>
  async stop(id: string): Promise<void>
}
```

**设计定位**: 提供不同类型的沙箱驱动 (mock/e2b/docker/webcontainer)，通过 provider 参数切换。

### 2.3 Repo1 Workspace Sandbox (参考)

```typescript
// sandbox-policy.ts
interface SandboxPolicy {
  allowedCommands: string[];
  allowedPaths: string[];
  readOnlyPaths: string[];
  maxFileSize: number;
  maxProcessCount: number;
}

// workspace-tools.ts — 沙箱内的文件操作工具
// ls, read_file, write_file, edit_file, search, glob, grep
// 所有操作都在 sandbox-policy 约束范围内执行
```

**设计定位**: 基于策略的 sandbox 控制，每个操作受 policy 约束。

---

## 3. 推荐方案: Multica (主) + Repo3 抽象层 (参考)

### 3.1 Sandbox 体系

```
Sandbox Manager
│
├── WorkDir Isolation (Multica + DeerFlow 风格)
│   ├── 每任务独立 work_dir: {workspace}/{task_id}/
│   │   ├── .agenthub.meta           — 任务元数据
│   │   ├── .session_id              — 会话 ID
│   │   └── ...                      — Agent 产出
│   ├── 虚拟路径映射 (DeerFlow 风格)
│   │   └── /mnt/workspace/ → 真实物理路径
│   └── 路径互斥锁 (Multica 风格)
│       └── local_directory 并发任务阻塞
│
├── GC Loop (Multica 风格)
│   ├── 间隔: 1h (默认)
│   ├── 完成任务目录清理 (TTL: 24h)
│   ├── 孤儿目录清理 (TTL: 72h)
│   └── 制品清理 (TTL: 12h)
│       └── 可配置 pattern: ["node_modules", "target", ".next", ...]
│
├── Policy Control (Repo1 风格)
│   ├── 命令白名单: allowedCommands[]
│   ├── 路径白名单: allowedPaths[]
│   ├── 只读路径: readOnlyPaths[]
│   └── 文件大小/进程数上限
│
└── Provider Abstraction (Repo3 风格)
    ├── local: 本地文件系统隔离 (开发/默认)
    ├── docker: 容器化沙箱 (生产)
    └── mock: 测试用
```

### 3.2 关键设计决策

| 特性 | 源项目 | AgentHub 选型 |
|------|--------|--------------|
| Work Dir 隔离 | Multica | ✅ 每任务独立目录 |
| GC 循环 | Multica | ✅ 调整 GC 间隔 + 可配置 TTL |
| 路径互斥锁 | Multica | ✅ local_directory 并发保护 |
| 虚拟路径映射 | DeerFlow | ✅ 可选启用 |
| 沙箱策略 | Repo1 | ✅ 命令/路径白名单 |
| 沙箱 Provider 抽象 | Repo3 | ✅ 支持 local/docker 切换 |
| 容器化沙箱 | DeerFlow | ❌ Phase 1 不做，后续加 |

---

## 4. Claude Code 内置沙箱集成

### 4.1 内置沙箱概览

Claude Code v2.1+ 提供了内置的沙箱化 Bash 工具，在 AgentHub 体系中可作为 Layer 2 安全增强层。

- **macOS**: 基于 Seatbelt framework 实现，无需额外安装依赖
- **Linux/WSL2**: 依赖 bubblewrap + socat，需预先安装
- **原生 Windows**: 不支持沙箱模式，需通过 WSL2 使用

这一层不替代已有的 Multica 工作目录隔离方案，而是在其之上提供操作系统级的强制安全边界。

### 4.2 沙箱边界

**文件系统**: 默认情况下，沙箱内的 Bash 工具只能写入工作目录（workspace）。通过 `allowWrite` 配置可开放额外写入路径，通过 `denyRead` 阻止读取敏感路径，通过 `allowRead` 开放只读访问。所有路径配置均作用于沙箱内的所有子进程。

**网络**: 沙箱启动时无预允许域名。首次访问新域名时，Claude Code 会提示用户批准。通过 `allowedDomains` 预配置可避免交互式批准流程，使用代理时也可指定代理域名白名单。

**OS 级强制**: 沙箱边界由操作系统强制实施，所有子进程（无论由 Bash 直接还是间接启动）继承同一沙箱约束，无法通过派生子进程绕过。

### 4.3 沙箱模式

内置沙箱提供三种运行模式，通过 `--sandbox` 参数控制：

- **Auto-allow 模式** (`--sandbox auto-allow`): 沙箱内的命令自动允许执行，无需每次确认，适用于自动化工作流
- **Regular permissions 模式**: 沙箱内的命令仍需通过常规的权限审批流程，提供更细粒度的控制
- **Strict 模式** (`--sandbox strict`): 设置 `failIfUnavailable=true`，当沙箱无法启用时直接报错退出，禁止降级为无沙箱运行。适用于对安全性有严格要求的场景

### 4.4 沙箱运行时 (Sandbox Runtime)

`@anthropic-ai/sandbox-runtime` 包提供了更彻底的沙箱化方案，它将整个 Claude Code 进程（包括文件工具、MCP 服务器、Hooks）置于同一沙箱边界之内。

- 默认拒绝所有写入和网络访问，需通过配置显式开放
- 相比内置 Bash 沙箱，覆盖范围更大，不仅限于 Bash 工具
- 适用于需要全进程沙箱化的高风险任务

### 4.5 AgentHub 沙箱策略

在 AgentHub 的架构中，Claude Code 内置沙箱的定位如下：

- **Worker Agent**: 利用 Claude Code 内置的沙箱化 Bash 工具，配合路径权限限制（`allowedPaths` / `denyRead`）实现对工作目录的受控访问。Worker 仅需在其独立的 worktree 内操作，天然与内置沙箱的默认权限一致
- **双重隔离**: Worktree 隔离（Multica 风格）提供目录级并发隔离，内置沙箱提供 OS 级强制执行。两者组合，即使 Worker 的 Bash 命令出现异常，也无法逃逸出 worktree 边界
- **沙箱运行时**: 可用于 Coordinator Agent 或需要全进程沙箱化的高风险任务，提供比 Bash 沙箱更广的覆盖范围
- **配置组合**: 通过 `--allowedTools` / `--disallowedTools` 控制工具级权限，结合 `allowRead` / `denyRead` / `allowedDomains` 等沙箱设置，实现多层权限叠加

### 4.6 与已有设计的对比

| 特性 | Multica GC | Repo3 沙箱 | Claude Code 内置沙箱 |
|------|-----------|-----------|-------------------|
| 隔离粒度 | 目录级别 | 进程级别 | OS 级别（Seatbelt/bubblewrap）|
| 网络控制 | 无 | 无 | 域名白名单 + 代理 |
| 子进程覆盖 | 部分 | 全部 | 全部（OS 级强制）|
| 实现成本 | 自研 | 自研 | 零成本（内置）|
| 适用场景 | 并发控制 | 资源隔离 | 安全沙箱 |