"""
Context message builder for Lark IM.
Mirrors internal/lark-adapter/context_message.go
"""

from typing import List

from .types import Change, MessageRecord


class ContextMessage:
    def __init__(
        self,
        change: Change = None,
        chat_history: List[MessageRecord] = None,
        thread_history: List[MessageRecord] = None,
        message_index: int = 0,
        keywords: List[str] = None,
    ):
        self.change = change or Change()
        self.chat_history = chat_history or []
        self.thread_history = thread_history or []
        self.message_index = message_index
        self.keywords = keywords or []

    def build_llm_input(self) -> str:
        parts = []

        if self.thread_history:
            parts.append("【同一话题的历史讨论】")
            for msg in self.thread_history:
                parts.append(f"{msg.sender_name}: {_truncate_content(msg.content, 200)}")
            parts.append("")

        if self.chat_history:
            parts.append("【最近聊天记录】")
            for msg in self.chat_history:
                parts.append(f"{msg.sender_name}: {_truncate_content(msg.content, 200)}")
            parts.append("")

        parts.append("【当前消息】")
        sender = self.change.sender_name or "unknown"
        content = self.change.raw_content or self.change.summary or ""
        parts.append(f"{sender}: {content}")

        return "\n".join(parts)


def _truncate_content(content: str, max_len: int) -> str:
    if len(content) <= max_len:
        return content
    return content[:max_len] + "..."


def extract_keywords(records: List[MessageRecord], max_keywords: int = 5) -> List[str]:
    if max_keywords <= 0:
        max_keywords = 5
    seen: dict = {}
    for r in records:
        if r.msg_type != "text":
            continue
        for w in r.content.split():
            w = w.strip()
            if len(w) < 2:
                continue
            seen[w] = seen.get(w, 0) + 1

    sorted_kw = sorted(seen.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_kw[:max_keywords]]