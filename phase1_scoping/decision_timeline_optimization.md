# 决策时间线现状分析与可追溯性优化方案

> 文件：`phase1_scoping/decision_timeline_optimization.md`  
> 生成日期：2026-07-28  
> 分析目标：系统梳理 Feishu-LongTerm-Mem 项目中的"时间线"设计，分析可追溯性缺口，输出结构化优化方案

---

## 目录

1. [当前时间线设计全景](#1-当前时间线设计全景)
2. [可追溯性缺口分析](#2-可追溯性缺口分析)
3. [优化方案](#3-优化方案)
4. [实施路线图](#4-实施路线图)

---

## 1. 当前时间线设计全景

### 1.1 数据流时间线总图

```
飞书 IM WebSocket 消息 → Episode 缓冲池 → 提取管道 → DecisionNode → Git 版本化
         ↓                        ↓                   ↓                   ↓
    timestamp (消息级)    start_time/end_time     created_at          commit hash
                         (Episode 级)            updated_at          (Git 级)
                                                  decided_at
```

### 1.2 各层时间字段梳理

#### L0：原始消息层 — `ChatMessage` / `SuspendedEpisode`

| 位置 | 字段 | 类型 | 语义 | 来源 |
|------|------|------|------|------|
| `src/detect/episode.py:34` | `ChatMessage.timestamp` | `float` | Unix 秒时间戳 | 飞书 IM 事件时间 |
| `src/detect/episode.py:43` | `ChatEpisode.start_time` | `float` | Episode 首条消息时间 | 聚合 |
| `src/detect/episode.py:44` | `ChatEpisode.end_time` | `float` | Episode 末条消息时间 | 聚合 |
| `src/detect/suspend_pool.py:28` | `SuspendedEpisode.start_time` | `float` | 挂起 Episode 开始时间 | 初始消息 |
| `src/detect/suspend_pool.py:29` | `SuspendedEpisode.last_timestamp` | `float` | 最近更新时间 | 每次消息追加 |
| `src/detect/suspend_pool.py:32` | `SuspendedEpisode.suspended_at` | `float` | 挂起/归档时间 | 挂起操作 |

**特征**：
- 全部使用 `float`（Unix 时间戳），精度高但缺乏语义
- `ChatEpisode.duration` 计算属性（`end_time - start_time`）已存在
- **缺少** Episode 角色语义（initiating/climax/concluding 等时间标注）

#### L1：Episode 节点层 — `EpisodeNode` / `EpisodeHyperedge`

| 位置 | 字段 | 类型 | 语义 |
|------|------|------|------|
| `src/structure.py:156` | `EpisodeNode.timestamp` | `Optional[datetime]` | Episode 事件时间 |
| `src/structure.py:261` | `EpisodeHyperedge.created_at` | `Optional[datetime]` | 超边创建时间 |
| `src/structure.py:137` | `FactHyperedge.created_at` | `Optional[datetime]` | 事实超边创建时间 |
| `src/structure.py:67` | `FactNode.timestamp` | `Optional[datetime]` | 事实时间戳 |

**特征**：
- `EpisodeNode.timestamp` 是 `datetime` 类型，但由原始的 `float` 转换而来
- 时间精度仅到秒级，缺少微秒/毫秒（影响消息级时序排列）
- **缺少** `start_timestamp` / `end_timestamp` / `duration` 语义字段
- `EpisodeHyperedge` 的 `created_at` 描述了"何时被聚合"，而非"Episode 自身的时间跨度"

#### L2: 决策节点层 — `DecisionNode`

| 位置 | 字段 | 类型 | 语义 | 当前状态 |
|------|------|------|------|----------|
| `src/node/node.py:105` | `created_at` | `Optional[datetime]` | 决策创建时间 | ✅ **存在但非必须**（default=None） |
| `src/node/node.py:106` | `updated_at` | `Optional[datetime]` | 决策更新时间 | ✅ **存在但非必须**（default=None） |
| `src/node/node.py:87` | `decided_at` | `Optional[datetime]` | 决策确认时间 | ⚠️ 仅 `change_status()` 设置 |
| `src/node/types.py:79` | `Objection.created_at` | `Optional[datetime]` | 异议创建时间 | ✅ |
| `src/node/types.py:172` | `AccessStats.last_accessed_at` | `Optional[datetime]` | 最近访问时间 | ✅ 用于热度计算 |
| `src/node/types.py:176` | `AccessStats.last_calculated` | `Optional[datetime]` | 热度最近计算时间 | ✅ |

**特征**：
- `created_at` 和 `updated_at` 在 `DecisionNode.__init__` 中默认为 `None`，仅在 MCP Server 的 `create_decision`（server.py:668-673）和 `PipelineEngine._apply_create`（engine.py:138-139）中设置
- `decided_at` 仅通过 `change_status(DecisionStatus.DECIDED)` 设置，但 `DecisionNode` 没有 `proposed_at`、`confirmed_at`、`obsoleted_at` 等生命周期时间戳
- **已有字段但未索引**：`created_at` 和 `updated_at` 未在 `MemoryGraph` 的索引中被专门维护

#### L3: Git 版本化层

| 位置 | 字段 / 能力 | 语义 |
|------|-------------|------|
| `src/storage/git_storage.py:263` | `get_commit_log()` | Git 提交历史（全局） |
| `src/storage/git_storage.py:281` | `get_decision_history()` | 单决策文件提交历史 |
| `src/storage/git_storage.py:266` | `blame_decision()` | 每行最后修改人追溯 |
| `src/storage/git_storage.py:270` | `search_content()` | 跨决策全文搜索 |
| `src/mcp_server/server.py:431` | `git_history` (MCP 工具) | 暴露 Git log 给 AI 客户端 |
| `src/mcp_server/server.py:635` | `decision_history` (MCP 工具) | 暴露单决策版本历史 |
| `src/mcp_server/server.py:460` | `git_blame` (MCP 工具) | 暴露代码追溯 |

**特征**：
- Git 层面提供了完整的版本历史，但**与决策语义（status 生命周期）脱钩**
- `get_decision_history` 返回的是 Git commit 级别的变化，不包含"为什么变了"（status change 语义）
- 无法直接回答"这个决策什么时候从 proposed 变为 decided 的"

### 1.3 MCP 时间线相关工具矩阵

| 工具名 | 位置 | 排序依据 | 时间筛选能力 | 状态筛选 |
|--------|------|----------|-------------|---------|
| `list_decisions` | server.py:282 | `created_at` 倒序 | ❌ | ❌（默认仅活跃） |
| `recent_decisions` | server.py:405 | `created_at` > since | `hours` 参数 | ✅ `is_active()` |
| `timeline` | 无独立实现 | — | — | — |
| `decision_history` | server.py:635 | Git commit 时间 | ❌ | — |
| `git_history` | server.py:431 | Git commit 时间（全局） | ❌ | — |
| `hot_decisions` | server.py:359 | 热度值（含时间衰减） | `min_score` | ✅ |
| `forgotten_decisions` | server.py:368 | 低热度（含时间衰减） | `max_score` | ✅ |
| `decision_tree` | server.py:604 | 递归子层级 | ❌ | ✅ |
| `show_tree` | server.py:623 | 根+递归层级 | ❌ | ✅ |

**关键发现**：MCP Server 中有 **39 个工具，但没有任何一个专门的 `timeline` 工具**。README 中声明了 `timeline` 工具名，但实际代码中没有实现。现有的时间相关功能散落在 `list_decisions`（按时间倒序）和 `recent_decisions`（按小时筛选）两个工具中，缺乏统一的、结构化时间线视图。

### 1.4 Mutation 系统时间追踪

`src/core/mutations.py` 定义了 8 种 Mutation 类型：

| MutationType | 时间记录 | 说明 |
|-------------|----------|------|
| CREATE | `created_at = datetime.now()` | ✅ engine 中设置 |
| UPDATE | `updated_at = datetime.now()` | ✅ engine 中设置 |
| STATUS_CHANGE | `updated_at = datetime.now()` | ✅ engine 中设置 |
| CONFLICT_MERGE | ❌ 无时间记录 | 仅更新 target status |
| CONFLICT_KEEP_BOTH | ❌ 无时间记录 | 仅标记 conflict |
| OBJECTION | ❌ 无时间记录 | 添加到 node.objections |
| DEPRECATE | ❌ 无时间记录 | 仅 status 变更 |
| REVERT | ❌ 无时间记录 | 回滚到历史版本 |

**特征**：
- Mutation 本身**不携带时间戳**。`DecisionMutation` dataclass 没有任何时间字段
- 时间只在 `PipelineEngine` 处理 Mutation 时通过 `datetime.now()` 写入 `DecisionNode`
- 无法追溯"这个 Mutation 是什么时候发生的"——只能通过 `created_at`/`updated_at` 反推

---

## 2. 可追溯性缺口分析

### 2.1 缺口 1：决策生命周期无完整时间线

```
当前状态：
  时间 ──────────────────────────────────────→
                ┌────────────┐          ┌──────────┐
  未知开始时间  │  created   │  未知过程 │ updated  │
                │  (无proposal 标记)│          │ (无status变更时间)│
                └────────────┘          └──────────┘

目标状态：
  时间 ──────────────────────────────────────→
  ┌──────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌──────────┐
  │proposed│→│discussed│→│decided │→│updated │→│obsoleted │
  │_at   │  │_at     │  │_at    │  │_at    │  │_at      │
  └──────┘  └────────┘  └────────┘  └────────┘  └──────────┘
  每个生命周期阶段都有独立时间戳
```

**具体问题**：
- `DecisionNode` 有 `created_at` 和 `updated_at`，但**没有每个 status 变更的时间记录**
- `status` 字段可以取 10 种值（PENDING → PENDING_CONFIRMATION → IN_DISCUSSION → DECIDED → EXECUTING → COMPLETED / SHELVED / REJECTED / SUPERSEDED / DEPRECATED），但无法回答"什么时间进入了 DECIDED 状态"
- `decided_at` 字段存在但**使用不充分**：仅在 `change_status(DECIDED)` 时设置，其他状态变更无对应字段

### 2.2 缺口 2：Episode - Decision 时间关联断裂

**具体问题**：
```
Episode (timestamp: 2026-01-15T10:30:00)
  └─→ 提取管道 ──→ DecisionNode (created_at: 2026-01-15T10:32:15)
                      
  两个时间点相关但缺少：
  - episode_timestamp: 10:30:00 (消息发生时间)
  - extraction_timestamp: 10:32:15 (提取时间)
  - processing_duration: 2分15秒 (可追溯延迟)
```

- `DecisionNode` 有 `source_message_id` / `source_chat_id`，但**没有直接关联到 `EpisodeNode` 的 ID**
- 无法追溯"这个决策是从哪段对话 Episode 提取出来的"
- `DecisionNode.created_at` 记录的是**提取/创建时间**，而非**消息原始发生时间**
- `MemoryGraph` 中没有决策→Episode 的反向索引

### 2.3 缺口 3：Version Range 未索引，不可查询

**具体问题**：
- `DecisionNode.version_chain: List[VersionRange]`（node.py:102）定义了版本链数据结构，但**没有任何代码实际写入或维护 version_chain**
- `VersionRange` 有 `from_version` 和 `to` 字段，设计上可追踪版本生效期，但**完全未被使用**
- 每次 `UPDATE` 或 `STATUS_CHANGE` 时，版本递增（`version += 1`），但之前的版本何时开始/结束无从得知
- `git_commit_hash`（node.py:109）只保留最后一次 commit hash，不保留 commit 时间线

### 2.4 缺口 4：Mutation 本身无时间戳，不可审计

**具体问题**：
- `DecisionMutation`（mutations.py:19）没有 `timestamp` 字段
- 8 种 Mutation 类型中有 5 种（CONFLICT_MERGE / CONFLICT_KEEP_BOTH / OBJECTION / DEPRECATE / REVERT）在 engine 中执行时**不更新 `updated_at`**
- 无法回答审计场景：谁、什么时候、做了什么变更

### 2.5 缺口 5：Git 提交与决策状态变更脱钩

**具体问题**：
```
Git 提交历史：
  a1b2c3 - "Update decision xxx"
  d4e5f6 - "Update decision xxx"
  g7h8i9 - "Create decision xxx"

能回答：这个决策被修改过几次
不能回答：第几次是状态变更（pending→decided）？
          第几次是内容变更？
```

- Git commit message 是"Update decision {sid}"，**不区分 content update 还是 status change**
- `decision_history` MCP 工具只返回 Git log，不包含对应的 status 变更信息
- 无法跨决策聚合"某一天有多少决策被确认/被拒绝"

### 2.6 缺口 6：父子决策缺少时间轴推理

**具体问题**：
```
父决策 A (created: 10:00)
  ├── 子决策 B (created: 10:05, 关系: DEPENDS_ON)
  └── 子决策 C (created: 11:00, 关系: REFINES)

现有能力：
  decision_tree(A) → 返回 {A, B, C} 层级
  
缺少的推理：
  B 依赖 A，时间差 5 分钟 → 高粘性推理
  A 和 C 时间差 1 小时 → 可能是独立演化
  同一时间段的父子 → 可能是并行讨论
```

- `decision_children` / `decision_descendants` / `decision_ancestors` 工具支持树结构查询，但**不带时间维度**
- 无法按"时间窗口 + 父子关系"进行推理分析

### 2.7 缺口 7：热点/遗忘算法时间维度单一

- `recalculate_hot_score()`（memory_graph.py:219）只使用 `created_at` 计算时间衰减：`25.0 - days_since_created * 1.5`
- 不使用 `updated_at`（最近修改时间）、`last_accessed_at`（最近访问时间）
- 一个长期未被修改但最近被大量访问的决策，热度计算中无法反映其"重新活跃"

---

## 3. 优化方案

### 3.1 方案一：决策生命周期时间戳（P0 — 立即实施）

#### 设计目标
为 `DecisionNode` 增加每个生命周期阶段的时间戳，实现完整的"决策时间线"。

#### 实现细节

**Step 1：在 `DecisionNode` 中增加时间戳字段**

```python
# 新增字段（src/node/node.py）
proposed_at: Optional[datetime] = Field(default=None)
discussed_at: Optional[datetime] = Field(default=None)
decided_at: Optional[datetime] = Field(default=None)
executed_at: Optional[datetime] = Field(default=None)
completed_at: Optional[datetime] = Field(default=None)
shelved_at: Optional[datetime] = Field(default=None)
rejected_at: Optional[datetime] = Field(default=None)
superseded_at: Optional[datetime] = Field(default=None)
```

**Step 2：扩展 `change_status()` 自动设置对应时间戳**

```python
# src/node/node.py
def change_status(self, new_status: DecisionStatus) -> None:
    self.status = new_status
    self.updated_at = datetime.now()
    # 自动设置生命周期时间戳
    if new_status == DecisionStatus.DECIDED:
        self.decided_at = self.decided_at or datetime.now()
    elif new_status == DecisionStatus.EXECUTING:
        self.executed_at = self.executed_at or datetime.now()
    elif new_status == DecisionStatus.COMPLETED:
        self.completed_at = self.completed_at or datetime.now()
    # 其他状态同理...
```

**Step 3：更新 `_node_to_dict` 输出所有时间戳**

```python
# src/mcp_server/server.py
# 在 _node_to_dict() 中添加
"proposed_at": node.proposed_at.isoformat() if node.proposed_at else "",
# 同理 for decided_at, superseded_at 等
```

**Step 4：新增/更新 MCP 工具**

```python
# 在 src/mcp_server/server.py 新增
@mcp.tool(name="decision_timeline", description="获取决策的完整生命周期时间线")
def decision_timeline(sid: str) -> str:
    """返回决策的生命周期时间轴 + 状态变更历史"""
    ...

@mcp.tool(name="timeline", description="获取全局时间线视图")
def timeline(start: str = "", end: str = "", status_filter: str = "", 
             topic: str = "", top_k: int = 50) -> str:
    """统一的时间线查询：时间范围 + 状态筛选 + 议题筛选"""
    ...
```

#### 影响评估

| 维度 | 影响 |
|------|------|
| 向后兼容 | ✅ 新增字段含 default=None，已有决策自动向后兼容 |
| 存储增长 | ~200 bytes/决策（9 个 Optional datetime），可忽略 |
| 查询性能 | 新增字段在 `_node_to_dict` 中无条件输出，无额外查询 |
| 代码变更 | DecisionNode（+9字段） + engine.py（`change_status`） + server.py（`_node_to_dict`）+ 新工具 |

---

### 3.2 方案二：可审计的 Mutation 时间线（P0 — 与方案一同时实施）

#### 设计目标
让每次 Mutation 携带时间戳，构建可审计的决策变更日志。

#### 实现细节

**Step 1：Mutation 增加时间戳**

```python
# src/core/mutations.py
@dataclass
class DecisionMutation:
    # 新增
    timestamp: Optional[datetime] = None
    mutation_metadata: Dict[str, Any] = field(default_factory=dict)
    # mutation_metadata 可包含：
    #   "agent_id": "agent-xxx" / "user_id": "user-xxx"
    #   "reason": "human correction"
    #   "source": "mcp_tool / sleep / auto"
```

**Step 2：Engine 中维护 Mutation 历史**

```python
# src/core/engine.py
class PipelineEngine:
    # 新增
    _mutation_history: List[Dict] = field(default_factory=list)
    
    def apply_mutation(self, mut: DecisionMutation) -> bool:
        if mut.timestamp is None:
            mut.timestamp = datetime.now()
        result = super().apply_mutation(mut)
        if result:
            self._mutation_history.append({
                "timestamp": mut.timestamp.isoformat(),
                "type": mut.mtype.value,
                "sid": mut.sdr_id,
                "old_status": mut.old_status,
                "new_status": mut.new_status,
            })
        return result
```

**Step 3：新增 MCP 审计工具**

```python
@mcp.tool(name="decision_audit", 
          description="获取决策的完整变更审计日志（包含每次 status change）")
def decision_audit(sid: str) -> str:
    """返回 Mutation 历史 + Git 提交历史，合并展示"""
    ...
```

#### 影响评估

| 维度 | 影响 |
|------|------|
| 向后兼容 | ✅ 新增字段含 default=None |
| 内存增长 | Mutation 历史仅保留在内存中，重启后丢失（可通过 Git 重新构建） |
| 可选增强 | 若需持久化，可将 Mutation 历史同步写入 Git（作为 commit message 元数据） |

---

### 3.3 方案三：Episode ↔ Decision 时间关联（P1 — 重要）

#### 设计目标
构建 Episode 节点与 Decision 节点之间的双向时间关联，支持"决策←消息"的溯源。

#### 实现细节

**Step 1：`DecisionNode` 增加 Episode 关联字段**

```python
# src/node/node.py
# 新增字段
episode_id: str = Field(default="", description="Source Episode ID")
episode_timestamp: Optional[datetime] = Field(default=None, description="Source episode timestamp")
extraction_duration: Optional[float] = Field(default=None, description="Extraction duration in seconds")
```

**Step 2：在提取管道中填充关联**

```python
# 提取时（extractors/decision_extractor.py 或相关代码）
decision_node.episode_id = episode_node.id
decision_node.episode_timestamp = episode_node.timestamp
decision_node.extraction_duration = (
    datetime.now() - episode_node.timestamp
).total_seconds()
```

**Step 3：`MemoryGraph` 增加反向索引**

```python
# src/graph/memory_graph.py
class MemoryGraph:
    # 新增
    _episode_decisions: Dict[str, List[str]] = {}  # episode_id → [decision_sid]
    
    def get_decisions_by_episode(self, episode_id: str) -> List[DecisionNode]:
        """通过 Episode ID 查找其产生的所有决策"""
        ...
    
    def get_episode_by_decision(self, sid: str) -> Optional[EpisodeNode]:
        """通过决策 SDRID 查找源 Episode"""
        ...
```

#### 影响评估

| 维度 | 影响 |
|------|------|
| 向后兼容 | ✅ 新增字段含 default |
| 索引增长 | `_episode_decisions` 字典，与决策数线性相关 |
| 提取管道 | 需修改 decision_extractor.py，约 +30 行 |

---

### 3.4 方案四：Version Range 启用 + Git-Status 联动（P1 — 重要）

#### 设计目标
启用 `version_chain` 字段，将 Git 提交与决策 status 变更关联起来。

#### 实现细节

**Step 1：每次 UPDATE/STATUS_CHANGE 时维护 version_chain**

```python
# src/core/engine.py
def _apply_update(self, mut: DecisionMutation) -> bool:
    # 修改前
    old_version = existing.version
    
    # 记录当前版本范围
    existing.version_chain.append(VersionRange(
        from_version=f"v{old_version}.0",
        to=f"v{existing.version}.0",
    ))
    
    existing.version += 1
    ...
```

**Step 2：Git commit message 包含 status 语义**

```python
# src/storage/git_storage.py 或 engine.py 中写决策时
# 当前: "Update decision {sid}"
# 改为: "status: pending→decided | decision/{sid} | updated by mcp_tool"
commit_msg = f"status: {old_status}→{new_status} | decision/{sid}" if status_changed else f"update: decision/{sid}"
```

**Step 3：`decision_history` MCP 工具增强**

```python
# 当前输出：Git commit log only
# 增强后：Git commit log + 对应 status + 变更原因
"history": [
    {
        "hash": "...",
        "date": "...",
        "status": "pending→decided",  # 新增
        "reason": "human confirmation via card",  # 新增
    }
]
```

---

### 3.5 方案五：父子决策时间轴推理（P2 — 增量价值）

#### 设计目标
新增 MCP 工具，支持基于时间的父子决策关系推理分析。

#### 实现细节

**新增 MCP 工具**

```python
@mcp.tool(name="decision_timeline_analyze",
          description="分析决策的时间轴关系：父子时间差、并行决策检测、时间窗口聚类")
def decision_timeline_analyze(sid: str, window_hours: int = 24) -> str:
    """
    对指定决策及其子决策进行时间轴分析：
    - 父子创建时间差（决策响应速度）
    - 并行决策检测（同一时间窗口内的兄弟决策）
    - 时间窗口聚类（按时间窗口分组的决策集）
    - 决策链时间映射（根→叶的连续时间线）
    """
    ...
```

#### 输出示例

```json
{
    "sid": "abc123",
    "chain_duration": {
        "root_to_deepest": "3h 25m",
        "average_child_gap": "25m"
    },
    "parallel_decisions": [
        {"sid": "def456", "overlap": "45m", "relation": "RELATES_TO"}
    ],
    "time_clusters": [
        {"window": "2026-01-15 10:00-11:00", "decision_count": 4, "context": "morning discussion"},
        {"window": "2026-01-15 14:00-15:30", "decision_count": 2, "context": "afternoon review"}
    ]
}
```

---

### 3.6 方案六：热点算法时间维度增强（P2 — 锦上添花）

#### 设计目标
让 `recalculate_hot_score()` 使用多维度时间信息，更精准反映决策活跃度。

```python
# src/graph/memory_graph.py 修改 recalculate_hot_score

# 当前：
# base_score = min(25.0, 25.0 - days_since_created * 1.5)

# 增强为三维时间衰减：
base_score = min(25.0, 25.0 - days_since_created * 0.8)  # 创建时间（衰减更慢）
recency_bonus = 0.0
days_since_update = 0.0
days_since_access = 0.0

if d.updated_at:
    days_since_update = (datetime.now() - d.updated_at).total_seconds() / 86400.0
    recency_bonus = max(0, 10.0 - days_since_update * 2.0)  # 最近更新加分

if d.access_stats.last_accessed_at:
    days_since_access = (datetime.now() - d.access_stats.last_accessed_at).total_seconds() / 86400.0
    recency_bonus += max(0, 5.0 - days_since_access * 1.0)  # 最近访问加分

hot_score = ref_score * 0.35 + access_score * 0.15 + relation_score * 0.15 + base_score + recency_bonus
```

---

## 4. 实施路线图

### 4.1 优先级与依赖关系

```
P0 ────────────── 立即实施（无外部依赖）
├── 方案一：决策生命周期时间戳     ← 独立
└── 方案二：可审计的 Mutation 时间线  ← 独立，可与方案一并行

P1 ────────────── 重要（依赖 P0 部分完成）
├── 方案三：Episode↔Decision 时间关联  ← 依赖方案一（created_at 已有）
└── 方案四：Version Range 启用 + Git-Status 联动 ← 依赖方案二

P2 ────────────── 增量价值
├── 方案五：父子决策时间轴推理  ← 依赖方案一
└── 方案六：热点算法时间维度增强  ← 独立
```

### 4.2 文件变更清单

| 文件 | P0 | P1 | P2 | 合计 |
|------|----|----|----|------|
| `src/node/node.py` | +9 字段 + `change_status` 增强 | +2 字段 | — | +11 字段 |
| `src/node/types.py` | — | — | — | 0 |
| `src/core/mutations.py` | +1 字段 | — | — | +1 字段 |
| `src/core/engine.py` | + `_mutation_history` + 版本链维护 | — | — | — |
| `src/graph/memory_graph.py` | — | + 反向索引 | + 热点算法增强 | ~30 行 |
| `src/mcp_server/server.py` | + `timeline` + `decision_timeline` 工具 | + `decision_audit` 增强 | + `decision_timeline_analyze` | ~100 行 |
| `src/storage/git_storage.py` | — | + commit msg 语义增强 | — | ~5 行 |
| `src/extractors/decision_extractor.py` | — | + episode 关联填充 | — | ~20 行 |
| `src/detect/episode.py` | — | — | — | 0 |

### 4.3 预计工作量

| 阶段 | 预估工时 | 产出 |
|------|---------|------|
| P0（方案一 + 方案二） | 2-3 天 | `timeline` MCP 工具上线，决策生命周期可追溯 |
| P1（方案三 + 方案四） | 2-3 天 | 决策↔Episode 双向关联，Git 提交语义化 |
| P2（方案五 + 方案六） | 1-2 天 | 时间轴推理分析工具，热点算法精准化 |
| **合计** | **5-8 天** | 完整的结构化决策时间线系统 |

---

## 附录：现有时间相关字段汇总

```
层             字段                               类型             存在性
────           ──────                             ────            ──────
IM消息         ChatMessage.timestamp              float            ✅
               ChatEpisode.start_time             float            ✅
               ChatEpisode.end_time               float            ✅
               ChatEpisode.duration               property(float)  ✅
               SuspendedEpisode.start_time         float            ✅
               SuspendedEpisode.last_timestamp     float            ✅
               SuspendedEpisode.suspended_at       float            ✅

Episode        EpisodeNode.timestamp              datetime         ✅
               EpisodeHyperedge.created_at         datetime         ✅
               FactNode.timestamp                  datetime         ✅
               FactHyperedge.created_at            datetime         ✅

Decision       DecisionNode.created_at             datetime         ✅（但 default=None）
               DecisionNode.updated_at             datetime         ✅（但 default=None）
               DecisionNode.decided_at             datetime         ⚠️（仅 change_status 设置）
               DecisionNode.version_chain          List[VersionRange]  ❌（定义但不维护）
               Objection.created_at                datetime         ✅
               AccessStats.last_accessed_at        datetime         ✅
               AccessStats.last_calculated         datetime         ✅

Git            get_decision_history               List[CommitLog]  ✅
               get_commit_log                     List[CommitLog]  ✅
               git_commit_hash                     str             ✅（仅最后 commit）

Mutation       DecisionMutation.timestamp          datetime         ❌（不存在）
```

---

*文档结束*