"""Tests for ConversationFileBridge and keyword extraction."""
import time

from src.detect.conv_file_bridge import (
    ConversationFileBridge,
    ConvFileBridgeLevel,
    extract_conversation_keywords,
)
from src.detect.types import SignalContext, SignalStrength, StateChangeSignal
from src.extractors.project_types import ProjectFileChange


def test_level_0_separate():
    """Level 0: no linking whatsoever."""
    bridge = ConversationFileBridge(ConvFileBridgeLevel.SEPARATE)
    changes = [
        ProjectFileChange(file_path="src/app.py", change_type="modified", content_hash="abc")
    ]
    ctx = bridge.assemble_context(None, changes)
    assert ctx.has_changes
    assert len(ctx.linked_conversation_snippets) == 0


def test_level_1_keyword_bridge():
    """Level 1: file path keyword matches conversation keyword."""
    bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD)
    bridge.feed_keywords(["migration", "database"])
    changes = [
        ProjectFileChange(file_path="migrations/001_users.sql", change_type="created", content_hash="def"),
    ]
    ctx = bridge.assemble_context(None, changes)
    assert ctx.has_changes
    assert len(ctx.linked_conversation_snippets) >= 1


def test_level_1_no_match():
    """Level 1: no keyword overlap → no linking."""
    bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD)
    bridge.feed_keywords(["frontend", "ui"])
    changes = [
        ProjectFileChange(file_path="api/handler.py", change_type="modified", content_hash="ghi"),
    ]
    ctx = bridge.assemble_context(None, changes)
    assert ctx.has_changes
    assert len(ctx.linked_conversation_snippets) == 0


def test_level_3_always_merge():
    """Level 3: always include conversation snippets."""
    bridge = ConversationFileBridge(ConvFileBridgeLevel.ALWAYS_MERGE)
    signal = StateChangeSignal(
        strength=SignalStrength.MEDIUM,
        context=SignalContext(
            content_snippet="Let's refactor the auth module",
            keywords=["refactor", "auth"],
        ),
    )
    ctx = bridge.assemble_context(signal, [])
    assert len(ctx.linked_conversation_snippets) >= 1


def test_keyword_extraction():
    """Extract code-related keywords from conversation text."""
    text = "We need a migration plan for PostgreSQL and refactor the API"
    kw = extract_conversation_keywords(text)
    assert "migration" in kw
    assert "refactor" in kw


def test_bridge_stats():
    """Bridge stats are always available."""
    bridge = ConversationFileBridge()
    stats = bridge.get_bridge_stats()
    assert stats["level"] == "keyword"
    assert stats["keyword_buffer_size"] >= 0


def test_keyword_feed_limit():
    """Keyword buffer respects the window size."""
    bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD, keyword_window=3)
    bridge.feed_keywords(["a", "b", "c", "d", "e"])  # Should only keep last 3
    assert len(bridge._recent_keywords) == 3
    assert bridge._recent_keywords == ["c", "d", "e"]