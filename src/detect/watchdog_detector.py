"""
Watchdog 文件检测器 — 基于文件系统事件的实时文档变更监听

通过 watchdog 库监听本地文件系统事件（创建/修改/删除），
取代轮询模式的 DocAdapter，并集成 EnhancedDetector 进行信号分析。

Usage:
    detector = WatchdogDocDetector(watch_dir="data/docs")
    await detector.start()
    try:
        while True:
            result = await detector.detect()
            if result.has_changes:
                # process changes
                ...
            await asyncio.sleep(0.5)
    finally:
        await detector.stop()
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from src.adapter.doc_adapter import DocChange, DocDetectResult
from src.detect.detector import EnhancedDetector, classify_doc_type
from src.detect.types import DocType
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DocFileHandler(FileSystemEventHandler):
    """Watchdog 事件处理器 — 监听文件创建/修改/删除

    使用防抖（debounce）机制避免短时间内同一文件的重复事件。
    通过 threading.Lock + asyncio.Queue 桥接 watchdog 的同步回调到 asyncio 消费者。
    """

    def __init__(
        self,
        debounce_seconds: float = 2.0,
        extensions: Optional[tuple[str, ...]] = None,
    ):
        super().__init__()
        self._debounce_seconds = debounce_seconds
        self._extensions = extensions or (".md",)
        self._pending: Dict[str, float] = {}  # path -> last_event_time
        self._lock = threading.Lock()
        self._changes: asyncio.Queue[Tuple[str, str]] = asyncio.Queue()  # (path, event_type)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory and self._matches(event.src_path):
            self._enqueue(event.src_path, "modified")

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory and self._matches(event.src_path):
            self._enqueue(event.src_path, "created")

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if not event.is_directory and self._matches(event.src_path):
            self._enqueue(event.src_path, "deleted")

    def _matches(self, path: str) -> bool:
        """检查文件扩展名是否在监听范围内"""
        return path.lower().endswith(self._extensions)

    def _enqueue(self, path: str, event_type: str) -> None:
        """防抖入队 — 同一文件在 debounce 窗口内的后续事件被忽略"""
        now = time.time()
        with self._lock:
            last_time = self._pending.get(path, 0.0)
            if now - last_time < self._debounce_seconds:
                return  # 仍在防抖窗口中，忽略
            self._pending[path] = now

        # 使用 run_coroutine_threadsafe 从 watchdog 的线程桥接到 asyncio 主循环
        asyncio.run_coroutine_threadsafe(
            self._changes.put((path, event_type)),
            self._changes._loop,  # type: ignore[attr-defined]
        )

    async def drain(self) -> List[Tuple[str, str]]:
        """清空当前所有待处理事件，返回 (path, event_type) 列表"""
        events: List[Tuple[str, str]] = []
        while not self._changes.empty():
            try:
                item = self._changes.get_nowait()
                events.append(item)
            except asyncio.QueueEmpty:
                break

        # 去重：同一 path 保留最后一个事件类型
        if len(events) > 1:
            seen: Dict[str, str] = {}
            for path, etype in events:
                seen[path] = etype
            events = list(seen.items())

        return events

    def cleanup_pending(self, path: str) -> None:
        """清理指定路径的防抖状态（处理完毕后调用）"""
        with self._lock:
            self._pending.pop(path, None)


class WatchdogDocDetector:
    """Watchdog 文档检测器 — 实时文件事件监听 + 信号分析

    流程:
      1. Observer 启动 watchdog 事件循环
      2. DocFileHandler 接收文件事件并防抖入队
      3. detect() 消费队列事件，读取文件内容，构建 DocChange
      4. EnhancedDetector 对变更文档进行信号分析
    """

    def __init__(
        self,
        watch_dir: str = "data/docs",
        debounce_seconds: float = 2.0,
        extensions: Optional[tuple[str, ...]] = None,
    ):
        self._watch_dir = os.path.abspath(watch_dir)
        self._handler = DocFileHandler(debounce_seconds=debounce_seconds, extensions=extensions)
        self._observer = Observer()
        self._signal_detector = EnhancedDetector.create_document_detector()
        self._content_cache: Dict[str, str] = {}  # doc_token -> content_hash
        self._started = False

    @property
    def name(self) -> str:
        return "watchdog_doc"

    @property
    def handler(self) -> DocFileHandler:
        return self._handler

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        """启动 watchdog observer 开始监听"""
        if self._started:
            logger.debug("WatchdogDocDetector already started")
            return

        os.makedirs(self._watch_dir, exist_ok=True)
        self._observer.schedule(self._handler, self._watch_dir, recursive=False)
        self._observer.start()
        self._started = True
        logger.info(
            "WatchdogDocDetector started watching: %s (debounce=%.1fs)",
            self._watch_dir,
            self._handler._debounce_seconds,
        )

    async def stop(self) -> None:
        """停止 watchdog observer"""
        if not self._started:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._started = False
        logger.info("WatchdogDocDetector stopped")

    async def detect(self) -> DocDetectResult:
        """消费待处理事件并返回文档变更结果

        从 handler 的事件队列中取出所有待处理事件，
        读取文件内容，计算内容哈希，构建 DocChange 并进行信号分析。
        """
        if not self._started:
            logger.debug("WatchdogDocDetector not started, skipping detect")
            return DocDetectResult(source=self.name, detected_at=time.time())

        events = await self._handler.drain()
        if not events:
            return DocDetectResult(source=self.name, detected_at=time.time())

        now = time.time()
        changes: List[DocChange] = []

        for file_path, event_type in events:
            doc_token = self._path_to_token(file_path)
            rel_path = os.path.relpath(file_path, os.path.dirname(self._watch_dir)) if os.path.dirname(self._watch_dir) else file_path

            if event_type == "deleted":
                # 删除事件 — 从缓存中移除
                change = DocChange(
                    type="doc_deleted",
                    doc_token=doc_token,
                    doc_title=doc_token,
                    content="",
                    current_hash="",
                    timestamp=now,
                    meta={"source": "watchdog", "file_path": rel_path, "event_type": event_type},
                )
                self._content_cache.pop(doc_token, None)
                changes.append(change)
                self._handler.cleanup_pending(file_path)
                logger.info("Doc deleted: %s", doc_token)
                continue

            # 创建/修改事件
            if not os.path.isfile(file_path):
                self._handler.cleanup_pending(file_path)
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning("Failed to read file %s: %s", file_path, e)
                self._handler.cleanup_pending(file_path)
                continue

            current_hash = hashlib.sha256(content.encode()).hexdigest()
            prev_hash = self._content_cache.get(doc_token)

            # 内容未变则跳过（文件元数据变更但不影响内容）
            if prev_hash == current_hash:
                self._handler.cleanup_pending(file_path)
                continue

            change_type = "doc_created" if prev_hash is None else "doc_updated"

            change = DocChange(
                type=change_type,
                doc_token=doc_token,
                doc_title=doc_token,
                content=content,
                prev_hash=prev_hash or "",
                current_hash=current_hash,
                timestamp=now if event_type == "created" else os.path.getmtime(file_path),
                meta={"source": "watchdog", "file_path": rel_path, "event_type": event_type},
            )

            # 更新内容缓存
            self._content_cache[doc_token] = current_hash

            # 执行信号分析（与 DocDetector.detect() 一致）
            doc_type = classify_doc_type(change.doc_title, content)
            detect_result = self._signal_detector.analyze_document(
                content=content,
                title=change.doc_title,
                doc_type=doc_type,
            )
            change.meta["signal_score"] = str(detect_result.score)
            change.meta["signal_level"] = detect_result.level.value
            change.meta["is_decision"] = str(detect_result.is_decision)
            change.meta["doc_type"] = doc_type.value

            changes.append(change)
            self._handler.cleanup_pending(file_path)

            logger.info(
                "Doc change detected: %s (%s) score=%.2f level=%s",
                doc_token, change_type, detect_result.score, detect_result.level.value,
            )

        return DocDetectResult(
            has_changes=len(changes) > 0,
            source=self.name,
            detected_at=now,
            changes=changes,
        )

    def _path_to_token(self, path: str) -> str:
        """从文件路径提取文档标识符（不带扩展名的文件名）"""
        return os.path.splitext(os.path.basename(path))[0]

    async def fetch_content(self, doc_token: str) -> str:
        """获取文档内容（兼容 DocAdapter.fetch_content API）"""
        file_path = os.path.join(self._watch_dir, f"{doc_token}.md")
        try:
            with open(file_path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("Doc file not found: %s", file_path)
            return ""
        except Exception as e:
            logger.warning("Failed to fetch doc %s: %s", doc_token, e)
            return ""