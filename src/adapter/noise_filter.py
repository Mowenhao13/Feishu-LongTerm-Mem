"""
Noise filter for Lark IM messages.
Mirrors internal/lark-adapter/noise_filter.go
"""

import re
import unicodedata
from typing import List


EMOJI_RANGES = [
    (0x1F600, 0x1F64F),  # Emoticons
    (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs
    (0x1F680, 0x1F6FF),  # Transport and Map
    (0x1F1E0, 0x1F1FF),  # Flags
    (0x2600, 0x26FF),    # Misc symbols
    (0x2700, 0x27BF),    # Dingbats
    (0xFE00, 0xFE0F),    # Variation Selectors
    (0x200D, 0x200D),    # Zero Width Joiner
    (0x1F900, 0x1F9FF),  # Supplemental Symbols
    (0x1FA00, 0x1FA6F),  # Chess Symbols
    (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended
]


_DECISION_SIGNALS = [
    "决定", "确认", "采用", "选择", "结论", "通过",
    "方案", "选型", "确认", "批准", "同意", "拒绝",
    "decide", "confirm", "adopt", "select", "choose",
    "approve", "agree", "reject", "conclusion",
]


def is_emoji(ch: str) -> bool:
    code = ord(ch)
    for lo, hi in EMOJI_RANGES:
        if lo <= code <= hi:
            return True
    return False


def is_only_emoji(s: str) -> bool:
    cleaned = re.sub(r'[\s.,!?，。！？、]', '', s)
    if not cleaned:
        return False
    emoji_count = sum(1 for ch in cleaned if is_emoji(ch))
    non_emoji_count = len(cleaned) - emoji_count
    if non_emoji_count == 0:
        return True
    if emoji_count > 0 and (emoji_count / len(cleaned)) > 0.8:
        return True
    return False


def contains_decision_signal(text: str) -> bool:
    lower = text.lower()
    for s in _DECISION_SIGNALS:
        if s in lower:
            return True
    return False


def is_link_only(content: str) -> bool:
    lower = content.lower()
    if "http" not in lower:
        return False
    trimmed = content.strip()
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        parts = trimmed.split(None, 1)
        if len(parts) == 1:
            return True
        comment = parts[1].strip()
        if len(comment) < 3:
            return True
    return False


def contains_noise_topic(text: str, topics: List[str]) -> bool:
    for t in topics:
        if t in text:
            return True
    return False


def has_cjk(s: str) -> bool:
    for ch in s:
        if unicodedata.unihan_data.get(ch, None) is not None:
            return True
        try:
            if unicodedata.name(ch).startswith(('CJK', 'HANGUL', 'HIRAGANA', 'KATAKANA')):
                return True
        except (ValueError, AttributeError):
            continue
    return False


class NoiseFilter:
    def __init__(self):
        self.noise_words: List[str] = [
            "好的", "收到", "嗯", "哦", "OK", "ok", "Ok",
            "好", "行", "是", "对", "嗯嗯", "哈哈", "嘿嘿",
            "谢谢", "感谢", "辛苦了", "赞", "+1", "1",
            "yes", "no", "thanks", "thx", "got it", "sure",
            "lol", "haha", "nice", "good", "well",
        ]
        self.noise_topics: List[str] = [
            "天气", "下雨", "太阳", "温度", "热", "冷",
            "吃饭", "午餐", "晚餐", "早餐", "外卖", "食堂",
            "周末", "假期", "旅游", "电影", "游戏", "综艺",
            "地铁", "公交", "堵车", "迟到",
        ]
        self.min_length: int = 5

    def is_noise(self, record) -> bool:
        content = record.content.strip() if hasattr(record, 'content') else str(record).strip()
        if not content:
            return True

        if is_only_emoji(content):
            return True

        content_lower = content.lower()
        for w in self.noise_words:
            if content_lower == w.lower():
                return True

        if len(content) < self.min_length and not contains_decision_signal(content):
            return True

        if contains_noise_topic(content_lower, self.noise_topics) and not contains_decision_signal(content):
            return True

        if is_link_only(content):
            return True

        return False

    def is_noise_for_doc(self, comment_text: str) -> bool:
        text = comment_text.strip()
        if not text:
            return True
        doc_noise = ["LGTM", "lgtm", "+1", "👍", "好的", "收到"]
        text_lower = text.lower()
        for w in doc_noise:
            if text_lower == w.lower():
                return True
        return False