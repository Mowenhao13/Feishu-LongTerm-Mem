"""声明式 Pipeline 加载器

将 configs/pipeline.yaml 解析为组件实例化配置，
支持组件注册、配置校验、依赖解析和 A/B 模式切换。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.pipeline_registry import create, get

logger = logging.getLogger(__name__)


class PipelineValidationError(Exception):
    """Pipeline 配置校验错误"""
    pass


@dataclass
class SourceConfig:
    name: str
    type: str
    enabled: bool = True
    mode: str = "poll"
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransformConfig:
    name: str
    type: str
    enabled: bool = True
    mode: str = "direct"
    inputs: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexConfig:
    name: str
    type: str
    source: str = ""
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsolidationConfig:
    name: str
    enabled: bool = True
    interval: int = 3600
    phases: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    version: str = "1.0"
    sources: List[SourceConfig] = field(default_factory=list)
    transforms: List[TransformConfig] = field(default_factory=list)
    indexes: List[IndexConfig] = field(default_factory=list)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)


class PipelineLoader:
    """Pipeline 加载器 — YAML → PipelineConfig"""

    def __init__(self) -> None:
        self._config: Optional[PipelineConfig] = None

    def load(self, path: str | Path) -> PipelineConfig:
        """加载并校验 Pipeline YAML 配置"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline config not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f)

        pipeline = raw.get("pipeline", raw)
        self._config = self._parse(pipeline)
        self._validate()

        logger.info(
            "[PipelineLoader] Loaded: sources=%d transforms=%d indexes=%d consolidation=%s",
            len(self._config.sources), len(self._config.transforms),
            len(self._config.indexes), self._config.consolidation.name,
        )
        return self._config

    @property
    def config(self) -> PipelineConfig:
        if self._config is None:
            raise RuntimeError("Pipeline not loaded yet")
        return self._config

    def _parse(self, raw: Dict[str, Any]) -> PipelineConfig:
        version = raw.get("version", "1.0")

        sources = [
            SourceConfig(**src)
            for src in raw.get("sources", [])
        ]
        transforms = [
            TransformConfig(**tf)
            for tf in raw.get("transforms", [])
        ]
        indexes = [
            IndexConfig(**idx)
            for idx in raw.get("indexes", [])
        ]

        cons_raw = raw.get("consolidation", {})
        consolidation = ConsolidationConfig(**cons_raw) if cons_raw else ConsolidationConfig()

        return PipelineConfig(
            version=version,
            sources=sources,
            transforms=transforms,
            indexes=indexes,
            consolidation=consolidation,
        )

    def _validate(self) -> None:
        """校验配置完整性"""
        config = self._config
        if not config:
            raise PipelineValidationError("No config loaded")

        for src in config.sources:
            if not src.name:
                raise PipelineValidationError("Source must have a name")
            if not RegistryLookupError.handle(get("source", src.type)) is None:
                # 非注册组件也可以使用（如通过模块路径），但给出警告
                logger.debug("[PipelineLoader] Source type '%s' not registered", src.type)
                continue

        for tf in config.transforms:
            if not tf.name:
                raise PipelineValidationError("Transform must have a name")
            if not tf.inputs:
                raise PipelineValidationError(f"Transform '{tf.name}' has no inputs")

        for idx in config.indexes:
            if not idx.source:
                raise PipelineValidationError(f"Index '{idx.name}' has no source")

        # 校验 consolidation phases
        valid_phases = {"light", "rem", "deep", "promote", "tree", "wave"}
        for p in config.consolidation.phases:
            if p not in valid_phases:
                logger.warning("[PipelineLoader] Unknown consolidation phase '%s'", p)

    def get_extract_mode(self) -> str:
        """获取提取模式: direct | two_stage"""
        for tf in (self._config or PipelineConfig()).transforms:
            if tf.type == "llm_extract":
                return tf.mode
        return "direct"

    def get_enabled_sources(self) -> List[SourceConfig]:
        return [s for s in (self._config or PipelineConfig()).sources if s.enabled]

    def get_enabled_transforms(self) -> List[TransformConfig]:
        return [t for t in (self._config or PipelineConfig()).transforms if t.enabled]

    def get_enabled_indexes(self) -> List[IndexConfig]:
        return [i for i in (self._config or PipelineConfig()).indexes if i.enabled]


class RegistryLookupError(Exception):
    pass


RegistryLookupError.handle = staticmethod(lambda x: x)