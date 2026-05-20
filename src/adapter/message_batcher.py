"""
Message batcher for grouping and context building.
Mirrors internal/lark-adapter/message_batcher.go
"""

import logging
import threading
import time
from typing import Dict, List, Optional

from .types import Change, MessageRecord
from .context_message import ContextMessage, extract_keywords, _truncate_content
from .noise_filter import NoiseFilter

logger = logging.getLogger(__name__)


def is_chinese(ch: str) -> bool:
    return '\u4e00' <= ch <= '\u9fff'


def all_chinese(s: str) -> bool:
    return all(is_chinese(ch) for ch in s)


def extract_words(text: str) -> List[str]:
    words = []
    for w in text.split():
        w = w.strip(".,!?;:\"'()[]{}").lower()
        if len(w) >= 2:
            words.append(w)
    for i in range(len(text)):
        ch = text[i]
        if is_chinese(ch):
            for length in range(4, 1, -1):
                if i + length <= len(text):
                    word = text[i:i + length]
                    if all_chinese(word):
                        words.append(word)
    return words


def has_keyword_overlap(group: List[MessageRecord], new_msg: MessageRecord) -> bool:
    group_keywords: set = set()
    for msg in group:
        group_keywords.update(extract_words(msg.content))
    new_words = extract_words(new_msg.content)
    return any(w in group_keywords for w in new_words)


def group_by_time_and_keywords(records: List[MessageRecord], window_seconds: float) -> List[List[MessageRecord]]:
    if not records:
        return []

    groups: List[List[MessageRecord]] = []
    current_group = [records[0]]

    for i in range(1, len(records)):
        time_diff = records[i].create_time - records[i - 1].create_time
        if time_diff > window_seconds:
            groups.append(current_group)
            current_group = [records[i]]
        else:
            if has_keyword_overlap(current_group, records[i]):
                current_group.append(records[i])
            else:
                groups.append(current_group)
                current_group = [records[i]]

    groups.append(current_group)
    return groups


def merge_records(existing: List[MessageRecord], incoming: List[MessageRecord]) -> List[MessageRecord]:
    seen = {r.message_id for r in existing}
    merged = list(existing)
    for r in incoming:
        if r.message_id not in seen:
            merged.append(r)
            seen.add(r.message_id)
    return merged


class MessageBatcher:
    def __init__(self):
        self._lock = threading.Lock()
        self.chat_cache: Dict[str, List[MessageRecord]] = {}
        self.context_limit: int = 30
        self.cache_expiry_seconds: float = 30 * 60  # 30 min
        self.last_cleanup: float = time.time()
        self.noise_filter = NoiseFilter()

    def update_cache(self, chat_id: str, records: List[MessageRecord]) -> None:
        if not records:
            return
        with self._lock:
            existing = self.chat_cache.get(chat_id, [])
            existing = merge_records(existing, records)
            existing.sort(key=lambda r: r.create_time)
            if len(existing) > self.context_limit * 2:
                existing = existing[-(self.context_limit * 2):]
            self.chat_cache[chat_id] = existing
            self._cleanup()

    def group_messages(self, records: List[MessageRecord]) -> List[List[MessageRecord]]:
        if not records:
            return []

        valid = [r for r in records if not self.noise_filter.is_noise(r)]
        if not valid:
            logger.info(f"[MessageBatcher] All %d messages filtered as noise", len(records))
            return []
        logger.info(f"[MessageBatcher] Noise filter: %d → %d messages", len(records), len(valid))

        thread_groups: Dict[str, List[MessageRecord]] = {}
        non_thread: List[MessageRecord] = []
        for r in valid:
            if r.thread_id:
                thread_groups.setdefault(r.thread_id, []).append(r)
            else:
                non_thread.append(r)

        time_groups = group_by_time_and_keywords(non_thread, 10.0)

        result = list(thread_groups.values()) + time_groups
        logger.info(f"[MessageBatcher] Grouped %d valid messages into %d discussion groups", len(valid), len(result))
        return result

    def build_group_context(self, group: List[MessageRecord]) -> Optional[ContextMessage]:
        if not group:
            return None

        last_msg = group[-1]
        sb_lines = ["【群聊讨论内容】"]
        for msg in group:
            sb_lines.append(f"{msg.sender_name}: {_truncate_content(msg.content, 300)}")
        raw_text = "\n".join(sb_lines)

        summary = f"[群聊] {last_msg.sender_name}: {_truncate_content(last_msg.content, 60)}"

        ctx = ContextMessage(
            change=Change(
                type="new_text",
                entity_type="group_message",
                entity_id=last_msg.message_id,
                summary=summary,
                timestamp=last_msg.create_time,
                chat_id=last_msg.chat_id,
                thread_id=last_msg.thread_id,
                sender_id=last_msg.sender_id,
                sender_name=last_msg.sender_name,
                mention_ids=list(last_msg.mentions),
                raw_content=raw_text,
                context_text=raw_text,
            ),
            message_index=len(group),
        )
        ctx.keywords = extract_keywords(group, 5)
        return ctx

    def build_context(self, record: MessageRecord, index: int, all_records: List[MessageRecord]) -> ContextMessage:
        ctx = ContextMessage(message_index=index + 1)

        if record.thread_id:
            ctx.thread_history = self._find_thread_history(record.thread_id, record.create_time, record.chat_id)

        ctx.chat_history = self._find_chat_history(
            record.chat_id, record.create_time, record.thread_id, record.message_id
        )

        combined = ctx.thread_history + ctx.chat_history
        ctx.keywords = extract_keywords(combined, 5)

        change_type = "new_text" if record.msg_type in ("text", "post") else "new"
        summary = record.content
        if len(summary) > 60:
            summary = summary[:60] + "..."

        ctx.change = Change(
            type=change_type,
            entity_type="group_message",
            entity_id=record.message_id,
            summary=summary,
            timestamp=record.create_time,
            chat_id=record.chat_id,
            thread_id=record.thread_id,
            sender_id=record.sender_id,
            sender_name=record.sender_name,
            mention_ids=list(record.mentions),
            raw_content=record.content,
        )

        return ctx

    def _find_thread_history(self, thread_id: str, before_time: int, chat_id: str) -> List[MessageRecord]:
        with self._lock:
            records = self.chat_cache.get(chat_id, [])
        history = [r for r in records if r.thread_id == thread_id and r.create_time < before_time]
        if len(history) > self.context_limit:
            history = history[-self.context_limit:]
        return history

    def _find_chat_history(self, chat_id: str, before_time: int, exclude_thread_id: str, exclude_msg_id: str) -> List[MessageRecord]:
        with self._lock:
            records = self.chat_cache.get(chat_id, [])
        history = []
        for r in records:
            if r.create_time >= before_time:
                continue
            if r.message_id == exclude_msg_id:
                continue
            if r.thread_id and r.thread_id != exclude_thread_id:
                continue
            history.append(r)
        if len(history) > self.context_limit:
            history = history[-self.context_limit:]
        return history

    def _cleanup(self) -> None:
        if time.time() - self.last_cleanup < self.cache_expiry_seconds:
            return
        self.last_cleanup = time.time()
        cutoff = time.time() - self.cache_expiry_seconds
        to_delete = []
        for chat_id, records in self.chat_cache.items():
            kept = [r for r in records if r.create_time >= cutoff]
            if not kept:
                to_delete.append(chat_id)
                logger.info(f"[MessageBatcher] Cleared expired cache for chat %s", chat_id)
            else:
                self.chat_cache[chat_id] = kept
        for chat_id in to_delete:
            del self.chat_cache[chat_id]