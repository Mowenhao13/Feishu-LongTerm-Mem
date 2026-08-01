# 飞书多维表格决策可视化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Git 仓库中的决策数据同步到飞书多维表格（Base），实现决策可视化

**Architecture:** GitStorage 的 `write_decision()` 在 commit 成功后触发 `post_commit_hooks` → `BaseViewSyncer.sync_decision(sid)` 增量同步单条决策到 Base。程序启动时调用 `full_sync()` 全量初始化 Base 表结构和数据。MCP 写操作工具保留接口但不触发同步。

**Tech Stack:** Python, lark_oapi SDK, GitStorage (已有), MemoryGraph (已有)

---

## 文件变更总览

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `src/storage/git_storage.py` | 增加 post_commit_hooks 基础设施 |
| 新建 | `src/view/__init__.py` | 导出 BaseViewSyncer |
| 新建 | `src/view/schema.py` | 多维表格表结构定义 |
| 新建 | `src/view/client.py` | 飞书 Base API 封装 |
| 新建 | `src/view/syncer.py` | 同步引擎（全量+增量） |

---

### Task 1: GitStorage — 增加 post_commit_hooks

**Files:**
- Modify: `src/storage/git_storage.py`

**改动点：**

- [ ] **Step 1: 在 `GitStorage.__init__` 中增加 hooks 字段**

在 `self._init_repo()` 后添加：

```python
from typing import Callable

# 在 __init__ 方法末尾
self.post_commit_hooks: List[Callable[[str], None]] = []
```

- [ ] **Step 2: 增加 `_run_post_commit_hooks` 方法**

```python
def _run_post_commit_hooks(self, sid: str) -> None:
    for hook in self.post_commit_hooks:
        try:
            hook(sid)
        except Exception as e:
            logger.error(f"Post-commit hook failed for {sid}: {e}")
```

- [ ] **Step 3: 在 `write_decision()` 的 commit 成功后调用钩子**

找到 `commit_hash = self._cli.commit(rel_path, msg)` 之后（原第 129-131 行），添加：

```python
self._run_post_commit_hooks(sid)
```

注意：`sid` 已经在方法内第 112 行定义。这段代码应在 `finally` 块之前执行（commit 成功后、切换回原分支前）。

- [ ] **Step 4: 提交**

```bash
git add src/storage/git_storage.py
git commit -m "feat: add post_commit_hooks to GitStorage"
```

---

### Task 2: 创建 schema.py — 多维表格表结构定义

**Files:**
- Create: `src/view/schema.py`

- [ ] **Step 1: 创建 schema.py**

```python
from typing import Any, Dict, List, Optional, Tuple

TABLE_NAME = "决策列表"

FIELD_DECISION_ID  = "决策ID"
FIELD_TOPIC        = "决策主题"
FIELD_VERSION      = "决策版本"
FIELD_STATUS       = "决策状态"
FIELD_TITLE        = "决策标题"
FIELD_CONTENT      = "决策内容"
FIELD_ASSIGNEE     = "决策关联人"
FIELD_CREATED_AT   = "决策提出时间"
FIELD_HOT_SCORE    = "决策热点值"
FIELD_CONFLICT_SID = "冲突关联决策"

ALL_FIELD_NAMES = [
    FIELD_DECISION_ID, FIELD_TOPIC, FIELD_VERSION,
    FIELD_STATUS, FIELD_TITLE, FIELD_CONTENT,
    FIELD_ASSIGNEE, FIELD_CREATED_AT, FIELD_HOT_SCORE,
    FIELD_CONFLICT_SID,
]

STATUS_OPTIONS = [
    {"name": "decided",  "color": 0},
    {"name": "rejected", "color": 4},
    {"name": "conflict", "color": 3},
    {"name": "draft",    "color": 2},
]

STATUS_COLORS = {"decided": 0, "rejected": 4, "conflict": 3, "draft": 2}
```

- [ ] **Step 2: 提交**

```bash
git add src/view/schema.py
git commit -m "feat: add Base table schema definition"
```

---

### Task 3: 创建 client.py — 飞书 Base API 封装

**Files:**
- Create: `src/view/client.py`

**功能：** 使用 `lark_oapi` SDK，Bot 身份认证，封装 Base CRUD 操作。
Base token 和 table id 持久化到 `src/view/.view_meta.json`。

- [ ] **Step 1: 创建 client.py**

