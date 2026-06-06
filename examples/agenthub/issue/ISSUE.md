Multica 的 Issue 设计核心是将 AI Agent 作为一等公民融入传统任务管理流程，通过多态 Actor 设计实现人和 Agent 的无缝协作。 [1](#13-0) 

---

## 核心设计理念

Issue 是 Multica 的核心工作对象，对应 Linear 的 Issue、Jira 的 Ticket、GitHub 的 Issue。其最大特色是 **Issue 可以分配给 Agent，和分配给人完全对等**。 [2](#13-1) 

### 多态 Actor 设计

这是 Multica Issue 设计的核心创新。几乎所有"谁做了什么"的字段都使用 `actor_type` + `actor_id` 的多态模式： [3](#13-2) 

- `assignee_type` + `assignee_id`：可以是 `member` 或 `agent`
- `creator_type` + `creator_id`：Agent 也能创建 issue
- `lead_type` + `lead_id`（Project）：Agent 可以作为项目负责人

这种设计让 Agent 能像人一样出现在 assignee 下拉、评论作者、订阅者列表里。 [4](#13-3) 

## 数据模型

### 核心字段

| 字段 | 说明 | 特殊设计 |
|------|------|----------|
| 标题、描述 | Tiptap 富文本 | 支持富文本编辑 |
| 状态 | backlog/todo/in_progress/in_review/done/blocked/cancelled | 标准工作流 |
| 优先级 | urgent/high/medium/low/none | - |
| 编号 | 自动递增，带 workspace 前缀（如 `MUL-123`） | workspace 可自定义前缀 |
| **Assignee** | 多态：member 或 agent | 核心设计点 |
| **Creator** | 多态：member 或 agent | Agent 可创建 issue |
| Parent issue | 用于子任务 | 支持任务分解 |
| Project | 归属项目 | 高层组织 |
| Due date | 截止日期 | - |
| Labels | 多对多标签 | - |
| Dependencies | 依赖/阻塞关系（blocks/blocked_by/related） | - |
| Acceptance criteria | 验收标准（JSONB） | - |
| Origin | 记录来源（如 autopilot run） | 追溯创建来源 |
| Position | 手动排序位置 | 用于看板拖拽排序 |

### Issue Metadata

每个 issue 携带一个小的 KV metadata bag，用于 Agent pin 重要信息： [5](#13-4) 

- **用途**：Agent 记录会被未来多次读取的事实（PR URL、deploy URL、blocked reason）
- **限制**：最多 50 个键，值是原始类型（string/number/bool），总大小 8KB
- **写入门槛**：只有当信息"对 issue 进展重要"且"未来会被多次读取"时才写入
- **推荐键名**：`pr_url`, `pr_number`, `pipeline_status`, `deploy_url`, `external_issue_url`, `waiting_on`, `blocked_reason`, `decision`

## 视图与交互

### 三种视图模式

1. **List 列表视图**：表格形式，支持按 status/priority/assignee/creator/project 过滤，按 position/priority/due_date/created_at/title 排序 [6](#13-5) 
2. **Board 看板视图**：Kanban，按状态分列，支持拖拽（拖动会自动切到"手动排序"模式）
3. **My Issues 我的议题**：专属视图，三个 scope（分配给我 / 我创建的 / 我的 agent 负责的）

### 关键交互

- **快速创建**：侧边栏单行快速创建或弹窗富文本创建
- **批量操作**：多选后批量改 status/priority/assignee/删除
- **子 issue**：父 issue 显示子任务完成比例圆环
- **订阅**：默认 creator、assignee、被 @ 的人会自动订阅
- **Reaction**：issue 和评论都能加 emoji 反应
- **Pin 固定**：把 issue 置顶到侧边栏快捷栏
- **Timeline 时间线**：所有关键动作（状态变更、指派变更、评论）按时间顺序展示

### 前端过滤逻辑

前端使用 `filterIssues` 函数实现客户端过滤，支持正向选择模型（空数组 = 无过滤）： [7](#13-6) 

```typescript
export function filterIssues(issues: Issue[], filters: IssueFilters): Issue[] {
  // 支持 status, priority, assignee, creator, project, label 过滤
  // 支持 agentRunningFilter（只显示有 agent 正在运行的 issue）
}
```

## 与 Agent 的集成

### 分配触发

当 issue 被分配给 agent 时（且状态不是 backlog），系统会： [8](#13-7) 

1. 入队一个 `queued` 状态的 `task`，优先级继承自 issue
2. Agent 的 daemon 轮询认领任务，状态转为 `dispatched`
3. Agent 开始执行，状态转为 `running`
4. 执行过程中 agent 可以改 issue 状态、发评论、编辑字段

### Agent 执行流程

Agent 被分配 issue 后，会按照以下流程执行： [9](#13-8) 

1. 运行 `multica issue get <id> --output json` 了解任务
2. 运行 `multica issue metadata list <id> --output json` 查看之前 agent pin 的信息
3. 运行 `multica issue comment list <id> --output json` 读取完整评论历史
4. 运行 `multica issue status <id> in_progress` 更新状态
5. 按照 Skills 和 Agent Identity 完成任务
6. 通过 `multica issue comment add <id> --content "..."` 发布结果
7. 如果产生了重要事实，通过 `multica issue metadata set`/`delete` 更新 metadata
8. 完成后运行 `multica issue status <id> in_review`

### 评论触发

在评论中 `@agent` 会自动触发该 agent 的新任务，让它来回复/处理。 [10](#13-9) 

## 数据表结构

Issue 相关的核心数据表： [11](#13-10) 

- `issue` - 议题主表
- `comment` - 评论（支持嵌套回复）
- `issue_label` / `issue_to_label` - 标签
- `issue_dependency` - 依赖关系
- `issue_subscriber` - 订阅者
- `issue_reaction` / `comment_reaction` - emoji 反应
- `attachment` - 附件
- `activity_log` - 审计日志
- `pinned_item` - 侧边栏置顶

## 产品中的位置

Issue 是所有工作流的载体： [12](#13-11) 

- Agent 通过"被分配到 issue"获得任务
- Autopilot 通过"创建 issue"来触发 agent
- 评论通过"@agent" 追加任务
- Inbox 通知围绕 issue 生成

## Notes

Multica 的 Issue 设计可以归结为一句话：**把"人在一个看板上协作"这件事，扩展到了"人 + AI agent 在同一个看板上协作"**。多态 Actor 设计是实现这一目标的核心技术手段，它让 Agent 在数据层面和人类完全对等，从而能够无缝融入现有的任务管理流程。 [13](#13-12) 

Wiki pages you might want to explore:
- [Issue List Views (Board and List) (multica-ai/multica)](/wiki/multica-ai/multica#4.1)
- [Assigning issues to agents (multica-ai/multica)](/wiki/multica-ai/multica#5.4)

Wiki pages you might want to explore:
- [Documentation Site (apps/docs) (multica-ai/multica)](/wiki/multica-ai/multica#13.2)
- [Issue List Views (Board and List) (multica-ai/multica)](/wiki/multica-ai/multica#4.1)

### Citations

**File:** docs/product-overview.md (L121-122)
```markdown
| **Polymorphic Actor 多态行动者** | 设计范式：几乎所有"谁做了什么"的字段都是 `actor_type` (`member`/`agent`) + `actor_id`。这就是为什么 agent 能像人一样创建 issue、发评论、被订阅 | 贯穿所有表 |

```

**File:** docs/product-overview.md (L151-212)
```markdown
### 3.2 Issue 议题管理

> **角色**：Multica 的核心工作对象。

Issue 对应的概念在 Linear 叫 Issue、在 Jira 叫 Ticket、在 GitHub 叫 Issue——就是一个任务单元。Multica 的特色在于**issue 可以分配给 agent，和分配给人完全对等**。

#### 核心字段

- 标题、描述（Tiptap 富文本）、状态、优先级
- 编号（自动递增，带 workspace 前缀）
- **Assignee（可以是 member 或 agent）**
- **Creator（可以是 member 或 agent）**——agent 也能创建 issue
- Parent issue（用来做子任务）
- Project（归属的项目）
- Due date（截止日期）
- Labels（多对多标签）
- Dependencies（依赖/阻塞关系）
- Acceptance criteria（验收标准，JSONB）
- Origin（如果是 autopilot 创建的，会记录来源 autopilot run）

#### 视图

- **List 列表视图**：表格形式，可按 status/priority/assignee/creator/project 过滤、按名称/优先级/截止日/手动位置排序；支持开放和已完成分页。
- **Board 看板视图**：Kanban，按状态分列；支持拖拽（拖动会自动切到"手动排序"模式）。
- **My Issues 我的议题**：专属视图，三个 scope：分配给我 / 我创建的 / 我的 agent 负责的。

#### 交互

- **快速创建**：侧边栏单行快速创建、或弹窗富文本创建（支持草稿本地持久化）
- **批量操作**：多选后批量改 status/priority/assignee/删除
- **子 issue**：父 issue 显示子任务完成比例圆环
- **订阅（subscribe）**：默认 creator、assignee、被 @ 的人会自动订阅
- **Reaction**：issue 和评论都能加 emoji 反应
- **Pin 固定**：把 issue 置顶到侧边栏快捷栏
- **复制链接 / 快捷键跳转（Cmd+K）**
- **Timeline 时间线**：所有关键动作（状态变更、指派变更、评论）按时间顺序展示，混合 `activity_log` + `comment` 两类记录

#### 评论与讨论

- Tiptap 富文本编辑器，支持 `@` 提到 member 或 agent
- 嵌套回复（一层）
- emoji 反应
- **@agent 触发任务**：在评论里提到某个 agent，会自动生成一个新的 agent task，让它来回复/处理

#### 附件

- 拖拽上传或按钮上传
- 图片内联预览
- 存储后端：S3/CloudFront 或本地磁盘（自托管）

#### 产品里的位置

Issue 是**所有工作流的载体**：
- Agent 通过"被分配到 issue"获得任务
- Autopilot 通过"创建 issue"来触发 agent
- 评论通过"@agent" 追加任务
- Inbox 通知围绕 issue 生成

#### 对应表

`issue`, `comment`, `issue_label`, `issue_to_label`, `issue_dependency`, `issue_subscriber`, `issue_reaction`, `comment_reaction`, `attachment`, `activity_log`, `pinned_item`

```

**File:** docs/product-overview.md (L931-940)
```markdown
### Issue / 协作

- `issue` — 议题（status, priority, assignee_type+assignee_id, creator_type+creator_id, parent_issue_id, project_id, origin_type, origin_id, acceptance_criteria, due_date, position）
- `issue_label` / `issue_to_label` — 标签
- `issue_dependency` — 依赖关系（blocks / blocked_by / related）
- `issue_subscriber` — 订阅者（reason: creator/assignee/commenter/mentioned/manual）
- `issue_reaction` / `comment_reaction` — emoji 反应
- `comment` — 评论（type: comment/status_change/progress_update/system, parent_id for threading）
- `attachment` — 附件

```

**File:** docs/product-overview.md (L971-983)
```markdown
## 尾声

Multica 的设计可以归结为一句话：**把"人在一个看板上协作"这件事，扩展到了"人 + AI agent 在同一个看板上协作"**。

所有功能都是围绕这个核心展开：
- 为了让 agent 能像人一样被分配任务 → polymorphic actor（`assignee_type`）
- 为了让 agent 能自己开工 → Autopilot
- 为了让 agent 的工作方式能沉淀复用 → Skill
- 为了让 agent 执行在用户控制的环境里 → Runtime + Daemon
- 为了让人不被通知淹没 → Inbox + 自动订阅
- 为了让一次会话有连续性 → Session Resumption

当你读到某段文案、某个 UI 模块、某张表时，请把它放回这个"人 + AI 协作"的坐标系里去理解它的位置。
```

**File:** apps/docs/content/docs/guides/agents.zh.mdx (L6-10)
```text
## Agents as Teammates

In Multica, agents are first-class citizens. They have profiles, show up on the board, post comments, create issues, and report blockers proactively.

Assignees are polymorphic — an issue can be assigned to a member or an agent. The `assignee_type` + `assignee_id` fields on issues distinguish between the two. Agents render with distinct styling (purple background, robot icon).
```

**File:** CLI_AND_DAEMON.md (L454-459)
```markdown
### Metadata

Per-issue metadata is a small KV map agents use to track pipeline state (PR number, pipeline status, waiting_on, ...). Keys match `^[a-zA-Z_][a-zA-Z0-9_.-]{0,63}$`, values are primitives (string / number / bool), max 50 keys per issue, blob capped at 8KB.

The bar for writing is high: pin a value only when it is materially important to the issue AND likely to be re-read by future runs on this same issue (the PR URL, the deploy URL, what we're blocked on). Most runs write zero new keys — that's the expected case. Don't pin runtime bookkeeping like `attempts`, single-run investigation notes, large logs, secrets/tokens, or description/comment copies — see the agent runtime prompt for the full anti-pattern list.

```

**File:** packages/core/issues/stores/view-store.ts (L62-120)
```typescript
export interface IssueViewState {
  viewMode: ViewMode;
  grouping: IssueGrouping;
  statusFilters: IssueStatus[];
  priorityFilters: IssuePriority[];
  assigneeFilters: ActorFilterValue[];
  includeNoAssignee: boolean;
  creatorFilters: ActorFilterValue[];
  projectFilters: string[];
  includeNoProject: boolean;
  labelFilters: string[];
  // When true, the list only shows issues that currently have at least one
  // agent task in `running` status. Drives the workspace "agents working"
  // quick filter chip in the issues header. Not persisted across reloads —
  // running state changes second-to-second, a persisted toggle would let
  // users return to an empty list with no obvious cause.
  agentRunningFilter: boolean;
  sortBy: SortField;
  sortDirection: SortDirection;
  cardProperties: CardProperties;
  listCollapsedStatuses: IssueStatus[];
  ganttZoom: GanttZoom;
  ganttShowCompleted: boolean;
  /** Active swimlane grouping dimension. */
  swimlaneGrouping: SwimlaneGrouping;
  /** Persisted lane order, keyed by grouping. Entries are raw lane ids
   *  (parent issue id, project id, or `<assigneeType>:<assigneeId>`). */
  swimlaneOrders: Record<SwimlaneGrouping, string[]>;
  /** Persisted collapsed lanes, keyed by grouping. Same id space as
   *  `swimlaneOrders`, plus the sentinel `"none"` for the pinned
   *  no-X lane and `"__orphans__"` for the parent-grouping fallback. */
  collapsedSwimlanes: Record<SwimlaneGrouping, string[]>;
  setViewMode: (mode: ViewMode) => void;
  setGanttZoom: (zoom: GanttZoom) => void;
  toggleGanttShowCompleted: () => void;
  setGrouping: (grouping: IssueGrouping) => void;
  toggleStatusFilter: (status: IssueStatus) => void;
  togglePriorityFilter: (priority: IssuePriority) => void;
  toggleAssigneeFilter: (value: ActorFilterValue) => void;
  toggleNoAssignee: () => void;
  toggleCreatorFilter: (value: ActorFilterValue) => void;
  toggleProjectFilter: (projectId: string) => void;
  toggleNoProject: () => void;
  toggleLabelFilter: (labelId: string) => void;
  toggleAgentRunningFilter: () => void;
  hideStatus: (status: IssueStatus) => void;
  showStatus: (status: IssueStatus) => void;
  clearFilters: () => void;
  setSortBy: (field: SortField) => void;
  setSortDirection: (dir: SortDirection) => void;
  toggleCardProperty: (key: keyof CardProperties) => void;
  toggleListCollapsed: (status: IssueStatus) => void;
  setSwimlaneGrouping: (grouping: SwimlaneGrouping) => void;
  /** Update the lane order for the currently active swimlane grouping. */
  setSwimlaneOrder: (order: string[]) => void;
  /** Toggle a lane key in the currently active swimlane grouping. */
  toggleSwimlaneCollapsed: (key: string) => void;
}

```

**File:** packages/views/issues/utils/filter.ts (L30-94)
```typescript
export function filterIssues(issues: Issue[], filters: IssueFilters): Issue[] {
  const { statusFilters, priorityFilters, assigneeFilters, includeNoAssignee, creatorFilters, projectFilters, includeNoProject, labelFilters, agentRunningFilter, runningIssueIds } = filters;
  const hasAssigneeFilter = assigneeFilters.length > 0 || includeNoAssignee;
  const hasProjectFilter = projectFilters.length > 0 || includeNoProject;
  // Empty set passed without `agentRunningFilter` is a no-op. When the
  // filter is on but the set is missing/empty, hide everything — the
  // user opted into "only running" and there is nothing running.
  const applyAgentRunning = agentRunningFilter === true;

  return issues.filter((issue) => {
    if (applyAgentRunning && !(runningIssueIds?.has(issue.id) ?? false))
      return false;

    if (statusFilters.length > 0 && !statusFilters.includes(issue.status))
      return false;

    if (priorityFilters.length > 0 && !priorityFilters.includes(issue.priority))
      return false;

    if (hasAssigneeFilter) {
      if (!issue.assignee_id) {
        // Unassigned issue — show only if "No assignee" is checked
        if (!includeNoAssignee) return false;
      } else if (assigneeFilters.length > 0) {
        // Assigned issue — show only if assignee is in the filter list
        if (!assigneeFilters.some(
          (f) => f.type === issue.assignee_type && f.id === issue.assignee_id,
        )) return false;
      } else {
        // Only "No assignee" is checked, no specific assignees → hide assigned issues
        return false;
      }
    }

    if (
      creatorFilters.length > 0 &&
      !creatorFilters.some(
        (f) => f.type === issue.creator_type && f.id === issue.creator_id,
      )
    ) {
      return false;
    }

    if (hasProjectFilter) {
      if (!issue.project_id) {
        if (!includeNoProject) return false;
      } else if (projectFilters.length > 0) {
        if (!projectFilters.includes(issue.project_id)) return false;
      } else {
        // Only "No project" is checked → hide issues that have a project
        return false;
      }
    }

    if (labelFilters.length > 0) {
      // OR semantics within the filter: keep issues that carry any of the
      // selected labels. Matches existing priority / project multi-select.
      const issueLabels = issue.labels;
      if (!issueLabels || issueLabels.length === 0) return false;
      if (!issueLabels.some((l) => labelFilters.includes(l.id))) return false;
    }

    return true;
  });
}
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

**File:** server/internal/daemon/execenv/runtime_config.go (L369-385)
```go
	} else {
		// Assignment-triggered: defer to agent Skills for workflow specifics.
		b.WriteString("You are responsible for managing the issue status throughout your work.\n\n")
		fmt.Fprintf(&b, "1. Run `multica issue get %s --output json` to understand your task\n", ctx.IssueID)
		fmt.Fprintf(&b, "2. Run `multica issue metadata list %s --output json` to see what prior agents pinned — best-effort, empty `{}` and CLI failures are normal. See the `## Issue Metadata` section above for what to look for.\n", ctx.IssueID)
		fmt.Fprintf(&b, "3. Run `multica issue comment list %s --output json` to read the full comment history (returns all comments, capped server-side at 2000) — this is mandatory, not optional. Earlier comments often carry context the issue body lacks (e.g. which repo to work in, the prior agent's findings, the reason the issue was reassigned to you). Skipping this step is the most common cause of agents acting on stale or incomplete instructions. When the flat dump is too large to ingest in one shot, treat `--recent 20 --output json` plus the `--before` / `--before-id` cursor (from the stderr `Next thread cursor:` line) as a paging strategy: keep walking older threads until you have read enough history to satisfy this mandatory step. `--recent` is a way to read the full history page-by-page, ... (truncated)
		fmt.Fprintf(&b, "4. Run `multica issue status %s in_progress`\n", ctx.IssueID)
		b.WriteString("5. Follow your Skills and Agent Identity to complete the task (write code, investigate, etc.)\n")
		if ctx.IsSquadLeader {
			fmt.Fprintf(&b, "6. **Post your final results as a comment** (unless your outcome is `no_action` — in that case, calling `multica squad activity %s no_action --reason \"...\"` alone is sufficient; you MUST exit without posting any comment. DO NOT post a comment announcing no_action or saying you are exiting silently): `multica issue comment add %s --content \"...\"`. Your results are only visible to the user if posted via this CLI call; text in your terminal or run logs is NOT delivered.\n", ctx.IssueID, ctx.IssueID)
		} else {
			fmt.Fprintf(&b, "6. **Post your final results as a comment — this step is mandatory**: `multica issue comment add %s --content \"...\"`. Your results are only visible to the user if posted via this CLI call; text in your terminal or run logs is NOT delivered.\n", ctx.IssueID)
		}
		b.WriteString("7. Before exiting: only if this run produced a fact that clears the high bar (important AND likely to be re-read by future runs on this same issue, e.g. a new PR URL or deploy URL), or you noticed a metadata key from entry that is now stale, pin or clear it via `multica issue metadata set`/`delete`. Most runs write nothing here — that is the expected outcome, not a gap. When in doubt, do not write. See the `## Issue Metadata` section above for the full bar.\n")
		fmt.Fprintf(&b, "8. When done, run `multica issue status %s in_review`\n", ctx.IssueID)
		fmt.Fprintf(&b, "9. If blocked, run `multica issue status %s blocked` and post a comment explaining why\n\n", ctx.IssueID)
	}
```
