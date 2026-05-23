"""
文档适配器 — 本地文件模拟版

TODO: 未来迁移到飞书 API 轮询时，替换 _poll_dir() 为_lark_api_poll()
TODO: 飞书 API 方案: docs +search -> docs +fetch -> CompareDocumentContent
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DocChange:
    type: str  # "doc_created" | "doc_updated" | "doc_deleted"
    entity_type: str = "doc"
    doc_token: str = ""
    doc_title: str = ""
    content: str = ""
    old_content: str = ""
    prev_hash: str = ""
    current_hash: str = ""
    timestamp: float = 0.0
    meta: Dict[str, str] = field(default_factory=dict)


@dataclass
class DocDetectResult:
    has_changes: bool = False
    source: str = "doc"
    detected_at: float = 0.0
    changes: List[DocChange] = field(default_factory=list)


class DocDebounceTracker:
    """文档防抖追踪器（对应 ref/lark-adapter/debounce_tracker.go）"""

    def __init__(self, debounce_window: int = 30, state_dir: str = "data"):
        self._debounce_window = debounce_window
        self._file_path = os.path.join(state_dir, "debounce_state.json")
        self._states: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._load()

    def on_document_changed(self, doc_token: str, content_hash: str) -> None:
        with self._lock:
            now = time.time()
            state = self._states.get(doc_token)
            if state is None:
                state = {
                    "doc_token": doc_token,
                    "first_detected": now,
                    "last_change": now,
                    "is_staged": False,
                    "content_hash": content_hash,
                }
                self._states[doc_token] = state
            else:
                if content_hash and state.get("content_hash") != content_hash:
                    state["is_staged"] = False
                    state["content_hash"] = content_hash
                    state["last_change"] = now
            self._save()

    def can_process_now(self, doc_token: str) -> tuple[bool, str]:
        with self._lock:
            state = self._states.get(doc_token)
            if state is None:
                return True, "no prior state"
            time_since = time.time() - state["last_change"]
            if time_since < self._debounce_window:
                remaining = self._debounce_window - time_since
                return False, f"waiting for debounce: {remaining:.0f}s remaining"
            if state.get("is_staged") and state.get("content_hash"):
                return False, f"content already processed"
            return True, "ready"

    def mark_processed(self, doc_token: str, content_hash: str) -> None:
        with self._lock:
            state = self._states.get(doc_token)
            if state:
                state["is_staged"] = True
                state["processed_at"] = time.time()
                if content_hash:
                    state["content_hash"] = content_hash
                self._save()

    def get_state(self, doc_token: str) -> Optional[dict]:
        with self._lock:
            state = self._states.get(doc_token)
            return dict(state) if state else None

    def get_ready_docs(self) -> List[str]:
        with self._lock:
            ready = []
            for token, state in self._states.items():
                if state.get("is_staged"):
                    continue
                if time.time() - state["last_change"] >= self._debounce_window:
                    ready.append(token)
            return ready

    def _load(self) -> None:
        try:
            if os.path.exists(self._file_path):
                with open(self._file_path) as f:
                    self._states = json.load(f)
        except Exception as e:
            logger.warning("Failed to load debounce state: %s", e)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
            with open(self._file_path, "w") as f:
                json.dump(self._states, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save debounce state: %s", e)


class DocAdapter:
    """
    文档适配器 — 模拟飞书文档检测

    当前实现:
      - 轮询本地文件目录（data/docs/）
      - content_hash 对比检测变更
      - 防抖机制避免频繁触发

    TODO: 飞书 API 实现
      - _lark_api_poll(): docs +search 按时间过滤
      - _lark_api_fetch(): docs +fetch --doc <token>
      - 白名单配置: DOC_DOC_TOKENS=xxx,yyy
    """

    def __init__(
        self,
        docs_dir: str = "data/docs",
        polling_interval: int = 30,
        debounce_window: int = 30,
        debounce_tracker: Optional[DocDebounceTracker] = None,
    ):
        self._docs_dir = docs_dir
        self._polling_interval = polling_interval
        self._debounce_window = debounce_window
        self._debounce_tracker = debounce_tracker or DocDebounceTracker(debounce_window)
        self._content_cache: Dict[str, str] = {}  # doc_token -> content_hash
        self._cache_lock = threading.Lock()
        self._last_poll_time: float = 0.0

    @property
    def name(self) -> str:
        return "lark_doc"

    def detect(self) -> DocDetectResult:
        """
        检测文档变化

        TODO: 替换为飞书 API 版 detect()
        参考 ref/lark-adapter/lark_doc.go Detect():
          1. searchDocsByTime(lastCheck)
          2. checkWhitelistedDocs()
          3. detectNewComments()
        """
        if not os.path.isdir(self._docs_dir):
            logger.debug("Docs dir not found: %s", self._docs_dir)
            return DocDetectResult(source=self.name, detected_at=time.time())

        now = time.time()
        changes: List[DocChange] = []

        # 扫描本地文件目录模拟飞书文档轮询
        for entry in sorted(os.listdir(self._docs_dir), key=lambda p: os.path.getmtime(os.path.join(self._docs_dir, p))):
            file_path = os.path.join(self._docs_dir, entry)
            if not os.path.isfile(file_path) or not entry.endswith(".md"):
                continue

            doc_token = os.path.splitext(entry)[0]
            mtime = os.path.getmtime(file_path)

            # 跳过无变化的文件
            if mtime <= self._last_poll_time:
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning("Failed to read doc %s: %s", entry, e)
                continue

            current_hash = hashlib.sha256(content.encode()).hexdigest()

            with self._cache_lock:
                prev_hash = self._content_cache.get(doc_token)

            change_type = "doc_created" if prev_hash is None else "doc_updated"

            if prev_hash == current_hash:
                continue  # 内容未变化

            doc_change = DocChange(
                type=change_type,
                doc_token=doc_token,
                doc_title=doc_token,
                content=content,
                old_content="",
                prev_hash=prev_hash or "",
                current_hash=current_hash,
                timestamp=mtime,
                meta={"source": "local_file", "file_path": file_path},
            )
            changes.append(doc_change)

            # 更新缓存
            with self._cache_lock:
                self._content_cache[doc_token] = current_hash

            # 防抖
            self._debounce_tracker.on_document_changed(doc_token, current_hash)

            logger.info("Doc change detected: %s (%s)", doc_token, change_type)

        self._last_poll_time = now

        return DocDetectResult(
            has_changes=len(changes) > 0,
            source=self.name,
            detected_at=now,
            changes=changes,
        )

    def fetch_content(self, doc_token: str) -> str:
        """获取文档内容

        TODO: 替换为飞书 API docs +fetch --doc <token>
        """
        file_path = os.path.join(self._docs_dir, f"{doc_token}.md")
        try:
            with open(file_path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("Doc file not found: %s", file_path)
            return ""
        except Exception as e:
            logger.warning("Failed to fetch doc %s: %s", doc_token, e)
            return ""

    def list_docs(self) -> List[str]:
        """列出所有已知文档

        TODO: 替换为飞书 API docs +search
        """
        if not os.path.isdir(self._docs_dir):
            return []
        docs = []
        for entry in os.listdir(self._docs_dir):
            if entry.endswith(".md"):
                docs.append(os.path.splitext(entry)[0])
        return sorted(docs)

    @property
    def polling_interval(self) -> int:
        return self._polling_interval

    @polling_interval.setter
    def polling_interval(self, value: int) -> None:
        self._polling_interval = value