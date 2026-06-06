# Claude Code CLI 工具准则

> **分析来源**: Claude Code Tools Reference (https://code.claude.com/docs/zh-CN/tools-reference)
> **适用范围**: AgentHub 多 Agent 协作系统中 Claude Code CLI 的工具使用规范
> **状态**: 设计阶段

---

## 1. 概述

Claude Code CLI 提供了约 30 个内置工具（Bash、Read、Write、Edit、Glob、Grep、Agent 等），但在多 Agent 协作平台中，不能将所有这些工具一视同仁地暴露给所有 Agent。

AgentHub 将工具的使用严格分层，每个层级只能看到和调用与其职责匹配的工具子集：

```
┌──────────────────────────────────────────────────────────┐
│  Layer 1: Coordinator Agent (DAG 规划)                    │
│  可用: 全量工具 + DAG 编排工具                            │
│  职责: Goal → Handoff DAG                                │
├──────────────────────────────────────────────────────────┤
│  Layer 2: Worker Agent (子任务执行)                       │
│  可用: 开发工具 (Read/Write/Bash/Glob/Grep/...)          │
│        + 3 个本地原语 (complete/block/show)              │
│  禁止: 编排工具、Worktree 管理、Agent 通信               │
│  范围: 限制在 Worktree 目录内                             │
├──────────────────────────────────────────────────────────┤
│  Layer 3: 平台运行时 (DAG 状态机)                         │
│  可用: 无 Claude Code 工具                               │
│  驱动: Exit Code / Git commit / Worktree 变化            │
│  决策: 事件驱动 + 状态机硬编码控制                       │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Claude Code CLI 内置工具概览

以下是 Claude Code CLI 所有内置工具的分类。工具名称与 Claude Code 官方文档一致，可以在权限规则、Hook 匹配器和 Subagent 配置中直接引用。

| 工具 | 描述 | 需要权限 |
|------|------|---------|
| `Bash` | 执行 shell 命令 | 是 |
| `Read` | 读取文件内容 | 否 |
| `Write` | 创建或覆盖文件 | 是 |
| `Edit` | 精确字符串替换编辑 | 是 |
| `Glob` | 按模式匹配查找文件 | 否 |
| `Grep` | 在文件内容中搜索模式 | 否 |
| `LSP` | 语言服务器代码智能 | 否 |
| `WebFetch` | 从 URL 获取内容 | 是 |
| `WebSearch` | 执行网络搜索 | 是 |
| `Agent` | 生成 Subagent (独立 context window) | 否 |
| `Monitor` | 后台监视命令输出 | 是 |
| `NotebookEdit` | 修改 Jupyter notebook 单元格 | 是 |
| `PowerShell` | 执行 PowerShell 命令 (Windows) | 是 |
| `AskUserQuestion` | 提出多选问题给用户 | 否 |
| `EnterPlanMode` | 切换到 Plan Mode | 否 |
| `ExitPlanMode` | 提交计划并退出 Plan Mode | 是 |
| `EnterWorktree` | 创建/切换到 Git Worktree | 否 |
| `ExitWorktree` | 退出 Worktree 会话 | 否 |
| `TaskCreate` | 创建新任务 | 否 |
| `TaskGet` | 获取任务详情 | 否 |
| `TaskList` | 列出所有任务 | 否 |
| `TaskUpdate` | 更新任务状态/依赖 | 否 |
| `TaskStop` | 终止运行中的任务 | 否 |
| `CronCreate` | 安排定期提示 | 否 |
| `CronDelete` | 取消计划任务 | 否 |
| `CronList` | 列出计划任务 | 否 |
| `SendMessage` | 向 Agent Team 队友发送消息 | 否 |
| `TeamCreate` | 创建 Agent Team | 否 |
| `TeamDelete` | 解散 Agent Team | 否 |
| `PushNotification` | 发送桌面/手机推送通知 | 否 |
| `Skill` | 执行 Skill | 是 |
| `ToolSearch` | 搜索并加载延迟 MCP 工具 | 否 |
| `ScheduleWakeup` | 重新安排自定步调的下次迭代 | 否 |

---

## 3. 三层工具分层

### 3.1 Layer 1: Coordinator Agent (DAG 规划层)

**角色**: 接收用户 Goal，调用 LLM 将 Goal 分解为 Handoff DAG，定义任务间的依赖关系。

**可用工具**: 全部 Claude Code 内置工具（权限由平台统一控制）

| 工具 | 用途场景 |
|------|---------|
| `AskUserQuestion` | 规划过程中向人类澄清需求歧义 |
| `EnterPlanMode` / `ExitPlanMode` | 复杂目标需要先规划再分解 |
| `TaskCreate` | 在 DAG 中创建 Handoff 任务节点 |
| `TaskGet` / `TaskList` | 查看当前 DAG 状态 |
| `TaskUpdate` | 更新 Handoff 依赖关系、分配 Agent |
| `Glob` / `Grep` / `Read` | 了解项目结构，辅助 DAG 分解决策 |
| `WebSearch` / `WebFetch` | 搜索外部资料辅助规划 |
| `Agent` | 生成探索型 Subagent 进行代码分析 |
| `CronCreate` | 安排定时任务（如定时代码审查） |

**权限范围**: 项目根目录，无目录限制。

**设计原则**: Coordinator 的任务是"想清楚做什么、谁来做、怎么做"——它在规划阶段使用全量工具，一旦规划完成进入执行阶段，其职责就结束了。

---

### 3.2 Layer 2: Worker Agent (子任务执行层)

**角色**: 在隔离的 Worktree 中执行具体的 Handoff 任务，改代码、跑测试、输出成果。

**Worker Agent 是"被关在 Worktree 沙箱里的高级码农"** — 它只能在自己的任务目录内工作，不知道其他 Agent 的存在，也不能影响 DAG 结构。

#### 3.2.1 可用工具

| 工具 | 用途 | 权限范围 |
|------|------|---------|
| `Read` | 读取代码文件 | 限 Worktree 目录 |
| `Write` | 创建或修改文件 | 限 Worktree 目录 |
| `Edit` | 精确编辑文件 | 限 Worktree 目录 |
| `Bash` | 运行命令、测试、构建 | 限 Worktree 目录 |
| `Glob` | 查找文件 | 限 Worktree 目录 |
| `Grep` | 搜索代码内容 | 限 Worktree 目录 |
| `LSP` | 代码智能、类型检查 | 限 Worktree 目录 |
| `Monitor` | 后台监视构建/测试 | 限 Worktree 目录 |
| `WebFetch` | 获取外部文档/API 参考 | 无条件 (研究型任务) |
| `WebSearch` | 搜索技术方案 | 无条件 (研究型任务) |

#### 3.2.2 MCP 本地原语工具（平台注入）

除了 Claude Code 内置工具，Worker Agent 还被注入三个 MCP 工具，作为其与平台交互的唯一通道：

| MCP 工具 | 用途 | 可用时机 |
|---------|------|---------|
| `handoff_complete(summary, metadata)` | 声明任务完成，提交结构化成果 | running 状态 |
| `handoff_block(reason, context)` | 阻塞任务，等待人工或审查介入 | running 状态 |
| `handoff_show()` | 读取当前任务上下文、父任务结果、历史尝试 | 始终可用 |

这些 MCP 工具通过 Claude Code 的 MCP Server 机制注入（在启动 CLI 时通过 `--mcp-servers` 或 `~/.claude/mcp.json` 配置）。

#### 3.2.3 被禁止的工具

Worker Agent 的 `disallowedTools` 配置必须包含以下工具，不允许 Agent 在任何情况下调用：

| 禁止工具 | 原因 |
|---------|------|
| `Agent` | Worker Agent 不能创建子 Agent — 它应该专注自己的任务 |
| `SendMessage` | Agent 之间不应直接通信 — 隔离性原则 |
| `EnterWorktree` | Worker 已经在 Worktree 内，不能切换或创建新的 |
| `ExitWorktree` | Worktree 生命周期由平台管理 |
| `TaskCreate` | Worker 不能创建新的 DAG 任务 |
| `TaskUpdate` | Worker 不能修改 DAG 结构或依赖关系 |
| `TaskStop` | Worker 不能终止其他任务 |
| `CronCreate` / `CronDelete` / `CronList` | Worker 不能安排或取消计划任务 |
| `TeamCreate` / `TeamDelete` | Worker 不能改变团队结构 |
| `EnterPlanMode` / `ExitPlanMode` | Worker 不需要规划模式，只需要执行 |
| `Skill` | Skill 执行权限由平台控制 |

#### 3.2.4 权限范围 (Permission Rules)

Worker Agent 的文件操作权限必须严格限制在 Worktree 目录内：

```yaml
# 权限规则配置 (模拟)
permissions:
  allow:
    - "Read({{worktree_path}}/**)"       # 读取限于 Worktree
    - "Write({{worktree_path}}/**)"       # 写入限于 Worktree
    - "Edit({{worktree_path}}/**)"        # 编辑限于 Worktree
    - "Bash(*)"                           # Bash 命令允许 (通过 Path Whitelist 二次控制)
    - "WebFetch(domain:*)"
    - "WebSearch"
  deny:
    - "Read({{worktree_path}}/.git/**)"   # 禁止读取 .git 内部
    - "Bash(git push *)"                  # 禁止直接推送，由平台管理
    - "Bash(git worktree *)"              # 禁止管理 Worktree
    - "Agent(*)"                          # 禁止创建 Subagent
    - "SendMessage"                       # 禁止跨 Agent 通信
    - "TaskCreate" / "TaskUpdate"         # 禁止修改 DAG
```

#### 3.2.5 Bash 命令限制

Worker Agent 的 Bash 命令受以下限制：

| 命令 | 策略 | 原因 |
|------|------|------|
| `npm test` / `npm run build` | ✅ 允许 | 正常的开发流程 |
| `git add` / `git commit` | ✅ 允许 | Worker 需要提交工作成果 |
| `git push` | ❌ 拒绝 | 由平台状态机自动管理 |
| `git worktree` | ❌ 拒绝 | Worktree 生命周期由平台管理 |
| `gh pr create` | ❌ 拒绝 | PR 由平台状态机自动创建 |
| `cd` | ✅ 允许 | 仅在 Worktree 内有效 |
| `pip install` / `npm install` | ✅ 允许 | 安装任务依赖 |
| `rm -rf` | ✅ 允许 (限 Worktree 内) | 清理临时文件 |

---

### 3.3 Layer 3: 平台运行时 (DAG 状态机)

**角色**: AgentHub 平台的后端服务，不运行任何 Claude Code CLI 实例。

**工具**: 无 Claude Code 工具。平台运行时使用以下**物理信号**驱动状态转换，不经过任何 LLM：

| 信号 | 来源 | 触发动作 |
|------|------|---------|
| Exit Code 0 | CLI 进程正常退出 | Handoff → done，自动 git commit |
| Exit Code ≠ 0 | CLI 进程异常退出 | Handoff → failed |
| handoff_complete() | Agent MCP 工具调用 | 标记完成，等待 exit 0 确认 |
| handoff_block() | Agent MCP 工具调用 | Handoff → blocked，触发通知 |
| Worktree 创建完成 | git worktree add | Handoff → running，准备注入上下文 |
| 超时 (IdleWatchdog) | Daemon 计时器 | Handoff → failed，清理 Worktree |

---

## 4. 工具分层总表

| 工具 | Coordinator | Worker Agent | 平台运行时 |
|------|:-----------:|:------------:|:----------:|
| `Read` | ✅ | ✅ (限 Worktree) | ❌ |
| `Write` | ✅ | ✅ (限 Worktree) | ❌ |
| `Edit` | ✅ | ✅ (限 Worktree) | ❌ |
| `Bash` | ✅ | ✅ (限 Worktree) | ❌ |
| `Glob` | ✅ | ✅ (限 Worktree) | ❌ |
| `Grep` | ✅ | ✅ (限 Worktree) | ❌ |
| `LSP` | ✅ | ✅ (限 Worktree) | ❌ |
| `Monitor` | ✅ | ✅ (限 Worktree) | ❌ |
| `WebFetch` | ✅ | ✅ | ❌ |
| `WebSearch` | ✅ | ✅ | ❌ |
| `AskUserQuestion` | ✅ | ❌ | ❌ |
| `EnterPlanMode` | ✅ | ❌ | ❌ |
| `ExitPlanMode` | ✅ | ❌ | ❌ |
| `TaskCreate` | ✅ | ❌ | ❌ |
| `TaskGet` / `TaskList` | ✅ | ❌ | ❌ |
| `TaskUpdate` | ✅ | ❌ | ❌ |
| `TaskStop` | ✅ | ❌ | ❌ |
| `Agent` | ✅ | ❌ | ❌ |
| `EnterWorktree` | ✅ | ❌ | ❌ |
| `ExitWorktree` | ✅ | ❌ | ❌ |
| `SendMessage` | ✅ | ❌ | ❌ |
| `TeamCreate` / `TeamDelete` | ✅ | ❌ | ❌ |
| `CronCreate` / `CronDelete` | ✅ | ❌ | ❌ |
| `CronList` | ✅ | ❌ | ❌ |
| `Skill` | ✅ | ❌ | ❌ |
| `PushNotification` | ✅ | ❌ | ❌ |
| `handoff_complete()` | ❌ | ✅ (MCP) | ❌ |
| `handoff_block()` | ❌ | ✅ (MCP) | ❌ |
| `handoff_show()` | ❌ | ✅ (MCP) | ❌ |

---

## 5. 工具使用场景

### 5.1 典型 Worker Agent 工作流

Worker Agent 在 Worktree 内的典型操作序列：

```
1. handoff_show()
   → 读取任务描述、验收标准、父任务结果、prior_attempts

2. Glob("**/*.ts") / Grep("class.*Service", path="src/")
   → 了解项目代码结构

3. Read("src/payment/gateway.ts")
   → 读取需要修改的文件

4. Write("src/payment/gateway.ts")
   → 实现支付网关接口

5. Bash("npm run typecheck")
   → 运行类型检查

6. Bash("npm test -- --coverage")
   → 运行测试

7. Bash("git add . && git commit -m 'feat: implement payment gateway'")
   → 提交工作成果

8. handoff_complete(
       summary="implemented payment gateway with Stripe integration",
       metadata={
           "changed_files": ["src/payment/gateway.ts", ...],
           "tests_run": 24,
           "tests_passed": 24,
           "decisions": ["Stripe as primary provider"]
       }
   )

9. exit 0
   → 进程正常退出，平台状态机拦截信号
```

### 5.2 典型 Coordinator Agent 工作流

Coordinator 在规划阶段的典型操作序列：

```
用户: "实现电商支付系统"

1. AskUserQuestion → "需要支持哪些支付渠道？"
   → 用户: "Stripe 和 PayPal"

2. Glob("src/**/*.ts") / Read("package.json") / Read("README.md")
   → 了解项目技术栈

3. TaskCreate → Handoff#1 (DELEGATE → Architect)
   deps: [], title: "设计支付 API 契约"
4. TaskCreate → Handoff#2 (DELEGATE → Backend)
   deps: ["Handoff#1"], title: "实现支付网关"
5. TaskCreate → Handoff#3 (DELEGATE → Frontend)
   deps: ["Handoff#1"], title: "实现前端支付页"
6. TaskCreate → Handoff#4 (REVIEW → Reviewer)
   deps: ["Handoff#2", "Handoff#3"], title: "支付安全审查"

7. ExitPlanMode → 提交 DAG 等待人类确认
```

### 5.3 Handoff Block 场景

Worker Agent 遇到无法自行解决的问题时：

```
1. handoff_show()
   → 发现父任务有循环依赖

2. handoff_block(
       reason="Detected circular dependency between payment.service.ts and user.service.ts",
       context={
           "files": ["src/payment/service.ts", "src/user/service.ts"],
           "suggestion": "Extract shared types to separate module"
       }
   )

3. 平台收到 block → 状态机: running → blocked
   → 通知人类审查

4. 人类审查后 → 手动解除阻塞
   → 状态机: blocked → running

5. Agent 继续执行...
```

---

## 6. 实现方式

### 6.1 通过 Subagent 配置控制 Worker Agent 工具

Worker Agent 的 Claude Code CLI 启动时，通过 Subagent frontmatter 或 `disallowedTools` 参数限制工具：

```yaml
# Worker Agent 的 Subagent 定义 (概念)
name: "worker-payment-gateway"
isolation: worktree
tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - LSP
  - Monitor
  - WebFetch
  - WebSearch
mcp_servers:
  - name: "agenthub-handoff"
    url: "http://localhost:9090/mcp"
```

### 6.2 通过 Permission Rules 限制路径

Worker Agent 的权限配置通过 `--allowedTools` 和 `--disallowedTools` 参数控制：

```bash
# Worker Agent 启动 (概念)
claude \
  --allowedTools "Read({{worktree_path}}/**)" \
  --allowedTools "Write({{worktree_path}}/**)" \
  --allowedTools "Edit({{worktree_path}}/**)" \
  --allowedTools "Bash(*)" \
  --disallowedTools "Agent" \
  --disallowedTools "SendMessage" \
  --disallowedTools "TaskCreate" \
  --disallowedTools "TaskUpdate" \
  --disallowedTools "EnterWorktree" \
  --disallowedTools "ExitWorktree" \
  --disallowedTools "EnterPlanMode" \
  --disallowedTools "ExitPlanMode" \
  --disallowedTools "Skill" \
  --disallowedTools "CronCreate" \
  --disallowedTools "CronDelete" \
  --disallowedTools "CronList" \
  --disallowedTools "TeamCreate" \
  --disallowedTools "TeamDelete"
```

### 6.3 MCP 工具注册

三个本地原语工具通过 MCP Server 注入，不依赖 Claude Code 内置工具集：

```json
{
  "mcpServers": {
    "agenthub": {
      "command": "agenthub",
      "args": ["mcp", "--worktree-id", "{{worktree_id}}"],
      "env": {
        "AGENTHUB_HANDOFF_ID": "{{handoff_id}}",
        "AGENTHUB_TOKEN": "{{session_token}}"
      }
    }
  }
}
```

---

## 7. 设计原则总结

1. **最小权限** — Worker Agent 只获得完成任务所需的最小工具集，不多不少
2. **路径锁定** — 所有文件操作限制在 Worktree 目录内，Worker 无法访问项目其他部分
3. **零编排能力** — Worker Agent 不可见任何能影响 DAG 结构、Agent 分配或团队组成的工具
4. **零通信能力** — Worker Agent 不可见任何跨 Agent 通信工具，Agent 之间保持隔离
5. **三工具接口** — Worker Agent 仅通过 `complete/block/show` 三个 MCP 工具与平台交互
6. **确定性的交接** — 跨 Agent 的接力棒传递由平台状态机通过 Exit Code 硬编码控制，不经过 LLM