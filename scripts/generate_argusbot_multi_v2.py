"""
生成 argusbot_multi_v2 数据集 — 基于 LLM 管线生成 ~1500 条消息

用法：
  uv run python scripts/generate_argusbot_multi_v2.py

配置参数可调：num_chats、noise_per_chat 控制最终消息总量
当前设计：30 个频道 × ~50 条/频道 ≈ 1500 条
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

# 让 logger 输出到 stdout 以便实时查看进度
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
    force=True,
)

OUTPUT_DIR = str((PROJECT_ROOT / "eval_dataset" / "argusbot_multi_v2").resolve())

# argusbot_multi_v2 域配置 — 3 个域，每个约 10 个频道，合计 ~1500 条
DOMAINS: list[dict[str, Any]] = [
    {
        "name": "core_arch",
        "description": "核心架构团队讨论多智能体架构、会话持久化、稳定性等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 12,
        "topics": [
            "多智能体循环架构", "Daemon与CLI双模式", "会话持久化与恢复",
            "JSONL命令总线", "Stall检测配置", "模型fallback链",
            "PlannerAgent策略", "BTW Side-Agent集成",
        ],
    },
    {
        "name": "integration_obs",
        "description": "集成与可观测性团队讨论 IM 集成、可观测性、质量保障等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 12,
        "topics": [
            "飞书集成方案", "Telegram集成", "可观测性三件套",
            "ReviewerAgent质量门禁", "Copilot Proxy", "语音转写方案",
            "日志采样策略", "告警规则设计",
        ],
    },
    {
        "name": "infra_data",
        "description": "基础设施与数据团队讨论数据库、缓存、消息队列、部署等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 12,
        "topics": [
            "数据库迁移策略", "缓存策略设计", "服务网格选型",
            "消息队列选型", "容器化部署方案", "CI/CD流水线设计",
            "微服务拆分策略", "灾备恢复方案",
        ],
    },
]


def main():
    print("=" * 60)
    print("  argusbot_multi_v2 数据集生成器")
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"  域数: {len(DOMAINS)}, 每域频道: {DOMAINS[0]['num_chats']}")
    total_chats = sum(d['num_chats'] for d in DOMAINS)
    print(f"  总频道数: {total_chats}")
    print(f"  每频道干扰消息: {DOMAINS[0]['noise_per_chat']}")
    print(f"  预计总消息: ~{total_chats * 50}")
    print("=" * 60)

    start = time.time()
    generator = EvalDatasetGenerator()
    generator.generate_benchmark(OUTPUT_DIR, domains=DOMAINS)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  生成完成！用时 {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
