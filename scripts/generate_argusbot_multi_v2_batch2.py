"""
第 2 批生成 — 追加到 argusbot_multi_v2 目录，补齐 ~1500 条

用法：
  uv run python scripts/generate_argusbot_multi_v2_batch2.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.eval.generator import EvalDatasetGenerator

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)

OUTPUT_DIR = str((PROJECT_ROOT / "eval_dataset" / "argusbot_multi_v2_batch2").resolve())

DOMAINS_BATCH2: list[dict[str, Any]] = [
    {
        "name": "frontend_ux",
        "description": "前端和用户体验团队讨论框架、构建工具、性能优化等技术决策",
        "num_chats": 8,
        "participants_per_chat": 4,
        "noise_per_chat": 12,
        "topics": [
            "前端框架选型", "SSR与CSR策略", "组件库设计理念",
            "状态管理方案", "微前端架构",
        ],
    },
    {
        "name": "qa_perf",
        "description": "质量与性能团队讨论测试策略、基准测试、异常处理等技术决策",
        "num_chats": 8,
        "participants_per_chat": 4,
        "noise_per_chat": 12,
        "topics": [
            "自动化测试框架", "混沌工程实践", "异常处理与重试",
            "性能基准测试方案", "错误码体系设计",
        ],
    },
]

def main():
    print("=" * 60)
    print("  argusbot_multi_v2 第2批生成")
    print(f"  追加到: {OUTPUT_DIR}")
    total_chats = sum(d['num_chats'] for d in DOMAINS_BATCH2)
    print(f"  第2批域数: {len(DOMAINS_BATCH2)}, 频道数: {total_chats}")
    print(f"  预计追加 ~{total_chats * 50} 条")
    print("=" * 60)

    start = time.time()
    generator = EvalDatasetGenerator()
    generator.generate_benchmark(OUTPUT_DIR, domains=DOMAINS_BATCH2)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  第2批完成！用时 {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  总输出目录: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
