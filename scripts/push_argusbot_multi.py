"""
向 8 个飞书群聊推送 argusbot_multi_v2 数据集消息（不启动 main.py）

用法：
  uv run python scripts/push_argusbot_multi.py --dataset v2

流程：
  1. 从 .env 读取 GROUP_CHAT_IDS（8 个群聊）
  2. 读取 eval_dataset/argusbot_multi_v2/messages.jsonl
  3. 将 v2 的 46 个频道消息轮流分配到 8 个真实群聊
  4. 每个群聊按消息顺序推送，间隔 1s
"""
from __future__ import annotations

import json
import os
import sys
import time
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

from src.utils.logger import get_logger
logger = get_logger(__name__)

# ==================== Config ====================

MSG_INTERVAL = 1.0          # 消息间隔（秒）
CHAT_INTERVAL = 3.0         # 切换群聊时的额外等待
TOPIC_INTERVAL = 2.0        # 切换话题时的额外等待

# 数据集路径
V1_PATH = PROJECT_ROOT / "eval_dataset" / "argusbot_multi"
V2_PATH = PROJECT_ROOT / "eval_dataset" / "argusbot_multi_v2"


def get_chat_ids() -> list[str]:
    raw = os.environ.get("GROUP_CHAT_IDS", "")
    result = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        cid = entry.split(":", 1)[0].strip()
        if cid:
            result.append(cid)
    return result


def get_group_map() -> dict[str, str]:
    raw = os.environ.get("GROUP_CHAT_IDS", "")
    mapping: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            cid, gname = entry.split(":", 1)
            cid, gname = cid.strip(), gname.strip()
            mapping[cid] = gname
        else:
            cid = entry
            mapping[cid] = cid[:16]
    return mapping


def load_messages(dataset_path: Path) -> list[dict[str, Any]]:
    msg_file = dataset_path / "messages.jsonl"
    if not msg_file.exists():
        print(f"  ❌ 数据集文件不存在: {msg_file}")
        sys.exit(1)
    messages = []
    with open(msg_file) as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def format_msg(msg: dict) -> str:
    speaker = msg.get("speaker", "Unknown")
    content = msg.get("msg", "")
    return f"{speaker}:\n{content}"


def send_to_chat(client, chat_id: str, messages: list[dict], group_name: str) -> int:
    display_name = group_name or chat_id[:16]
    total = len(messages)
    current_topic = None
    sent = 0
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"  📢 向 {display_name} 推送 {total} 条消息")
    print(f"{'='*60}")

    for idx, msg in enumerate(messages, 1):
        topic = msg.get("topic", "") or msg.get("expected_topic", "")
        if topic and topic != current_topic:
            if sent > 0:
                time.sleep(TOPIC_INTERVAL)
            current_topic = topic
            is_decision = msg.get("expected_decision", False)
            print(f"\n  ── [{display_name}] 话题: {topic}" + (" (决策)" if is_decision else "") + " ──")

        text = format_msg(msg)
        try:
            result = client.send_text_message(
                receive_id=chat_id,
                text=text,
                receive_id_type="chat_id",
            )
            print(f"    [{idx}/{total}] 💬 {text[:60]}...", end="")
            if result.message_id:
                print(f" ✅")
            else:
                print(f" ⚠️")
            sent += 1
        except Exception as e:
            print(f"    [{idx}/{total}] ❌ {text[:40]}... error: {e}")

        if idx < total:
            time.sleep(MSG_INTERVAL)

    elapsed = time.time() - start_time
    rate = sent / elapsed if elapsed > 0 else 0
    print(f"  ✅ [{display_name}] 完成: {sent}/{total} 条, 用时 {elapsed:.0f}s, 速率 {rate:.1f} 条/s")
    return sent


def main():
    parser = argparse.ArgumentParser(description="推送 argusbot_multi 数据集到飞书群聊")
    parser.add_argument("--dataset", choices=["v1", "v2"], default="v2",
                        help="数据集版本 (默认 v2)")
    args = parser.parse_args()

    dataset_path = V2_PATH if args.dataset == "v2" else V1_PATH
    dataset_label = "argusbot_multi_v2" if args.dataset == "v2" else "argusbot_multi"

    print(f"{'='*60}")
    print(f"  {dataset_label} 推送器")
    print(f"  数据源: {dataset_path}")
    print(f"  消息间隔: {MSG_INTERVAL}s")
    print(f"{'='*60}")

    chat_ids = get_chat_ids()
    group_map = get_group_map()

    if args.dataset == "v2":
        # v2: 5 个群聊 (chat_0~chat_4) 直接映射
        num_chats = 5
    else:
        # v1: 8 个群聊 (chat_0~chat_7)
        num_chats = 8

    chat_ids = chat_ids[:num_chats]

    if len(chat_ids) < num_chats:
        print(f"  ❌ 需要 {num_chats} 个群聊，当前只有 {len(chat_ids)} 个")
        sys.exit(1)

    print(f"  目标群聊: {[group_map.get(cid, cid[:10]) for cid in chat_ids]}")

    # 加载消息
    all_messages = load_messages(dataset_path)
    print(f"  数据集: {len(all_messages)} 条消息")

    if args.dataset == "v2":
        # v2: chat_0~chat_4 直接一一映射（5个群聊）
        chat_order = [f"chat_{i}" for i in range(num_chats)]
        v2_groups: dict[str, list[dict]] = defaultdict(list)
        for msg in all_messages:
            v2_groups[msg["chat_id"]].append(msg)
        assigned = {}
        for i, cid in enumerate(chat_ids[:num_chats]):
            dataset_cid = chat_order[i]
            assigned[cid] = v2_groups.get(dataset_cid, [])
        total_msgs = sum(len(v) for v in assigned.values())
        print(f"  v2 {num_chats}群聊映射完成")
    else:
        # v1: 按 chat_0~chat_7 顺序一一映射
        chat_order = [f"chat_{i}" for i in range(8)]
        v1_groups: dict[str, list[dict]] = defaultdict(list)
        for msg in all_messages:
            v1_groups[msg["chat_id"]].append(msg)
        assigned = {}
        for i, cid in enumerate(chat_ids[:num_chats]):
            dataset_cid = chat_order[i]
            assigned[cid] = v1_groups.get(dataset_cid, [])
        total_msgs = sum(len(v) for v in assigned.values())
        print(f"  v1 {num_chats}群聊映射完成")

    try:
        from src.adapter.lark_im import create_client_from_env
        client = create_client_from_env()
        print("  ✅ LarkIMClient 创建成功")
    except Exception as e:
        print(f"  ❌ 创建客户端失败: {e}")
        sys.exit(1)

    overall_start = time.time()
    total_sent = 0
    for i, cid in enumerate(chat_ids):
        msgs = assigned.get(cid, [])
        if not msgs:
            print(f"  ⚠️ {group_map.get(cid, cid[:10])}: 没有消息数据")
            continue
        gname = group_map.get(cid, "")
        sent = send_to_chat(client, cid, msgs, gname)
        total_sent += sent

        if i < len(chat_ids) - 1:
            print(f"  等待 {CHAT_INTERVAL}s 后推送下一个群聊...")
            time.sleep(CHAT_INTERVAL)

    overall_elapsed = time.time() - overall_start
    print(f"\n{'='*60}")
    print(f"  全部完成！共推送 {total_sent}/{total_msgs} 条消息到 {len(chat_ids)} 个群聊")
    print(f"  总用时: {overall_elapsed:.0f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