```python
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppRequest, CreateAppResponse, ReqApp,
    CreateAppTableRequest, CreateAppTableResponse,
    CreateAppTableRecordRequest, CreateAppTableRecordResponse,
    UpdateAppTableRecordRequest, UpdateAppTableRecordResponse,
    SearchAppTableRecordRequest, SearchAppTableRecordResponse,
    SearchAppTableRecordRequestBody,
    ListAppTableRequest, ListAppTableResponse,
    BatchDeleteAppTableRecordRequest, BatchDeleteAppTableRecordRequestBody,
    AppTableRecord, AppTableCreateHeader, ReqTable,
)
from lark_oapi.api.base.v1 import App

from src.utils.logger import get_logger
from .schema import (
    ALL_FIELD_NAMES, STATUS_OPTIONS, TABLE_NAME,
    FIELD_DECISION_ID,
)

logger = get_logger(__name__)

META_FILE = Path(__file__).resolve().parent / ".view_meta.json"


class BaseViewClient:
    def __init__(self):
        self._client: Optional[lark.Client] = None
        self._base_token: Optional[str] = None
        self._table_id: Optional[str] = None
        self._load_meta()

    # ============ 认证 ============

    def _get_client(self) -> lark.Client:
        if self._client is None:
            self._client = lark.Client.builder() \
                .app_id(os.environ.get("LARK_APP_ID", "")) \
                .app_secret(os.environ.get("LARK_APP_SECRET", "")) \
                .log_level(lark.LogLevel.ERROR) \
                .build()
        return self._client

    # ============ Base 元信息持久化 ============

    def _meta_path(self) -> Path:
        return META_FILE

    def _load_meta(self) -> None:
        meta_path = self._meta_path()
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                self._base_token = data.get("base_token")
                self._table_id = data.get("table_id")
            except Exception:
                pass

    def _save_meta(self) -> None:
        data = {
            "base_token": self._base_token,
            "table_id": self._table_id,
        }
        self._meta_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ============ Base 管理 ============

    def ensure_base(self, name: str = "feishu-mem-决策看板") -> str:
        if self._base_token:
            return self._base_token

        client = self._get_client()
        body = ReqApp.builder().name(name).build()
        request = CreateAppRequest.builder().request_body(body).build()
        response: CreateAppResponse = client.bitable.v1.app.create(request)

        if not response.success():
            raise RuntimeError(
                f"Failed to create Base: code={response.code}, msg={response.msg}"
            )

        self._base_token = response.data.app_token
        self._save_meta()
        logger.info("Created Base: %s (token=%s)", name, self._base_token)
        return self._base_token

    def ensure_table(self) -> str:
        if self._table_id:
            return self._table_id

        base_token = self.ensure_base()
        client = self._get_client()

        fields = [
            AppTableCreateHeader.builder()
                .field_name(FIELD_DECISION_ID).type(1).build(),
            AppTableCreateHeader.builder()
                .field_name("决策主题").type(3)
                .property(self._build_single_select_property([])).build(),
            AppTableCreateHeader.builder()
                .field_name("决策版本").type(2).build(),
            AppTableCreateHeader.builder()
                .field_name("决策状态").type(3)
                .property(self._build_single_select_property(STATUS_OPTIONS)).build(),
            AppTableCreateHeader.builder()
                .field_name("决策标题").type(1).build(),
            AppTableCreateHeader.builder()
                .field_name("决策内容").type(1).build(),
            AppTableCreateHeader.builder()
                .field_name("决策关联人").type(11).build(),
            AppTableCreateHeader.builder()
                .field_name("决策提出时间").type(5).build(),
            AppTableCreateHeader.builder()
                .field_name("决策热点值").type(2).build(),
            AppTableCreateHeader.builder()
                .field_name("冲突关联决策").type(1).build(),
        ]

        body = ReqTable.builder() \
            .name(TABLE_NAME) \
            .default_view_name("决策视图") \
            .fields(fields) \
            .build()

        request = CreateAppTableRequest.builder() \
            .app_token(base_token) \
            .request_body(CreateAppTableRequestBody.builder().table(body).build()) \
            .build()

        response: CreateAppTableResponse = client.bitable.v1.app_table.create(request)

        if not response.success():
            raise RuntimeError(
                f"Failed to create table: code={response.code}, msg={response.msg}"
            )

        self._table_id = response.data.table_id
        self._save_meta()
        logger.info("Created table: %s (id=%s)", TABLE_NAME, self._table_id)
        return self._table_id

    @staticmethod
    def _build_single_select_property(
        options: List[Dict[str, Any]],
    ) -> Any:
        from lark_oapi.api.bitable.v1 import (
            AppTableFieldProperty,
            AppTableFieldPropertyOption,
        )
        opts = [AppTableFieldPropertyOption.builder()
                .name(o["name"]).color(o.get("color", 0)).build()
                for o in options]
        return AppTableFieldProperty.builder().options(opts).build()

    # ============ 记录操作 ============

    def search_record(self, sid: str) -> Optional[str]:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()

        body = SearchAppTableRecordRequestBody.builder() \
            .field_names([FIELD_DECISION_ID]) \
            .filter(self._build_filter(FIELD_DECISION_ID, sid)) \
            .build()

        request = SearchAppTableRecordRequest.builder() \
            .app_token(base_token).table_id(table_id) \
            .request_body(body).build()

        response = client.bitable.v1.app_table_record.search(request)

        if response.success() and response.data.items:
            return response.data.items[0].record_id
        return None

    @staticmethod
    def _build_filter(field_name: str, value: str) -> Any:
        from lark_oapi.api.bitable.v1 import Condition, FilterInfo
        return FilterInfo.builder().conjunction("and").conditions([
            Condition.builder().field_name(field_name).operator("is").value([value]).build()
        ]).build()

    def upsert_record(self, fields: Dict[str, Any]) -> None:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()

        sid = fields.get(FIELD_DECISION_ID, "")
        existing = self.search_record(sid) if sid else None

        if existing:
            request = UpdateAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id) \
                .record_id(existing) \
                .request_body(AppTableRecord.builder().fields(fields).build()) \
                .build()
            response = client.bitable.v1.app_table_record.update(request)
        else:
            request = CreateAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id) \
                .request_body(AppTableRecord.builder().fields(fields).build()) \
                .build()
            response = client.bitable.v1.app_table_record.create(request)

        if not response.success():
            logger.error(
                "Failed to upsert record for %s: code=%s, msg=%s",
                sid, response.code, response.msg,
            )

    def delete_all_records(self) -> None:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()

        request = SearchAppTableRecordRequest.builder() \
            .app_token(base_token).table_id(table_id) \
            .request_body(SearchAppTableRecordRequestBody.builder()
                .field_names([FIELD_DECISION_ID]).build()) \
            .build()

        response = client.bitable.v1.app_table_record.search(request)
        if not response.success():
            return

        record_ids = [item.record_id for item in response.data.items]
        if not record_ids:
            return

        batch_req = BatchDeleteAppTableRecordRequest.builder() \
            .app_token(base_token).table_id(table_id) \
            .request_body(BatchDeleteAppTableRecordRequestBody.builder()
                .records(record_ids).build()) \
            .build()

        client.bitable.v1.app_table_record.batch_delete(batch_req)
        logger.info("Deleted %d records from Base", len(record_ids))

    def batch_create_records(self, records: List[Dict[str, Any]]) -> None:
        base_token = self.ensure_base()
        table_id = self.ensure_table()
        client = self._get_client()

        for i, record in enumerate(records):
            request = CreateAppTableRecordRequest.builder() \
                .app_token(base_token).table_id(table_id) \
                .request_body(AppTableRecord.builder().fields(record).build()) \
                .build()
            response = client.bitable.v1.app_table_record.create(request)
            if not response.success():
                logger.error(
                    "Failed to create record %d (%s): code=%s",
                    i, record.get(FIELD_DECISION_ID, ""), response.code,
                )
            if (i + 1) % 10 == 0:
                time.sleep(0.5)
```

