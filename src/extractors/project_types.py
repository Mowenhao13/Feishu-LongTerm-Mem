"""Project development context types.

Data types for tracking and representing project-level codebase changes.
Complement existing memory_types.py (extracted entities/relationships/facts)
with project development-specific types.

Key types:
- ProjectFileChange: A single file change event from watchdog + MemoStore
- ProjectSnapshot: Periodic project state for structural delta detection
- ProjectDevelopmentContext: Aggregated context for LLM prompt injection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FileChangeType(str, Enum):
    """Type of file system change detected."""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class ProjectFileChange:
    """A single file change event detected in the project codebase.

    Attributes:
        file_path: Path relative to the project root directory.
        change_type: CREATED, MODIFIED, or DELETED
        content_hash: SHA256[:16] of current file content (empty if deleted).
        prev_content_hash: SHA256[:16] of previous content (empty if created).
        extension: File extension (lowercase, e.g. ".py", ".md").
        language: Inferred programming language (e.g. "Python", "Markdown").
        diff_summary: Short diff summary (first 200 chars of diff, or empty for
            binary/deleted files).
        timestamp: Unix timestamp of the detected change.
        size_bytes: File size in bytes (0 if deleted).
    """
    file_path: str
    change_type: str  # "created" | "modified" | "deleted"
    content_hash: str = ""
    prev_content_hash: str = ""
    extension: str = ""
    language: str = ""
    diff_summary: str = ""
    timestamp: float = 0.0
    size_bytes: int = 0

    @property
    def is_binary(self) -> bool:
        """Check if the file extension suggests a binary file."""
        binary_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
            ".woff", ".woff2", ".ttf", ".eot",
            ".o", ".so", ".dylib", ".exe", ".dll",
            ".pyc", ".pyo", ".pyd",
            ".zip", ".tar", ".gz", ".bz2", ".7z",
            ".db", ".sqlite", ".db3",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
            ".mp3", ".mp4", ".avi", ".mov",
            ".ttf", ".otf",
            ".DS_Store",
        }
        return self.extension.lower() in binary_extensions

    @property
    def is_significant(self) -> bool:
        """Check if change is worth LLM attention (non-binary, non-trivial content).

        A change is significant if:
        - File was deleted, OR
        - File is non-binary AND has meaningful content (content_hash is non-empty
          and size_bytes > 10)
        """
        if self.change_type == "deleted":
            return True
        if self.is_binary:
            return False
        return bool(self.content_hash) and self.size_bytes > 10


@dataclass
class ProjectSnapshot:
    """Periodic snapshot of the project state.

    Captures aggregate structural information (not full file contents).
    Used to detect structural changes like new/deleted directories,
    dependency additions, file type distribution shifts.

    Attributes:
        total_files: Number of files being tracked.
        total_size_bytes: Total size of tracked files.
        file_type_counts: Extension → count mapping.
        recent_files: 10 most recently modified files.
        imports: Set of import statements found (top-level only).
        detected_at: Unix timestamp of snapshot creation.
    """
    total_files: int = 0
    total_size_bytes: int = 0
    file_type_counts: Dict[str, int] = field(default_factory=dict)
    recent_files: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    detected_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_size_bytes": self.total_size_bytes,
            "file_type_counts": self.file_type_counts,
            "recent_files": self.recent_files[:10],
            "imports": self.imports[:20],
            "detected_at": self.detected_at,
        }


@dataclass
class ProjectDevelopmentContext:
    """Aggregated project development context for LLM prompt injection.

    This is the final "context packet" that gets assembled and injected
    into the LLM alongside conversation context (if the conv-file bridge
    decides to merge them).

    Attributes:
        recent_changes: Recent file changes (ordered by timestamp, newest first).
        snapshot: Latest project snapshot (if available).
        linked_conversation_snippets: Conversation snippets that the bridge
            linked to these file changes (Level 1+ only).
        summary: LLM-generated or auto-summary of recent development activity
            (empty if not yet computed).
        detected_at: Unix timestamp of context assembly.
    """
    recent_changes: List[ProjectFileChange] = field(default_factory=list)
    snapshot: Optional[ProjectSnapshot] = None
    linked_conversation_snippets: List[str] = field(default_factory=list)
    summary: str = ""
    detected_at: float = 0.0

    @property
    def has_changes(self) -> bool:
        return len(self.recent_changes) > 0

    @property
    def significant_changes(self) -> List[ProjectFileChange]:
        """Return only changes that pass the significance filter."""
        return [c for c in self.recent_changes if c.is_significant]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_count": len(self.recent_changes),
            "significant_count": len(self.significant_changes),
            "has_snapshot": self.snapshot is not None,
            "linked_snippets": len(self.linked_conversation_snippets),
            "summary": self.summary[:200] if self.summary else "",
            "detected_at": self.detected_at,
        }


@dataclass
class ProjectDetectResult:
    """Result from a single ProjectDetector.detect() call.

    Mirrors DocDetectResult from doc_adapter.py pattern.
    """
    has_changes: bool = False
    source: str = "project"
    detected_at: float = 0.0
    changes: List[ProjectFileChange] = field(default_factory=list)
    snapshot: Optional[ProjectSnapshot] = None

    @property
    def significant_count(self) -> int:
        return sum(1 for c in self.changes if c.is_significant)