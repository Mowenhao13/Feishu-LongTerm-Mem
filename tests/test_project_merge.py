"""Integration tests for the conversation-file merge pipeline.

Tests the full flow:
1. ProjectDetector detects file changes
2. ConversationFileBridge decides to merge based on level
3. ProjectDevelopmentContext is passed to extract_with_context()
4. Prompt includes project context preamble

These tests verify the wiring between components, not the LLM output
(which requires real LLM calls).
"""
import asyncio
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.detect.project_detector import ProjectDetector
from src.detect.conv_file_bridge import ConversationFileBridge, ConvFileBridgeLevel
from src.extractors.project_types import ProjectFileChange, ProjectDevelopmentContext
from src.extractors.project_context_prompt import (
    PROJECT_CONTEXT_PROMPT,
    format_file_changes_for_prompt,
)


def test_project_context_prompt_injection():
    """Verify project context is injectable into a prompt string."""
    changes = [
        ProjectFileChange(
            file_path="src/main.py",
            change_type="modified",
            content_hash="abc",
            extension=".py",
            language="Python",
            diff_summary="+3 lines; -1 lines",
            timestamp=time.time(),
            size_bytes=100,
        ),
    ]
    formatted = format_file_changes_for_prompt(changes)
    assert "src/main.py" in formatted
    assert "+3 lines" in formatted

    full_prompt = PROJECT_CONTEXT_PROMPT.format(file_changes_text=formatted)
    assert "src/main.py" in full_prompt
    assert "modified" in full_prompt


def test_project_context_empty_changes():
    """Verify format with no changes."""
    formatted = format_file_changes_for_prompt([])
    assert "无文件变更" in formatted or not formatted


def test_project_context_max_changes():
    """Verify max_changes limit works."""
    changes = [
        ProjectFileChange(
            file_path=f"file_{i}.py",
            change_type="modified",
            content_hash=f"hash_{i}",
            extension=".py",
            language="Python",
            timestamp=time.time() + i,
            size_bytes=100,
        )
        for i in range(20)
    ]
    formatted = format_file_changes_for_prompt(changes, max_changes=5)
    # Should only include 5 entries (newest first)
    assert "file_19" in formatted  # Newest (highest index)
    # Count the file path occurrences
    count = formatted.count("file_")
    assert count <= 5, f"Expected max 5 files, got {count}"


def test_project_context_prompt_with_types():
    """Verify ProjectFileChange types work with the prompt formatter."""
    changes = [
        ProjectFileChange(
            file_path="new.py",
            change_type="created",
            content_hash="abc",
            extension=".py",
            language="Python",
            diff_summary="+50 lines",
            timestamp=time.time(),
            size_bytes=500,
        ),
        ProjectFileChange(
            file_path="old.py",
            change_type="deleted",
            content_hash="",
            extension=".py",
            language="Python",
            timestamp=time.time(),
            size_bytes=0,
        ),
    ]
    formatted = format_file_changes_for_prompt(changes)
    assert "created" in formatted
    assert "deleted" in formatted
    assert "old.py" in formatted


def test_extract_with_context_signature():
    """Verify extract_with_context accepts project_context."""
    from src.extractors.simple_llm_extractor import SimpleLLMExtractor
    import inspect

    sig = inspect.signature(SimpleLLMExtractor.extract_with_context)
    assert "project_context" in sig.parameters, "Missing project_context parameter"


def test_engine_has_merge_logic():
    """Verify _process_episode_v2 references project_ctx."""
    from src.core.engine import MemoryEngine
    import inspect

    src = inspect.getsource(MemoryEngine._process_episode_v2)
    assert "project_ctx" in src, "_process_episode_v2 missing project_ctx logic"
    assert "project_context=project_ctx" in src, "project_context not wired to extract_with_context"


# ── Async tests (watchdog-based) ──


def test_detector_with_bridge_merge():
    """ProjectDetector + bridge: file change feeds into bridge keywords."""
    async def run():
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD)
            detector = ProjectDetector(tmpdir, bridge=bridge, watcher_debounce=0.5)
            await detector.start()

            # Feed conversation keywords
            bridge.feed_keywords(["database", "migration"])

            # Create a matching file
            (Path(tmpdir) / "migrations" / "add_table.sql").parent.mkdir()
            (Path(tmpdir) / "migrations" / "add_table.sql").write_text("CREATE TABLE test;")
            await asyncio.sleep(0.8)

            result = await detector.detect()
            # Bridge should have received these changes
            stats = bridge.get_bridge_stats()
            assert stats["keyword_buffer_size"] >= 2

            # Build development context
            ctx = detector.build_development_context(
                changes=result.changes,
                conv_signal=None,
            )
            assert ctx.has_changes

            # The bridge should link the file path containing "migration"
            ctx2 = bridge.assemble_context(None, result.changes)
            assert ctx2.has_changes, "Bridge should have changes"

            # Format for prompt injection — verify the full flow
            from src.extractors.project_context_prompt import format_file_changes_for_prompt
            formatted = format_file_changes_for_prompt(result.changes)
            assert formatted, "Changes should be formattable"

            await detector.stop()

    asyncio.run(run())