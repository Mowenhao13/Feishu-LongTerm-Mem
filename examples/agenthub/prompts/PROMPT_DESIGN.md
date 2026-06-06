# System Prompts 设计文档

> **分析来源**: Multica (ref/multica), Repo3 (ref/repo3), Repo1 (ref/repo1)
> **推荐方案**: Multica (主) + Repo3 PromptRole 模板引擎 (参考)

---

## 1. 分析范围

| 仓库 | 实现 | 关键文件 |
|------|------|---------|
| **multica** | Go — BuildPrompt 4 种任务类型 | server/internal/daemon/prompt.go |
| **repo3** | TypeScript — PromptRole 模板库 + renderTemplate | packages/prompts/src/index.ts |
| **repo1** | TypeScript — system-agents prompt 定义 | agent-runtime/src/runtime/system-agents.ts |

---

## 2. 方案对比

### 2.1 Multica BuildPrompt (推荐主方案)

**设计定位**: 根据 task 类型构造不同的 prompt，通过 execenv 注入上下文。

```go
// prompt.go
func BuildPrompt(task Task, provider string) string {
    switch {
    case task.ChatSessionID != "":
        return buildChatPrompt(task)        // 聊天任务
    case task.TriggerCommentID != "":
        return buildCommentPrompt(task, provider)  // 评论触发任务
    case task.AutopilotRunID != "":
        return buildAutopilotPrompt(task)   // 自动运行任务
    case task.QuickCreatePrompt != "":
        return buildQuickCreatePrompt(task) // 快速创建任务
    default:
        // 默认: Issue 分配任务
        return "issue_get + comment_list: 读取任务上下文后执行"
    }
}
```

#### 4 种 Prompt 类型

| 类型 | 触发条件 | Prompt 内容 |
|------|---------|------------|
| **chat** | `ChatSessionID != ""` | 直接嵌入 `ChatMessage` + 附件列表，Agent 直接回复 |
| **comment** | `TriggerCommentID != ""` | 嵌入触发评论内容 + 作者类型(人/Agent) + Squad leader no_action 规则 + 评论阅读指引 |
| **quick-create** | `QuickCreatePrompt != ""` | 完整的 Issue 创建指南 (title/description/priority/assignee/project/parent 字段规则 + 输出格式) |
| **autopilot** | `AutopilotRunID != ""` | 嵌入 autopilot 配置 + 触发 payload + 运行说明 |
| **default** | — | Issue ID + `multica issue get` + `multica issue comment list` 指引 |

#### Comment Prompt 的关键设计

```go
func buildCommentPrompt(task Task, provider string) string {
    // 1. 注入触发评论 (含 author_type 判断)
    if task.TriggerAuthorType == "agent" {
        // Agent 互发时的防循环规则:
        //   - 产生了实际工作 → 正常回复
        //   - 纯确认/感谢 → 不回复 (silence = best)
        //   - 回复时不要 @mention 对方 (防循环)
    }

    // 2. Squad Leader no_action 规则
    if task.Agent.Instructions contains "Squad Operating Protocol" {
        // 不需要行动 → 只记录 squad activity，不发评论
    }

    // 3. 评论阅读策略
    switch {
    case hint := BuildNewCommentsHint(): // 有新评论 → 增量读取
    case task.PriorSessionID != "":      // 恢复会话 → 读取触发线程
    default:                            // 冷启动 → 读取触发线程
    }

    // 4. 回复指令 (每个 turn 重新注入, 防 session 残留)
    execenv.BuildCommentReplyInstructions(provider, issueID, triggerCommentID)
}
```

#### Quick-Create Prompt 的关键设计

```
Agent 角色: 快速创建 Issue 的助手 (不是通用执行 Agent)

核心职责:
  1. 从用户的一句话自然语言输入 → 构造 `multica issue create` 命令
  2. title: 简洁但语义丰富, 可 URL 抓取增强
  3. description: 两段式 (User request + Context), 忠实保留技术细节
  4. assignee: 通过 workspace member/agent/squad list 命令查找 UUID
  5. 输出: 只打印一行 "Created <id>: <title>" + 退出

禁止:
  - 不调用 issue get / comment add (没有已存在的 Issue)
  - 不重试 create (防止重复创建)
  - 不插入注释或额外输出
```

