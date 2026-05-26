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
import logging
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root and src/ to sys.path for all import styles
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

# Pre-import lark_oapi WS client before asyncio.run() so it creates
# its own event loop instead of grabbing the running one.
import lark_oapi.ws.client as _lark_ws_client  # noqa: F401

from src.card.config import CardConfig
from src.card.pusher import PushEngine
from src.core.engine import MemoryEngine
from src.core.engine_config import EngineConfig
from src.graph.memory_graph import MemoryGraph
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ==================== 文件日志配置 ====================
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
_file_handler = RotatingFileHandler(
    _log_file,
    maxBytes=50 * 1024 * 1024,  # 50MB
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)
logger.info("File logging to %s", _log_file)


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


async def run_episode_check_loop(
    episode_manager: Any,
    engine: Optional[Any],
    check_interval: float = 10.0,
) -> None:
    """后台检查所有 episode buffer 的超时边界

    两种模式下都运行：
      - WS 模式：WS 消息实时累积 + 本循环处理超时边界
      - 轮询模式：poll() 拉取消息累积 + 本循环处理超时边界
    """
    logger.info("[Episode] Check loop started (interval=%.0fs)", check_interval)
    while True:
        try:
            now = time.time()
            stats = episode_manager.stats()
            if stats.get("buffers"):
                logger.debug("[Episode] Pre-check: %s", stats)
            for episode in episode_manager.check_all_timeouts(now):
                if engine is not None:
                    logger.info("[Episode] >>> Timeout closed episode=%s (msgs=%d, dur=%.0fs), dispatching to engine",
                                episode.id[:12], episode.message_count, episode.duration)
                    await engine._process_episode(episode, episode_manager)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[Episode] Check loop error: %s\n%s", e, traceback.format_exc())
        await asyncio.sleep(check_interval)


# ==================== IM 检测器 ====================


