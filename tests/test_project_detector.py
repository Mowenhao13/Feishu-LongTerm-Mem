"""Tests for ProjectDetector integration layer."""
import asyncio
import tempfile
from pathlib import Path

from src.detect.project_detector import ProjectDetector


def test_detect_empty():
    """Detect returns no changes when nothing happened."""
    async def run():
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = ProjectDetector(tmpdir, watcher_debounce=0.5)
            await detector.start()
            await asyncio.sleep(0.3)

            result = await detector.detect()
            assert result.source == "project_codebase"
            assert not result.has_changes

            await detector.stop()
    asyncio.run(run())


def test_detect_file_create():
    """Detect returns change when a file is created."""
    async def run():
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = ProjectDetector(tmpdir, watcher_debounce=0.5)
            await detector.start()
            await asyncio.sleep(0.3)

            Path(tmpdir, "hello.py").write_text("print('hello')")
            await asyncio.sleep(0.8)

            result = await detector.detect()
            assert result.has_changes
            assert len(result.changes) == 1
            assert result.changes[0].file_path == "hello.py"
            assert result.changes[0].change_type == "created"
            assert result.changes[0].language == "Python"

            await detector.stop()

    asyncio.run(run())


def test_detect_no_duplicate():
    """Detect returns same content only once (MemoStore dedup)."""
    async def run():
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = ProjectDetector(tmpdir, watcher_debounce=0.5)
            await detector.start()
            await asyncio.sleep(0.3)

            f = Path(tmpdir, "test.py")
            f.write_text("same content")
            await asyncio.sleep(0.8)

            result1 = await detector.detect()
            assert result1.has_changes

            # Write same content again — should be deduplicated
            f.write_text("same content")
            await asyncio.sleep(0.8)

            result2 = await detector.detect()
            assert not result2.has_changes  # MemoStore hit!

            await detector.stop()

    asyncio.run(run())


def test_name_property():
    """Detector name is always project_codebase."""
    with tempfile.TemporaryDirectory() as tmpdir:
        detector = ProjectDetector(tmpdir)
        assert detector.name == "project_codebase"


def test_bridge_stats():
    """Bridge stats are available after initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        detector = ProjectDetector(tmpdir)
        stats = detector.get_bridge_stats()
        assert stats["level"] == "keyword"