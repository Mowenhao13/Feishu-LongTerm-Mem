"""Conversation-File Dependency Bridge

Strategically handles the mutual dependency between conversation context
and project file changes when building LLM inputs.

Four levels of dependency (configurable):

Level 0 (SEPARATE):
  - Conversation processed independently of file changes.
  - File changes stored in a separate timeline.
  - No cross-referencing in LLM context at all.
  - Use case: Code formatting only, no meaningful decisions.

Level 1 (KEYWORD) — DEFAULT:
  - File changes that share keywords with recent conversation topics
    are linked together.
  - e.g., conversation says "PostgreSQL migration" → file change in
    `migrations/` is linked.
  - Use case: Default behavior. Catches obvious connections, low noise.

Level 2 (RECENT_MERGE):
  - If file changes occur within a temporal window of a matching
    conversation topic, both are merged for the next LLM query.
  - Uses topic_id overlap + temporal proximity (configurable window).
  - Use case: Active development where conversation and coding interleave.

Level 3 (ALWAYS_MERGE):
  - Every LLM input includes BOTH conversation context AND recent file
    changes.
  - Token-budget aware: truncates if exceeded.
  - Use case: Debugging, comprehensive analysis, small codebases.

Usage:
    bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD)
    ctx = await bridge.assemble_context(
        conv_signal=signal,
        file_changes=[...],
        recent_keywords=["PostgreSQL", "migration"],
    )
"""

from __future__ import annotations

