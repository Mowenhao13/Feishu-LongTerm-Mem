from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import numpy as np

from src.detect.suspend_pool import SuspendPool, SuspendedEpisode
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.model.embedding_provider import EmbeddingProvider

logger = get_logger(__name__)

TOPIC_SHIFT_KEYWORDS = [
    "对了", "话说", "另外", "换个话题", "顺便问", "说起来",
    "对了另外", "回到", "说回", "插一句",
    "ok next", "anyway", "by the way",
    "还有一个", "还有件事", "另外一件事",
]

SEMANTIC_GAP_THRESHOLD = 0.45
REOPEN_THRESHOLD = 0.65
TOPIC_DIVERSION_THRESHOLD = 0.30
TOPIC_BASELINE_SIZE = 5


@dataclass
class ChatMessage:
    chat_id: str
    sender_id: str
    content: str
    timestamp: float
    message_id: str


@dataclass
class ChatEpisode:
    id: str
    chat_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    topic: str = ""
    embedding: Optional[np.ndarray] = None

    @property
    def full_text(self) -> str:
        return "\n".join(m.content for m in self.messages)

    @property
    def message_count(self) -> int:
        return len(self.messages)



    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def get_sender_id_set(self) -> set:
        return {m.sender_id for m in self.messages}

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "chat_id": self.chat_id,
            "message_count": self.message_count,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "topic": self.topic,
            "participants": list(self.get_sender_id_set()),
            "messages": [
                {
                    "sender_id": m.sender_id,
                    "content": m.content,
                    "timestamp": m.timestamp,
                }
                for m in self.messages
            ],
            "full_text": self.full_text,
        }
        if self.embedding is not None:
            result["embedding"] = self.embedding.tolist()
        return result


class _InternalChatEpisode:
    def __init__(self, chat_id: str, baseline_size: int = TOPIC_BASELINE_SIZE):
        self.id = _generate_episode_id()
        self.chat_id = chat_id
        self.messages: List[ChatMessage] = []
        self.first_timestamp: float = 0.0
        self.last_timestamp: float = 0.0
        self.last_content: str = ""
        self.message_count: int = 0
        self._embeddings: List[np.ndarray] = []
        self._last_embedding: Optional[np.ndarray] = None
        self._baseline_size = baseline_size
        self._baseline_embedding: Optional[np.ndarray] = None

    @classmethod
    def resume(cls, suspended: "SuspendedEpisode") -> "_InternalChatEpisode":
        ep = cls.__new__(cls)
        ep.id = suspended.episode_id
        ep.chat_id = suspended.chat_id
        ep.messages = [ChatMessage(**m) for m in suspended.messages_data]
        ep.first_timestamp = suspended.start_time
        ep.last_timestamp = suspended.last_timestamp
        ep.last_content = suspended.last_content
        ep._embeddings = [np.array(e) for e in suspended.embeddings]
        ep._last_embedding = ep._embeddings[-1] if ep._embeddings else None
        ep.message_count = len(ep.messages)
        return ep

    def add(self, msg: ChatMessage, embedding: Optional[np.ndarray] = None) -> None:
        if self.message_count == 0:
            self.first_timestamp = msg.timestamp
        self.last_timestamp = msg.timestamp
        self.last_content = msg.content
        self.messages.append(msg)
        self.message_count = len(self.messages)
        if embedding is not None:
            self._embeddings.append(embedding)
            self._last_embedding = embedding
            # Build baseline from first N messages
            if len(self._embeddings) == self._baseline_size:
                self._baseline_embedding = np.mean(self._embeddings, axis=0)

    def aggregate_embedding(self) -> Optional[np.ndarray]:
        if not self._embeddings:
            return None
        return np.mean(self._embeddings, axis=0)

    def to_chat_episode(self) -> ChatEpisode:
        agg_emb = self.aggregate_embedding()
        return ChatEpisode(
            id=self.id,
            chat_id=self.chat_id,
            messages=self.messages,
            start_time=self.first_timestamp,
            end_time=self.last_timestamp,
            embedding=agg_emb,
        )

    def time_since_last_msg(self, now: float) -> float:
        return now - self.last_timestamp

    def total_duration(self, now: float) -> float:
        return now - self.first_timestamp


