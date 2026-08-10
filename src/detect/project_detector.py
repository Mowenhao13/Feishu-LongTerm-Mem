"""ProjectDetector — project codebase change detection integration layer.

Integrates ProjectWatcher (watchdog + MemoStore) with ConversationFileBridge
and the existing pipeline. Provides a detect() API that mirrors the existing
DocDetector pattern for consistency.

Data flow:
  1. ProjectWatcher.poll() → raw ProjectFileChange events
  2. ConversationFileBridge.assemble_context() → ProjectDevelopmentContext
  3. ProjectDetector returns ProjectDetectResult to MemoryEngine

Usage:
    detector = ProjectDetector("/path/to/project")
    await detector.start()
    result = await detector.detect()
    if result.has_changes:
        # process result.changes
    await detector.stop()
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from src.detect.conv_file_bridge import ConversationFileBridge, ConvFileBridgeLevel
from src.detect.project_watcher import ProjectWatcher
from src.extractors.project_types import (
    ProjectDetectResult,
    ProjectDevelopmentContext,
    ProjectFileChange,
    ProjectSnapshot,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ProjectDetector:
    """Project development change detector.

    Integrates ProjectWatcher with ConversationFileBridge to provide
    a unified detect() API for the MemoryEngine.

    This is the top-level class that the MemoryEngine interacts with.
    It manages the lifecycle of:
    - ProjectWatcher (watchdog + MemoStore)
    - ConversationFileBridge (keyword/temporal context merging)

    Args:
        project_dir: Absolute path to the project to watch.
        bridge: ConversationFileBridge instance for context merging.
            If None, creates one with KEYWORD default level.
        watcher_debounce: Debounce seconds for file events.
        snapshot_interval: Number of detect cycles between snapshots.
            None = no automatic snapshots.
    """

    def __init__(
        self,
        project_dir: str,
        bridge: Optional[ConversationFileBridge] = None,
        watcher_debounce: float = 2.0,
        snapshot_interval: Optional[int] = 10,
    ):
        self._watcher = ProjectWatcher(
            project_dir=project_dir,
            debounce_seconds=watcher_debounce,
        )
        self._bridge = bridge or ConversationFileBridge(
            level=ConvFileBridgeLevel.KEYWORD,
        )
        self._snapshot_interval = snapshot_interval
        self._detect_cycle = 0
        self._last_snapshot: Optional[ProjectSnapshot] = None

    @property
    def name(self) -> str:
        return "project_codebase"

    @property
    def watcher(self) -> ProjectWatcher:
        return self._watcher

    @property
    def bridge(self) -> ConversationFileBridge:
        return self._bridge

    async def start(self) -> None:
        """Start the watcher and prepare for detection."""
        await self._watcher.start()
        logger.info("ProjectDetector started (dir=%s)", self._watcher.project_dir)

    async def stop(self) -> None:
        """Stop the watcher."""
        await self._watcher.stop()
        logger.info("ProjectDetector stopped")

    async def detect(self) -> ProjectDetectResult:
        """Run a detection cycle.

        1. Poll ProjectWatcher for file changes
        2. Feed changes to ConversationFileBridge
        3. Take periodic snapshot if configured
        4. Return ProjectDetectResult

        Returns:
            ProjectDetectResult with any detected changes and optional snapshot.
        """
        self._detect_cycle += 1
        now = time.time()

        # Step 1: Poll for file changes
        changes = await self._watcher.poll()

        # Step 2: Feed to bridge for keyword accumulation
        if changes:
            self._bridge.feed_file_changes(changes)

        # Step 3: Take periodic snapshot
        snapshot = None
        if self._snapshot_interval and self._detect_cycle % self._snapshot_interval == 0:
            try:
                snapshot = await self._watcher.take_snapshot()
                self._last_snapshot = snapshot
                if snapshot.total_files > 0:
                    logger.debug(
                        "Snapshot: %d files, %d types",
                        snapshot.total_files,
                        len(snapshot.file_type_counts),
                    )
            except Exception as e:
                logger.warning("Snapshot failed: %s", e)
        else:
            snapshot = self._last_snapshot

        # Step 4: Build result
        return ProjectDetectResult(
            has_changes=len(changes) > 0,
            source=self.name,
            detected_at=now,
            changes=changes,
            snapshot=snapshot,
        )

    def build_development_context(
        self,
        changes: Optional[List[ProjectFileChange]] = None,
        conv_signal: Any = None,
    ) -> ProjectDevelopmentContext:
        """Build ProjectDevelopmentContext from changes + conversation signal.

        Uses the ConversationFileBridge to determine whether and how to
        merge conversation context with file changes.

        Args:
            changes: File changes to include. If None, uses the bridge buffer.
            conv_signal: Optional conversation signal for context merging.

        Returns:
            ProjectDevelopmentContext ready for LLM prompt injection.
        """
        file_changes = changes if changes is not None else self._bridge._recent_file_changes
        return self._bridge.assemble_context(
            conv_signal=conv_signal,
            file_changes=file_changes,
        )

    def get_bridge_stats(self) -> Dict[str, Any]:
        """Get current bridge statistics."""
        return self._bridge.get_bridge_stats()