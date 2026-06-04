#!/usr/bin/env python3
"""大规模评估数据生成 CLI — Phase 1

Usage:
    # 单群聊（单批：~100条）
    python -m scripts.generate_eval_data --mode single_chat --output eval_dataset/single_chat

    # 单群聊（分批：每批2-3个话题，~300+条，共6次LLM调用）
    python -m scripts.generate_eval_data --mode single_chat --num-batches 5 --output eval_dataset/single_chat_large

    # 多群聊（单批）
    python -m scripts.generate_eval_data --mode multi_chat --output eval_dataset/multi_chat

    # 多群聊（每群聊分批，5次LLM调用，~400+条）
    python -m scripts.generate_eval_data --mode multi_chat --per-chat --output eval_dataset/multi_chat_large
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.eval.generator import EvalDatasetGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="大规模评估数据生成")
    parser.add_argument("--mode", choices=["single_chat", "multi_chat"], default="single_chat",
                        help="生成模式")
    parser.add_argument("--output", default="eval_dataset/single_chat",
                        help="输出目录")
    parser.add_argument("--config", default="",
                        help="配置文件路径 (可选)")
    parser.add_argument("--num-chats", type=int, default=0,
                        help="覆盖多群聊数量")
    parser.add_argument("--num-decisions", type=int, default=0,
                        help="覆盖每主题决策数")
    # 分批参数
    parser.add_argument("--num-batches", type=int, default=1,
                        help="单群聊分批次数 (1=单批, >1=分批生成)")
    parser.add_argument("--per-chat", action="store_true",
                        help="多群聊按群聊分批生成")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generator = EvalDatasetGenerator(config_path=args.config or None)
    generator.generate(
        str(Path(args.output).resolve()),
        mode=args.mode,
        num_batches=args.num_batches,
        per_chat=args.per_chat,
    )


if __name__ == "__main__":
    main()