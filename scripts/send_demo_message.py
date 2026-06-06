"""
快速演示消息发送器 — 向 GROUP_CHAT_IDS 发送 2 条决策性消息

用法（启动 main.py 后 2s 执行）：
  uv run python scripts/send_demo_message.py

流程：
  1. 读取 GROUP_CHAT_IDS 群聊列表（与 main.py 监听群聊一致）
  2. 发送 2 条带有决策内容的测试消息
"""

from __future__ import annotations

import os
import sys
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

logger = get_logger(__name__)

# 2 条带有明确决策性的消息
DEMO_MESSAGES = [
    "大家好，我是UserOnly，我决定前端使用React框架，组件库用Ant Design，构建工具用Vite",
    "项目排期我决定第一阶段3周完成需求分析和核心功能开发，第二阶段2周完成测试和优化，整体6月1日上线",
]


def get_chat_ids() -> list[str]:
    """解析 GROUP_CHAT_IDS 格式: "chat_id1:群名1,chat_id2:群名2"，返回 chat_id 列表"""
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
    """解析 GROUP_CHAT_IDS 格式，返回 {chat_id: group_name} 映射"""
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


def main():
    print(f"{'='*60}")
    print(f"  快速演示消息发送器")
    print(f"  发送 {len(DEMO_MESSAGES)} 条决策消息")
    print(f"{'='*60}")

    chat_ids = get_chat_ids()
    if not chat_ids:
        print("  ❌ GROUP_CHAT_IDS 未配置")
        sys.exit(1)

    group_map = get_group_map()
    print(f"  目标群聊: {[group_map.get(cid, cid[:16]) for cid in chat_ids]}")

    try:
        client = create_client_from_env()
        print("  ✅ LarkIMClient 创建成功")
    except Exception as e:
        print(f"  ❌ 创建客户端失败: {e}")
        sys.exit(1)

    for chat_id in chat_ids:
        print(f"\n  ── 发送到 {chat_id[:16]} ──")
        for i, text in enumerate(DEMO_MESSAGES, 1):
            try:
                result = client.send_text_message(
                    receive_id=chat_id,
                    text=text,
                    receive_id_type="chat_id",
                )
                print(f"    [{i}/{len(DEMO_MESSAGES)}] ✅ {text[:50]}... message_id={result.message_id[:16]}")
            except Exception as e:
                print(f"    [{i}/{len(DEMO_MESSAGES)}] ❌ 发送失败: {e}")

    print(f"\n  ✅ 演示消息发送完成！请检查 main.py 日志输出")


if __name__ == "__main__":
    main()