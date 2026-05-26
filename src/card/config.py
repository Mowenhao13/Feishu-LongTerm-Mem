from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class CardConfig:
    enable_feishu: bool = False
    enable_terminal: bool = True
    enable_osascript: bool = False

    feishu_chat_id: str = ""
    card_chat_ids: List[str] = field(default_factory=list)
    feishu_receive_id_type: str = "chat_id"

    trigger_on_conflict: bool = True
    trigger_on_update: bool = True
    trigger_on_hot_score_threshold: bool = True
    hot_score_low_threshold: float = 20.0
    hot_score_scan_interval: int = 600

    enable_daily_summary: bool = True
    daily_summary_time: str = "08:00"
    weekly_summary_day: str = "6"
    weekly_summary_time: str = "21:00"

    push_hot_score_increment: float = 10.0
    hot_score_decay_rate: float = 0.95
    hot_score_decay_interval: int = 86400

    @staticmethod
    def from_env() -> CardConfig:
        import os

        cfg = CardConfig()
        cfg.enable_feishu = os.getenv("PUSH_FEISHU_ENABLED", "false").lower() == "true"
        cfg.enable_terminal = os.getenv("PUSH_TERMINAL_ENABLED", "true").lower() == "true"
        cfg.enable_osascript = os.getenv("PUSH_OSASCRIPT_ENABLED", "false").lower() == "true"
        cfg.feishu_chat_id = os.getenv("PUSH_FEISHU_CHAT_ID", "")
        raw_card_ids = os.getenv("CARD_CHAT_IDS", "")
        cfg.card_chat_ids = [cid.strip() for cid in raw_card_ids.split(",") if cid.strip()]
        cfg.trigger_on_conflict = os.getenv("PUSH_TRIGGER_CONFLICT", "true").lower() == "true"
        cfg.trigger_on_update = os.getenv("PUSH_TRIGGER_UPDATE", "true").lower() == "true"
        cfg.trigger_on_hot_score_threshold = os.getenv("PUSH_TRIGGER_HOT_SCORE", "true").lower() == "true"
        raw_threshold = os.getenv("PUSH_HOT_SCORE_THRESHOLD", "20.0")
        try:
            cfg.hot_score_low_threshold = float(raw_threshold)
        except ValueError:
            cfg.hot_score_low_threshold = 20.0
        cfg.enable_daily_summary = os.getenv("PUSH_DAILY_SUMMARY", "true").lower() == "true"
        cfg.daily_summary_time = os.getenv("PUSH_DAILY_TIME", "08:00")
        cfg.weekly_summary_day = os.getenv("PUSH_WEEKLY_DAY", "6")
        cfg.weekly_summary_time = os.getenv("PUSH_WEEKLY_TIME", "21:00")
        raw_increment = os.getenv("PUSH_HOT_SCORE_INCREMENT", "10.0")
        try:
            cfg.push_hot_score_increment = float(raw_increment)
        except ValueError:
            cfg.push_hot_score_increment = 10.0
        raw_decay = os.getenv("PUSH_HOT_SCORE_DECAY", "0.95")
        try:
            cfg.hot_score_decay_rate = float(raw_decay)
        except ValueError:
            cfg.hot_score_decay_rate = 0.95
        return cfg