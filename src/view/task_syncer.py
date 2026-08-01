"""Task View Syncer — 将本地决策同步到飞书任务清单

核心功能：
1. 按 STORAGE_PATH 创建独立任务清单（名字与 STORAGE_PATH 一致）
2. 读写锁机制避免同步时重复创建/遗漏决策
3. 决策字段与记忆文件保持一致，标注 is_suggestion
4. 父子决策通过 parent_task_guid 在 task 视图层级显示
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dotenv import load_dotenv

from src.utils.logger import get_logger

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = get_logger(__name__)

# Meta 文件路径，存储 tasklist_guid 和已同步任务的映射
_VIEW_META_DIR = Path(__file__).resolve().parent
_VIEW_META_FILE = _VIEW_META_DIR / ".view_meta.json"

_BASE_URL = "https://open.feishu.cn/open-apis"


class TaskViewSyncer:
    """将本地 MemoryGraph 决策同步到飞书任务视图。

    Args:
        graph_path: 存储路径（即 STORAGE_PATH），用于生成任务清单名称和定位 meta 文件。
    """

    def __init__(self, graph_path: str = "") -> None:
        self._graph_path = graph_path or os.environ.get("STORAGE_PATH", "data")
        self._lock = threading.RLock()  # 读写锁保护同步过程
        self._syncing = False
        self._last_sync_time = 0.0
        self._cooldown = 5.0  # 同步冷却时间（秒），防抖

        # 加载 meta 数据
        self._meta = self._load_meta()
        self._tasklist_guid: Optional[str] = self._meta.get("tasklist_guid")
        # sid -> task_guid 映射
        self._synced_tasks: Dict[str, str] = self._meta.get("synced_tasks", {})

    def _load_meta(self) -> Dict[str, Any]:
        if _VIEW_META_FILE.exists():
            try:
                return json.loads(_VIEW_META_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_meta(self) -> None:
        _VIEW_META_FILE.write_text(
            json.dumps(self._meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    _tenant_token: Optional[str] = None
    _tenant_token_expires_at: float = 0

    @staticmethod
    def _get_user_token() -> Optional[str]:
        return os.environ.get("LARK_USER_ACCESS_TOKEN") or os.getenv("USER_ACCESS_TOKEN")

    def _get_tenant_token(self) -> Optional[str]:
        now = time.time()
        if self._tenant_token and now < self._tenant_token_expires_at:
            return self._tenant_token
        app_id = os.environ.get("LARK_APP_ID", "")
        app_secret = os.environ.get("LARK_APP_SECRET", "")
        if not app_id or not app_secret:
            logger.warning("[TaskView] LARK_APP_ID or LARK_APP_SECRET not set")
            return None
        try:
            import subprocess
            data_str = json.dumps({"app_id": app_id, "app_secret": app_secret})
            proc = subprocess.run(
                ["curl", "-s", "-k", "-X", "POST",
                 "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                 "-H", "Content-Type: application/json; charset=utf-8",
                 "-d", data_str],
                capture_output=True, text=True, timeout=10,
            )
            data = json.loads(proc.stdout.strip())
            if data.get("code") == 0:
                self._tenant_token = data.get("tenant_access_token")
                self._tenant_token_expires_at = now + data.get("expire", 7200) - 60
                return self._tenant_token
            logger.warning("[TaskView] Failed to get tenant token: %s", data.get("msg", ""))
        except Exception as e:
            logger.warning("[TaskView] Failed to get tenant token: %s", e)
        return None

    def _api_headers(self) -> Dict[str, str]:
        # 优先使用 tenant_access_token，失败时降级到 user_access_token
        token = self._get_tenant_token()
        if token:
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
        token = self._get_user_token()
        if token:
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
        raise RuntimeError("No access token available (try LARK_USER_ACCESS_TOKEN or LARK_APP_ID/LARK_APP_SECRET)")

    def _api_request(self, method: str, path: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Optional[Dict]:
        """调用飞书 OpenAPI，返回解析后的 JSON。"""
        import subprocess
        from urllib.parse import urlencode

        url = f"{_BASE_URL}{path}"
        if params:
            qs = urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                url = f"{url}?{qs}"
        headers = self._api_headers()

        # 使用 curl（Python requests SSL 在此环境不稳定）
        cmd = ["curl", "-s", "-k", "-X", method, url]
        for k, v in headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
        if data is not None:
            cmd.extend(["-d", json.dumps(data)])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = proc.stdout.strip()
            if not output:
                output = proc.stderr.strip()
            if output.startswith("{"):
                result = json.loads(output)
                code = result.get("code", -1)
                if code != 0:
                    msg = result.get("msg", result.get("error", {}).get("message", "unknown"))
                    logger.warning("[TaskView] API error [%d] %s — %s %s", code, method, path, msg)
                    return result
                return result
        except subprocess.TimeoutExpired:
            logger.error("[TaskView] API timeout: %s %s", method, path)
        except Exception as e:
            logger.warning("[TaskView] API failed: %s %s — %s", method, path, e)
        return None

    def _get_tasklist_name(self) -> str:
        """用 STORAGE_PATH 作为任务清单名称，确保切换路径时创建新清单。"""
        parts = Path(self._graph_path).parts
        return parts[-1] if parts else self._graph_path

    def _ensure_tasklist(self) -> str:
        """确保存在以 STORAGE_PATH 命名的任务清单，返回 tasklist_guid。"""
        if self._tasklist_guid:
            # 验证清单是否还存在
            result = self._api_request("GET", f"/task/v2/tasklists/{self._tasklist_guid}")
            if result and result.get("code") == 0:
                return self._tasklist_guid
            # 清单已不存在，清空重建
            self._tasklist_guid = None
            self._synced_tasks.clear()
            self._meta.pop("tasklist_guid", None)
            self._meta.pop("synced_tasks", None)

        tasklist_name = self._get_tasklist_name()

        # 先查找是否已有同名清单
        result = self._api_request("GET", "/task/v2/tasklists", params={"page_size": "50"})
        if result:
            items = result.get("data", {}).get("items", [])
            has_more = result.get("data", {}).get("has_more", False)
            # 如果还有更多，需要分页获取（通常不超过50个清单）
            page_token = result.get("data", {}).get("page_token", "")
            while has_more and page_token:
                result = self._api_request("GET", "/task/v2/tasklists", params={"page_size": "50", "page_token": page_token})
                if not result:
                    break
                items.extend(result.get("data", {}).get("items", []))
                has_more = result.get("data", {}).get("has_more", False)
                page_token = result.get("data", {}).get("page_token", "")

            for item in items:
                if item.get("name") == tasklist_name:
                    self._tasklist_guid = item.get("tasklist_guid") or item.get("guid")
                    self._meta["tasklist_guid"] = self._tasklist_guid
                    self._save_meta()
                    logger.info("[TaskView] Found existing tasklist: %s (%s)", tasklist_name, self._tasklist_guid)
                    return self._tasklist_guid

        # 创建新清单
        result = self._api_request("POST", "/task/v2/tasklists", data={"name": tasklist_name})

        if result and result.get("code") == 0:
            # tasklists create 返回结构: data.tasklist
            tasklist_data = result.get("data", {}).get("tasklist", {})
            self._tasklist_guid = tasklist_data.get("tasklist_guid") or tasklist_data.get("guid")
            self._meta["tasklist_guid"] = self._tasklist_guid
            self._save_meta()
            logger.info("[TaskView] Created tasklist: %s (%s)", tasklist_name, self._tasklist_guid)
            return self._tasklist_guid

        raise RuntimeError(f"Failed to create/find tasklist: {tasklist_name}")

    def sync_decision(self, sid: str) -> None:
        """Post-commit hook: 单个决策变更后增量同步。"""
        with self._lock:
            if self._syncing:
                return
            now = time.time()
            if now - self._last_sync_time < self._cooldown:
                return
            try:
                self._syncing = True
                self._sync_single_decision(sid)
            finally:
                self._syncing = False
                self._last_sync_time = time.time()

    def _sync_single_decision(self, sid: str) -> None:
        """同步单个决策到飞书任务。需要从外部传入 graph 来获取决策数据。"""
        logger.debug("[TaskView] Incremental sync triggered for: %s", sid)

    @staticmethod
    def _sort_by_parent(decisions: List[Any]) -> List[Any]:
        """按父子关系拓扑排序：父决策在前，子决策在后。"""
        sids = {getattr(d, "sid", ""): d for d in decisions if getattr(d, "sid", "")}
        by_parent: Dict[str, List[str]] = {}
        for d in decisions:
            sid = getattr(d, "sid", "")
            pid = getattr(d, "parent_id", "")
            if sid:
                by_parent.setdefault(pid, []).append(sid)

        ordered: List[Any] = []
        visited: Set[str] = set()

        def visit(sid: str) -> None:
            if sid in visited:
                return
            visited.add(sid)
            # 父决策先加入，子决策后加入（预序遍历）
            if sid in sids:
                ordered.append(sids[sid])
            for child_sid in by_parent.get(sid, []):
                if child_sid in sids and child_sid not in visited:
                    visit(child_sid)

        # 从父决策链根部开始
        for d in decisions:
            sid = getattr(d, "sid", "")
            if sid and sid not in visited:
                visit(sid)

        return ordered

    def full_sync(self, decisions: List[Any] | None = None) -> Dict[str, int]:
        """全量同步：将本地所有决策同步到飞书任务清单。

        Args:
            decisions: DecisionNode 列表。如果不提供，会尝试从 MemoryGraph 加载。

        Returns:
            同步统计：{"created": N, "updated": N, "deleted": N}
        """
        with self._lock:
            if decisions is None:
                decisions = self._load_decisions_from_graph()

            if not decisions:
                logger.info("[TaskView] No decisions to sync")
                return {"created": 0, "updated": 0, "deleted": 0}

            # 拓扑排序：父决策先创建，子决策才能引用 parent_task_guid
            decisions = self._sort_by_parent(decisions)

            try:
                tasklist_guid = self._ensure_tasklist()
            except Exception as e:
                logger.error("[TaskView] Failed to ensure tasklist: %s", e)
                return {"created": 0, "updated": 0, "deleted": 0}

            stats = {"created": 0, "updated": 0, "deleted": 0}
            current_sids: Set[str] = set()

            for node in decisions:
                sid = getattr(node, "sid", None)
                if not sid:
                    continue
                current_sids.add(sid)

                task_guid = self._synced_tasks.get(sid)
                if task_guid:
                    if self._update_task(task_guid, node):
                        stats["updated"] += 1
                else:
                    new_guid = self._create_task(tasklist_guid, node)
                    if new_guid:
                        self._synced_tasks[sid] = new_guid
                        stats["created"] += 1

            # 删除本地已不存在的任务
            orphan_sids = set(self._synced_tasks.keys()) - current_sids
            for orphan_sid in orphan_sids:
                task_guid = self._synced_tasks.pop(orphan_sid)
                if self._delete_task(task_guid):
                    stats["deleted"] += 1

            self._meta["synced_tasks"] = self._synced_tasks
            self._save_meta()

            logger.info(
                "[TaskView] Full sync done: created=%d updated=%d deleted=%d",
                stats["created"], stats["updated"], stats["deleted"],
            )
            return stats

    def _load_decisions_from_graph(self) -> List[Any]:
        """从 MemoryGraph 加载所有决策。"""
        try:
            from src.mcp_server.server import _loader
            _loader.ensure_loaded()
            return _loader.graph.get_all_decisions()
        except Exception as e:
            logger.warning("[TaskView] Failed to load decisions from graph: %s", e)
            return []

    def _decision_to_task_payload(self, node: Any) -> Dict[str, Any]:
        """将 DecisionNode 转为飞书任务创建/更新参数。

        标题格式: [GUID]标题 或 [GUID]标题(suggestion)
        描述格式与多维表格决策看板对齐。
        """
        sid = getattr(node, "sid", "")
        title = getattr(node, "title", "") or getattr(node, "summary", "")
        summary = getattr(node, "summary", "")
        status = getattr(node, "status", None)
        is_suggestion = getattr(node, "is_suggestion", False)
        parent_id = getattr(node, "parent_id", "")
        impact_level = getattr(node, "impact_level", "")
        proposer = getattr(node, "proposer", "")
        authority = getattr(node, "authority", "")
        version = getattr(node, "version", "")
        topic = getattr(node, "topic", "")

        # 标题格式: [GUID]标题
        summary_text = title or summary or f"决策-{sid[:8]}"
        if is_suggestion:
            task_summary = f"[{sid[:12]}]{summary_text}(suggestion)"
        else:
            task_summary = f"[{sid[:12]}]{summary_text}"

        # 状态映射：SUPERSEDED / SHELVED / DEPRECATED / REJECTED → done
        # DECIDED / 其他 → todo（最新决策不标记完成）
        done_statuses = {"shelved", "superseded", "deprecated", "rejected", "completed"}
        status_str = str(status or "").lower()
        # 去除 DecisionStatus. 前缀
        status_str = status_str.replace("decisionstatus.", "").strip()
        task_status = "done" if status_str in done_statuses else "todo"

        # 构建描述：与多维表格决策看板字段对齐
        desc_parts = []
        if topic:
            desc_parts.append(f"【决策主题】{topic}")
        desc_parts.append(f"【决策ID】{sid}")
        if version:
            desc_parts.append(f"【决策版本】{version}")
        status_display = str(status or "").replace("DecisionStatus.", "")
        if status_display:
            desc_parts.append(f"【决策状态】{status_display}")
        if summary_text:
            desc_parts.append(f"【决策标题】{summary_text}")
        if summary and summary != title:
            desc_parts.append(f"【决策内容】{summary}")
        desc_parts.append("")
        if is_suggestion:
            desc_parts.append("【类型】建议（suggestion）")
        else:
            desc_parts.append("【类型】正式决策")
        if proposer:
            desc_parts.append(f"【提出者】{proposer}")
        if authority:
            desc_parts.append(f"【决策者】{authority}")
        if impact_level:
            desc_parts.append(f"【影响级别】{impact_level}")
        if parent_id:
            desc_parts.append(f"【父决策】{parent_id}")

        description = "\n".join(desc_parts)

        payload = {
            "summary": task_summary,
            "description": description,
        }

        # 已完成的决策设置 completed_at
        if task_status == "done":
            payload["completed_at"] = str(int(time.time() * 1000))

        return payload, parent_id, is_suggestion

    def _create_task(self, tasklist_guid: str, node: Any) -> Optional[str]:
        """创建飞书任务，并加入指定清单。

        如果有已同步的父决策，通过 subtasks.create API 创建子任务以建立层级关系。
        子任务创建时不含 tasklists，创建后单独添加到任务清单。
        """
        payload, parent_id, is_suggestion = self._decision_to_task_payload(node)

        parent_task_guid = None
        if parent_id:
            parent_task_guid = self._synced_tasks.get(parent_id)

        task_guid = None
        if parent_task_guid:
            payload_sub = {k: v for k, v in payload.items()}
            result = self._api_request(
                "POST",
                f"/task/v2/tasks/{parent_task_guid}/subtasks",
                data=payload_sub,
            )
            if result and result.get("code") == 0:
                task_data = result.get("data", {}).get("subtask", {})
                task_guid = task_data.get("guid")
        else:
            payload_root = {**payload, "tasklists": [{"tasklist_guid": tasklist_guid}]}
            result = self._api_request("POST", "/task/v2/tasks", data=payload_root)
            if result and result.get("code") == 0:
                task_data = result.get("data", {}).get("task", {})
                task_guid = task_data.get("guid")

        # 子任务创建后单独添加到任务清单
        if task_guid and parent_task_guid:
            self._api_request(
                "POST",
                f"/task/v2/tasklists/{tasklist_guid}/tasks/{task_guid}",
            )

        return task_guid

    def _update_task(self, task_guid: str, node: Any) -> bool:
        """更新飞书任务。PATCH 支持 summary/description/completed_at 等。"""
        payload, parent_id, is_suggestion = self._decision_to_task_payload(node)

        update_fields = ["summary", "description"]
        task_patch = {
            "summary": payload["summary"],
            "description": payload["description"],
        }

        # 判断是否已完成状态
        status = getattr(node, "status", None)
        done_statuses = {"shelved", "superseded", "deprecated", "rejected", "completed"}
        status_str = str(status or "").lower().replace("decisionstatus.", "").strip()
        if status_str in done_statuses:
            task_patch["completed_at"] = str(int(time.time() * 1000))
            update_fields.append("completed_at")

        result = self._api_request(
            "PATCH",
            f"/task/v2/tasks/{task_guid}",
            data={
                "task": task_patch,
                "update_fields": update_fields,
            },
        )

        if result and result.get("code") == 0:
            return True

        return False

    def _delete_task(self, task_guid: str) -> bool:
        """删除飞书任务。只有创建者能删除。"""
        try:
            result = self._api_request("DELETE", f"/task/v2/tasks/{task_guid}")
            return result is not None and result.get("code") == 0
        except Exception:
            return False

    def get_sync_status(self) -> Dict[str, Any]:
        """获取当前同步状态。"""
        with self._lock:
            return {
                "graph_path": self._graph_path,
                "tasklist_name": self._get_tasklist_name(),
                "tasklist_guid": self._tasklist_guid,
                "synced_count": len(self._synced_tasks),
                "syncing": self._syncing,
                "last_sync_time": self._last_sync_time,
            }
