"""Project file system watcher — watchdog + MemoStore incremental change detection.

Monitors a local project directory using watchdog.Observer for real-time
file system events, and uses MemoStore (content-addressed memoization) to
detect when file content actually changed (not just metadata events).

Data flow:
  1. watchdog.Observer receives filesystem events (create/modify/delete)
  2. ProjectFileHandler debounces and enqueues events into asyncio.Queue
  3. poll() drains the queue, reads file content, computes content hash
  4. MemoStore.lookup() checks if this content has been processed before
  5. Cache MISS → produce ProjectFileChange, store new hash in MemoStore
  6. Cache HIT  → skip (content hasn't changed since last detection)

Design rationale (cocoindex-style):
  - watchdog handles "WHAT file changed" (filesystem events)
  - MemoStore handles "WHETHER the INPUT content changed" (content hashing)
  - Together they provide incremental detection without polling
  - No git diff needed — pure content-addressed memoization

Usage:
    watcher = ProjectWatcher("/path/to/project", memo_store=memo)
    await watcher.start()
    try:
        while True:
            changes = await watcher.poll()
            if changes:
                process(changes)
            await asyncio.sleep(0.5)
    finally:
        await watcher.stop()
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from src.core.memo import (
    MemoKey,
    MemoStore,
    compute_code_fingerprint,
    compute_content_hash,
)
from src.extractors.project_types import (
    FileChangeType,
    ProjectFileChange,
    ProjectSnapshot,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default set of file extensions to watch
DEFAULT_EXTENSIONS: Tuple[str, ...] = (
    ".py", ".md", ".toml", ".yaml", ".yml", ".json", ".cfg",
    ".ini", ".env", ".go", ".rs", ".ts", ".js", ".tsx", ".jsx",
    ".css", ".scss", ".html", ".sh", ".zsh", ".bash",
    ".sql", ".graphql", ".proto", ".gradle", ".kt",
    ".rb", ".php", ".java", ".c", ".cpp", ".h", ".hpp",
)

# Directories to always ignore (regardless of .gitignore)
ALWAYS_IGNORE_DIRS: Tuple[str, ...] = (
    ".git", "__pycache__", ".venv", "venv", ".tox",
    "node_modules", ".next", "dist", "build", ".build",
    ".egg-info", ".mypy_cache", ".pytest_cache",
    ".claude", ".cursor", ".idea", ".vscode",
)

BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".o", ".so", ".dylib", ".exe", ".dll",
    ".pyc", ".pyo", ".pyd",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".db", ".sqlite", ".db3",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp3", ".mp4", ".avi", ".mov",
    ".DS_Store",
}

LANGUAGE_MAP: Dict[str, str] = {
    ".py": "Python",
    ".md": "Markdown",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".cfg": "Config",
    ".ini": "Config",
    ".env": "Environment",
    ".go": "Go",
    ".rs": "Rust",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".js": "JavaScript",
    ".jsx": "JavaScript React",
    ".css": "CSS",
    ".scss": "SCSS",
    ".html": "HTML",
    ".sql": "SQL",
    ".sh": "Shell",
    ".zsh": "Shell",
    ".bash": "Shell",
    ".gradle": "Gradle",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C Header",
    ".hpp": "C++ Header",
    ".proto": "Protobuf",
    ".graphql": "GraphQL",
}


def _infer_language(extension: str) -> str:
    """Infer programming language from file extension."""
    return LANGUAGE_MAP.get(extension.lower(), "")


def _is_binary_by_ext(extension: str) -> bool:
    """Check if extension is known as binary."""
    return extension.lower() in BINARY_EXTENSIONS


class ProjectFileHandler(FileSystemEventHandler):
    """Watchdog event handler for project files.

    Pattern mirrors DocFileHandler from watchdog_detector.py:
    - Debounce: prevents duplicate events for the same file within a window
    - Thread-safe bridging: watchdog runs on its own thread, events are bridged
      to asyncio via run_coroutine_threadsafe
    - Extension filtering: only watches configured file extensions
    - Ignore filtering: skips known noise dirs and files
    """

    def __init__(
        self,
        debounce_seconds: float = 2.0,
        extensions: Optional[Tuple[str, ...]] = None,
        ignore_dirs: Optional[Tuple[str, ...]] = None,
    ):
        super().__init__()
        self._debounce_seconds = debounce_seconds
        self._extensions = extensions or DEFAULT_EXTENSIONS
        self._ignore_dirs = ignore_dirs or ALWAYS_IGNORE_DIRS

        # Debounce state: path -> last_event_time
        self._pending: Dict[str, float] = {}
        self._lock = threading.Lock()

        # Async event queue: (path, event_type)
        # NOTE: Must be created inside a running event loop, or _loop is None.
        # store the loop reference explicitly.
        self._events: asyncio.Queue[Tuple[str, str]] = asyncio.Queue()
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory and self._should_watch(event.src_path):
            self._enqueue(event.src_path, FileChangeType.MODIFIED.value)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory and self._should_watch(event.src_path):
            self._enqueue(event.src_path, FileChangeType.CREATED.value)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if not event.is_directory and self._should_watch(event.src_path):
            self._enqueue(event.src_path, FileChangeType.DELETED.value)

    def _should_watch(self, path: str) -> bool:
        """Check if the path should be watched.

        Returns True if:
        - Extension is in the watch list
        - Path is not in an ignored directory
        - Extension is not binary
        """
        ext = os.path.splitext(path)[1].lower()
        if not ext or ext not in self._extensions:
            return False
        if _is_binary_by_ext(ext):
            return False
        # Check if path is inside an ignored directory
        for part in Path(path).parts:
            if part in self._ignore_dirs:
                return False
        return True

    def _enqueue(self, path: str, event_type: str) -> None:
        """Debounce and enqueue an event.

        If the same path was queued within the debounce window, it's ignored.
        Events are bridged from watchdog's thread to the asyncio main loop.
        """
        now = time.time()
        with self._lock:
            last_time = self._pending.get(path, 0.0)
            if now - last_time < self._debounce_seconds:
                return  # Still in debounce window, skip
            self._pending[path] = now

        # Bridge from watchdog thread to asyncio main loop
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._events.put((path, event_type)),
                self._loop,
            )

    async def drain(self) -> List[Tuple[str, str]]:
        """Drain all pending events from the queue.

        Returns deduplicated list of (path, event_type) — if the same path
        appears multiple times, the last event type wins.
        """
        events: List[Tuple[str, str]] = []
        while not self._events.empty():
            try:
                item = self._events.get_nowait()
                events.append(item)
            except asyncio.QueueEmpty:
                break

        # Deduplicate: same path → keep last event type
        if len(events) > 1:
            seen: Dict[str, str] = {}
            for path, etype in events:
                seen[path] = etype
            events = list(seen.items())

        return events

    def cleanup_pending(self, path: str) -> None:
        """Remove debounce state for a path after processing."""
        with self._lock:
            self._pending.pop(path, None)


class ProjectWatcher:
    """Watchdog + MemoStore project file watcher.

    Monitors a project directory for real-time file changes using watchdog,
    then uses MemoStore (content-addressed memoization) to filter out
    spurious events where the file content hasn't actually changed.

    This is the "incremental change detection" layer — it ensures that
    only meaningful content changes produce ProjectFileChange events.

    Args:
        project_dir: Absolute path to the project directory to watch.
        memo_store: MemoStore instance for content-addressed caching.
            If None, creates one with a default storage dir outside the
            watched project dir to avoid recursive detection.
        extensions: Tuple of file extensions to watch. Default: source code.
        debounce_seconds: Debounce window for duplicate file events.
        enable_diff_summary: Whether to compute basic diff summaries
            (only the first 200 chars, for LLM context).
    """

    def __init__(
        self,
        project_dir: str,
        memo_store: Optional[MemoStore] = None,
        extensions: Optional[Tuple[str, ...]] = None,
        debounce_seconds: float = 2.0,
        enable_diff_summary: bool = True,
    ):
        # Resolve project dir to real path to handle macOS /var -> /private/var symlinks
        self._project_dir = os.path.realpath(os.path.abspath(project_dir))

        # MemoStore for content-addressed caching.
        # Store MemoStore data OUTSIDE the watched dir to avoid recursive detection
        # of the memo_store.json file's own writes.
        if memo_store is not None:
            self._memo_store = memo_store
        else:
            # Use a stable path outside the project dir
            memo_dir = os.path.join(
                os.path.expanduser("~"), ".feishu-mem", "project_watcher"
            )
            os.makedirs(memo_dir, exist_ok=True)
            self._memo_store = MemoStore(storage_dir=memo_dir)
        self._code_fingerprint = compute_code_fingerprint(
            "project_watcher",
            prompt_version="v1",
        )

        self._handler = ProjectFileHandler(
            debounce_seconds=debounce_seconds,
            extensions=extensions,
        )
        self._observer = Observer()
        self._started = False
        self._enable_diff_summary = enable_diff_summary

        # Content cache: file_path -> (content_hash, old_content)
        # Used to detect content changes and compute diff summaries
        self._content_cache: Dict[str, Tuple[str, str]] = {}

        # .gitignore patterns cache
        self._gitignore_patterns: List[str] = []
        self._gitignore_loaded = False

    def _load_gitignore(self) -> List[str]:
        """Load .gitignore patterns from the project directory.

        Returns list of pattern strings (only used for advisory filtering;
        the actual .gitignore handling uses pathspec if available).
        """
        if self._gitignore_loaded:
            return self._gitignore_patterns
        gitignore_path = os.path.join(self._project_dir, ".gitignore")
        try:
            if os.path.isfile(gitignore_path):
                with open(gitignore_path, encoding="utf-8") as f:
                    self._gitignore_patterns = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
        except Exception as e:
            logger.warning("Failed to load .gitignore: %s", e)
        self._gitignore_loaded = True
        return self._gitignore_patterns

    def _get_relative_path(self, absolute_path: str) -> str:
        """Convert absolute path to project-relative path."""
        try:
            return os.path.relpath(absolute_path, self._project_dir)
        except ValueError:
            return absolute_path

    @property
    def name(self) -> str:
        return "project_watcher"

    @property
    def started(self) -> bool:
        return self._started

    @property
    def project_dir(self) -> str:
        return self._project_dir

    async def start(self) -> None:
        """Start the watchdog observer and begin listening for file events."""
        if self._started:
            logger.debug("ProjectWatcher already started")
            return

        if not os.path.isdir(self._project_dir):
            logger.warning("Project directory not found: %s", self._project_dir)
            return

        self._observer.schedule(
            self._handler,
            self._project_dir,
            recursive=True,
        )
        self._observer.start()
        self._started = True
        logger.info(
            "ProjectWatcher started: %s (debounce=%.1fs, exts=%d)",
            self._project_dir,
            self._handler._debounce_seconds,
            len(self._handler._extensions),
        )

    async def stop(self) -> None:
        """Stop the watchdog observer."""
        if not self._started:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._started = False
        logger.info("ProjectWatcher stopped: %s", self._project_dir)

    async def poll(self) -> List[ProjectFileChange]:
        """Poll for file changes since the last call.

        Drains the watchdog event queue, reads file content, compares
        against MemoStore, and returns only genuinely changed files.

        Returns:
            List of ProjectFileChange objects. Empty if no changes detected.
        """
        if not self._started:
            logger.debug("ProjectWatcher not started, skipping poll")
            return []

        events = await self._handler.drain()
        if not events:
            return []

        now = time.time()
        changes: List[ProjectFileChange] = []

        for file_path, event_type in events:
            rel_path = self._get_relative_path(file_path)

            if event_type == FileChangeType.DELETED.value:
                change = ProjectFileChange(
                    file_path=rel_path,
                    change_type=FileChangeType.DELETED.value,
                    timestamp=now,
                )
                # Clean up content cache
                self._content_cache.pop(rel_path, None)
                self._handler.cleanup_pending(file_path)
                changes.append(change)
                continue

            # Created / Modified: read content and compare with MemoStore
            if not os.path.isfile(file_path):
                self._handler.cleanup_pending(file_path)
                continue

            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stat = os.stat(file_path)
            except (FileNotFoundError, PermissionError, OSError):
                self._handler.cleanup_pending(file_path)
                continue

            current_hash = compute_content_hash(content)
            cache_entry = self._content_cache.get(rel_path)
            prev_hash = cache_entry[0] if cache_entry else None

            # MemoStore check: has this (content_hash, code_fingerprint) been processed?
            memo_key = MemoKey(
                component_type="project_watcher",
                input_hash=current_hash,
                code_fingerprint=self._code_fingerprint,
            )
            memo_hit = self._memo_store.lookup(memo_key)

            if memo_hit and prev_hash == current_hash:
                # Content hasn't changed — skip
                self._handler.cleanup_pending(file_path)
                continue

            # Determine actual change type
            actual_type = (
                FileChangeType.CREATED.value
                if prev_hash is None
                else FileChangeType.MODIFIED.value
            )

            # Compute basic diff summary (first 200 chars) if content changed
            diff_summary = ""
            if self._enable_diff_summary and actual_type == FileChangeType.MODIFIED.value and cache_entry:
                old_content = cache_entry[1]
                if old_content is not None and old_content != content:
                    diff_summary = self._compute_diff_summary(old_content, content)

            ext = os.path.splitext(file_path)[1].lower()
            language = _infer_language(ext)

            change = ProjectFileChange(
                file_path=rel_path,
                change_type=actual_type,
                content_hash=current_hash,
                prev_content_hash=prev_hash or "",
                extension=ext,
                language=language,
                diff_summary=diff_summary,
                timestamp=now if event_type == FileChangeType.CREATED.value else os.path.getmtime(file_path),
                size_bytes=stat.st_size,
            )

            # Update caches
            self._content_cache[rel_path] = (current_hash, content)
            self._memo_store.store(memo_key, current_hash)
            self._handler.cleanup_pending(file_path)

            changes.append(change)

            logger.debug(
                "File change: %s (%s) lang=%s hash=%s",
                rel_path, actual_type, language, current_hash[:8],
            )

        if changes:
            logger.info(
                "ProjectWatcher detected %d file change(s)",
                len(changes),
            )

        return changes

    async def take_snapshot(self) -> ProjectSnapshot:
        """Take a snapshot of the current project state.

        Walks all tracked files and computes aggregate statistics.
        Used for structural delta detection.

        Returns:
            ProjectSnapshot with current project state.
        """
        snapshot = ProjectSnapshot(detected_at=time.time())
        file_type_counts: Dict[str, int] = {}
        recent_files: List[str] = []
        imports: Set[str] = set()
        total_size = 0
        total_files = 0

        if not os.path.isdir(self._project_dir):
            return snapshot

        for root, dirs, files in os.walk(self._project_dir):
            # Skip ignored directories in-place (prevents os.walk from descending)
            dirs[:] = [
                d for d in dirs
                if d not in ALWAYS_IGNORE_DIRS
            ]

            for fname in files:
                fpath = os.path.join(root, fname)
                ext = os.path.splitext(fname)[1].lower()

                if ext not in self._handler._extensions:
                    continue
                if _is_binary_by_ext(ext):
                    continue

                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                rel_path = self._get_relative_path(fpath)
                total_files += 1
                total_size += stat.st_size

                # File type distribution
                file_type_counts[ext] = file_type_counts.get(ext, 0) + 1

                # Track recent files (latest mtime)
                recent_files.append((rel_path, stat.st_mtime))

                # Try to extract top-level imports
                if ext == ".py" and stat.st_size < 10000:
                    try:
                        with open(fpath, encoding="utf-8", errors="replace") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("import ") or line.startswith("from "):
                                    imports.add(line)
                    except OSError:
                        pass

        snapshot.total_files = total_files
        snapshot.total_size_bytes = total_size
        snapshot.file_type_counts = file_type_counts
        snapshot.recent_files = [f[0] for f in sorted(recent_files, key=lambda x: -x[1])[:10]]
        snapshot.imports = sorted(imports)[:20]

        return snapshot

    def _compute_diff_summary(self, old_content: str, new_content: str) -> str:
        """Compute a simple diff summary (first 200 chars).

        Uses a simple line-level diff (not proper git diff) to give the LLM
        context about what changed. Truncated to 200 chars to avoid bloat.

        Args:
            old_content: Previous file content.
            new_content: Current file content.

        Returns:
            Truncated diff summary string.
        """
        old_lines = old_content.split("\n")
        new_lines = new_content.split("\n")

        added = 0
        removed = 0
        changed = 0

        # Simple line-level comparison
        old_set = set(old_lines)
        new_set = set(new_lines)
        added = len(new_set - old_set)
        removed = len(old_set - new_set)

        summary_parts = []
        if added > 0:
            summary_parts.append(f"+{added} lines")
        if removed > 0:
            summary_parts.append(f"-{removed} lines")

        if not summary_parts:
            return ""

        result = "; ".join(summary_parts)
        if len(result) > 200:
            result = result[:197] + "..."

        return result


_ALWAYS_IGNORE_DIRS = ALWAYS_IGNORE_DIRS