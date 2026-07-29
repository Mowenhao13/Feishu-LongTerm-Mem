"""Langfuse 可观测性配置模块"""

import os
from typing import Optional

# Langfuse 客户端（惰性初始化）
_langfuse_client = None
_langfuse_enabled = False


def is_langfuse_enabled() -> bool:
    return os.getenv("LANGFUSE_ENABLE", "false").lower() == "true"


def get_langfuse():
    """获取 Langfuse 客户端（单例，惰性初始化）"""
    global _langfuse_client, _langfuse_enabled
    if _langfuse_client is not None:
        return _langfuse_client
    if not is_langfuse_enabled():
        return None
    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        )
        _langfuse_enabled = True
        return _langfuse_client
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Langfuse init failed: %s", e)
        return None


def get_sample_rate() -> float:
    """获取采样率，决定是否记录当前 Trace"""
    rate = float(os.getenv("LANGFUSE_SAMPLE_RATE", "1.0"))
    return max(0.0, min(1.0, rate))


def should_sample() -> bool:
    """根据采样率判断是否记录本次 Trace"""
    if not is_langfuse_enabled():
        return False
    rate = get_sample_rate()
    if rate >= 1.0:
        return True
    import random
    return random.random() < rate