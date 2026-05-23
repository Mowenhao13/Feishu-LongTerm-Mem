from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.signal.types import DetectContext, DetectionResult, ScoreBreakdown, SignalDetail
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DetectorSnapshot:
    """一次检测的状态快照"""

    def __init__(
        self,
        snapshot_id: str,
        timestamp: str,
        content_snippet: str,
        source: str,
        detection_result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.snapshot_id = snapshot_id
        self.timestamp = timestamp
        self.content_snippet = content_snippet
        self.source = source
        self.detection_result = detection_result
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "content_snippet": self.content_snippet,
            "source": self.source,
            "detection_result": self.detection_result,
            "context": self.context,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> DetectorSnapshot:
        return DetectorSnapshot(
            snapshot_id=data["snapshot_id"],
            timestamp=data["timestamp"],
            content_snippet=data.get("content_snippet", ""),
            source=data.get("source", "im"),
            detection_result=data.get("detection_result", {}),
            context=data.get("context", {}),
        )

    @staticmethod
    def from_detection(
        content: str,
        source: str,
        result: DetectionResult,
        ctx: Optional[DetectContext] = None,
    ) -> DetectorSnapshot:
        return DetectorSnapshot(
            snapshot_id=_generate_snapshot_id(),
            timestamp=datetime.now().isoformat(),
            content_snippet=content[:200],
            source=source,
            detection_result=_result_to_dict(result),
            context=_context_to_dict(ctx),
        )


class SnapshotManager:
    """检测器快照管理器 — 持久化到 {STORAGE_PATH}/snapshots/"""

    def __init__(self, storage_path: str) -> None:
        self._snapshots_dir = Path(storage_path) / "snapshots"
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)

    @property
    def snapshots_dir(self) -> Path:
        return self._snapshots_dir

    def save_snapshot(self, snapshot: DetectorSnapshot) -> str:
        file_path = self._snapshots_dir / f"{snapshot.snapshot_id}.json"
        file_path.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Snapshot saved: %s", file_path)
        return str(file_path)

    def load_snapshot(self, snapshot_id: str) -> Optional[DetectorSnapshot]:
        file_path = self._snapshots_dir / f"{snapshot_id}.json"
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return DetectorSnapshot.from_dict(data)
        except Exception as e:
            logger.warning("Failed to load snapshot %s: %s", snapshot_id, e)
            return None

    def list_snapshots(self, limit: int = 50) -> List[DetectorSnapshot]:
        files = sorted(self._snapshots_dir.glob("*.json"), reverse=True)[:limit]
        snapshots: List[DetectorSnapshot] = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                snapshots.append(DetectorSnapshot.from_dict(data))
            except Exception:
                continue
        return snapshots

    def list_snapshots_by_source(self, source: str, limit: int = 50) -> List[DetectorSnapshot]:
        return [s for s in self.list_snapshots(limit) if s.source == source]

    def delete_old_snapshots(self, keep_count: int = 1000) -> int:
        files = sorted(self._snapshots_dir.glob("*.json"))
        if len(files) <= keep_count:
            return 0
        deleted = 0
        for f in files[:-keep_count]:
            f.unlink()
            deleted += 1
        logger.info("Cleaned %d old snapshots, kept %d", deleted, keep_count)
        return deleted


def _generate_snapshot_id() -> str:
    return f"snap-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _result_to_dict(result: DetectionResult) -> Dict[str, Any]:
    return {
        "score": result.score,
        "level": result.level.value if result.level else "none",
        "is_decision": result.is_decision,
        "signal_details": [_signal_to_dict(s) for s in (result.signal_details or [])],
        "anti_signals": result.anti_signals or [],
        "factors": {
            "lexical": result.factors.lexical if result.factors else 0.0,
            "structural": result.factors.structural if result.factors else 0.0,
            "dynamic": result.factors.dynamic if result.factors else 0.0,
            "pattern": result.factors.pattern if result.factors else 0.0,
            "anti_score": result.factors.anti_score if result.factors else 0.0,
            "final": result.factors.final if result.factors else 0.0,
        } if result.factors else {},
    }


def _signal_to_dict(signal: SignalDetail) -> Dict[str, Any]:
    return {
        "category": signal.category,
        "name": signal.name,
        "weight": signal.weight,
        "matched": signal.matched,
    }


def _context_to_dict(ctx: Optional[DetectContext]) -> Dict[str, Any]:
    if ctx is None:
        return {}
    return {
        "is_reply": ctx.is_reply,
        "has_mention": ctx.has_mention,
        "recent_keywords": ctx.recent_keywords,
        "sender_name": ctx.sender_name,
        "message_index": ctx.message_index,
    }