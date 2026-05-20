"""
Git-based storage backend for decision persistence.

Provides version-controlled storage using Git as the backend,
enabling history tracking, branching, and collaboration.
"""
from .git_cli import GitCLI, CommitLogEntry, BlameEntry, SearchHit
from .git_format import (
    parse_decision_file,
    parse_objection_file,
    render_decision_file,
    render_objection_file,
    format_decision_summary,
)
from .git_storage import GitStorage, GitStorageConfig

__all__ = [
    "GitCLI",
    "CommitLogEntry",
    "BlameEntry",
    "SearchHit",
    "render_decision_file",
    "parse_decision_file",
    "render_objection_file",
    "parse_objection_file",
    "format_decision_summary",
    "GitStorage",
    "GitStorageConfig",
]