- [ ] **Step 2: 提交**

```bash
git add src/view/client.py
git commit -m "feat: add BaseViewClient for Feishu Base API"
```

---

### Task 4: 创建 syncer.py — 同步引擎

**Files:**
- Create: `src/view/syncer.py`

- [ ] **Step 1: 创建 syncer.py**

```python
from typing import Any, Dict, List, Optional

from src.storage.git_storage import GitStorage
from src.graph.memory_graph import MemoryGraph
from src.node.node import DecisionNode
from src.utils.logger import get_logger

from .client import BaseViewClient
from .schema import (
    FIELD_DECISION_ID, FIELD_TOPIC, FIELD_VERSION,
    FIELD_STATUS, FIELD_TITLE, FIELD_CONTENT,
    FIELD_ASSIGNEE, FIELD_CREATED_AT, FIELD_HOT_SCORE,
    FIELD_CONFLICT_SID, STATUS_COLORS,
)

logger = get_logger(__name__)

PROJECT = "default"


class BaseViewSyncer:
    def __init__(self, storage: GitStorage, graph: MemoryGraph):
        self._storage = storage
        self._graph = graph
        self._client = BaseViewClient()

    def full_sync(self) -> None:
        logger.info("[BaseView] Starting full sync...")
        self._client.ensure_base()
        self._client.ensure_table()

        self._client.delete_all_records()

        decisions = self._graph.get_all_decisions()
        records = [self._decision_to_record(d) for d in decisions]

        self._client.batch_create_records(records)
        logger.info("[BaseView] Full sync completed: %d decisions synced", len(records))

    def sync_decision(self, sid: str) -> None:
        node = self._graph.get_decision(sid)
        if not node:
            logger.warning("[BaseView] Decision %s not found, skipping sync", sid)
            return
        record = self._decision_to_record(node)
        self._client.upsert_record(record)
        logger.info("[BaseView] Synced decision %s v%s", sid, node.version)

    def _decision_to_record(self, node: DecisionNode) -> Dict[str, Any]:
        status_str = node.status.value if hasattr(node.status, "value") else str(node.status)
        if self._graph.has_conflict(node.sid):
            status_str = "conflict"

        hot_score = 0.0
        if hasattr(node, "access_stats") and node.access_stats:
            hot_score = round(getattr(node.access_stats, "hot_score", 0.0), 1)

        created_ts = None
        if node.created_at:
            created_ts = int(node.created_at.timestamp() * 1000)

        return {
            FIELD_DECISION_ID: node.sid,
            FIELD_TOPIC: {"text": node.topic_id or ""},
            FIELD_VERSION: node.version,
            FIELD_STATUS: {"text": status_str},
            FIELD_TITLE: node.summary or "",
            FIELD_CONTENT: node.full_text or "",
            FIELD_ASSIGNEE: self._resolve_assignee(node),
            FIELD_CREATED_AT: created_ts,
            FIELD_HOT_SCORE: hot_score,
            FIELD_CONFLICT_SID: self._resolve_conflict_sid(node),
        }

    @staticmethod
    def _resolve_assignee(node: DecisionNode) -> List[Dict[str, str]]:
        ids = []
        if node.assignee:
            ids.append({"id": node.assignee})
        if node.authority:
            ids.append({"id": node.authority})
        return ids

    def _resolve_conflict_sid(self, node: DecisionNode) -> str:
        if not hasattr(node, "relations") or not node.relations:
            return ""
        for rel in node.relations:
            if hasattr(rel, "type") and "conflict" in str(rel.type).lower():
                return rel.target_id or ""
        return ""
```