class LarkIMDetector:
    """飞书 IM 检测器 — 基于 LarkIMClient 的完整实现

    支持两种消息接收模式:
      1. 轮询模式（默认）: get_conversation_history() 按间隔拉取
      2. WS 长连接模式（可选）: start_ws_listener() 事件驱动

    LarkIMClient 已实现的功能:
      - send_message / reply_message / edit_message / forward_message
      - get_conversation_history / get_all_conversation_history
      - start_ws_listener (WebSocket 长连接, 自动重连)
      - get_group_info / list_groups
    """

    def __init__(self):
        self._client: Optional[Any] = None
        self._chat_ids: List[str] = []
        self._last_poll_time: Dict[str, str] = {}  # chat_id -> end_time (毫秒时间戳)
        self._available = False
        self._engine: Optional[Any] = None  # MemoryEngine 引用（WS 和轮询模式共用）
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._episode_manager: Optional[Any] = None  # 两种模式共用

    def initialize(self) -> bool:
        """初始化 LarkIM 客户端

        从 .env 加载 LARK_APP_ID / LARK_APP_SECRET / GROUP_CHAT_IDS
        若配置缺失则打印警告并返回 False（不影响系统启动）
        """
        app_id = os.environ.get("LARK_APP_ID", "")
        app_secret = os.environ.get("LARK_APP_SECRET", "")
        chat_ids_raw = os.environ.get("GROUP_CHAT_IDS", "")

        if not app_id or not app_secret:
            logger.warning("[lark_im] LARK_APP_ID / LARK_APP_SECRET not configured, IM detector disabled")
            logger.warning("[lark_im] Set these in .env to enable real Lark IM message detection")
            return False

        if not chat_ids_raw:
            logger.warning("[lark_im] GROUP_CHAT_IDS not configured, IM detector disabled")
            logger.warning("[lark_im] Add GROUP_CHAT_IDS=oc_xxxxx,oc_yyyyy to .env")
            return False

        try:
            from src.adapter.lark_im import LarkIMClient, LarkIMConfig

            config = LarkIMConfig(
                app_id=app_id,
                app_secret=app_secret,
                encrypt_key=os.environ.get("LARK_ENCRYPT_KEY", ""),
                verification_token=os.environ.get("LARK_VERIFICATION_TOKEN", ""),
            )
            self._client = LarkIMClient(config)
            self._chat_ids = [cid.strip() for cid in chat_ids_raw.split(",") if cid.strip()]
            self._available = True

            from src.detect.episode import EpisodeManager
            self._episode_manager = EpisodeManager()
            logger.info("[lark_im] EpisodeManager created: gap=%.0fs max_msgs=%d max_dur=%.0fs flush=%ds semantic=%.2f reopen=%.2f",
                        self._episode_manager._time_gap,
                        self._episode_manager._max_messages,
                        self._episode_manager._max_duration,
                        self._episode_manager._idle_flush,
                        self._episode_manager._semantic_threshold,
                        self._episode_manager._reopen_threshold)

            # 初始化轮询时间戳（记录最新已拉取的时间作为游标）
            now_ms = str(int(time.time() * 1000))
            for chat_id in self._chat_ids:
                self._last_poll_time[chat_id] = now_ms

            logger.info("[lark_im] Initialized: %d chat(s) monitored: %s", len(self._chat_ids), self._chat_ids)
            return True

        except ImportError as e:
            logger.warning("[lark_im] Failed to import LarkIMClient: %s", e)
            return False
        except Exception as e:
            logger.warning("[lark_im] Initialization failed: %s", e)
            return False

    def poll(self) -> Any:
        """轮询模式 — 拉取所有群聊的新消息并通过信号检测器分析

        LarkIMClient.get_all_conversation_history() 内部处理分页
        返回 DetectResult（含 has_changes / messages 列表）
        """
        if not self._available or self._client is None:
            return type("DetectResult", (), {"has_changes": False, "messages": [], "signal_results": []})()

        all_new_messages: List[Any] = []
        signal_results: List[Dict] = []

        for chat_id in self._chat_ids:
            try:
                start_time = self._last_poll_time.get(chat_id)
                # 获取在该时间之前的消息（ByCreateTimeDesc 返回最新的消息，end_time 作为上限）
                response = self._client.get_conversation_history(
                    container_id=chat_id,
                    container_id_type="chat",
                    page_size=50,
                    sort_type="ByCreateTimeDesc",
                )

                if response.data and response.data.items:
                    messages = response.data.items
                    all_new_messages.extend(messages)

                    # 更新轮询起点（取最新消息的时间戳）
                    if messages:
                        latest = messages[0]
                        if hasattr(latest, "create_time") and latest.create_time:
                            self._last_poll_time[chat_id] = str(
                                max(
                                    int(self._last_poll_time.get(chat_id, "0")),
                                    int(latest.create_time),
                                )
                            )

                    # 将每条消息送入 EpisodeBuffer
                    for msg in messages:
                        content = getattr(msg, "body", None)
                        sender = getattr(msg, "sender", None)
                        if content is not None and hasattr(content, "content"):
                            msg_text = content.content or ""
                        else:
                            msg_text = ""

                        sender_id = str(sender.id) if sender and hasattr(sender, "id") else "unknown"
                        msg_id = getattr(msg, "message_id", "") or ""

                        signal_results.append({
                            "message_id": msg_id,
                            "chat_id": chat_id,
                        })

                        if self._episode_manager is not None and msg_text:
                            create_time_str = getattr(msg, "create_time", None)
                            try:
                                msg_ts = int(create_time_str) / 1000.0 if create_time_str else time.time()
                            except (ValueError, TypeError):
                                msg_ts = time.time()

                            from src.detect.episode import EpisodeMessage
                            ep_msg = EpisodeMessage(
                                chat_id=chat_id,
                                sender_id=sender_id,
                                content=msg_text,
                                timestamp=msg_ts,
                                message_id=msg_id,
                            )
                            closed_episode = self._episode_manager.add_message(ep_msg)
                            if closed_episode is not None:
                                logger.info("[lark_im] Episode closed in poll: id=%s chat=%s msgs=%d, dispatching to LLM",
                                            closed_episode.id[:12], chat_id[:12], closed_episode.message_count)
                                if self._engine is not None and self._loop is not None:
                                    asyncio.run_coroutine_threadsafe(
                                        self._engine._process_episode(closed_episode, self._episode_manager),
                                        self._loop,
                                    )

            except Exception as e:
                logger.debug("[lark_im] Poll chat=%s error: %s", chat_id[:12], e)

        if all_new_messages:
            logger.info("[lark_im] Polled %d new messages from %d chat(s), %d decision signals",
                        len(all_new_messages), len(self._chat_ids),
                        sum(1 for r in signal_results if r["is_decision"]))

        result = type("DetectResult", (), {
            "has_changes": bool(all_new_messages),
            "messages": all_new_messages,
            "signal_results": signal_results,
        })()
        return result

    def start_ws(self, engine: Optional[Any] = None, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """WS 长连接模式 — 事件驱动，实时接收消息推送

        LarkIMClient.start_ws_listener() 内部使用：
          - lark_oapi.ws.Client
          - 自动重连 auto_reconnect=True
          - 独立 daemon 线程运行

        参数:
          engine: 若传入 MemoryEngine，WS 收到决策信号后自动触发决策提取
          loop:   主事件循环引用（engine 传入时需要），用于 run_coroutine_threadsafe
        """
        if not self._available or self._client is None:
            logger.warning("[lark_im] Cannot start WS listener: client not initialized")
            return

        self._engine = engine
        self._loop = loop

        from src.detect.episode import EpisodeMessage

        def on_message(event: Any) -> None:
            try:
                logger.info("[lark_im] WS >>> on_message called, event type=%s", type(event).__name__)

                msg = getattr(event, "event", None)
                if msg is None:
                    logger.warning("[lark_im] WS event has no 'event' attribute, raw=%s", str(event)[:200])
                    return
                message = getattr(msg, "message", None)
                if message is None:
                    logger.warning("[lark_im] WS event has no 'message', attrs=%s", [a for a in dir(msg) if not a.startswith('_')][:10])
                    return
                content = getattr(message, "content", "")
                chat_id = getattr(message, "chat_id", "")
                sender = getattr(message, "sender", None)
                sender_id = str(getattr(sender, "sender_id", "") or getattr(sender, "id", "")) if sender else ""

                logger.info("[lark_im] WS received: chat=%s sender=%s len=%d content=%.60s",
                            chat_id[:12], sender_id[:12], len(content or ""), content[:60])

                if self._engine is not None and self._loop is not None and content and self._episode_manager is not None:
                    msg_obj = EpisodeMessage(
                        chat_id=chat_id,
                        sender_id=sender_id,
                        content=content,
                        timestamp=time.time(),
                        message_id=getattr(message, "message_id", "") or "",
                    )
                    closed_episode = self._episode_manager.add_message(msg_obj)
                    if closed_episode is not None:
                        logger.info("[lark_im] Episode closed: id=%s chat=%s msgs=%d, dispatching to LLM",
                                    closed_episode.id[:12], chat_id[:12], closed_episode.message_count)
                        asyncio.run_coroutine_threadsafe(
                            self._engine._process_episode(closed_episode, self._episode_manager),
                            self._loop,
                        )

            except Exception as e:
                logger.error("[lark_im] WS handler error: %s\n%s", e, traceback.format_exc())

        self._client.set_event_handler(on_message)
        self._client.start_ws_listener(auto_reconnect=True)
        logger.info("[lark_im] WS listener started for %d chat(s)", len(self._chat_ids))

    def stop_ws(self) -> None:
        if self._client is not None:
            self._client.stop_ws_listener()
            self._client = None
        self._engine = None
        self._loop = None


# 全局 IM 检测器实例（在 main_async 中初始化）
_im_detector = LarkIMDetector()


def detect_im() -> Any:
    """IM 检测器 — 轮询 LarkIMClient.get_conversation_history()

    仅在 LARK_IM_MODE=poll 时由 run_detector_loop() 定期调用。
    消息到达后自动通过 EnhancedDetector 进行决策信号分析。

    LARK_IM_MODE=websocket 时使用 start_ws() 事件驱动模式，不调用此函数。
    """
    return _im_detector.poll()


# ==================== 文档检测器（本地文件模式） ====================


def detect_docs(docs_dir: str) -> Any:
    """文档检测器 — 轮询本地文件目录

    TODO: 替换为飞书 API docs +search 轮询
    """
    from src.detect.doc_detector import DocDetector
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
                "mode": os.environ.get("LARK_IM_MODE", "poll").lower(),
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
        storage_path=cfg["storage_path"],
    )

    # 创建 LLM 决策提取器
    from src.model.llm_provider import LLMProvider
    from src.extractors.simple_llm_extractor import SimpleLLMExtractor

    llm_provider = None
    if os.getenv("API_KEY"):
        llm_provider = LLMProvider(
            provider_type="openai",
            base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("API_KEY", ""),
            model=os.getenv("MODEL_NAME", "deepseek-chat"),
            max_tokens=4096,
        )
        logger.info("[LLM] LLMProvider created: %s model=%s",
                    os.getenv("BASE_URL"), os.getenv("MODEL_NAME"))
    else:
        logger.warning("[LLM] API_KEY not configured, decision extraction disabled")

    decision_extractor = SimpleLLMExtractor(llm_provider) if llm_provider else None
    if decision_extractor:
        logger.info("[LLM] Decision extractor enabled")

    engine = MemoryEngine(config=engine_cfg, decision_extractor=decision_extractor)
    engine.initialize()
    logger.info("[MemoryEngine] initialized")

    # Inject embedding/reranker for similarity search
    try:
        from src.model.embedding_provider import EmbeddingProvider
        from src.model.reranker_provider import RerankerProvider
        embedder = EmbeddingProvider()
        reranker = RerankerProvider()

        # 检查 embedding 和 reranker 服务连接
        emb_ok = embedder.check_connection(timeout=5)
        rerank_ok = reranker.check_connection(timeout=5)
        if emb_ok and rerank_ok:
            logger.info("[Engine] Embedding+Reranker services both connected")
        elif not emb_ok and not rerank_ok:
            logger.warning("[Engine] Both embedding and reranker services unreachable — will fallback to bigram similarity")
        elif not emb_ok:
            logger.warning("[Engine] Embedding service unreachable — will fallback to bigram similarity")
        else:
            logger.warning("[Engine] Reranker service unreachable — embedding only, no rerank")

        engine.set_embedding_reranker(embedder, reranker)
        logger.info("[Engine] Embedding+Reranker injected for similarity search")
    except Exception as e:
        logger.warning("[Engine] Failed to init embedding/reranker (non-fatal): %s", e)

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

    det_cfg = cfg["detectors"]

    # 6. 初始化 IM 检测器
    im_initialized = _im_detector.initialize()
    im_mode = det_cfg["lark_im"]["mode"]
    if im_initialized:
        logger.info("[lark_im] IM detector ready (mode=%s)", im_mode)

        try:
            if _im_detector._episode_manager is not None:
                _im_detector._episode_manager.set_embedding_provider(embedder)
                logger.info("[lark_im] EmbeddingProvider injected for episode boundary detection")
        except Exception as e:
            logger.warning("[lark_im] Failed to inject embedding provider (non-fatal): %s", e)

    # 7. 启动检测器循环
    detector_states: Dict[str, asyncio.Task] = {}

    # lark_im 检测器 — 根据 mode 选择启动方式
    im_state = DetectorState(
        name="lark_im",
        enabled=det_cfg["lark_im"]["enabled"],
        interval=det_cfg["lark_im"]["interval"],
        burst_interval=det_cfg["lark_im"]["burst_interval"],
        burst_timeout=det_cfg["lark_im"]["burst_timeout"],
    )
    if im_state.enabled:
        if im_mode == "websocket":
            _im_detector.start_ws(engine=engine, loop=asyncio.get_event_loop())
            logger.info("[lark_im] WS listener started (mode=%s)", im_mode)
        else:
            _im_detector._loop = asyncio.get_event_loop()
            task = asyncio.create_task(
                run_detector_loop("lark_im", detect_im, im_state, engine, stop_event)
            )
            detector_states["lark_im"] = task
            logger.info("[lark_im] poll detector started (interval=%ds)", im_state.interval)

        # 两种模式都启动 episode 检查循环
        if _im_detector._episode_manager is not None:
            ep_check_task = asyncio.create_task(
                run_episode_check_loop(_im_detector._episode_manager, engine)
            )
            detector_states["episode_check"] = ep_check_task
            logger.info("[Episode] Check loop task created")

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
            mode_str = f" mode={im_mode}" if name == "lark_im" else ""
            logger.info("  %s: interval=%ds, burst=%ds, timeout=%ds%s", name, state.interval, state.burst_interval, state.burst_timeout, mode_str)
        else:
            logger.info("  %s: disabled", name)

    logger.info("[System] All detectors started, waiting for signals...")

    # 8. 等待停止信号
    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("[System] Shutting down...")
    finally:
        # 停止所有检测器循环任务
        for name, task in detector_states.items():
            task.cancel()
        if detector_states:
            await asyncio.gather(*detector_states.values(), return_exceptions=True)

        # 停止 WS 长连接（websocket 模式）
        if im_state.enabled and im_mode == "websocket":
            _im_detector.stop_ws()
            logger.info("[lark_im] WS listener stopped")

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