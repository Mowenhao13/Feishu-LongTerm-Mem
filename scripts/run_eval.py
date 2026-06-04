#!/usr/bin/env python3
"""大规模评估 CLI — Phase 2

加载 JSONL 消息 → EvalRunner 模拟处理 → Comparator 精度评估。

Usage:
    # 单群聊评估
    python -m scripts.run_eval \
        --input eval_dataset/single_chat/messages.jsonl \
        --expected eval_dataset/single_chat/expected.jsonl \
        --mode single

    # 多群聊评估
    python -m scripts.run_eval \
        --input eval_dataset/multi_chat/messages.jsonl \
        --expected eval_dataset/multi_chat/expected.jsonl \
        --mode multi
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.eval_runner import EvalRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="大规模评估 — 决策提取精度测试")
    parser.add_argument("--input", required=True,
                        help="输入 JSONL 消息文件路径")
    parser.add_argument("--expected", required=True,
                        help="expected.jsonl 真值文件路径")
    parser.add_argument("--mode", choices=["single", "multi"], default="single",
                        help="评估模式：single=单群聊, multi=多群聊")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="消息间延迟 (秒)")
    parser.add_argument("--max-messages", type=int, default=0,
                        help="最大处理消息数 (0=全部)")
    parser.add_argument("--model", default="deepseek-chat",
                        help="提取模型名称")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    expected_path = Path(args.expected)

    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}")
        sys.exit(1)
    if not expected_path.exists():
        print(f"错误: 真值文件不存在: {expected_path}")
        sys.exit(1)

    group_num = 1 if args.mode == "single" else 0  # 0 = 从消息中读取 chat_id

    runner = EvalRunner(
        input_path=str(input_path),
        delay=args.delay,
        max_messages=args.max_messages,
        group_num=group_num,
        expected_path=str(expected_path),
    )
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())