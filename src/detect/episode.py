from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import numpy as np

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


@dataclass
class EpisodeMessage:
    chat_id: str
    sender_id: str
    content: str
    timestamp: float
    message_id: str


@dataclass
class Episode:
    id: str
    chat_id: str
    messages: List[EpisodeMessage] = field(default_factory=list)
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


class _InternalEpisode:
    def __init__(self, chat_id: str):
        self.id = _generate_episode_id()
        self.chat_id = chat_id
        self.messages: List[EpisodeMessage] = []
        self.first_timestamp: float = 0.0
        self.last_timestamp: float = 0.0
        self.last_content: str = ""
        self.message_count: int = 0
        self._embeddings: List[np.ndarray] = []
        self._last_embedding: Optional[np.ndarray] = None

    def add(self, msg: EpisodeMessage, embedding: Optional[np.ndarray] = None) -> None:
        if self.message_count == 0:
            self.first_timestamp = msg.timestamp
        self.last_timestamp = msg.timestamp
        self.last_content = msg.content
        self.messages.append(msg)
        self.message_count = len(self.messages)
        if embedding is not None:
            self._embeddings.append(embedding)
            self._last_embedding = embedding

    def aggregate_embedding(self) -> Optional[np.ndarray]:
        if not self._embeddings:
            return None
        return np.mean(self._embeddings, axis=0)

    def to_episode(self) -> Episode:
        agg_emb = self.aggregate_embedding()
        return Episode(
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


class EpisodeBuffer:
    def __init__(
        self,
        chat_id: str,
        time_gap_threshold: float = 1800.0,
        max_messages: int = 100,
        max_duration: float = 7200.0,
        semantic_threshold: float = SEMANTIC_GAP_THRESHOLD,
        idle_flush_interval: float = 30.0,
    ):
        self.chat_id = chat_id
        self._time_gap = time_gap_threshold
        self._max_messages = max_messages
        self._max_duration = max_duration
        self._semantic_threshold = semantic_threshold
        self._idle_flush = idle_flush_interval
        self._current: Optional[_InternalEpisode] = None
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

    def add_message(self, msg: EpisodeMessage) -> Optional[Episode]:
        msg_embedding = self._compute_embedding(msg.content)

        if self._current is None:
            self._current = _InternalEpisode(chat_id=self.chat_id)
            logger.info("[Episode] chat=%s new episode=%s started with msg=%s",
                        self.chat_id[:12], self._current.id[:12], msg.message_id[:12])

        if self._current.message_count > 0:
            gap = msg.timestamp - self._current.last_timestamp
            if gap >= self._time_gap:
                gap_min = gap / 60.0
                logger.info("[Episode] chat=%s TIME-GAP boundary: gap=%.1fmin >= %.0fmin, closing episode=%s (msgs=%d)",
                            self.chat_id[:12], gap_min, self._time_gap / 60.0,
                            self._current.id[:12], self._current.message_count)
                closed = self._close_current()
                self._current = _InternalEpisode(chat_id=self.chat_id)
                logger.info("[Episode] chat=%s new episode=%s started after time-gap close",
                            self.chat_id[:12], self._current.id[:12])
                self._current.add(msg, msg_embedding)
                return closed

        if self._current.message_count > 0:
            if _is_topic_shift(msg.content, self._current.last_content):
                logger.info("[Episode] chat=%s KEYWORD boundary: keyword match in '%s', closing episode=%s (msgs=%d)",
                            self.chat_id[:12], msg.content[:30],
                            self._current.id[:12], self._current.message_count)
                closed = self._close_current()
                self._current = _InternalEpisode(chat_id=self.chat_id)
                logger.info("[Episode] chat=%s new episode=%s started after keyword close",
                            self.chat_id[:12], self._current.id[:12])
                self._current.add(msg, msg_embedding)
                return closed

        if (self._current.message_count > 0
                and msg_embedding is not None
                and self._current._last_embedding is not None):
            sim = self._cosine_similarity(msg_embedding, self._current._last_embedding)
            if sim < self._semantic_threshold:
                logger.info("[Episode] chat=%s SEMANTIC-GAP boundary: sim=%.4f < %.2f, closing episode=%s (msgs=%d)",
                            self.chat_id[:12], sim, self._semantic_threshold,
                            self._current.id[:12], self._current.message_count)
                closed = self._close_current()
                self._current = _InternalEpisode(chat_id=self.chat_id)
                logger.info("[Episode] chat=%s new episode=%s started after semantic gap",
                            self.chat_id[:12], self._current.id[:12])
                self._current.add(msg, msg_embedding)
                return closed
            logger.debug("[Episode] chat=%s semantic sim=%.4f within threshold",
                         self.chat_id[:12], sim)

        self._current.add(msg, msg_embedding)
        logger.debug("[Episode] chat=%s msg=%s added to episode=%s (total=%d)",
                     self.chat_id[:12], msg.message_id[:12],
                     self._current.id[:12], self._current.message_count)

        if self._current.message_count >= self._max_messages:
            logger.info("[Episode] chat=%s MAX-MSG boundary: %d >= %d, force-closing episode=%s",
                        self.chat_id[:12], self._current.message_count, self._max_messages,
                        self._current.id[:12])
            return self.force_close()

        return None

    def check_timeout(self, now: float) -> Optional[Episode]:
        if self._current is None or self._current.message_count == 0:
            return None

        # 短超时静默刷新：用户停止发送一段时间后，自动关闭并分发
        gap = now - self._current.last_timestamp
        if gap >= self._idle_flush:
            logger.info("[Episode] chat=%s IDLE-FLUSH: idle=%.1fs >= %.0fs, closing episode=%s (msgs=%d)",
                        self.chat_id[:12], gap, self._idle_flush,
                        self._current.id[:12], self._current.message_count)
            return self.force_close()

        # 长超时主题边界：长时间无消息，视为新主题的开始
        if gap >= self._time_gap:
            gap_min = gap / 60.0
            logger.info("[Episode] chat=%s TIME-GAP boundary: idle=%.1fmin >= %.0fmin, closing episode=%s (msgs=%d)",
                        self.chat_id[:12], gap_min, self._time_gap / 60.0,
                        self._current.id[:12], self._current.message_count)
            return self.force_close()

        total_dur = now - self._current.first_timestamp
        if total_dur >= self._max_duration:
            dur_min = total_dur / 60.0
            logger.info("[Episode] chat=%s DURATION timeout: span=%.1fmin >= %.0fmin, closing episode=%s (msgs=%d)",
                        self.chat_id[:12], dur_min, self._max_duration / 60.0,
                        self._current.id[:12], self._current.message_count)
            return self.force_close()
        return None

    def force_close(self) -> Optional[Episode]:
        if self._current is None or self._current.message_count == 0:
            if self._current is not None:
                self._current = None
            return None
        closed = self._close_current()
        if closed:
            logger.info("[Episode] chat=%s FORCE-CLOSE episode=%s (msgs=%d, dur=%.0fs)",
                        self.chat_id[:12], closed.id[:12], closed.message_count,
                        closed.duration)
        self._current = None
        return closed

    def _close_current(self) -> Optional[Episode]:
        if self._current is None:
            return None
        ep = self._current.to_episode()
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
class _ClosedEpisodeRecord:
    episode_id: str
    chat_id: str
    embedding: np.ndarray
    full_text_snippet: str
    message_count: int
    topic: str
    closed_at: float


class EpisodeManager:
    """Thread-safe manager for per-chat episode buffers with semantic reconnection."""

    def __init__(
        self,
        time_gap_threshold: Optional[float] = None,
        max_messages: Optional[int] = None,
        max_duration: Optional[float] = None,
        semantic_threshold: Optional[float] = None,
        reopen_threshold: Optional[float] = None,
        idle_flush_interval: Optional[float] = None,
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
        self._reopen_threshold = (
            reopen_threshold if reopen_threshold is not None
            else float(os.getenv("EPISODE_REOPEN_THRESHOLD", str(REOPEN_THRESHOLD)))
        )
        self._idle_flush = (
            idle_flush_interval if idle_flush_interval is not None
            else float(os.getenv("EPISODE_IDLE_FLUSH", "30"))
        )
        self._buffers: Dict[str, EpisodeBuffer] = {}
        self._lock = threading.Lock()
        self._embedding_provider: Any = None
        self._closed_episodes: Dict[str, _ClosedEpisodeRecord] = {}

    def set_embedding_provider(self, provider: Any) -> None:
        self._embedding_provider = provider
        embed_fn = getattr(provider, "embed", None)
        if embed_fn is None:
            logger.warning("[EpisodeManager] Embedding provider has no embed() method")
            return
        with self._lock:
            for buf in self._buffers.values():
                buf.set_embedding_fn(embed_fn)

    def get_or_create_buffer(self, chat_id: str) -> EpisodeBuffer:
        with self._lock:
            buf = self._buffers.get(chat_id)
            if buf is None:
                buf = EpisodeBuffer(
                    chat_id=chat_id,
                    time_gap_threshold=self._time_gap,
                    max_messages=self._max_messages,
                    max_duration=self._max_duration,
                    semantic_threshold=self._semantic_threshold,
                    idle_flush_interval=self._idle_flush,
                )
                embed_fn = getattr(self._embedding_provider, "embed", None) if self._embedding_provider else None
                if embed_fn:
                    buf.set_embedding_fn(embed_fn)
                self._buffers[chat_id] = buf
                logger.info("[EpisodeManager] Created buffer for chat=%s", chat_id[:12])
            return buf

    def add_message(self, msg: EpisodeMessage) -> Optional[Episode]:
        buf = self.get_or_create_buffer(msg.chat_id)
        return buf.add_message(msg)

    def register_closed_episode(self, episode: Episode) -> None:
        if episode.embedding is None:
            logger.debug("[EpisodeManager] Episode %s has no embedding, computing on close", episode.id[:12])
            episode.embedding = self._compute_episode_embedding(episode)
        if episode.embedding is None:
            return
        record = _ClosedEpisodeRecord(
            episode_id=episode.id,
            chat_id=episode.chat_id,
            embedding=episode.embedding,
            full_text_snippet=episode.full_text[:120],
            message_count=episode.message_count,
            topic=episode.topic,
            closed_at=time.time(),
        )
        with self._lock:
            self._closed_episodes[episode.id] = record
        logger.info("[EpisodeManager] Registered closed episode=%s chat=%s (msgs=%d, topic=%s)",
                    episode.id[:12], episode.chat_id[:12], episode.message_count, episode.topic or "untagged")

    def find_similar_episode(
        self,
        episode: Episode,
        min_similarity: Optional[float] = None,
    ) -> Optional[_ClosedEpisodeRecord]:
        threshold = min_similarity if min_similarity is not None else self._reopen_threshold
        if episode.embedding is None:
            episode.embedding = self._compute_episode_embedding(episode)
        if episode.embedding is None:
            return None

        best_sim = 0.0
        best_record: Optional[_ClosedEpisodeRecord] = None
        with self._lock:
            for record in self._closed_episodes.values():
                if record.chat_id != episode.chat_id:
                    continue
                sim = float(np.dot(episode.embedding, record.embedding)) / (
                    float(np.linalg.norm(episode.embedding)) * float(np.linalg.norm(record.embedding)) + 1e-9
                )
                if sim > best_sim:
                    best_sim = sim
                    best_record = record

        if best_record and best_sim >= threshold:
            logger.info("[EpisodeManager] Found similar episode: new=%s old=%s sim=%.4f (threshold=%.2f)",
                        episode.id[:12], best_record.episode_id[:12], best_sim, threshold)
        else:
            logger.debug("[EpisodeManager] No similar episode found for %s (best=%.4f, threshold=%.2f)",
                         episode.id[:12], best_sim, threshold)

        return best_record if best_sim >= threshold else None

    def _compute_episode_embedding(self, episode: Episode) -> Optional[np.ndarray]:
        if self._embedding_provider is None:
            return None
        try:
            full_text = episode.full_text
            if not full_text or len(full_text.strip()) < 10:
                return None
            embed_fn = getattr(self._embedding_provider, "embed", None)
            if embed_fn is None:
                return None
            vectors = embed_fn([full_text])
            if vectors:
                return np.array(vectors[0])
        except Exception as e:
            logger.debug("[EpisodeManager] Embedding compute failed: %s", str(e)[:60])
        return None

    def check_all_timeouts(self, now: float) -> List[Episode]:
        ready: List[Episode] = []
        with self._lock:
            for chat_id, buf in self._buffers.items():
                if buf.current_message_count > 0:
                    last_ts = buf._current.last_timestamp if buf._current else 0
                    logger.debug("[EpisodeManager] Checking chat=%s episode=%s msgs=%d idle=%.0fs",
                                 chat_id[:12], buf.current_episode_id, buf.current_message_count,
                                 now - last_ts)
                ep = buf.check_timeout(now)
                if ep is not None:
                    ready.append(ep)
        if ready:
            logger.info("[EpisodeManager] Timeout check: %d episode(s) closed", len(ready))
        return ready

    def force_close(self, chat_id: str) -> Optional[Episode]:
        with self._lock:
            buf = self._buffers.get(chat_id)
            if buf is None:
                return None
            return buf.force_close()

    def close_all(self) -> List[Episode]:
        all_episodes: List[Episode] = []
        with self._lock:
            for chat_id in list(self._buffers.keys()):
                buf = self._buffers[chat_id]
                ep = buf.force_close()
                if ep is not None:
                    all_episodes.append(ep)
                self._buffers.pop(chat_id, None)
        if all_episodes:
            logger.info("[EpisodeManager] Closed all: %d episode(s)", len(all_episodes))
        return all_episodes

    @property
    def buffer_count(self) -> int:
        with self._lock:
            return len(self._buffers)

    @property
    def closed_count(self) -> int:
        with self._lock:
            return len(self._closed_episodes)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "buffer_count": len(self._buffers),
                "closed_episodes": len(self._closed_episodes),
                "buffers": {
                    cid: {
                        "episode": buf.current_episode_id,
                        "messages": buf.current_message_count,
                    }
                    for cid, buf in self._buffers.items()
                    if buf.current_message_count > 0
                },
            }


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