# Diff 视图设计文档

> **分析来源**: Repo4 (ref/repo4), Vibe Kanban (docs 分析)
> **推荐方案**: Repo4 GitHub Diff 体系 (主) + Vibe Kanban Review 流程 (参考)

---

## 1. 分析范围

| 仓库 | 实现 | 关键文件 |
|------|------|---------|
| **repo4** | Swift — GitHubDiffRenderAdapter + GitHubCLIService + GitHubViewModel | AgentHubGitHub/Services/GitHubCLIService.swift, Utils/GitHubDiffRenderAdapter.swift, ViewModels/GitHubViewModel.swift, Models/GitHubModels.swift |
| **repo4** | Swift — PR 观察服务 (GitHubPRObservationService) | ViewModels/GitHubViewModel.swift (observation) |

---

## 2. 方案对比

### 2.1 Repo4 Diff 体系 (推荐主方案)

#### Diff 渲染适配器

```swift
// GitHubDiffRenderAdapter.swift
// 将 GitHub 统一补丁文本转换为旧/新缓冲区

class GitHubDiffRenderAdapter {
    /// 将统一 diff 文本解析为旧/新文件快照
    /// 输入: git diff 或 PR 补丁文本
    /// 输出: 前端可渲染的 Old/New 缓冲区
    static func parse(_ diffText: String) -> (oldBuffer: [String], newBuffer: [String])

    /// 定位 diff 中的变化行 (用于行级评论)
    static func changedLines(_ diffText: String) -> [(oldLine: Int?, newLine: Int?)]
}
```

#### PR 审查流程

```swift
// GitHubCLIService — 完整的 PR 生命周期管理

// 1. 列出 PR（按状态/作者/标签过滤）
func listPullRequests(at repoPath: String, state: PRState,
    limit: Int, authoredByMe: Bool? = nil, labels: [String]) async throws -> [GitHubPullRequest]

// 2. 获取 PR 详情（含 diff 和文件列表）
func getPullRequest(at repoPath: String, number: Int) async throws -> GitHubPullRequest
func getPRDiff(at repoPath: String, number: Int) async throws -> String
func getPRFiles(at repoPath: String, number: Int) async throws -> [GitHubPRFile]

// 3. 审查评论
func listPRReviewComments(at repoPath: String, number: Int)
    async throws -> [GitHubComment]
func addPRComment(at repoPath: String, number: Int, body: String) async throws
func addPRReview(at repoPath: String, number: Int, body: String,
    event: ReviewEvent) async throws

// 4. 创建/更新 PR
func createPR(at repoPath: String, title: String, body: String?,
    head: String, base: String, draft: Bool) async throws -> GitHubPullRequest
func updatePR(at repoPath: String, number: Int, title: String?,
    body: String?) async throws -> GitHubPullRequest

// 5. CI 检查
func listCheckRuns(at repoPath: String, prNumber: Int) async throws -> [GitHubCheckRun]
```

#### GitHubViewModel 状态管理

```swift
// 核心状态
class GitHubViewModel {
    // PR 列表
    var pullRequests: [GitHubPullRequest]    // 按 filter 过滤后的列表
    var prFilter: GitHubPRFilter             // open / draft / merged / closed / all

    // PR 详情
    var selectedPR: GitHubPullRequest?
    var selectedPRFiles: [GitHubPRFile]      // 变更文件列表
    var selectedPRDiff: String               // 完整 diff 文本
    var selectedPRReviewComments: [GitHubComment]  // 审查评论

    // CI 检查
    var checks: [GitHubCheckRun]             // 状态检查列表

    // PR 观察服务 — 自动轮询更新
    var currentBranchObservationState: GitHubPRObservationState
}
```

#### PR 观察服务

```swift
// Swift async 序列模式 — 自动轮询当前分支 PR 状态
func startCurrentBranchObservation() {
    currentBranchObservationTask = Task { [weak self] in
        for await event in observationService.observe(repoPath: repoPath)  {
            switch event {
            case .prUpdated(let pr):      self?.updateCurrentBranchPR(pr)
            case .checksUpdated(let cks): self?.updateChecks(cks)
            case .commentsUpdated(let cs): self?.updateComments(cs)
            }
        }
    }
}
```

### 2.2 Vibe Kanban 审查流程 (参考)

**审查机制描述**: 强调人工在每个环节的审查介入，工作流为:
```
规划 (Issue) → 执行 (Workspace) → 审查 (Diff) → 合并 (PR)
```

**关键设计**: Git Worktree 隔离后，Agent 产出的代码通过 Diff 对比后，人类在合并前可审查并内联评论。

---

## 3. 推荐方案: Repo4 GitHub Diff (主) + Vibe Kanban Review 流程 (参考)

### 3.1 AgentHub Diff 视图体系

```
Diff 视图系统
│
├── Diff 渲染引擎 (采纳 Repo4)
│   ├── GitHubDiffRenderAdapter — 统一 diff → 旧/新缓冲区
│   ├── 行级变化定位 (oldLine/newLine)
│   ├── 文件列表 (GitHubPRFile[])
│   └── 完整 diff 文本渲染
│
├── PR 审查流程 (采纳 Repo4)
│   ├── PR 列表 (过滤: open/draft/merged/closed)
│   ├── PR 详情 (变更文件/完整 diff/审查评论)
│   ├── 审查评论 CRUD (行级/全局)
│   ├── CI 检查展示 (GitHubCheckRun)
│   └── PR CRUD (create/update/merge)
│
├── Review 工作流 (采纳 Vibe Kanban)
│   ├── Issue → Agent Worktree → Diff 生成 → 审查 → 合并
│   ├── 内联评论系统 (diff 行级评论)
│   └── 审批门禁 (approve/request-changes)
│
└── 自动观察 (采纳 Repo4)
    ├── 当前分支 PR 自动轮询
    ├── CI 状态变化推送
    └── 审查评论实时更新
```

### 3.2 关键设计决策

| 特性 | Repo4 | AgentHub 选型 |
|------|-------|--------------|
| **Diff 渲染** | GitHubDiffRenderAdapter | ✅ 采纳 — 统一 diff → 行级缓冲区 |
| **PR 列表** | gh CLI list | ✅ 采纳 — 4 种过滤状态 |
| **PR 详情** | gh CLI view | ✅ 采纳 — 文件列表/diff/评论 |
| **审查评论** | 行级评论 | ✅ 采纳 |
| **CI 检查** | gh CLI checks | ✅ 采纳 |
| **PR 观察** | Swift async 序列 | ✅ 采纳 — WS 实时推送模式 |
| **工作流** | — | ✅ 采用 Vibe Kanban Review 流程 |

### 3.3 在 AgentHub 协作流程中的位置

```
Agent 在 Worktree 中完成任务
    │
    ▼
Agent: git commit + git push
    │
    ▼
Agent: gh pr create (Agent 自己创建 PR)
    │
    ▼
AgentHub: 自动识别新 PR → Board Issue 状态: in_review
    │
    ▼
人类/Review Agent: 在 Diff 视图中审查
    │
    ├── 行级评论 → Agent 收到通知 → 在 worktree 修改
    │   └── 循环直到通过审查
    │
    ├── Approve → Agent 合并 PR
    │   └── Board Issue 状态: done
    │
    └── Request Changes → Agent 收到通知 → 修改
        └── 重新提交审查
```