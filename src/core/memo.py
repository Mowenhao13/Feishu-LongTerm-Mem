"""内容寻址增量处理（MemoStore）

基于 CocoIndex 的 memoization 机制的精简实现。

核心概念：
- MemoKey: 标识一个处理单元的唯一性（组件类型 + 输入 hash + 代码指纹 + 依赖 hash 列表）
- MemoEntry: 缓存条目（key + 结果 hash + 元数据）
- MemoStore: 持久化存储（JSON 文件，后续可换 LMDB）

用法：
    memo_store = MemoStore("data")
    key = MemoKey(
        component_type="extractor_stage1",
        input_hash=compute_content_hash(content),
        code_fingerprint=compute_code_fingerprint("MyExtractor", prompt_version="v2"),
    )
    cached = memo_store.lookup(key)
    if cached is None:
        result_hash = do_work()
        memo_store.store(key, result_hash)
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


# ============================================================================
# Data Types
# ============================================================================


@dataclass
class MemoKey:
    """组件级别 memo 键 —— 标识一个处理单元的唯一性

    Attributes:
        component_type: 组件类型，如 "detector" | "extractor_stage1"
            | "extractor_stage2" | "dedup"
        input_hash: 输入内容 hash (SHA256 前 16 位)
        code_fingerprint: 代码/配置指纹（prompt version + component version）
        dependencies: 外部依赖 hash 列表（如上游组件输出 hash）
    """

    component_type: str
    input_hash: str
    code_fingerprint: str
    dependencies: List[str] = field(default_factory=list)

    def to_key(self) -> str:
        """序列化为 dict 查找用的字符串键"""
        return json.dumps(
            [
                self.component_type,
                self.input_hash,
                self.code_fingerprint,
                sorted(self.dependencies),
            ],
            sort_keys=True,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "MemoKey":
        return cls(
            component_type=d["component_type"],
            input_hash=d["input_hash"],
            code_fingerprint=d["code_fingerprint"],
            dependencies=d.get("dependencies", []),
        )


@dataclass
class MemoEntry:
    """持久化 memo 条目"""

    key: MemoKey
    result_hash: str
    created_at: float
    hit_count: int = 0


# ============================================================================
# Hash Utilities
# ============================================================================


def compute_content_hash(text: str) -> str:
    """计算文本内容的 hash

    使用 SHA256，取前 16 位 hex，与 MemoryEngine._processed_episode_hashes
    的格式保持一致。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def compute_code_fingerprint(
    component_name: str,
    prompt_version: str = "",
    model_name: str = "",
) -> str:
    """计算代码/配置指纹

    将组件名称、prompt 版本和模型名组合后取 SHA256。
    当任一配置变化时，指纹变化导致缓存失效。

    Args:
        component_name: 组件的 fully qualified 名称
        prompt_version: Prompt 版本号或内容 hash
        model_name: 使用的模型名称
    """
    payload = f"{component_name}:{prompt_version}:{model_name}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ============================================================================
# MemoStore
# ============================================================================


class MemoStore:
    """Memo 持久化存储

    使用 JSON 文件存储。线程安全（threading.Lock）。
    """

    def __init__(self, storage_dir: str = "data") -> None:
        self._entries: Dict[str, MemoEntry] = {}
        self._storage_path = Path(storage_dir) / "memo_store.json"
        self._lock = threading.Lock()
        self._load()

    # ---- 公开 API ----

    def lookup(self, key: MemoKey) -> Optional[str]:
        """查找 memo，返回缓存的结果 hash

        Returns:
            缓存的结果 hash，如果 miss 则返回 None
        """
        with self._lock:
            entry = self._entries.get(key.to_key())
            if entry is None:
                return None
            entry.hit_count += 1
            self._save()
            return entry.result_hash

    def store(self, key: MemoKey, result_hash: str) -> None:
        """存储 memo 条目"""
        with self._lock:
            entry = MemoEntry(
                key=key,
                result_hash=result_hash,
                created_at=time.time(),
                hit_count=1,
            )
            self._entries[key.to_key()] = entry
            self._save()

    def invalidate(self, component_type: Optional[str] = None) -> int:
        """失效所有（或指定类型的）memo

        Args:
            component_type: 如果提供，只失效该类型的条目

        Returns:
            失效的条目数
        """
        with self._lock:
            if component_type is None:
                count = len(self._entries)
                self._entries.clear()
                self._save()
                return count

            to_delete = [
                k
                for k, v in self._entries.items()
                if v.key.component_type == component_type
            ]
            for k in to_delete:
                del self._entries[k]
            if to_delete:
                self._save()
            return len(to_delete)

    def is_valid(self, key: MemoKey) -> bool:
        """判断 memo 是否有效（存在且未被失效）"""
        with self._lock:
            entry = self._entries.get(key.to_key())
            if entry is None:
                return False
            # 验证所有字段一致（防止 key hash 碰撞）
            return (
                entry.key.component_type == key.component_type
                and entry.key.input_hash == key.input_hash
                and entry.key.code_fingerprint == key.code_fingerprint
                and entry.key.dependencies == key.dependencies
            )

    def count(self) -> dict:
        """统计各类 memo 数量

        Returns:
            {"total": int, "by_type": {str: int}}
        """
        with self._lock:
            by_type: Dict[str, int] = {}
            for entry in self._entries.values():
                ct = entry.key.component_type
                by_type[ct] = by_type.get(ct, 0) + 1
            return {
                "total": len(self._entries),
                "by_type": by_type,
            }

    def get_stats(self) -> dict:
        """获取详细统计信息

        Returns:
            {
                "total": int,
                "by_type": {str: int},
                "total_hits": int,
                "oldest": float,   # 最早创建时间
                "newest": float,   # 最晚创建时间
            }
        """
        with self._lock:
            if not self._entries:
                return {"total": 0, "by_type": {}, "total_hits": 0}

            by_type: Dict[str, int] = {}
            total_hits = 0
            oldest = float("inf")
            newest = 0.0

            for entry in self._entries.values():
                ct = entry.key.component_type
                by_type[ct] = by_type.get(ct, 0) + 1
                total_hits += entry.hit_count
                created = entry.created_at
                if created < oldest:
                    oldest = created
                if created > newest:
                    newest = created

            return {
                "total": len(self._entries),
                "by_type": by_type,
                "total_hits": total_hits,
                "oldest": oldest,
                "newest": newest,
            }

    # ---- 持久化 ----

    def _load(self) -> None:
        """从 JSON 文件加载 memo 条目"""
        try:
            if not self._storage_path.exists():
                self._entries = {}
                return

            raw = self._storage_path.read_text("utf-8")
            data = json.loads(raw)

            entries: Dict[str, MemoEntry] = {}
            for serialized_key, entry_data in data.items():
                key = MemoKey.from_dict(entry_data["key"])
                entry = MemoEntry(
                    key=key,
                    result_hash=entry_data["result_hash"],
                    created_at=entry_data["created_at"],
                    hit_count=entry_data.get("hit_count", 0),
                )
                entries[serialized_key] = entry
            self._entries = entries
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            self._entries = {}

    def _save(self) -> None:
        """将 memo 条目保存到 JSON 文件"""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            data: dict = {}
            for serialized_key, entry in self._entries.items():
                data[serialized_key] = {
                    "key": asdict(entry.key),
                    "result_hash": entry.result_hash,
                    "created_at": entry.created_at,
                    "hit_count": entry.hit_count,
                }

            self._storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning("Failed to save memo store: %s", e)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __repr__(self) -> str:
        return f"MemoStore(path={self._storage_path}, entries={len(self._entries)})"