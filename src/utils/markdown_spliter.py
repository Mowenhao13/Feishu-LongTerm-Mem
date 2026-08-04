"""
CocoIndex-based text chunker — replaces the old MarkdownHeaderTextSplitter.

Uses cocoindex.ops.text.RecursiveSplitter for syntax-aware recursive chunking.
Supports Markdown, code, and plain text with configurable chunk_size and overlap.
"""

from __future__ import annotations

from typing import List, Optional

from cocoindex.ops.text import RecursiveSplitter
from cocoindex.resources.chunk import Chunk

from src.utils.logger import get_logger

logger = get_logger(__name__)


class MarkdownSplitter:
    """A text chunker using cocoindex's RecursiveSplitter.

    Splits text into chunks that respect syntax boundaries (paragraphs, sentences).
    Supports configurable chunk_size, min_chunk_size, and chunk_overlap.

    Args:
        chunk_size: Target chunk size in bytes (characters for plain text).
        min_chunk_size: Minimum chunk size. Defaults to chunk_size / 2.
        chunk_overlap: Overlap between consecutive chunks.
        language: Language for syntax-aware splitting (e.g. "markdown", "python").
            If None, uses generic text splitting.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        min_chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        language: Optional[str] = None,
    ):
        self._chunk_size = chunk_size
        self._min_chunk_size = min_chunk_size
        self._chunk_overlap = chunk_overlap
        self._language = language
        self._splitter = RecursiveSplitter()
        logger.debug(
            "[MarkdownSplitter] Init: chunk_size=%d min_chunk_size=%s overlap=%s language=%s",
            chunk_size, min_chunk_size, chunk_overlap, language,
        )

    def split(self, text: str, language: Optional[str] = None) -> List[Chunk]:
        """Split text into chunks with position information.

        Args:
            text: The text to split.
            language: Override language for syntax-aware splitting.
                If None, uses the instance's language (set at __init__).

        Returns:
            A list of Chunk objects with text content and position info.
        """
        lang = language or self._language
        chunks = self._splitter.split(
            text,
            chunk_size=self._chunk_size,
            min_chunk_size=self._min_chunk_size,
            chunk_overlap=self._chunk_overlap,
            language=lang,
        )
        logger.debug("[MarkdownSplitter] Split %d chars → %d chunks (lang=%s)", len(text), len(chunks), lang or "auto")
        return chunks

    def split_text(self, text: str) -> List[str]:
        """Split text and return only the text content of each chunk.

        Convenience method compatible with the old API.

        Args:
            text: The text to split.

        Returns:
            A list of chunk text strings.
        """
        return [c.text for c in self.split(text)]