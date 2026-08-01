# Kanban 看板设计文档

> **分析来源**: Vibe-Kanban (ref/vibe-kanban), Multica (ref/multica)
> **推荐方案**: Vibe-Kanban (主) — Rust 核心看板 + MCP 服务 + Git Worktree 隔离
> **补充**: 融入 AgentHub 的 Polymorphic Actor 模型和 Handoff DAG

---

## 1. 分析范围

| 仓库 | 实现 | 关键文件 |
|------|------|---------|
| **vibe-kanban** | Rust — 完整看板系统 + Git Worktree + MCP 服务 | crates/{db,api-types,mcp,git,worktree-manager,executors,server,remote}.rs |
| **multica** | Go — Issue Board + Squad + Polymorphic Actor | server/pkg/db/queries/issue.sql, squad.sql |

---

## 2. Vibe-Kanban 核心设计

### 2.1 整体架构

```
Vibe-Kanban Architecture
│
├── Rust 后端 (crates/)
│   ├── api-types/         — 数据结构定义 (Issue, Project, Tag, Status)
│   │                       ts-rs 自动生成 TypeScript 类型
│   ├── db/                — 数据库 KV 存储
│   ├── server/            — HTTP API 服务 (axum)
│   ├── mcp/               — MCP 服务器 (Model Communication Protocol)
│   │                       Agent 通过 MCP 工具操作看板
│   ├── executors/         — 执行器 (Claude/Codex/Cursor/Gemini/...)
│   ├── git/               — Git 仓库管理
│   ├── worktree-manager/  — Git Worktree 隔离管理
│   ├── workspace-manager/ — 工作区配置
│   └── remote/            — 云端服务 (ElectricSQL, 认证, 多用户)
│
├── Shared TypeScript (shared/)
│   ├── types.ts           — Agent 通信类型
│   └── remote-types.ts    — 远程 API 类型
│
└── NPX CLI (npx-cli/)
    └── src/cli.ts         — 命令行入口
```

### 2.2 Issue 看板数据模型

```rust
// api-types/src/issue.rs — Issue 核心结构

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use ts_rs::TS;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct Issue {
    pub id: Uuid,
    pub project_id: Uuid,
    pub rank: String,              // 排序位序 (Fractional Indexing)
    pub title: String,
    pub description: String,
    pub status: IssueStatus,
    pub parent_issue: Option<Uuid>, // 父子任务层级
    pub assigned_executor: Option<String>, // Agent 分配 (executor 名称)
    pub labels: Vec<IssueLabel>,
    pub notion_url: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub workspace_id: Uuid,
    pub last_accessed_at: Option<DateTime<Utc>>,
    pub last_accessed_repo_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, TS)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum IssueStatus {
    Backlog,
    Todo,
    InProgress,
    InReview,
    Done,
    Cancelled,
}
```

**关键设计决策**:
- `rank` 使用 Fractional Indexing (而非整数 position)，支持 O(1) 插入和重排序
- `assigned_executor` 使用 executor 名称而非 UUID，Agent 可直接通过名称识别
- `parent_issue` 支持任意深度的父子任务层级
- `labels` 关联 `IssueLabel` 实现标签分类
- `last_accessed_at` + `last_accessed_repo_path` 支持工作区恢复

### 2.3 Project 模型

```rust
// api-types/src/project.rs

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct Project {
    pub id: Uuid,
    pub organization_id: Uuid,
    pub name: String,
    pub color: String,          // UI 显示颜色
    pub sort_order: i32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

// 支持 Client-generated ID 实现乐观更新
#[derive(Debug, Clone, Deserialize, TS)]
pub struct CreateProjectRequest {
    #[ts(optional)]
    pub id: Option<Uuid>,       // 客户端生成 ID → 稳定乐观更新
    pub organization_id: Uuid,
    pub name: String,
    pub color: String,
}
```

**客户端生成 ID**: Issue 和 Project 都支持客户端生成 UUID，实现稳定的乐观更新 (optimistic updates) ——客户端创建立即显示，无需等服务端返回。

### 2.4 MCP 看板服务 (核心创新)

**设计定位**: Agent 通过 MCP 协议操作看板——创建 Issue、切换状态、分配 Agent、读取上下文。

