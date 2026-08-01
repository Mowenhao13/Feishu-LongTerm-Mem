"""
文档检测器 — 基于 DocAdapter + EnhancedDetector 的文档决策检测

TODO: 飞书 API 模式
  - 使用 LARK_DOC_POLL_INTERVAL 控制轮询频率
  - 使用 LARK_DOC_DEBOUNCE_WINDOW 控制防抖窗口
  - 白名单配置 LARK_DOC_TOKENS
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.adapter.doc_adapter import DocAdapter, DocChange, DocDetectResult
from src.detect.detector import EnhancedDetector, classify_doc_type
from src.detect.types import (
    AdapterType,
    ChangeType,
    DecisionLevel,
    DetectContext,
    DetectorMode,
    DocType,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DocDetectionJob:
    doc_token: str
    doc_title: str
    content: str
    change_type: str  # "doc_created" | "doc_updated" | "doc_deleted"
    timestamp: float = 0.0
    adapter: AdapterType = AdapterType.DOCS
    meta: Dict[str, str] = field(default_factory=dict)


class DocDetector:
    """
    文档检测器 — 集成信号检测 + 决策提取触发

    流程:
      1. DocAdapter.detect() → 获取文档变更列表
      2. EnhancedDetector.analyze_document() → 信号级别判断
      3. 决定是否触发 LLM 决策提取
    """

    def __init__(
        self,
        adapter: Optional[DocAdapter] = None,
        docs_dir: str = "data/docs",
        polling_interval: int = 30,
        debounce_window: int = 30,
    ):
        self._adapter = adapter or DocAdapter(
            docs_dir=docs_dir,
            polling_interval=polling_interval,
            debounce_window=debounce_window,
        )
        self._signal_detector = EnhancedDetector.create_document_detector()
        self._last_check: float = 0.0

    @property
    def name(self) -> str:
        return "lark_doc"

    @property
    def adapter(self) -> DocAdapter:
        return self._adapter

    def detect(self) -> DocDetectResult:
        """执行检测循环 — 返回文档变更列表"""
        result = self._adapter.detect()
        self._last_check = time.time()

        if result.has_changes:
            logger.info("[DocDetector] %d document changes detected", len(result.changes))

            # 对每个变更执行信号检测
            for change in result.changes:
                doc_type = classify_doc_type(change.doc_title, change.content)
                detect_result = self._signal_detector.analyze_document(
                    content=change.content,
                    title=change.doc_title,
                    doc_type=doc_type,
                )
                change.meta["signal_score"] = str(detect_result.score)
                change.meta["signal_level"] = detect_result.level.value
                change.meta["is_decision"] = str(detect_result.is_decision)
                change.meta["doc_type"] = doc_type.value

                logger.info(
                    "  %s: score=%.2f level=%s is_decision=%s doc_type=%s",
                    change.doc_token, detect_result.score,
                    detect_result.level.value, detect_result.is_decision, doc_type.value,
                )

        return result

    def create_jobs(self, result: DocDetectResult) -> List[DocDetectionJob]:
        """将检测结果转换为处理任务"""
        jobs: List[DocDetectionJob] = []
        for change in result.changes:
            meta = dict(change.meta)
            meta["signal_score"] = meta.get("signal_score", "0.0")
            meta["signal_level"] = meta.get("signal_level", "none")

            job = DocDetectionJob(
                doc_token=change.doc_token,
                doc_title=change.doc_title,
                content=change.content,
                change_type=change.type,
                timestamp=change.timestamp,
                adapter=AdapterType.DOCS,
                meta=meta,
            )
            jobs.append(job)
        return jobs