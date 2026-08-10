from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from src.structure import Hypergraph, HypergraphEmbedding

logger = logging.getLogger(__name__)


class HypergraphPersistence:
    """Hypergraph persistence manager.

    Responsibilities:
    1. Serialize/deserialize Hypergraph to/from JSON
    2. Persist/restore HypergraphEmbedding (.npz cache)
    3. Check persistence file existence

    Storage:
    - state.json: structural data (nodes, metadata)
    - embeddings.npz: embedding vectors (derived data, retrieval cache)
    """

    def __init__(self, file_path: str | Path):
        self._path = Path(file_path)

    def save(self, hypergraph: Hypergraph) -> None:
        """Serialize Hypergraph to JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = hypergraph.to_dict()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Hypergraph saved to %s", self._path)

    def load(self) -> Hypergraph:
        """Deserialize Hypergraph from JSON file."""
        if not self._path.exists():
            raise FileNotFoundError(f"Hypergraph file not found: {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
        hypergraph = Hypergraph.from_dict(data)
        logger.debug("Hypergraph loaded from %s", self._path)
        return hypergraph

    def exists(self) -> bool:
        return self._path.exists()

    def delete(self) -> None:
        if self._path.exists():
            self._path.unlink()
            logger.debug("Hypergraph file deleted: %s", self._path)

    # ─── Embedding persistence ─────────────────────────────────

    @property
    def _emb_path(self) -> Path:
        return self._path.with_name("embeddings.npz")

    def save_embeddings(self, embedding: HypergraphEmbedding) -> None:
        """Persist HypergraphEmbedding to .npz file."""
        data: Dict[str, Any] = {}
        for key in ("decisions", "episodes", "topics"):
            d = getattr(embedding, key, {})
            for nid, vec in d.items():
                data[f"{key}/{nid}"] = vec
        if not data:
            return
        self._emb_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self._emb_path, **data)
        logger.debug("Embeddings saved to %s (%d vectors)", self._emb_path, len(data))

    def load_embeddings(self) -> Optional[HypergraphEmbedding]:
        """Restore HypergraphEmbedding from .npz file, or None if missing."""
        if not self._emb_path.exists():
            return None
        loaded = np.load(self._emb_path)
        emb = HypergraphEmbedding()
        for key in loaded.files:
            parts = key.split("/", 1)
            if len(parts) != 2:
                continue
            layer, nid = parts
            vec = loaded[key]
            if layer == "decisions":
                emb.decisions[nid] = vec
            elif layer == "episodes":
                emb.episodes[nid] = vec
            elif layer == "topics":
                emb.topics[nid] = vec
        logger.debug("Embeddings loaded from %s (%d vectors)", self._emb_path, len(loaded.files))
        return emb

    def delete_embeddings(self) -> None:
        if self._emb_path.exists():
            self._emb_path.unlink()
            logger.debug("Embeddings deleted: %s", self._emb_path)