"""
手动触发记忆整理（睡眠机制）

用法:
  # 使用 uv 运行（推荐）
  uv run python scripts/sleep_mem.py

  # 使用系统 Python
  source .venv/bin/activate
  python scripts/sleep_mem.py

配置（在 .env 中）:
  MEMORY_SLEEP_ENABLED=true            # 自动睡眠开关(默认true)
  MEMORY_SLEEP_INTERVAL=3600           # 自动睡眠间隔(秒, 默认1小时)
  MEMORY_SLEEP_DEDUP_THRESHOLD=0.7     # 决策去重 Dice 系数阈值
  MEMORY_SLEEP_NOISE_HOT_MIN=5.0       # 噪音修剪最低 hot score
  MEMORY_SLEEP_NOISE_CONFIDENCE_MIN=0.3 # 噪音修剪最低置信度
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

# Add project root and src/ to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv

load_dotenv()

from src.core.engine import MemoryEngine
from src.core.engine_config import EngineConfig
from src.graph.memory_graph import MemoryGraph
from src.graph.persistence import HypergraphPersistence
from src.memory.sleep import SleepManager, SleepReport
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.structure import Hypergraph
from src.utils.logger import get_logger
from src.view.syncer import BaseViewSyncer

logger = get_logger("sleep_mem")


def build_sleep_manager() -> SleepManager:
    """从当前存储状态构建 SleepManager

    读取：
    1. GitStorage（决策持久化目录）
    2. MemoryGraph（从 GitStorage 加载）
    3. HypergraphPersistence（从 state.json 加载）
    4. BaseViewSyncer（用于同步到飞书多维表格）
    """
    config = EngineConfig()

    if not config.storage_path:
        logger.error("storage_path not configured (check .env)")
        sys.exit(1)

    storage_config = GitStorageConfig(work_dir=str(config.storage_path))
    storage = GitStorage(storage_config)

    try:
        git_branch = os.getenv("LARK_GIT_BRANCH", "main")
        storage.switch_branch(git_branch)
    except Exception as e:
        logger.warning("Git branch switch failed: %s", e)

    graph = MemoryGraph()
    try:
        graph.load_from_git(storage, config.project)
        logger.info("MemoryGraph loaded: %d decisions", graph.count())
    except Exception as e:
        logger.warning("MemoryGraph load failed: %s", e)

    hypergraph: Hypergraph = Hypergraph()
    hg_persistence = None
    try:
        hg_dir = Path(config.storage_path) / "hypergraph"
        hg_persistence = HypergraphPersistence(hg_dir / "state.json")
        if hg_persistence.exists():
            hypergraph = hg_persistence.load()
            stats = hypergraph.get_stats()
            logger.info("Hypergraph loaded: decisions=%d facts=%d episodes=%d topics=%d",
                        stats["decisions"], stats["facts"], stats["episodes"], stats["topics"])
        else:
            logger.info("No existing hypergraph, starting fresh")
    except Exception as e:
        logger.warning("Hypergraph load failed: %s", e)

    base_syncer = None
    try:
        base_syncer = BaseViewSyncer(storage, graph)
        logger.info("BaseViewSyncer initialized")
    except Exception as e:
        logger.debug("BaseViewSyncer not available: %s", e)

    return SleepManager(
        graph=graph,
        storage=storage,
        hypergraph=hypergraph,
        hg_persistence=hg_persistence,
        base_view_syncer=base_syncer,
    )


def print_report(report: SleepReport) -> None:
    """打印睡眠整理报告"""
    print()
    print("=" * 60)
    print(f"Memory Consolidation Report ({report.phase})")
    print("=" * 60)
    print(f"  总决策数:       {report.total_decisions}")
    print(f"  发现重复:       {report.duplicates_found}")
    print(f"  已合并:         {report.duplicates_merged}")
    print(f"  噪音修剪:       {report.noise_pruned}")
    print(f"  冲突检测:       {report.conflicts_found}")
    print(f"  Hot Score 更新: {report.hot_scores_updated}")
    print(f"  决策提升:       {report.decisions_promoted}")
    print(f"  时间:           {report.timestamp}")
    if report.errors:
        print(f"  错误:")
        for err in report.errors:
            print(f"    - {err}")
    print("=" * 60)
    print()


def main() -> None:
    print()
    print("=" * 60)
    print("Memory Consolidation (Sleep) — Manual Trigger")
    print("=" * 60)

    start = time.time()
    manager = build_sleep_manager()
    report = manager.sleep()
    elapsed = time.time() - start

    print_report(report)
    print(f"Done in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