```rust
// mcp/src/lib.rs — MCP 服务器

// MCP 工具列表 (Agent 可调用的看板操作):
// mcp_kv_get              — 读取键值存储
// mcp_kv_list             — 列出键值对
// mcp_task_create         — 创建 Issue
// mcp_task_get            — 获取 Issue 详情
// mcp_task_start          — 开始 Issue (status → InProgress)
// mcp_task_complete       — 完成 Issue (status → Done)
// mcp_task_pause          — 暂停 Issue
// mcp_task_cancel         — 取消 Issue
// mcp_task_add_comment    — 添加评论
// mcp_task_get_comments   — 获取评论列表
// mcp_task_get_messages   — 获取 Agent 执行消息
// mcp_task_update_issue_number — 更新 Issue 编号
// mcp_project_get         — 获取 Project
// mcp_project_list        — 列出 Project
// mcp_get_prompt          — 获取系统提示模板

// crates/mcp/src/task_server/handler.rs
// Agent 执行上下文注入:
//   - issue: 当前 Issue 的全部信息
//   - history: 历史执行消息
//   - worktree: 关联的工作树路径
```

**MCP 看板的关键设计**:

```
Agent 操作看板的流程:

对外: Agent 通过 MCP 工具调用看板 API
  1. mcp_task_get → 读取 Issue 上下文
  2. mcp_task_create → 创建子 Issue
  3. mcp_task_start → 开始执行
  4. mcp_task_complete → 完成后更新状态

对内: MCP 服务器操作本地数据库
  1. handler.rs 解析工具调用
  2. 调用 db/lib.rs 的 CRUD 方法
  3. 返回结果给 Agent
```

### 2.5 Git Worktree + 看板联动

**设计定位**: 每个 Issue 关联独立的工作树 (Worktree)，Agent 在隔离环境中执行。

```rust
// worktree-manager/src/lib.rs

// 工作树生命周期:
//   1. Issue 创建 → 不创建 worktree (延迟创建)
//   2. Issue 开始 (InProgress) → 创建 worktree:
//      git branch -f feature/issue-{id} {base_commit}
//      git worktree add {path} feature/issue-{id}
//   3. Issue 完成 (Done) → Agent push → 创建 PR
//   4. Issue 取消/结束 → 清理 worktree

// crates/git/src/cli.rs — Git CLI 命令封装
//   git worktree list --porcelain  → 列出所有 worktree
//   git worktree add {path} {branch} → 创建 worktree
//   git worktree remove --force {path} → 清理 worktree
```

**四种看板状态驱动的工作树状态**:

```
Backlog → (无 worktree, 只维护 Issue 数据)
Todo    → (无 worktree)
InProgress → (创建 worktree, Agent 在此工作)
InReview   → (Agent push 到远程, 创建 PR)
Done       → (清理 worktree, PR 合并)
Cancelled  → (清理 worktree)
```

### 2.6 执行器 (Executor) 体系

```rust
// executors/src/executors/mod.rs

// 支持 9 种 Agent 执行器:
#[derive(...)]
pub enum ExecutorKind {
    ClaudeCode,
    Codex,
    CursorAgent,
    QwenCode,
    Copilot,
    OpenCode,
    Gemini,
    Amp,
}

pub enum BaseAgentCapability {
    SessionFork,      // 支持会话分叉 (并行执行)
    SetupHelper,      // 需要设置脚本
    ContextUsage,      // 报告上下文/token 使用
}
```

### 2.7 Multica Issue Board 补充

Multica 的 Issue 模型补充看板需要的 Polymorphic Actor 和 Squad 分配能力：

```sql
-- issue.sql — Multica 多态分配
assignee_type TEXT  -- 'member' | 'agent' | 'squad'
assignee_id   UUID  -- FK to member/agent/squad
creator_type  TEXT
creator_id    UUID

-- status 流转 (与 vibe-kanban 兼容):
-- backlog → todo → in_progress → in_review → done / blocked / cancelled
```

---

## 3. 推荐方案: Vibe-Kanban (主) + Multica Actor 模型 (补充)

### 3.1 AgentHub Kanban 体系

