"""Pipeline 组件注册机制

提供组件类型与实现类的映射注册。PipelineLoader 通过 Registry
将 YAML 中的 type name 解析为具体的 Python 类实例。

使用方式：

    @registry.register("source", "im")
    class LarkIMDetector:
        ...

    @registry.register("transform", "llm_extract")
    class LLMExtractTransform:
        ...

    # 获取实例
    cls = registry.get("source", "im")
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

_registry: Dict[str, Dict[str, type]] = {
    "source": {},
    "transform": {},
    "index": {},
    "consolidation": {},
}


def register(category: str, name: str) -> Callable[[type], type]:
    """注册组件类到指定类别和名称下"""

    def decorator(cls: type) -> type:
        if category not in _registry:
            _registry[category] = {}
        _registry[category][name] = cls
        return cls

    return decorator


def get(category: str, name: str) -> Optional[type]:
    """获取已注册的组件类"""
    return _registry.get(category, {}).get(name)


def list_registered(category: Optional[str] = None) -> Dict[str, Dict[str, type]]:
    """列出已注册的组件"""
    if category:
        return {category: _registry.get(category, {})}
    return dict(_registry)


def create(category: str, name: str, **kwargs: Any) -> Any:
    """创建已注册组件的实例"""
    cls = get(category, name)
    if cls is None:
        raise KeyError(f"Component not registered: {category}/{name}")
    return cls(**kwargs)


def available(category: str) -> list[str]:
    """获取某类别下所有已注册的组件名"""
    return list(_registry.get(category, {}).keys())