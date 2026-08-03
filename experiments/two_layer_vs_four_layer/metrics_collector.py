"""性能与内存指标采集器

用于对比实验的 system delay 和 memory usage 监控。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricsSnapshot:
    """单次采集的指标快照"""
    timestamp: float
    rss_mb: float
    vms_mb: float
    cpu_percent: float


@dataclass
class TimingRecord:
    """处理单条消息的时间记录"""
    message_index: int
    chat_id: str
    content_preview: str
    elapsed_ms: float
    llm_call_count: int = 0
    note: str = ""


class MetricsCollector:
    """运行时指标采集器

    用法：
        collector = MetricsCollector()
        collector.start()
        # ... 处理消息 ...
        metrics = collector.stop()
        print(metrics["summary"])
    """

    def __init__(self, interval: float = 5.0) -> None:
        self._interval = interval
        self._snapshots: List[MetricsSnapshot] = []
        self._timings: List[TimingRecord] = []
        self._start_time: float = 0.0
        self._end_time: float = 0.0
        self._last_llm_calls: int = 0

    def start(self) -> None:
        self._start_time = time.time()
        self._snapshots = []
        self._timings = []
        self._snapshot_now()

    def stop(self) -> Dict[str, Any]:
        self._end_time = time.time()
        self._snapshot_now()
        return self.compute_metrics()

    def record_timing(
        self,
        message_index: int,
        chat_id: str,
        content_preview: str,
        elapsed_ms: float,
        llm_call_count: int = 0,
        note: str = "",
    ) -> None:
        self._timings.append(TimingRecord(
            message_index=message_index,
            chat_id=chat_id,
            content_preview=content_preview[:40],
            elapsed_ms=elapsed_ms,
            llm_call_count=llm_call_count,
            note=note,
        ))

    def _snapshot_now(self) -> None:
        rss, vms = self._get_memory_usage()
        self._snapshots.append(MetricsSnapshot(
            timestamp=time.time(),
            rss_mb=rss,
            vms_mb=vms,
            cpu_percent=self._get_cpu_percent(),
        ))

    @staticmethod
    def _get_memory_usage() -> tuple:
        """获取进程内存使用 (RSS, VMS) in MB"""
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem = proc.memory_info()
            return mem.rss / 1024 / 1024, mem.vms / 1024 / 1024
        except ImportError:
            # 回退到 /proc/self/status (Linux) 或 resource (macOS)
            try:
                import resource
                rusage = resource.getrusage(resource.RUSAGE_SELF)
                rss = rusage.ru_maxrss / 1024  # macOS: KB → MB
                return rss, 0.0
            except Exception:
                return 0.0, 0.0

    @staticmethod
    def _get_cpu_percent() -> float:
        try:
            import psutil
            return psutil.Process(os.getpid()).cpu_percent(interval=0.1)
        except (ImportError, Exception):
            return 0.0

    def compute_metrics(self) -> Dict[str, Any]:
        elapsed = self._end_time - self._start_time if self._end_time > self._start_time else 0.0
        timings_ms = [t.elapsed_ms for t in self._timings]
        rss_values = [s.rss_mb for s in self._snapshots]
        vms_values = [s.vms_mb for s in self._snapshots]

        return {
            "total_elapsed_seconds": round(elapsed, 1),
            "messages_processed": len(self._timings),
            "processing_rate_msgs_per_sec": round(len(self._timings) / elapsed, 2) if elapsed > 0 else 0,
            "timing_ms": {
                "mean": round(sum(timings_ms) / len(timings_ms), 1) if timings_ms else 0,
                "median": round(sorted(timings_ms)[len(timings_ms) // 2], 1) if timings_ms else 0,
                "p95": round(sorted(timings_ms)[int(len(timings_ms) * 0.95)], 1) if len(timings_ms) >= 20 else 0,
                "max": round(max(timings_ms), 1) if timings_ms else 0,
                "min": round(min(timings_ms), 1) if timings_ms else 0,
            },
            "memory_mb": {
                "rss_mean": round(sum(rss_values) / len(rss_values), 1) if rss_values else 0,
                "rss_peak": round(max(rss_values), 1) if rss_values else 0,
                "rss_final": round(rss_values[-1], 1) if rss_values else 0,
                "vms_mean": round(sum(vms_values) / len(vms_values), 1) if vms_values else 0,
            },
            "snapshots_count": len(self._snapshots),
            "summary": (
                f"Processed {len(self._timings)} msgs in {elapsed:.0f}s "
                f"({len(self._timings) / max(elapsed, 0.1):.1f} msg/s), "
                f"avg {round(sum(timings_ms) / len(timings_ms), 1) if timings_ms else 0} ms/msg, "
                f"RSS peak {round(max(rss_values), 1) if rss_values else 0} MB"
            ),
        }