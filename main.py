"""
系统启动入口 — 管理所有检测器的生命周期

用法:
  # 交互式运行
  uv run python main.py

  # 后台服务模式
  uv run python main.py --mode service

配置:
  - main.py 读取 .env 中的 LARK_* 和 DOC_* 配置
  - 检测器仅启用 lark_doc 和 lark_im 两个
  - 所有检测器共享 MemoryEngine + PipelineEngine
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.card.config import CardConfig
from src.card.pusher import PushEngine
from src.core.engine import MemoryEngine
from src.core.engine_config import EngineConfig
from src.graph.memory_graph import MemoryGraph
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 状态管理 ====================


class DetectorState:
    """单个检测器的运行时状态（对应 ref/main.go detectorState）"""

    def __init__(
        self,
        name: str,
        enabled: bool = True,
        interval: int = 30,
        burst_interval: int = 5,
        burst_timeout: int = 120,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.interval = interval
        self.burst_interval = burst_interval
        self.burst_timeout = burst_timeout
        self.in_burst_mode = False
        self.last_change_time: float = 0.0
        self.last_check: float = 0.0


# ==================== 检测器实现 ====================


async def run_detector_loop(
    name: str,
    detect_fn: Any,
    state: DetectorState,
    memory_engine: Optional[MemoryEngine],
    stop_event: asyncio.Event,
) -> None:
    """单个检测器的异步循环（对应 ref/main.go runDetectorLoop）"""
    while not stop_event.is_set():
        try:
            interval = state.burst_interval if state.in_burst_mode else state.interval

            # 执行一次检测
            result = await asyncio.to_thread(detect_fn)
            if result is None:
                await asyncio.sleep(interval)
                continue

            has_changes = getattr(result, "has_changes", False) if hasattr(result, "has_changes") else bool(result)

            if has_changes:
                logger.info("[%s] Changes detected, entering burst mode", name)
                state.in_burst_mode = True
                state.last_change_time = time.time()
                interval = state.burst_interval
            elif state.in_burst_mode:
                if time.time() - state.last_change_time > state.burst_timeout:
                    logger.info("[%s] No changes for %ds, exiting burst mode", name, state.burst_timeout)
                    state.in_burst_mode = False
                    interval = state.interval

            state.last_check = time.time()

        except asyncio.CancelledError:
            break
        except Exception:
            logger.error("[%s] Detector error: %s", name, traceback.format_exc())

        await asyncio.sleep(interval)

    logger.info("[%s] Detector loop stopped", name)


# ==================== IM 检测器（占位） ====================


def detect_im() -> Any:
    """IM 检测器 — 监听飞书群聊消息

    TODO: 飞书 WebSocket 或轮询实现
    """
    from src.signal.detector import EnhancedDetector
    from src.signal.types import DetectContext

    logger.debug("[IM] Detecting messages...")

    # placeholder: 未来通过 LarkIMAdapter 实现
    # lark_im_adapter.poll_new_messages() -> list[MessageRecord]
    # EnhancedDetector.analyze(content, ctx) -> DetectionResult

    return type("DetectResult", (), {"has_changes": False})()


# ==================== 文档检测器（本地文件模式） ====================


def detect_docs(docs_dir: str) -> Any:
    """文档检测器 — 轮询本地文件目录

    TODO: 替换为飞书 API docs +search 轮询
    """
    from src.signal.doc_detector import DocDetector
    from src.adapter.doc_adapter import DocAdapter

    adapter = DocAdapter(docs_dir=docs_dir, polling_interval=30, debounce_window=30)
    detector = DocDetector(adapter=adapter)
    result = detector.detect()

    if result.has_changes:
        for change in result.changes:
            logger.info("[DOC] >>> %s: %s (score=%s)", change.doc_token, change.type, change.meta.get("signal_score"))

    return result


# ==================== 配置加载 ====================


def load_config() -> Dict[str, Any]:
    """加载系统配置"""
    cfg = {
        "project": os.environ.get("PROJECT_NAME", "default"),
        "storage_path": os.environ.get("STORAGE_PATH", "data"),
        "docs_dir": os.environ.get("DOC_DOCS_DIR", "data/docs"),
        "detectors": {
            "lark_im": {
                "enabled": os.environ.get("LARK_IM_DETECTOR_ENABLED", "true").lower() == "true",
                "interval": int(os.environ.get("LARK_IM_POLL_INTERVAL", "30")),
                "burst_interval": int(os.environ.get("LARK_IM_BURST_INTERVAL", "5")),
                "burst_timeout": int(os.environ.get("LARK_IM_BURST_TIMEOUT", "120")),
            },
            "lark_doc": {
                "enabled": os.environ.get("LARK_DOC_DETECTOR_ENABLED", "true").lower() == "true",
                "interval": int(os.environ.get("LARK_DOC_POLL_INTERVAL", "30")),
                "burst_interval": int(os.environ.get("LARK_DOC_BURST_INTERVAL", "5")),
                "burst_timeout": int(os.environ.get("LARK_DOC_BURST_TIMEOUT", "120")),
                "docs_dir": os.environ.get("DOC_DOCS_DIR", "data/docs"),
                "debounce_window": int(os.environ.get("LARK_DOC_DEBOUNCE_WINDOW", "30")),
            },
        },
    }
    return cfg


# ==================== 主启动流程 ====================


async def main_async() -> None:
    """异步主流程（对应 ref/main.go main()）"""
    cfg = load_config()
    logger.info("========================================")
    logger.info("  飞书协作记忆系统 v1 (Python)")
    logger.info("========================================")
    logger.info("Project: %s", cfg["project"])
    logger.info("Storage: %s", cfg["storage_path"])
    logger.info("DocsDir: %s", cfg["docs_dir"])

    # 1. 初始化存储
    storage = GitStorage(GitStorageConfig(
        work_dir=cfg["storage_path"],
    ))
    logger.info("[GitStorage] initialized")

    # 2. 初始化 MemoryGraph
    graph = MemoryGraph()
    try:
        graph.load_from_git(storage, cfg["project"])
        logger.info("[MemoryGraph] loaded %d decisions from Git", len(graph.get_all_decisions()))
    except Exception as e:
        logger.info("[MemoryGraph] No existing data to load: %s", e)

    # 3. 初始化 MemoryEngine
    engine_cfg = EngineConfig(
        project=cfg["project"],
        git_storage_path=cfg["storage_path"],
    )
    engine = MemoryEngine(config=engine_cfg)
    engine.initialize()
    logger.info("[MemoryEngine] initialized")

    # 4. 初始化 PushEngine
    push_engine = PushEngine(
        config=CardConfig.from_env(),
        memory_graph=graph,
        pipeline=engine.pipeline,
        lark_client=None,
    )
    push_engine.start_push_scheduler()
    logger.info("[PushEngine] scheduler started")

    # 5. 创建停止事件
    stop_event = asyncio.Event()

    # 6. 启动检测器循环
    detector_states: Dict[str, asyncio.Task] = {}
    det_cfg = cfg["detectors"]

    # lark_im 检测器
    im_state = DetectorState(
        name="lark_im",
        enabled=det_cfg["lark_im"]["enabled"],
        interval=det_cfg["lark_im"]["interval"],
        burst_interval=det_cfg["lark_im"]["burst_interval"],
        burst_timeout=det_cfg["lark_im"]["burst_timeout"],
    )
    if im_state.enabled:
        task = asyncio.create_task(
            run_detector_loop("lark_im", detect_im, im_state, engine, stop_event)
        )
        detector_states["lark_im"] = task
        logger.info("[lark_im] detector started (interval=%ds)", im_state.interval)

    # lark_doc 检测器
    doc_state = DetectorState(
        name="lark_doc",
        enabled=det_cfg["lark_doc"]["enabled"],
        interval=det_cfg["lark_doc"]["interval"],
        burst_interval=det_cfg["lark_doc"]["burst_interval"],
        burst_timeout=det_cfg["lark_doc"]["burst_timeout"],
    )
    if doc_state.enabled:
        docs_dir = det_cfg["lark_doc"]["docs_dir"]
        task = asyncio.create_task(
            run_detector_loop(
                "lark_doc",
                lambda: detect_docs(docs_dir),
                doc_state,
                engine,
                stop_event,
            )
        )
        detector_states["lark_doc"] = task
        logger.info("[lark_doc] detector started (interval=%ds, docs_dir=%s)", doc_state.interval, docs_dir)

    # 7. 打印检测器状态
    logger.info("[Detectors] Configuration:")
    for name, state in [("lark_im", im_state), ("lark_doc", doc_state)]:
        if state.enabled:
            logger.info("  %s: interval=%ds, burst=%ds, timeout=%ds", name, state.interval, state.burst_interval, state.burst_timeout)
        else:
            logger.info("  %s: disabled", name)

    logger.info("[System] All detectors started, waiting for signals...")

    # 8. 等待停止信号
    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("[System] Shutting down...")
    finally:
        # 停止所有检测器
        for name, task in detector_states.items():
            task.cancel()
        if detector_states:
            await asyncio.gather(*detector_states.values(), return_exceptions=True)

        # 停止推送引擎
        await push_engine.stop()

        # 停止引擎
        await engine.stop()

        logger.info("[System] Shutdown complete")


def main() -> None:
    """同步入口"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("[System] Interrupted by user")
    except Exception:
        logger.error("[System] Fatal error: %s", traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()