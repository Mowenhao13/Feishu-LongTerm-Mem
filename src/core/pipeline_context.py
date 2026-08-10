"""运行时 Pipeline 上下文

组件之间共享的运行时状态。PipelineEngine 初始化时创建，
Detector→Extractor→Index 各阶段通过 Context 传递数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from src.core.pipeline_loader import PipelineConfig


@dataclass
class PipelineContext:
    """Pipeline 运行时上下文"""

    config: PipelineConfig
    metadata: Dict[str, Any] = field(default_factory=dict)
    extract_mode: str = "direct"  # direct | two_stage

    # 运行时状态
    source_states: Dict[str, Any] = field(default_factory=dict)
    transform_states: Dict[str, Any] = field(default_factory=dict)
    index_states: Dict[str, Any] = field(default_factory=dict)

    # 处理统计
    total_processed: int = 0
    total_errors: int = 0
    total_llm_calls: int = 0

    # 脏标记
    dirty_sources: Set[str] = field(default_factory=set)

    def get_trace_prefix(self) -> str:
        """生成 Trace 前缀（A/B 标签）"""
        return f"pipeline_v2_{self.extract_mode}"