from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class BM25Indexer:
    """BM25 索引构建器

    整合 ref/main stage3 的逻辑。
    注：本地尚未配置 embedding/reranker 模型，此模块仅提供骨架。
    """

    def __init__(self, index_dir: Optional[str] = None) -> None:
        self._index_dir = Path(index_dir) if index_dir else None
        self._bm25 = None
        self._docs: List[Dict] = []

    def build_from_hypergraph(self, hypergraph: Dict[str, Any]) -> None:
        from rank_bm25 import BM25Okapi

        corpus: List[List[str]] = []
        self._docs = []

        for fact_id, fact_data in hypergraph.get("facts", {}).items():
            text = fact_data.get("content", "") or str(fact_data)
            tokens = self._tokenize(text)
            if tokens:
                corpus.append(tokens)
                self._docs.append({"id": fact_id, "type": "fact", "data": fact_data})

        for ep_id, ep_data in hypergraph.get("episodes", {}).items():
            text = ep_data.get("summary", "") or ep_data.get("episode_description", "")
            tokens = self._tokenize(text)
            if tokens:
                corpus.append(tokens)
                self._docs.append({"id": ep_id, "type": "episode", "data": ep_data})

        if corpus:
            self._bm25 = BM25Okapi(corpus)
            logger.info("BM25 index built with %d documents", len(self._docs))
        else:
            logger.warning("No documents to build BM25 index")

    def search(self, query: str, top_n: int = 10) -> List[Dict]:
        if self._bm25 is None:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)
        return [self._docs[i] for i, s in indexed[:top_n] if s > 0]

    def save(self, path: str) -> None:
        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            pickle.dump({"bm25": self._bm25, "docs": self._docs}, f)
        logger.info("BM25 index saved to %s", save_path)

    def load(self, path: str) -> bool:
        load_path = Path(path)
        if not load_path.exists():
            return False
        try:
            with open(load_path, "rb") as f:
                data = pickle.load(f)
            self._bm25 = data["bm25"]
            self._docs = data["docs"]
            logger.info("BM25 index loaded from %s (%d docs)", load_path, len(self._docs))
            return True
        except Exception as e:
            logger.warning("Failed to load BM25 index: %s", e)
            return False

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        if not text:
            return []
        import re
        tokens = re.findall(r"\w+", text.lower())
        return [t for t in tokens if len(t) >= 2]