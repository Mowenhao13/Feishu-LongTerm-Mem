"""Langfuse 可观测性配置模块

提供 Langfuse 客户端的惰性初始化、采样率和启用状态查询。
遵循"降级安全"原则：Langfuse 初始化失败或不可用时，系统正常运行不报错。
"""

import os
from typing import Optional

# Langfuse 客户端（惰性初始化单例）
_langfuse_client = None
_langfuse_enabled = False


def is_langfuse_enabled() -> bool:
    """检查 Langfuse 是否启用（环境变量 LANGFUSE_ENABLE=true）"""
    return os.getenv("LANGFUSE_ENABLE", "false").lower() == "true"


def _get_langfuse_host() -> str:
    """获取 Langfuse host，兼容 LANGFUSE_HOST 和 LANGFUSE_BASE_URL 两种变量名"""
    return os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")


def get_langfuse():
    """获取 Langfuse 客户端（单例，惰性初始化）

    首次调用时初始化，之后复用同一实例。
    如果 LANGFUSE_ENABLE=false 或初始化失败，返回 None。

    Returns:
        Langfuse 客户端实例，或 None（未启用/初始化失败）
    """
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
            host=_get_langfuse_host(),
        )
        _langfuse_enabled = True
        return _langfuse_client
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Langfuse init failed (non-fatal): %s", e)
        return None


def get_sample_rate() -> float:
    """获取采样率，决定是否记录当前 Trace

    取值范围 0.0~1.0，1.0 表示全部记录。
    环境变量：LANGFUSE_SAMPLE_RATE。
    """
    rate = float(os.getenv("LANGFUSE_SAMPLE_RATE", "1.0"))
    return max(0.0, min(1.0, rate))


def should_sample() -> bool:
    """根据采样率判断是否记录本次 Trace

    如果 Langfuse 未启用，直接返回 False。
    采样率 >= 1.0 时全部记录。
    否则按概率采样。
    """
    if not is_langfuse_enabled():
        return False
    rate = get_sample_rate()
    if rate >= 1.0:
        return True
    import random
    return random.random() < rate