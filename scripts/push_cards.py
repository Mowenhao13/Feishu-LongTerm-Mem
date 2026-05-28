"""
手动推送决策消息卡片到飞书群聊

使用 PushEngine.push_decision_card() 渲染并推送 Lark 交互卡片，
推送到 .env 中 CARD_CHAT_IDS 指定的群聊。

用法:
  python scripts/push_cards.py --num 5 --order time
  python scripts/push_cards.py --num 10 --order topic --dry-run

参数:
  --num N      推送 N 条决策卡片（默认全部）
  --order      排序方式: time（按时间倒序）/ topic（按议题分组，组内按时间倒序）（默认 time）
  --dry-run    仅预览决策列表，不实际推送
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.card.config import CardConfig
from src.card.pusher import PushEngine, PushTrigger
from src.graph.memory_graph import MemoryGraph
from src.node.node import DecisionNode
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


def load_graph() -> MemoryGraph:
    storage = GitStorage(GitStorageConfig(work_dir="data"))
    graph = MemoryGraph()
    graph.load_from_git(storage, "default")
    return graph


def sort_by_time(decisions: List[DecisionNode]) -> List[DecisionNode]:
    return sorted(
        decisions,
        key=lambda d: d.created_at or datetime.min,
        reverse=True,
    )


def sort_by_topic(decisions: List[DecisionNode]) -> List[DecisionNode]:
    topic_groups: Dict[str, List[DecisionNode]] = {}
    for d in decisions:
        topic = d.topic_id or "general"
        topic_groups.setdefault(topic, []).append(d)

    result: List[DecisionNode] = []
    for topic in sorted(topic_groups.keys()):
        group = sorted(
            topic_groups[topic],
            key=lambda d: d.created_at or datetime.min,
            reverse=True,
        )
        result.extend(group)
    return result


def show_preview(decisions: List[DecisionNode]) -> None:
    print(f"\n{'='*70}")
    print(f"  决策卡片推送预览 ({len(decisions)} 条)")
    print(f"{'='*70}")
    for i, d in enumerate(decisions, 1):
        hs = d.access_stats.hot_score if d.access_stats else 0.0
        ts = d.created_at.strftime("%m-%d %H:%M") if d.created_at else "--"
        print(f"  {i:2d}. [{d.sid[:10]}] {d.summary[:50]:50s} | {d.topic_id or '-':12s} | {ts} | 🔥{hs:.0f}")
    print(f"{'='*70}\n")


def push_cards(engine: PushEngine, decisions: List[DecisionNode]) -> Tuple[int, int]:
    success = 0
    fail = 0
    for d in decisions:
        ok = engine.push_decision_card(d.sid, PushTrigger.MANUAL_QUERY)
        if ok:
            success += 1
            print(f"  ✅ {d.sid[:10]}: {d.summary[:40]}")
        else:
            fail += 1
            print(f"  ❌ {d.sid[:10]}: {d.summary[:40]}")
    return success, fail


def main():
    parser = argparse.ArgumentParser(description="手动推送决策消息卡片到飞书群聊")
    parser.add_argument(
        "--num",
        type=int,
        default=0,
        help="推送的决策卡片数量（0=全部）",
    )
    parser.add_argument(
        "--order",
        choices=["time", "topic"],
        default="time",
        help="排序方式: time（按时间倒序）/ topic（按议题分组）（默认 time）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览决策列表，不实际推送",
    )
    args = parser.parse_args()

    graph = load_graph()
    all_decisions = graph.get_all_decisions()
    if not all_decisions:
        print("❌ 没有决策可推送")
        sys.exit(1)

    if args.order == "topic":
        sorted_decisions = sort_by_topic(all_decisions)
    else:
        sorted_decisions = sort_by_time(all_decisions)

    if args.num > 0:
        sorted_decisions = sorted_decisions[: args.num]

    show_preview(sorted_decisions)

    if args.dry_run:
        print("  预览模式（--dry-run），未实际推送")
        return

    config = CardConfig.from_env()
    if not config.card_chat_ids:
        print("⚠️  CARD_CHAT_IDS 未配置，将在终端输出卡片内容")
    else:
        print(f"📤 目标群聊: {config.card_chat_ids}")

    from src.adapter.lark_im import create_client_from_env
    try:
        lark_client = create_client_from_env()
    except RuntimeError as e:
        print(f"❌ 创建飞书客户端失败: {e}")
        print("   请检查 .env 中 LARK_APP_ID 和 LARK_APP_SECRET 是否正确配置")
        sys.exit(1)

    engine = PushEngine(
        config=config,
        memory_graph=graph,
        pipeline=None,
        lark_client=lark_client,
    )

    print(f"\n📤 推送中 ({len(sorted_decisions)} 条)...")
    success, fail = push_cards(engine, sorted_decisions)
    print(f"\n{'='*50}")
    print(f"  推送完成: ✅ {success} 条成功, ❌ {fail} 条失败")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()