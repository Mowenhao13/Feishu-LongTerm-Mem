from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.structure import Hypergraph

logger = logging.getLogger(__name__)


class HypergraphPersistence:
    """Hypergraph 持久化管理器

    职责：
    1. 将 Hypergraph 序列化写入 JSON 文件
    2. 从 JSON 文件反序列化恢复 Hypergraph
    3. 检查持久化文件是否存在

    存储策略：
    - 只持久化结构数据（nodes, hyperedges, metadata）
    - 不持久化 embedding 向量（派生数据，按需重新计算）
    - 每次 episode 处理后全量覆写 state.json
    - Git 版本管理由外部 _hg_sync_loop() 负责
    """

    def __init__(self, file_path: str | Path):
        self._path = Path(file_path)

    def save(self, hypergraph: Hypergraph) -> None:
        """将 Hypergraph 序列化写入 JSON 文件"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = hypergraph.to_dict()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Hypergraph saved to %s", self._path)

    def load(self) -> Hypergraph:
        """从 JSON 文件反序列化恢复 Hypergraph"""
        if not self._path.exists():
            raise FileNotFoundError(f"Hypergraph file not found: {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
        hypergraph = Hypergraph.from_dict(data)
        logger.debug("Hypergraph loaded from %s", self._path)
        return hypergraph

    def exists(self) -> bool:
        """检查持久化文件是否存在"""
        return self._path.exists()

    def delete(self) -> None:
        """删除持久化文件"""
        if self._path.exists():
            self._path.unlink()
            logger.debug("Hypergraph file deleted: %s", self._path)