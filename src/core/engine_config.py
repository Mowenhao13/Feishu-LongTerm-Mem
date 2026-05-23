from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EngineConfig:
    """Engine 配置 — 读取自 .env 或手动设置"""

    project: str = "feishu-mem"
    default_topic: str = "general"

    storage_path: str = "data"
    storage_auto_sync: bool = True
    storage_sync_interval: int = 60

    detector_enabled: bool = True
    detector_min_score: float = 0.5
    detector_snapshot_enabled: bool = True
    detector_snapshot_storage_path: str = "data"

    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_max_tokens: int = 4096

    ingester_im_enabled: bool = False
    ingester_doc_enabled: bool = False
    ingester_poll_interval: int = 30

    conflict_auto_resolve: bool = False
    conflict_notification_enabled: bool = False

    graph_auto_sync: bool = True
    graph_sync_interval: int = 60

    @staticmethod
    def from_env() -> EngineConfig:
        """从环境变量加载配置"""
        import os

        cfg = EngineConfig()
        cfg.storage_path = os.getenv("STORAGE_PATH", "data")
        cfg.detector_snapshot_storage_path = os.getenv("STORAGE_PATH", "data")
        cfg.llm_base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
        cfg.llm_api_key = os.getenv("API_KEY", "")
        cfg.llm_model = os.getenv("MODEL_NAME", "deepseek-chat")
        return cfg


@dataclass
class EngineStatus:
    """Engine 运行状态"""

    is_running: bool = False
    decisions_loaded: int = 0
    topics_loaded: int = 0
    total_mutations_applied: int = 0
    failed_mutations: int = 0
    uptime_seconds: int = 0
    last_snapshot_time: str = ""
    error_count: int = 0
    last_error: str = ""