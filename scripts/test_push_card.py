"""
决策卡片推送测试 — 调用 PushEngine API 推送卡片

扫码卡片推送到飞书群聊需要 LarkIMClient。
若不配置飞书，卡片内容会输出到终端。

用法:
  uv run python scripts/test_push_card.py

参数:
  --feishu    推送到飞书群聊（需配置 .env 中的 PUSH_FEISHU_CHAT_ID）
  --all       推送所有决策
  --conflict  推送冲突卡片（默认仅推送单条决策卡片）
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

# 添加项目根目录和 src/ 到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

from src.card.config import CardConfig
from src.card.pusher import PushEngine, PushTrigger
from src.graph.memory_graph import MemoryGraph
from src.storage.git_storage import GitStorage, GitStorageConfig


def load_graph() -> MemoryGraph:
    storage = GitStorage(GitStorageConfig(work_dir="data"))
    graph = MemoryGraph()
    graph.load_from_git(storage, "default")
    return graph


def print_decisions(graph: MemoryGraph):
    decisions = graph.get_all_decisions()
    print(f"\n📋 现有决策 ({len(decisions)} 条)")
    print("-" * 60)
    for d in decisions:
        hs = d.access_stats.hot_score if d.access_stats else "N/A"
        print(f"  {d.sid[:12]} | {d.summary[:48]:48s} | {d.status.value:10s} | 🔥{hs}")
    print()


def push_to_feishu(engine: PushEngine, graph: MemoryGraph, push_all: bool, push_conflict: bool):
    """推送到飞书群聊"""
    decisions = graph.get_all_decisions()
    if not decisions:
        print("❌ 没有决策可推送")
        return

    if push_all:
        print(f"\n📤 推送所有决策到飞书 ({len(decisions)} 条)...")
        for d in decisions:
            ok = engine.push_decision_card(d.sid, PushTrigger.MANUAL_QUERY)
            print(f"  {'✅' if ok else '❌'} {d.sid[:12]}: {d.summary[:40]}")
    elif push_conflict and len(decisions) >= 2:
        print(f"\n⚔️ 推送冲突卡片...")
        ok = engine.push_conflict_card(
            decisions[0].sid, decisions[1].sid,
            "重复决策冲突演示",
        )
        print(f"  {'✅' if ok else '❌'} 冲突: {decisions[0].summary[:30]} ↔ {decisions[1].summary[:30]}")
    else:
        d = decisions[0]
        print(f"\n📤 推送单条决策卡片...")
        ok = engine.push_decision_card(d.sid, PushTrigger.MANUAL_QUERY)
        print(f"  {'✅' if ok else '❌'} {d.sid[:12]}: {d.summary[:40]}")

    print(f"\n✅ 推送完成")


def push_to_terminal(graph: MemoryGraph):
    """仅输出到终端"""
    config = CardConfig(
        enable_feishu=False,
        enable_terminal=True,
        enable_osascript=False,
    )
    engine = PushEngine(config=config, memory_graph=graph, pipeline=None, lark_client=None)

    decisions = graph.get_all_decisions()
    if not decisions:
        print("❌ 没有决策")
        return

    d = decisions[0]
    print(f"\n📤 推送决策卡片（终端模式）...")
    ok = engine.push_decision_card(d.sid, PushTrigger.MANUAL_QUERY)
    print(f"  {'✅' if ok else '❌'} {d.sid[:12]}: {d.summary[:40]}")

    if len(decisions) >= 2:
        print(f"\n⚔️ 推送冲突卡片...")
        engine.push_conflict_card(
            decisions[0].sid, decisions[1].sid,
            "冲突演示",
        )

    print(f"\n📤 推送更新卡片...")
    engine.push_decision_update_card(d.sid, "proposed", "decided")


def main():
    parser = argparse.ArgumentParser(description="决策卡片推送测试")
    parser.add_argument("--feishu", action="store_true", help="推送至飞书群聊")
    parser.add_argument("--all", action="store_true", help="推送所有决策")
    parser.add_argument("--conflict", action="store_true", help="推送冲突卡片")
    parser.add_argument("--dry-run", action="store_true", help="仅打印决策列表，不推送")
    args = parser.parse_args()

    graph = load_graph()
    print_decisions(graph)

    if args.dry_run:
        return

    if args.feishu:
        config = CardConfig.from_env()
        if not config.feishu_chat_id:
            print("\n⚠️  PUSH_FEISHU_CHAT_ID 未配置，将使用终端输出替代")
            push_to_terminal(graph)
        else:
            from src.adapter.lark_im import create_client_from_env
            lark_client = create_client_from_env()
            engine = PushEngine(
                config=config,
                memory_graph=graph,
                pipeline=None,
                lark_client=lark_client,
            )
            push_to_feishu(engine, graph, args.all, args.conflict)
    else:
        push_to_terminal(graph)


if __name__ == "__main__":
    main()