- [ ] **Step 2: 提交**

```bash
git add src/view/syncer.py
git commit -m "feat: add BaseViewSyncer for decision sync"
```

---

### Task 5: 创建 __init__.py

**Files:**
- Create: `src/view/__init__.py`

- [ ] **Step 1: 创建 __init__.py**

```python
from .syncer import BaseViewSyncer
from .client import BaseViewClient

__all__ = ["BaseViewSyncer", "BaseViewClient"]
```

- [ ] **Step 2: 提交**

```bash
git add src/view/__init__.py
git commit -m "feat: add view package init"
```

---

### Task 6: 在应用入口注册 Hook

**Files:**
- Modify: `src/mcp_server/server.py` — 在 `ensure_loaded()` 或初始化处注册 hook
- Modify: `src/core/engine.py` — 在 `_init_repo` 处注册 hook

**注意：** `MemoryLoader.ensure_loaded()` 中的 `GitStorage` 和 `MemoryGraph` 实例是局部变量，需要将 syncer 作为模块级对象注册 hook。

- [ ] **Step 1: 在 mcp_server/server.py 中注册 hook**

在文件头部导入 `BaseViewSyncer`：

```python
from src.view import BaseViewSyncer
```

在 `MemoryLoader.ensure_loaded()` 方法内，创建 storage 和 graph 后，注册 hook：

```python
# 在 self._graph = graph 之后添加
self._syncer = BaseViewSyncer(self._storage, self._graph)
self._storage.post_commit_hooks.append(self._syncer.sync_decision)
# 全量初始化
self._syncer.full_sync()
```

需在 `MemoryLoader.__init__` 中增加 `self._syncer: Optional[BaseViewSyncer] = None`。

- [ ] **Step 2: 在 core/engine.py 中注册 hook（可选）**

在 `MemoryEngine.__init__` 中，`self._storage` 创建后，如果也开启同步，注册 hook：

```python
if self._storage:
    from src.view import BaseViewSyncer
    try:
        self._syncer = BaseViewSyncer(self._storage, self._graph)
        self._storage.post_commit_hooks.append(self._syncer.sync_decision)
        self._syncer.full_sync()
    except Exception as e:
        logger.warning("BaseView sync init failed (non-fatal): %s", e)
```

并在 `MemoryEngine.__init__` 中增加 `self._syncer: Optional[BaseViewSyncer] = None`。

- [ ] **Step 3: 提交**

```bash
git add src/mcp_server/server.py src/core/engine.py
git commit -m "feat: register BaseView syncer hooks in application"
```