"""
全量演示消息发送器 — 向 GROUP_CHAT_IDS 所有群聊发送 UserOnly 演示消息

用法：
  uv run python scripts/send_message.py

流程：
  1. 读取 GROUP_CHAT_IDS 所有群聊
  2. 逐个群聊分批发送全部消息（无测试阶段，直接全量）
  3. 每批 20 条，批次间隔 10s（大于 IM 检测器突发间隔 5s）
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

from src.adapter.lark_im import create_client_from_env
from src.utils.logger import get_logger
from eval_data.user_only_messages import ALL_MESSAGES, BATCH_SIZE, BATCH_INTERVAL, MSG_INTERVAL

logger = get_logger(__name__)


def get_chat_ids() -> list[str]:
    raw = os.environ.get("GROUP_CHAT_IDS", "")
    return [cid.strip() for cid in raw.split(",") if cid.strip()]


def send_to_chat(client, chat_id: str) -> int:
    """向单个群聊分批发送所有消息，返回发送成功数"""
    total = len(ALL_MESSAGES)
    batches = [ALL_MESSAGES[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    total_sent = 0
    start_time = time.time()

    print(f"\n  ── 发送到群聊 {chat_id[:16]} ({total} 条, {len(batches)} 批) ──")

    for batch_idx, batch in enumerate(batches, 1):
        batch_start = time.time()
        for msg_idx, msg in enumerate(batch, 1):
            global_idx = total_sent + msg_idx
            try:
                result = client.send_text_message(
                    receive_id=chat_id,
                    text=msg.text,
                    receive_id_type="chat_id",
                )
                print(f"    [{global_idx}/{total}] ✅ {msg.text[:50]}")
            except Exception as e:
                print(f"    [{global_idx}/{total}] ❌ {msg.text[:30]}... error: {str(e)[:60]}")

            if msg_idx < len(batch):
                time.sleep(MSG_INTERVAL)

        total_sent += len(batch)
        elapsed = time.time() - batch_start
        total_elapsed = time.time() - start_time
        rate = total_sent / total_elapsed if total_elapsed > 0 else 0
        remaining = (total - total_sent) / rate if rate > 0 else 0
        print(f"    批次 {batch_idx}/{len(batches)} 完成: 已发送 {total_sent}/{total}, "
              f"已用 {total_elapsed:.0f}s, 预计剩余 {remaining:.0f}s")

        if batch_idx < len(batches):
            print(f"    等待 {BATCH_INTERVAL}s 后发送下一批...")
            time.sleep(BATCH_INTERVAL)

    return total_sent


def main():
    print(f"{'='*60}")
    print(f"  飞书演示消息发送器")
    print(f"  发送者: UserOnly | 消息总数: {len(ALL_MESSAGES)}")
    print(f"  批次: {BATCH_SIZE}条/批 | 间隔: {BATCH_INTERVAL}s")
    print(f"{'='*60}")

    chat_ids = get_chat_ids()
    if not chat_ids:
        print("  ❌ GROUP_CHAT_IDS 未配置")
        sys.exit(1)

    print(f"  目标群聊: {chat_ids}")

    try:
        client = create_client_from_env()
        print("  ✅ LarkIMClient 创建成功")
    except Exception as e:
        print(f"  ❌ 创建客户端失败: {e}")
        sys.exit(1)

    overall_start = time.time()
    grand_total = 0
    for chat_id in chat_ids:
        sent = send_to_chat(client, chat_id)
        grand_total += sent

    total_time = time.time() - overall_start
    print(f"\n{'='*60}")
    print(f"  🎉 全部发送完成！")
    print(f"  总计: {grand_total} 条 | 用时: {total_time:.0f}s | "
          f"速率: {grand_total/total_time:.1f} 条/秒")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()