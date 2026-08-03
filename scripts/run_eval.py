#!/usr/bin/env python3
"""大规模评估 CLI — Phase 2 + Phase 4

支持单群聊/多群聊评估和 WebSearch 记忆评测。

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

    # WebSearch 记忆评测（单轮）
    python -m scripts.run_eval \
        --input eval_dataset/argusbot_websearch/messages.jsonl \
        --expected eval_dataset/argusbot_websearch/expected.jsonl \
        --mode websearch

    # WebSearch 跨 session 评测
    python -m scripts.run_eval \
        --input eval_dataset/argusbot_websearch/messages.jsonl \
        --expected eval_dataset/argusbot_websearch/expected.jsonl \
        --mode websearch \
        --websearch-sessions \
        --session1-input eval_dataset/argusbot_websearch/session1_messages.jsonl \
        --session2-input eval_dataset/argusbot_websearch/session2_messages.jsonl \
        --cross-session-expected eval_dataset/argusbot_websearch/cross_session_expected.jsonl
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
    parser.add_argument("--mode", choices=["single", "multi", "websearch"], default="single",
                        help="评估模式：single=单群聊, multi=多群聊, websearch=WebSearch 评测")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="消息间延迟 (秒)")
    parser.add_argument("--max-messages", type=int, default=0,
                        help="最大处理消息数 (0=全部)")
    parser.add_argument("--model", default="deepseek-chat",
                        help="提取模型名称")
    # WebSearch 跨 session 参数
    parser.add_argument("--websearch-sessions", action="store_true",
                        help="启用跨 session 评测模式（场景 4）")
    parser.add_argument("--session1-input", default="",
                        help="Session 1 消息文件（跨 session 模式）")
    parser.add_argument("--session2-input", default="",
                        help="Session 2 消息文件（跨 session 模式）")
    parser.add_argument("--cross-session-expected", default="",
                        help="跨 session 真值文件（跨 session 模式）")
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

    group_num = 1 if args.mode in ("single", "websearch") else 0  # 0 = 从消息中读取 chat_id
    websearch_expected = str(expected_path) if args.mode == "websearch" else ""

    if args.websearch_sessions and args.session1_input and args.session2_input:
        s1_path = Path(args.session1_input)
        s2_path = Path(args.session2_input)
        if not s1_path.exists():
            print(f"错误: Session 1 文件不存在: {s1_path}")
            sys.exit(1)
        if not s2_path.exists():
            print(f"错误: Session 2 文件不存在: {s2_path}")
            sys.exit(1)

    runner = EvalRunner(
        input_path=str(input_path),
        delay=args.delay,
        max_messages=args.max_messages,
        group_num=group_num,
        expected_path=str(expected_path),
        websearch_expected=websearch_expected,
        websearch_sessions=args.websearch_sessions,
        session1_input=args.session1_input,
        session2_input=args.session2_input,
        cross_session_expected=args.cross_session_expected,
    )

    if args.websearch_sessions:
        print("\n📚 WebSearch 跨 Session 评测模式")
        print(f"   Session 1: {args.session1_input}")
        print(f"   Session 2: {args.session2_input}")
        print(f"   跨 Session 真值: {args.cross_session_expected}")
        # 扩展 run 方法在 eval_runner 内部处理多 session 加载
        # 将 session 文件路径传给 runner
        print()

    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())