```
Kanban 系统
│
├── 核心数据模型 (采纳 Vibe-Kanban)
│   ├── Issue { id, project_id, rank, title, description, status,
│   │           parent_issue, assigned_executor, labels, timestamps }
│   ├── Project { id, name, color, sort_order }
│   ├── Status 流转: Backlog → Todo → InProgress → InReview → Done/Cancelled
│   └── Fractional Indexing: rank 字段支持 O(1) 插入排序
│
├── Polymorphic Actor (采纳 Multica)
│   ├── assignee_type + assignee_id: 'member' | 'agent' | 'squad'
│   └── Agent → Human → Squad 统一分配接口
│
├── MCP 看板操作 (采纳 Vibe-Kanban)
│   ├── Agent 通过 MCP 工具调用看板 CRUD
│   ├── mcp_task_create / get / start / complete / pause / cancel
│   ├── mcp_task_add_comment / get_comments
│   └── mcp_project_get / list
│
├── Worktree 联动 (采纳 Vibe-Kanban)
│   ├── Issue Backlog/Todo → 无 worktree
│   ├── Issue InProgress → 创建 worktree (git worktree add)
│   ├── Issue InReview → Agent push, 创建 PR
│   └── Issue Done/Cancelled → 清理 worktree
│
├── 父子层级 (采纳 Vibe-Kanban + AgentHub Handoff DAG)
│   ├── parent_issue → 子任务层级
│   ├── 与 Handoff DAG 联动: 父 Issue = Handoff DELEGATE,
│   │   子 Issue = 分解后的子任务
│   └── DAG 拓扑 → 自动管理父子 Issue 状态
│
└── 乐观更新 + Client ID (采纳 Vibe-Kanban)
    ├── 客户端生成 Issue/Project ID
    └── 创建后立即显示，无需等服务端返回
```

### 3.2 看板与 Handoff DAG 的联动

```
Goal → Coordinator Agent Handoff DAG
    │
    └── Task"A" → 创建 Issue#1 (Backlog)
        │
        ├── Handoff DELEGATE(A,B) → Issue#1 → InProgress
        │   └── Worktree 创建 → Agent 执行
        │
        ├── Agent 完成 → Issue#1 → InReview → PR 创建 → Worktree 保留
        │
        ├── 子 Task "A.1" → 创建 Issue#1.1 (子 Issue)
        │   ├── parent_issue = Issue#1
        │   └── 状态跟随子任务独立流转
        │
        └── 审查通过 → Issue#1 → Done → Worktree 清理 → PR 合并
```

### 3.3 看板状态机 + Daemon 协同

```
状态变化        Daemon 动作               Agent 动作
─────────────────────────────────────────────────────
Backlog →      —                        —
Todo →         —                        —
InProgress →   创建 worktree +           mcp_task_start
                spawn agent CLI
InReview →     保留 worktree             git push + gh pr create
Done →         清理 worktree             — (PR 已合并)
Cancelled →    清理 worktree             —
```

### 3.4 关键设计决策

| 特性 | Vibe-Kanban | Multica | AgentHub 选型 |
|------|-------------|---------|--------------|
| **核心语言** | Rust | Go | ✅ Rust (选型确定后定) |
| **数据模型** | Issue + Project + Label + Status | Issue + Squad + Actor | ✅ Vibe-Kanban + Polymorphic Actor |
| **排序** | Fractional Indexing (rank) | — | ✅ Vibe-Kanban |
| **父子层级** | parent_issue (递归) | parent_issue (单层) | ✅ Vibe-Kanban (递归) |
| **乐观更新** | Client-generated UUID | — | ✅ Vibe-Kanban |
| **Agent 操作** | MCP 协议工具 | @mention + CLI | ✅ Vibe-Kanban MCP |
| **状态流转** | Backlog→Todo→InProg→InReview→Done/Cancelled | backlog→todo→ready→running→done/blocked/cancelled | ✅ 合并: 增加 blocked |
| **Worktree 联动** | 状态驱动自动创建/清理 | — | ✅ Vibe-Kanban |
| **多态分配** | assigned_executor (string) | assignee_type + assignee_id | ✅ Multica 多态 |
| **与 DAG 联动** | — | — | ✅ AgentHub Handoff DAG |
| **Agent 执行** | 9 种 executor | Daemon + CLI | ✅ Multica Daemon |