class ChatEpisodeBuffer:
    def __init__(
        self,
        chat_id: str,
        time_gap_threshold: float = 1800.0,
        max_messages: int = 100,
        max_duration: float = 7200.0,
        semantic_threshold: float = SEMANTIC_GAP_THRESHOLD,
        topic_diversion_threshold: float = TOPIC_DIVERSION_THRESHOLD,
        reopen_threshold: float = REOPEN_THRESHOLD,
        idle_flush_interval: float = 30.0,
        pool: Optional[SuspendPool] = None,
    ):
        self.chat_id = chat_id
        self._time_gap = time_gap_threshold
        self._max_messages = max_messages
        self._max_duration = max_duration
        self._semantic_threshold = semantic_threshold
        self._topic_diversion = topic_diversion_threshold
        self._reopen_threshold = reopen_threshold
        self._idle_flush = idle_flush_interval
        self._pool = pool
        self._current: Optional[_InternalChatEpisode] = None
        self._embedding_fn: Optional[Any] = None

    def set_embedding_fn(self, fn: Any) -> None:
        self._embedding_fn = fn

    def _compute_embedding(self, text: str) -> Optional[np.ndarray]:
        if self._embedding_fn is None or not text or len(text.strip()) < 10:
            return None
        try:
            vectors = self._embedding_fn([text])
            return np.array(vectors[0]) if vectors else None
        except Exception as e:
            logger.debug("[Episode] Embedding failed: %s", str(e)[:60])
            return None

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        dot = float(np.dot(a, b))
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        return dot / norm if norm > 1e-9 else 0.0

    def _suspend_current(self) -> Optional[ChatEpisode]:
        if self._current is None or self._pool is None:
            return None
        episode = self._current.to_chat_episode()
        self._pool.suspend(
            chat_id=self.chat_id,
            messages_data=[m.__dict__ for m in self._current.messages],
            embeddings=self._current._embeddings,
            start_time=self._current.first_timestamp,
            last_timestamp=self._current.last_timestamp,
            last_content=self._current.last_content,
            episode_id=self._current.id,
        )
        self._current = None
        return episode

    def _try_reopen(self, msg_embedding: Optional[np.ndarray]) -> bool:
        if self._pool is None or msg_embedding is None:
            return False
        candidate = self._pool.find_reopen(
            self.chat_id, msg_embedding, self._reopen_threshold
        )
        if candidate is None:
            return False
        suspended = self._pool.reopen(candidate.episode_id)
        if suspended is None:
            return False
        self._current = _InternalChatEpisode.resume(suspended)
        logger.info("[Episode] chat=%s REOPENED episode=%s (msgs=%d)",
                    self.chat_id[:12], self._current.id[:12], self._current.message_count)
        return True

    def add_message(self, msg: ChatMessage) -> Optional[ChatEpisode]:
        msg_embedding = self._compute_embedding(msg.content)

        if self._current is None:
            if self._try_reopen(msg_embedding):
                self._current.add(msg, msg_embedding)
                return None
            self._current = _InternalChatEpisode(chat_id=self.chat_id)
            logger.info("[Episode] chat=%s new episode=%s started with msg=%s",
                        self.chat_id[:12], self._current.id[:12], msg.message_id[:12])

        if self._current.message_count > 0:
            gap = msg.timestamp - self._current.last_timestamp
            if gap >= self._time_gap:
                gap_min = gap / 60.0
                logger.info("[Episode] chat=%s TIME-GAP boundary: gap=%.1fmin >= %.0fmin, suspend episode=%s (msgs=%d)",
                            self.chat_id[:12], gap_min, self._time_gap / 60.0,
                            self._current.id[:12], self._current.message_count)
                self._suspend_current()
                if self._try_reopen(msg_embedding):
                    self._current.add(msg, msg_embedding)
                    return None
                self._current = _InternalChatEpisode(chat_id=self.chat_id)
                logger.info("[Episode] chat=%s new episode=%s started after time-gap suspend",
                            self.chat_id[:12], self._current.id[:12])
                self._current.add(msg, msg_embedding)
                return None

        if self._current.message_count > 0:
            if _is_topic_shift(msg.content, self._current.last_content):
                logger.info("[Episode] chat=%s KEYWORD boundary: keyword match in '%s', suspend episode=%s (msgs=%d)",
                            self.chat_id[:12], msg.content[:30],
                            self._current.id[:12], self._current.message_count)
                self._suspend_current()
                if self._try_reopen(msg_embedding):
                    self._current.add(msg, msg_embedding)
                    return None
                self._current = _InternalChatEpisode(chat_id=self.chat_id)
                logger.info("[Episode] chat=%s new episode=%s started after keyword suspend",
                            self.chat_id[:12], self._current.id[:12])
                self._current.add(msg, msg_embedding)
                return None

        if (self._current.message_count > 0
                and msg_embedding is not None
                and self._current._baseline_embedding is not None):
            sim = self._cosine_similarity(msg_embedding, self._current._baseline_embedding)
            if sim < self._topic_diversion:
                logger.info("[Episode] chat=%s TOPIC-DIVERGENCE boundary: baseline_sim=%.4f < %.2f, suspend episode=%s (msgs=%d)",
                            self.chat_id[:12], sim, self._topic_diversion,
                            self._current.id[:12], self._current.message_count)
                self._suspend_current()
                if self._try_reopen(msg_embedding):
                    self._current.add(msg, msg_embedding)
                    return None
                self._current = _InternalChatEpisode(chat_id=self.chat_id)
                logger.info("[Episode] chat=%s new episode=%s started after topic divergence",
                            self.chat_id[:12], self._current.id[:12])
                self._current.add(msg, msg_embedding)
                return None

        if (self._current.message_count > 0
                and msg_embedding is not None
                and self._current._last_embedding is not None):
            sim = self._cosine_similarity(msg_embedding, self._current._last_embedding)
            if sim < self._semantic_threshold:
                logger.info("[Episode] chat=%s SEMANTIC-GAP boundary: sim=%.4f < %.2f, suspend episode=%s (msgs=%d)",
                            self.chat_id[:12], sim, self._semantic_threshold,
                            self._current.id[:12], self._current.message_count)
                self._suspend_current()
                if self._try_reopen(msg_embedding):
                    self._current.add(msg, msg_embedding)
                    return None
                self._current = _InternalChatEpisode(chat_id=self.chat_id)
                logger.info("[Episode] chat=%s new episode=%s started after semantic gap",
                            self.chat_id[:12], self._current.id[:12])
                self._current.add(msg, msg_embedding)
                return None
            logger.debug("[Episode] chat=%s semantic sim=%.4f within threshold",
                         self.chat_id[:12], sim)

        self._current.add(msg, msg_embedding)
        logger.debug("[Episode] chat=%s msg=%s added to episode=%s (total=%d)",
                     self.chat_id[:12], msg.message_id[:12],
                     self._current.id[:12], self._current.message_count)

        if self._current.message_count >= self._max_messages:
            logger.info("[Episode] chat=%s MAX-MSG boundary: %d >= %d, suspending episode=%s",
                        self.chat_id[:12], self._current.message_count, self._max_messages,
                        self._current.id[:12])
            self._suspend_current()
            if self._try_reopen(None):
                return None
            self._current = _InternalChatEpisode(chat_id=self.chat_id)
            logger.info("[Episode] chat=%s new episode=%s started after max-msg suspend",
                        self.chat_id[:12], self._current.id[:12])

        return None

    def check_timeout(self, now: float) -> Optional[ChatEpisode]:
        if self._current is None or self._current.message_count == 0:
            return None

        gap = now - self._current.last_timestamp
        if gap >= self._idle_flush:
            logger.info("[Episode] chat=%s IDLE-FLUSH: idle=%.1fs >= %.0fs, suspending episode=%s (msgs=%d)",
                        self.chat_id[:12], gap, self._idle_flush,
                        self._current.id[:12], self._current.message_count)
            return self._suspend_current()

        if gap >= self._time_gap:
            gap_min = gap / 60.0
            logger.info("[Episode] chat=%s TIME-GAP boundary: idle=%.1fmin >= %.0fmin, suspending episode=%s (msgs=%d)",
                        self.chat_id[:12], gap_min, self._time_gap / 60.0,
                        self._current.id[:12], self._current.message_count)
            return self._suspend_current()

        total_dur = now - self._current.first_timestamp
        if total_dur >= self._max_duration:
            dur_min = total_dur / 60.0
            logger.info("[Episode] chat=%s DURATION timeout: span=%.1fmin >= %.0fmin, suspending episode=%s (msgs=%d)",
                        self.chat_id[:12], dur_min, self._max_duration / 60.0,
                        self._current.id[:12], self._current.message_count)
            return self._suspend_current()
        return None

    def force_close(self) -> Optional[ChatEpisode]:
        if self._current is None or self._current.message_count == 0:
            if self._current is not None:
                self._current = None
            return None
        return self._suspend_current()

    def _close_current(self) -> Optional[ChatEpisode]:
        if self._current is None:
            return None
        ep = self._current.to_chat_episode()
        self._current = None
        logger.debug("[Episode] chat=%s episode=%s closed (msgs=%d)",
                     self.chat_id[:12], ep.id[:12], ep.message_count)
        return ep

    @property
    def current_message_count(self) -> int:
        return self._current.message_count if self._current else 0

    @property
    def current_episode_id(self) -> str:
        return self._current.id[:12] if self._current else "none"


