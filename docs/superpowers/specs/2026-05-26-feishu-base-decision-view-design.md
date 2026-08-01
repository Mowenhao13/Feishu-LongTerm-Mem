# 飞书多维表格决策可视化方案设计

## 1. 概述

将 Git 仓库中存储的决策数据同步到飞书多维表格（Base），实现决策的可视化浏览和管理。多维表格作为只读视图展示，数据源始终以 Git 仓库为准。

## 2. 架构

```
┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────┐
│  GitStorage          │ ──→  │  BaseViewSyncer       │ ──→  │  飞书多维表格    │
│                      │      │  src/view/syncer.py   │      │  (Base)          │
│  write_decision()    │      │                      │      └──────────────────┘
│  commit 成功后触发   │      │  注册为 post_hook     │
│  post_commit_hooks   │      │                      │
└──────────────────────┘      │  ┌──────────────┐    │
                              │  │ client.py    │    │
                              │  │  Base API 封装│    │
                              │  └──────────────┘    │
                              │  ┌──────────────┐    │
                              │  │ schema.py    │    │
                              │  │  表结构定义   │    │
                              │  └──────────────┘    │
                              └──────────────────────┘

┌──────────────────────┐
│  MCP Tools           │
│  (写操作: 保留接口)  │
│  不触发同步          │
└──────────────────────┘
```

### 2.1 触发链路

```
GitStorage.write_decision() / update_decision()
  → git commit (在 decision/{sid} 分支)
  → commit_hash 返回
  → post_commit_hooks 依次执行
  → BaseViewSyncer.sync_decision(sid) 被调用
  → 读取该 sid 最新 version 数据
  → 写入/更新到多维表格对应记录
```

### 2.2 全量初始化

```
启动时首次调用 full_sync()
  → BaseManager.ensure_base() 创建 Base(如已存在则复用)
  → BaseManager.ensure_table() 创建数据表及字段
  → 遍历 Git 所有 decision/* 分支
  → 取每个分支最新 version
  → 批量 upsert 到多维表格
```

## 3. 目录结构

```
src/view/
├── __init__.py       # 导出 BaseViewSyncer
├── client.py         # 飞书 Base API 封装
├── schema.py         # 表结构定义
└── syncer.py         # 同步引擎
```

## 4. 模块设计

### 4.1 schema.py — 表结构定义

```python
# 表名
TABLE_NAME = "决策列表"

# 字段定义: (字段名, 字段类型编号, 字段属性)
FIELD_DECISION_ID     = ("决策ID",     1, None)           # 文本
FIELD_TOPIC           = ("决策主题",   3, SingleSelect)    # 单选
FIELD_VERSION         = ("决策版本",   2, None)            # 数字
FIELD_STATUS          = ("决策状态",   3, SingleSelect)    # 单选
FIELD_TITLE           = ("决策标题",   1, None)            # 文本
FIELD_CONTENT         = ("决策内容",   1, None)            # 多行文本
FIELD_ASSIGNEE        = ("决策关联人", 11, None)           # 人员
FIELD_CREATED_AT      = ("决策提出时间", 5, None)          # 日期
FIELD_HOT_SCORE       = ("决策热点值", 2, None)            # 数字
FIELD_CONFLICT_SID    = ("冲突关联决策", 1, None)          # 文本

ALL_FIELDS = [
    FIELD_DECISION_ID, FIELD_TOPIC, FIELD_VERSION,
    FIELD_STATUS, FIELD_TITLE, FIELD_CONTENT,
    FIELD_ASSIGNEE, FIELD_CREATED_AT, FIELD_HOT_SCORE,
    FIELD_CONFLICT_SID,
]

# 单选字段可选值
TOPIC_OPTIONS = [...]       # 从已有决策数据动态获取
STATUS_OPTIONS = [
    ("decided", 0),    # 绿色
    ("rejected", 4),   # 红色
    ("conflict", 3),   # 橙色
    ("draft", 2),      # 灰色
]
```

### 4.2 client.py — Base API 封装

职责：
- 使用 `lark_oapi` SDK，Bot 身份（LARK_APP_ID / LARK_APP_SECRET）
- `ensure_base()`: 创建 Base（名称：`{project}-决策看板`），或根据持久化的 `base_token` 复用已有 Base
- `ensure_table()`: 创建数据表及字段，或根据持久化的 `table_id` 复用
- `upsert_record(fields: dict)`: 按决策ID匹配，存在则更新、不存在则创建
- `batch_upsert(records: list[dict])`: 批量写入（每批 ≤ 200 条）
- `clear_all_records()`: 全量同步前清空旧数据
- `search_record(sid: str)`: 按决策ID查找记录，返回 record_id
- `persist_meta(base_token, table_id)`: 将 Base 元信息保存到文件或配置