### 2.2 Repo3 PromptRole 模板引擎 (参考)

```typescript
// prompts/src/index.ts
interface PromptRole {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  fewShots?: Array<{ user: string; assistant: string }>;
  recommendedAdapters?: string[];
  recommendedCapabilities?: Array<'fileEdit' | 'codeExecution' | 'webBrowse' | 'toolUse'>;
}

// 7 个内置角色
export const builtinRoles: PromptRole[] = [
  architect,  // 架构设计
  frontend,   // 前端开发
  backend,    // 后端开发
  devops,     // 运维
  reviewer,   // 代码审查
  planner,    // 计划
  critic,     // 评审
];

// 模板渲染引擎 ({{var}} 插值)
export function renderTemplate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key) => vars[key] ?? `{{${key}}}`);
}
```

**设计定位**: 角色化的系统提示模板引擎。每个角色有独立的 systemPrompt 和 few-shot 示例，通过 `{{var}}` 插值注入上下文。

### 2.3 Repo1 System Agents (参考)

```typescript
// system-agents.ts
type SystemAgentId = 'title' | 'summarize' | 'plan';

// 每个系统 Agent 有:
// - systemPrompt: 完整指令
// - 输出格式: Zod schema 校验
// - 钩子: beforeRun / afterRun
```

---

## 3. 推荐方案: Multica (主) + Repo3 PromptRole 模板引擎 (参考)

### 3.1 AgentHub Prompt 体系

```
Prompt Builder
│
├── 任务类型 Prompt (采纳 Multica)
│   ├── Chat Prompt        — 直接回复用户消息
│   ├── Comment Prompt     — 评论触发, 含防循环 + Squad 规则
│   ├── QuickCreate Prompt — 自然语言 → Issue 创建指令
│   └── Default Prompt     — Issue 分配, 读取上下文后执行
│
├── 角色 Prompt 模板 (采纳 Repo3)
│   ├── architect     — 架构设计
│   ├── backend       — 后端开发
│   ├── frontend      — 前端开发
│   ├── reviewer      — 文件审查
│   ├── planner       — 任务计划
│   └── critic        — 结果评审
│
├── 注入层 (execenv 风格)
│   ├── Squad Operating Protocol (来自 Agent.Instructions)
│   ├── Skill 文件注入 (来自 Agent.Skills)
│   ├── 评论阅读策略 (Hints)
│   └── 评论回复指令 (Reply Instructions)
│
└── 模板渲染 (采纳 Repo3)
    └── renderTemplate(template, vars)  — {{var}} 插值
```

### 3.2 关键设计决策

| 特性 | 源项目 | AgentHub 选型 |
|------|--------|--------------|
| 任务类型分派 | Multica | ✅ BuildPrompt() 按 task 类型路由 |
| 防循环规则 | Multica | ✅ Agent 互发时不回复/不要 @mention |
| Squad no_action | Multica | ✅ 记录 activity 不发评论 |
| 评论阅读策略 | Multica | ✅ 增量/恢复/冷启动三策略 |
| 角色模板 | Repo3 | ✅ PromptRole 接口 + renderTemplate |
| 回复指令 (每个 turn) | Multica | ✅ 防止 session 残留 |
| 快速创建 Prompt | Multica | ✅ 详细的字段规则注入 |
| Agent 注册/SystemPrompt | Multica | ✅ Agent.Instructions 注入 |

### 3.3 设计要点

1. **Multica 的 prompt 设计哲学**: "Keep this minimal — detailed instructions live in CLAUDE.md/AGENTS.md injected by execenv.InjectRuntimeConfig." AgentHub 也应保持 BuildPrompt 简洁，详细指令通过 Skill 文件注入。

2. **每 turn 注入回复指令**: Multica 在每个 turn 都重新注入 `--parent` 回复参数，防止 session 恢复后携带旧的 `--parent` UUID 导致回复错位。

3. **防 Agent 互发循环**: Agent 互发评论时不回复无实际产出的消息 (纯确认/感谢/sign-off)，回复时也不 @mention 对方，防止触发对方的自动回复。

4. **Reporter 风格与直接 Agent 场景分离**: Multica 把 quick-create prompt 与执行 prompt 分离——quick-create 的 Agent 不是通用执行 Agent，而是"CLI 命令构造器"。