@dataclass
class _ClosedChatEpisodeRecord:
    episode_id: str
    chat_id: str
    embedding: np.ndarray
    full_text_snippet: str
    message_count: int
    topic: str
    closed_at: float


class ChatEpisodeManager:
    """Thread-safe manager for per-chat episode buffers with semantic reconnection."""

    def __init__(
        self,
        time_gap_threshold: Optional[float] = None,
        max_messages: Optional[int] = None,
        max_duration: Optional[float] = None,
        semantic_threshold: Optional[float] = None,
        topic_diversion_threshold: Optional[float] = None,
        reopen_threshold: Optional[float] = None,
        idle_flush_interval: Optional[float] = None,
        pool: Optional[SuspendPool] = None,
    ):
        self._time_gap = (
            time_gap_threshold if time_gap_threshold is not None
            else float(os.getenv("EPISODE_TIME_GAP", "1800"))
        )
        self._max_messages = (
            max_messages if max_messages is not None
            else int(os.getenv("EPISODE_MAX_MESSAGES", "100"))
        )
        self._max_duration = (
            max_duration if max_duration is not None
            else float(os.getenv("EPISODE_MAX_DURATION", "7200"))
        )
        self._semantic_threshold = (
            semantic_threshold if semantic_threshold is not None
            else float(os.getenv("EPISODE_SEMANTIC_THRESHOLD", str(SEMANTIC_GAP_THRESHOLD)))
        )
        self._topic_diversion = (
            topic_diversion_threshold if topic_diversion_threshold is not None
            else float(os.getenv("EPISODE_TOPIC_DIVERSION", str(TOPIC_DIVERSION_THRESHOLD)))
        )
        self._reopen_threshold = (
            reopen_threshold if reopen_threshold is not None
            else float(os.getenv("EPISODE_REOPEN_THRESHOLD", str(REOPEN_THRESHOLD)))
        )
        self._idle_flush = (
            idle_flush_interval if idle_flush_interval is not None
            else float(os.getenv("EPISODE_IDLE_FLUSH", "30"))
        )
        self._buffers: Dict[str, ChatEpisodeBuffer] = {}
        self._lock = threading.Lock()
        self._pool = pool or SuspendPool()
        self._embedding_fn: Optional[Any] = None

    def get_or_create_buffer(self, chat_id: str) -> ChatEpisodeBuffer:
        with self._lock:
            if chat_id not in self._buffers:
                buf = ChatEpisodeBuffer(
                    chat_id=chat_id,
                    time_gap_threshold=self._time_gap,
                    max_messages=self._max_messages,
                    max_duration=self._max_duration,
                    semantic_threshold=self._semantic_threshold,
                    topic_diversion_threshold=self._topic_diversion,
                    reopen_threshold=self._reopen_threshold,
                    idle_flush_interval=self._idle_flush,
                    pool=self._pool,
                )
                if self._embedding_fn is not None:
                    buf.set_embedding_fn(self._embedding_fn)
                self._buffers[chat_id] = buf
                logger.info("[EpisodeManager] Created buffer for chat=%s", chat_id[:12])
            return self._buffers[chat_id]

    def set_buffer_embedding_fn(self, embed_fn: Any) -> None:
        self._embedding_fn = embed_fn
        with self._lock:
            for buf in self._buffers.values():
                buf.set_embedding_fn(embed_fn)

    def set_idle_flush_threshold(self, threshold: float) -> None:
        with self._lock:
            for buf in self._buffers.values():
                buf._idle_flush = threshold

    def add_message(self, msg: ChatMessage) -> None:
        buf = self.get_or_create_buffer(msg.chat_id)
        buf.add_message(msg)

    def check_all_timeouts(self) -> List[ChatEpisode]:
        now = time.time()
        suspended: List[ChatEpisode] = []
        for buf in self._buffers.values():
            ep = buf.check_timeout(now)
            if ep is not None:
                suspended.append(ep)
        return suspended

    def drain_suspended_episodes(self) -> List[ChatEpisode]:
        """Remove and return all suspended episodes as ChatEpisode objects."""
        entries = self._pool.drain_all()
        episodes = []
        for entry in entries:
            msg_dicts = entry["messages_data"]
            messages = []
            for md in msg_dicts:
                # ChatMessage.__dict__ stores: chat_id, sender_id, content, timestamp, message_id
                messages.append(ChatMessage(
                    chat_id=md.get("chat_id", entry["chat_id"]),
                    sender_id=md.get("sender_id", "unknown"),
                    content=md.get("content", ""),
                    timestamp=md.get("timestamp", entry["last_timestamp"]),
                    message_id=md.get("message_id", ""),
                ))
            ep = ChatEpisode(
                id=entry["episode_id"],
                chat_id=entry["chat_id"],
                messages=messages,
                start_time=entry["start_time"],
                end_time=entry["last_timestamp"],
            )
            episodes.append(ep)
            logger.info("[EpisodeManager] Drained episode=%s (chat=%s, msgs=%d)",
                        entry["episode_id"][:12], entry["chat_id"][:12], len(messages))
        return episodes

    def close_all(self) -> List[ChatEpisode]:
        closed: List[ChatEpisode] = []
        with self._lock:
            for buf in self._buffers.values():
                ep = buf.force_close()
                if ep is not None:
                    closed.append(ep)
            self._buffers.clear()
        self._pool.save()
        return closed

    def pool_size(self) -> int:
        return self._pool.size

    def pool_stats(self) -> Dict[str, Any]:
        return self._pool.stats()


def _is_topic_shift(content: str, last_content: str) -> bool:
    if not last_content:
        return False
    stripped = content.strip()
    for kw in TOPIC_SHIFT_KEYWORDS:
        if stripped.startswith(kw) or stripped.lower().startswith(kw):
            logger.debug("[Episode] Topic shift keyword: %s", kw)
            return True
    return False


def _generate_episode_id() -> str:
    return "ep_" + hashlib.md5(
        f"{time.time_ns()}_{id({})}".encode()
    ).hexdigest()[:12]