### 4.3 syncer.py — 同步引擎

```python
class BaseViewSyncer:
    def __init__(self, storage: GitStorage, graph: MemoryGraph):
        self._storage = storage
        self._graph = graph
        self._client = BaseViewClient()        # client.py
        self._schema = DecisionTableSchema()   # schema.py

    def full_sync(self) -> None:
        """全量同步：初始化 Base 并写入所有决策"""
        self._client.ensure_base()
        self._client.ensure_table(self._schema)
        decisions = self._graph.get_all_decisions()  # 遍历分支取最新 version
        records = [self._decision_to_record(d) for d in decisions]
        self._client.clear_all_records()
        self._client.batch_upsert(records)
        logger.info(f"Full sync completed: {len(records)} decisions")

    def sync_decision(self, sid: str) -> None:
        """增量同步单条决策"""
        self._client.ensure_table(self._schema)
        node = self._graph.get_decision(sid)
        if not node:
            logger.warning(f"Decision {sid} not found, skipping")
            return
        record = self._decision_to_record(node)
        self._client.upsert_record(record)
        logger.info(f"Synced decision {sid} v{node.version}")

    def _decision_to_record(self, node) -> dict:
        """将 DecisionNode 转为多维表格记录"""
        return {
            "决策ID": node.sid,
            "决策主题": node.topic_id,
            "决策版本": node.version,
            "决策状态": self._resolve_status(node),
            "决策标题": node.summary,
            "决策内容": node.full_text,
            "决策关联人": self._resolve_assignee(node),
            "决策提出时间": node.created_at.timestamp() * 1000 if node.created_at else None,
            "决策热点值": getattr(node.access_stats, "hot_score", 0) if node.access_stats else 0,
            "冲突关联决策": self._resolve_conflict_sid(node),
        }
```

### 4.4 GitStorage Hook 注册

在 `src/storage/git_storage.py` 中增加：

```python
class GitStorage:
    def __init__(self, config):
        ...
        self.post_commit_hooks: List[Callable[[str], None]] = []
        # ^ 钩子签名: (sid: str) -> None

    def _run_post_commit_hooks(self, sid: str) -> None:
        for hook in self.post_commit_hooks:
            try:
                hook(sid)
            except Exception as e:
                logger.error(f"Post-commit hook failed for {sid}: {e}")
```

在 `write_decision()` 和 `update_decision()` 的 commit 成功后调用 `self._run_post_commit_hooks(sid)`。

## 5. 表结构映射

| 多维表格字段 | DecisionNode 属性 | 类型 | 备注 |
|-------------|-------------------|------|------|
| 决策ID | `sid` | 文本 | 唯一键，用于 upsert 匹配 |
| 决策主题 | `topic_id` | 单选 | 选项值从数据中提取 |
| 决策版本 | `version` | 数字 | int |
| 决策状态 | `status` | 单选 | decided/rejected/conflict/draft |
| 决策标题 | `summary` | 文本 | |
| 决策内容 | `full_text` | 多行文本 | |
| 决策关联人 | `assignee` / `authority` | 人员 | 通过 Lark 用户 ID |
| 决策提出时间 | `created_at` | 日期 | 毫秒时间戳 |
| 决策热点值 | `access_stats.hot_score` | 数字 | |
| 冲突关联决策 | 冲突关系中的 sid | 文本 | 无冲突则为空 |

## 6. 视图配置（自动创建）

- 默认视图：表格视图，按"决策主题"分组，同一主题内按"决策版本"降序
- 冲突决策（状态=conflict）置顶或红色高亮
- 隐藏不必要的字段（如内部 ID）

## 7. 环境变量

```
# 已存在的认证变量（复用）
LARK_APP_ID=xxx
LARK_APP_SECRET=xxx

# 新增
BASE_VIEW_BASE_TOKEN=              # 持久化的 Base token，为空则自动创建
BASE_VIEW_TABLE_ID=                # 持久化的 table_id，为空则自动创建
BASE_VIEW_AUTO_SYNC=true           # 是否启用自动同步
```

## 8. 与 MCP Tools 的关系

MCP 写操作工具（`create_decision`, `update_decision` 等）保留接口签名和注册，内部实现保持当前逻辑不变。同步行为由 `GitStorage.post_commit_hooks` 驱动，与 MCP 工具解耦。

## 9. 错误处理

- Base API 调用失败 → 记录日志，不阻塞主流程
- Base 创建失败 → 降级跳过，下次 full_sync 重试
- 单条同步失败 → 不影响其他决策同步
- 限频控制：批量写入批次间延迟 0.5~1s