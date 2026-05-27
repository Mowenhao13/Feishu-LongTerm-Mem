from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

POOL_MAX_SIZE = int(os.getenv("EPISODE_POOL_MAX_SIZE", "20"))
POOL_ARCHIVE_HOURS = int(os.getenv("EPISODE_POOL_ARCHIVE_HOURS", "24"))
POOL_PATH = os.getenv("EPISODE_SUSPEND_POOL_PATH", "data/suspend_pool.json")


@dataclass
class SuspendedEpisode:
    episode_id: str
    chat_id: str
    messages_data: List[Dict[str, Any]] = field(default_factory=list)
    embeddings: List[List[float]] = field(default_factory=list)
    start_time: float = 0.0
    last_timestamp: float = 0.0
    last_content: str = ""
    message_count: int = 0
    suspended_at: float = 0.0

    def aggregate_embedding(self) -> Optional[List[float]]:
        if not self.embeddings:
            return None
        arr = np.mean([np.array(e) for e in self.embeddings], axis=0)
        return arr.tolist()

    def max_similarity(self, query: np.ndarray) -> float:
        if not self.embeddings:
            return 0.0
        best = 0.0
        for emb in self.embeddings:
            sim = float(np.dot(query, np.array(emb))) / (
                float(np.linalg.norm(query)) * float(np.linalg.norm(emb)) + 1e-9
            )
            if sim > best:
                best = sim
        return best


