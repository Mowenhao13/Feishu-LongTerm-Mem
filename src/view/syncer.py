import os
from typing import Any, Dict, List

from src.storage.git_storage import GitStorage
from src.graph.memory_graph import MemoryGraph
from src.node.node import DecisionNode
from src.utils.logger import get_logger

from .client import BaseViewClient
from .schema import (
    FIELD_ASSIGNEE,
    FIELD_CONFLICT_SID,
    FIELD_CONTENT,
    FIELD_CREATED_AT,
    FIELD_DECISION_ID,
    FIELD_HOT_SCORE,
    FIELD_PARENT,
    FIELD_STATUS,
    FIELD_TITLE,
    FIELD_TOPIC,
    FIELD_VERSION,
)

logger = get_logger(__name__)


class BaseViewSyncer:

    def __init__(self, storage: GitStorage, graph: MemoryGraph):
        self._storage = storage
        self._graph = graph
        self._client = BaseViewClient()

    def full_sync(self) -> None:
        if os.environ.get("BITABLE_ENABLED", "").strip().lower() != "true":
            logger.info("[BaseView] Skipped (BITABLE_ENABLED=false)")
            return
        logger.info("[BaseView] Starting full sync...")
        self._client.ensure_base()
        self._client.ensure_table()

        self._client.delete_all_records()

        decisions = self._graph.get_all_decisions()
        records = [self._decision_to_record(d) for d in decisions]

        self._client.batch_create_records(records)
        logger.info("[BaseView] Full sync completed: %d decisions synced", len(records))

    def sync_decision(self, sid: str) -> None:
        if os.environ.get("BITABLE_ENABLED", "").strip().lower() != "true":
            return
        node = self._graph.get_decision(sid)
        if not node:
            logger.warning("[BaseView] Decision %s not found, skipping sync", sid)
            return
        record = self._decision_to_record(node)
        self._client.upsert_record(record)
        logger.info("[BaseView] Synced decision %s v%s", sid, node.version)

    def _decision_to_record(self, node: DecisionNode) -> Dict[str, Any]:
        status_str = node.status.value if hasattr(node.status, "value") else str(node.status)
        has_conflict = any(
            hasattr(r, "type") and "conflict" in str(r.type).lower()
            for r in (node.relations or [])
        )
        if has_conflict:
            status_str = "conflict"

        hot_score = 0.0
        if hasattr(node, "access_stats") and node.access_stats:
            hot_score = round(getattr(node.access_stats, "hot_score", 0.0), 1)

        created_ts = None
        if node.created_at:
            created_ts = int(node.created_at.timestamp() * 1000)

        return {
            FIELD_DECISION_ID: node.sid,
            FIELD_TOPIC: node.topic_id or "",
            FIELD_VERSION: node.version,
            FIELD_STATUS: status_str,
            FIELD_TITLE: node.summary or "",
            FIELD_CONTENT: node.full_text or "",
            FIELD_ASSIGNEE: self._resolve_assignee(node),
            FIELD_CREATED_AT: created_ts,
            FIELD_HOT_SCORE: hot_score,
            FIELD_CONFLICT_SID: self._resolve_conflict_sid(node),
            FIELD_PARENT: self._resolve_parent(node),
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

    def _resolve_parent(self, node: DecisionNode) -> str:
        if not node.parent_id or not self._graph:
            return ""
        parent = self._graph.get_decision(node.parent_id)
        if parent is None:
            return node.parent_id
        return parent.title or parent.summary or node.parent_id