import re
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from src.detect.types import SignalStrength, StateChangeSignal
from src.extractors.project_types import (
    FileChangeType,
    ProjectDevelopmentContext,
    ProjectFileChange,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConvFileBridgeLevel(str, Enum):
    """Conversation-file dependency strategy levels.

    Higher levels = more context merging, more token usage.
    """
    SEPARATE = "separate"       # Level 0: no linking whatsoever
    KEYWORD = "keyword"          # Level 1: keyword overlap linking
    RECENT_MERGE = "recent"      # Level 2: temporal + topic merge
    ALWAYS_MERGE = "always"      # Level 3: always combined


# Common code-related keywords that help bridge conversation → files
CODE_KEYWORDS: Set[str] = {
    "refactor", "migration", "bump", "upgrade", "downgrade", "deprecate",
    "optimize", "rewrite", "revert", "merge", "deploy", "release",
    "import", "export", "config", "configure", "setup", "install",
    "database", "schema", "table", "query", "index", "cache",
    "api", "endpoint", "route", "middleware", "lambda", "function",
    "class", "module", "package", "library", "framework", "tool",
    "test", "mock", "assert", "coverage", "ci", "cd",
    "docker", "container", "k8s", "kubernetes", "deployment",
    "auth", "auth", "login", "permission", "role",
    "error", "bug", "fix", "hotfix", "patch",
    "pr", "pull request", "review", "lgtm", "approve",
}


class ConversationFileBridge:
    """Bridges conversation context with project file changes.

    The bridge decides whether, and how, to merge file change context
    with conversation context for LLM input.

    Design rationale:
    - SEPARATE (L0): File changes are purely mechanical (formatting, linting).
      No LLM value in linking them.
    - KEYWORD (L1): The conversation mentions specific technology/framework.
      The file change is in that framework's config. Obvious link.
    - RECENT_MERGE (L2): You were discussing database schema. Then you edited
      migration files. The bridge merges both contexts because they're likely
      related.
    - ALWAYS_MERGE (L3): Full context for comprehensive analysis. Suitable
      when changes are small, or when debugging requires seeing everything.
    """

    def __init__(
        self,
        level: ConvFileBridgeLevel = ConvFileBridgeLevel.KEYWORD,
        keyword_window: int = 10,       # Keep last N conversation keywords
        temporal_window: float = 300.0,  # 5 minutes for "recent" context
        max_linked_snippets: int = 5,   # Max linked conversation snippets
    ):
        self._level = level
        self._keyword_window = keyword_window
        self._temporal_window = temporal_window
        self._max_linked_snippets = max_linked_snippets

        # Rolling buffers
        self._recent_keywords: List[str] = []
        self._recent_file_changes: List[ProjectFileChange] = []
        self._max_file_changes: int = 20

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    @property
    def level(self) -> ConvFileBridgeLevel:
        return self._level

    def set_level(self, level: ConvFileBridgeLevel) -> None:
        """Change the bridge level at runtime."""
        old = self._level
        self._level = level
        logger.info("ConvFileBridge: level changed %s -> %s", old.value, level.value)

    def feed_keywords(self, keywords: List[str]) -> None:
        """Feed keywords from a processed conversation episode.

        Called after each conversation episode is processed, so the bridge
        can build up a keyword profile of what the team is discussing.
        """
        self._recent_keywords.extend(keywords)
        self._recent_keywords = self._recent_keywords[-self._keyword_window:]
        logger.debug("ConvFileBridge: keywords buffer updated (%d items)", len(self._recent_keywords))

    def feed_file_changes(self, changes: List[ProjectFileChange]) -> None:
        """Feed file changes for bridging."""
        self._recent_file_changes.extend(changes)
        # Keep only the most recent N
        self._recent_file_changes = self._recent_file_changes[-self._max_file_changes:]

    def assemble_context(
        self,
        conv_signal: Optional[StateChangeSignal],
        file_changes: List[ProjectFileChange],
    ) -> ProjectDevelopmentContext:
        """Assemble project development context with optional conversation linking.

        Args:
            conv_signal: The current conversation signal (if any).
            file_changes: File changes detected in the current cycle.

        Returns:
            ProjectDevelopmentContext with linked snippets if the bridge
            determined a merge is appropriate.
        """
        now = time.time()
        ctx = ProjectDevelopmentContext(
            recent_changes=file_changes,
            detected_at=now,
        )

        if self._level == ConvFileBridgeLevel.SEPARATE:
            # Level 0: No linking at all
            return ctx

        if self._level == ConvFileBridgeLevel.ALWAYS_MERGE:
            # Level 3: Always include conversation keywords
            if conv_signal:
                ctx.linked_conversation_snippets = self._build_snippets(conv_signal)
            return ctx

        if self._level == ConvFileBridgeLevel.KEYWORD:
            if not file_changes or not self._recent_keywords:
                return ctx
            linked = self._find_keyword_bridges(
                file_changes,
                self._recent_keywords,
            )
            if linked:
                ctx.linked_conversation_snippets = [
                    f"Related keywords: {', '.join(kw for _, _, kw in linked[:self._max_linked_snippets])}"
                ]
            return ctx

        if self._level == ConvFileBridgeLevel.RECENT_MERGE:
            if not file_changes:
                return ctx

            # Check temporal proximity
            now = time.time()
            recent_changes = [
                c for c in file_changes
                if now - c.timestamp < self._temporal_window
            ]
            if not recent_changes:
                return ctx

            # Check keyword overlap with recent changes
            if self._recent_keywords:
                linked = self._find_keyword_bridges(
                    recent_changes,
                    self._recent_keywords,
                )
                if linked:
                    ctx.linked_conversation_snippets = [
                        f"[Recent merge] Keywords: {', '.join(kw for _, _, kw in linked[:self._max_linked_snippets])})"
                    ]
                else:
                    # No keyword overlap, but within temporal window
                    ctx.linked_conversation_snippets = [
                        f"[Recent merge] {len(recent_changes)} recent file changes near conversation"
                    ]
            else:
                ctx.linked_conversation_snippets = [
                    f"[Recent merge] {len(recent_changes)} recent file changes"
                ]

            return ctx

        return ctx

    # ─────────────────────────────────────────────
    # Keyword bridging logic (Level 1)
    # ─────────────────────────────────────────────

    def _find_keyword_bridges(
        self,
        file_changes: List[ProjectFileChange],
        keywords: List[str],
    ) -> List[tuple[ProjectFileChange, str, str]]:
        """Find keyword bridges between file changes and conversation keywords.

        A "bridge" exists when a file path or its content-related metadata
        contains a keyword that also appears in the conversation keyword buffer.

        Returns:
            List of (file_change, matched_keyword, bridge_type) tuples.
        """
        if not keywords:
            return []

        bridges: List[tuple[ProjectFileChange, str, str]] = []
        lower_keywords = [kw.lower() for kw in keywords]

        for change in file_changes:
            path_lower = change.file_path.lower()

            for kw in lower_keywords:
                if not kw:
                    continue

                # Check file path
                if kw in path_lower:
                    bridges.append((change, kw, "file_path"))
                    break

                # Check language match (e.g., "Python" ↔ ".py")
                if change.language and kw.lower() == change.language.lower():
                    bridges.append((change, kw, "language"))
                    break

                # Check diff summary
                if change.diff_summary and kw in change.diff_summary.lower():
                    bridges.append((change, kw, "diff_summary"))
                    break

        return bridges

    # ─────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────

    def _build_snippets(self, signal: StateChangeSignal) -> List[str]:
        """Build conversation snippets from a signal for always-merge mode."""
        snippets: List[str] = []
        if signal.context.content_snippet:
            snippets.append(signal.context.content_snippet[:200])
        if signal.context.keywords:
            snippets.append(f"Keywords: {', '.join(signal.context.keywords)}")
        return snippets

    def get_bridge_stats(self) -> Dict[str, Any]:
        """Get statistics about the bridge state."""
        return {
            "level": self._level.value,
            "keyword_buffer_size": len(self._recent_keywords),
            "file_change_buffer_size": len(self._recent_file_changes),
            "temporal_window_seconds": self._temporal_window,
        }


def extract_conversation_keywords(text: str) -> List[str]:
    """Extract code/tech keywords from a conversation text.

    Finds words that look like technology names, programming languages,
    frameworks, or common development terms.

    Args:
        text: Conversation text to extract keywords from.

    Returns:
        List of extracted keywords (lowercase, deduplicated).
    """
    if not text:
        return []

    found: List[str] = []
    lower = text.lower()

    # Check for known code keywords (stem-friendly: check substring)
    for kw in CODE_KEYWORDS:
        if kw in lower:
            found.append(kw)

    # Check for PascalCase (likely project names, class names)
    # and technical terms
    words = re.findall(r"[A-Z][a-z]+[A-Z]\w*|`[^`]+`|\b\w+[-_]\w+\b", text)
    for word in words:
        cleaned = word.strip("`").strip()
        if cleaned and len(cleaned) > 2:
            found.append(cleaned)

    return list(set(found))[:15]  # Dedup and limit