class SuspendPool:
    def __init__(
        self,
        pool_path: str = POOL_PATH,
        max_size: int = POOL_MAX_SIZE,
        archive_hours: int = POOL_ARCHIVE_HOURS,
    ):
        self._pool: Dict[str, SuspendedEpisode] = {}
        self._pool_path = Path(pool_path)
        self._max_size = max_size
        self._archive_hours = archive_hours
        self._lock = threading.Lock()
        self._dirty = False
        self._reopen_count = 0

    # ── core operations ──

    def suspend(self, chat_id: str, messages_data: List[Dict],
                embeddings: List[np.ndarray],
                start_time: float, last_timestamp: float,
                last_content: str, episode_id: str) -> List[SuspendedEpisode]:
        agg = np.mean(embeddings, axis=0).tolist() if embeddings else []
        entry = SuspendedEpisode(
            episode_id=episode_id,
            chat_id=chat_id,
            messages_data=messages_data,
            embeddings=[e.tolist() for e in embeddings],
            start_time=start_time,
            last_timestamp=last_timestamp,
            last_content=last_content,
            message_count=len(messages_data),
            suspended_at=time.time(),
        )
        evicted: List[SuspendedEpisode] = []
        with self._lock:
            if episode_id in self._pool:
                self._pool[episode_id] = entry
                logger.debug("[SuspendPool] Updated episode=%s in pool (chat=%s, msgs=%d)",
                             episode_id[:12], chat_id[:12], entry.message_count)
            else:
                self._pool[episode_id] = entry
                logger.info("[SuspendPool] Suspended episode=%s (chat=%s, msgs=%d, pool=%d/%d)",
                            episode_id[:12], chat_id[:12], entry.message_count,
                            len(self._pool), self._max_size)
            if len(self._pool) > self._max_size:
                evicted = self._evict_lru()
            self._dirty = True
        return evicted

    def find_reopen(self, chat_id: str, embedding: np.ndarray,
                    threshold: float) -> Optional[SuspendedEpisode]:
        if embedding is None:
            return None
        best_sim = 0.0
        best: Optional[SuspendedEpisode] = None
        with self._lock:
            for entry in self._pool.values():
                if entry.chat_id != chat_id:
                    continue
                sim = entry.max_similarity(embedding)
                if sim > best_sim:
                    best_sim = sim
                    best = entry
        if best:
            if best_sim >= threshold:
                logger.info("[SuspendPool] Reopen: episode=%s chat=%s sim=%.4f >= %.2f ✓",
                            best.episode_id[:12], chat_id[:12], best_sim, threshold)
                return best
            logger.info("[SuspendPool] Reopen below threshold: episode=%s chat=%s sim=%.4f < %.2f ✗",
                        best.episode_id[:12], chat_id[:12], best_sim, threshold)
        else:
            logger.debug("[SuspendPool] No reopen candidate for chat=%s", chat_id[:12])
        return None

    def reopen(self, episode_id: str) -> Optional[SuspendedEpisode]:
        with self._lock:
            entry = self._pool.pop(episode_id, None)
            if entry:
                self._dirty = True
                self._reopen_count += 1
                logger.info("[SuspendPool] Reopened episode=%s (chat=%s, msgs=%d, pool=%d/%d)",
                            episode_id[:12], entry.chat_id[:12], entry.message_count,
                            len(self._pool), self._max_size)
            return entry

    # ── stale / archive ──

    def get_stale(self) -> List[SuspendedEpisode]:
        now = time.time()
        cutoff = now - self._archive_hours * 3600
        stale: List[SuspendedEpisode] = []
        with self._lock:
            for entry in list(self._pool.values()):
                if entry.suspended_at < cutoff:
                    stale.append(entry)
        return stale

    def archive(self, episode_ids: List[str]) -> List[SuspendedEpisode]:
        archived: List[SuspendedEpisode] = []
        with self._lock:
            for eid in episode_ids:
                entry = self._pool.pop(eid, None)
                if entry:
                    archived.append(entry)
                    self._dirty = True
        if archived:
            logger.info("[SuspendPool] Archived %d episode(s), pool=%d/%d",
                        len(archived), len(self._pool), self._max_size)
        return archived

    def archive_all(self) -> List[SuspendedEpisode]:
        with self._lock:
            entries = list(self._pool.values())
            self._pool.clear()
            self._dirty = True
        if entries:
            logger.info("[SuspendPool] Archive all: %d episode(s)", len(entries))
        return entries

    # ── pool info ──

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._pool)

    def contains(self, episode_id: str) -> bool:
        with self._lock:
            return episode_id in self._pool

    def get_ids_by_chat(self, chat_id: str) -> List[str]:
        with self._lock:
            return [e.episode_id for e in self._pool.values() if e.chat_id == chat_id]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pool_size": len(self._pool),
                "max_size": self._max_size,
                "archive_hours": self._archive_hours,
                "dirty": self._dirty,
                "reopen_count": self._reopen_count,
                "chat_ids": list({e.chat_id for e in self._pool.values()}),
            }

    # ── persistence ──

    def save(self) -> None:
        if not self._dirty:
            return
        with self._lock:
            data = {
                "episodes": {
                    eid: {
                        "episode_id": e.episode_id,
                        "chat_id": e.chat_id,
                        "messages_data": e.messages_data,
                        "embeddings": e.embeddings,
                        "start_time": e.start_time,
                        "last_timestamp": e.last_timestamp,
                        "last_content": e.last_content,
                        "message_count": e.message_count,
                        "suspended_at": e.suspended_at,
                    }
                    for eid, e in self._pool.items()
                }
            }
            self._pool_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._pool_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._dirty = False
        logger.info("[SuspendPool] Saved %d episode(s) to %s",
                    len(data["episodes"]), self._pool_path)

    def load(self) -> None:
        if not self._pool_path.exists():
            logger.info("[SuspendPool] No existing pool at %s", self._pool_path)
            return
        try:
            with open(self._pool_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                for eid, raw in data.get("episodes", {}).items():
                    self._pool[eid] = SuspendedEpisode(**raw)
                self._dirty = False
            logger.info("[SuspendPool] Loaded %d episode(s) from %s",
                        len(data.get("episodes", {})), self._pool_path)
        except Exception as e:
            logger.warning("[SuspendPool] Load failed: %s", e)

    # ── internal ──

    def _evict_lru(self) -> List[SuspendedEpisode]:
        if len(self._pool) <= self._max_size:
            return []
        sorted_entries = sorted(
            self._pool.items(),
            key=lambda x: x[1].suspended_at,
        )
        to_remove = len(self._pool) - self._max_size
        evicted: List[SuspendedEpisode] = []
        for eid, entry in sorted_entries[:to_remove]:
            self._pool.pop(eid, None)
            evicted.append(entry)
            logger.info("[SuspendPool] Evicted episode=%s (chat=%s, suspended_at=%s)",
                        eid[:12], entry.chat_id[:12],
                        time.strftime("%H:%M:%S", time.localtime(entry.suspended_at)))
        return evicted