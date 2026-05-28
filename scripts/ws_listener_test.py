#!/usr/bin/env python3
"""WebSocket 长连接监听指定群聊消息（仅检测，不做决策提取）"""

import os
import sys
import json
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client as WSClient

# 读取 .env
env_path = Path(__file__).resolve().parent.parent / ".env"
app_id = ""
app_secret = ""

for line in env_path.read_text().splitlines():
    line = line.strip()
    if line.startswith("LARK_APP_ID=") and not line.startswith("#"):
        app_id = line.split("=", 1)[1].strip().strip('"').strip("'")
    elif line.startswith("LARK_APP_SECRET=") and not line.startswith("#"):
        app_secret = line.split("=", 1)[1].strip().strip('"').strip("'")

if not app_id or not app_secret:
    print("Error: LARK_APP_ID or LARK_APP_SECRET not found in .env")
    sys.exit(1)

TARGET_CHAT_ID = "oc_fbf3f0d351e33ead43a4c5be0138a0a6"


def on_message(event: P2ImMessageReceiveV1) -> None:
    msg = event.event.message
    chat_id = msg.chat_id if msg else ""
    msg_id = msg.message_id if msg else "unknown"

    if chat_id != TARGET_CHAT_ID:
        return

    sender_id = ""
    if msg and msg.sender:
        sender_id = msg.sender.sender_id.open_id or msg.sender.sender_id.user_id or "unknown"

    content_raw = msg.body.content if msg and msg.body else "{}"
    msg_type = msg.msg_type if msg else "unknown"

    try:
        content = json.loads(content_raw)
        text = content.get("text", content_raw)
    except json.JSONDecodeError:
        text = content_raw

    print(f"\n{'='*60}")
    print(f"📩 收到群聊消息")
    print(f"  chat_id:   {chat_id}")
    print(f"  msg_id:    {msg_id}")
    print(f"  sender:    {sender_id}")
    print(f"  msg_type:  {msg_type}")
    print(f"  content:   {text}")
    print(f"{'='*60}")
    print(f"  ⚠️  仅检测，不做决策提取")


if __name__ == "__main__":
    dispatcher = (
        EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    ws_client = WSClient(
        app_id=app_id,
        app_secret=app_secret,
        log_level=lark.LogLevel.INFO,
        event_handler=dispatcher,
        auto_reconnect=True,
    )

    print(f"🔌 启动 WebSocket 长连接监听...")
    print(f"   目标群聊: {TARGET_CHAT_ID}")
    print(f"   按 Ctrl+C 停止\n")

    try:
        ws_client.start()
    except KeyboardInterrupt:
        print("\n\n👋 已停止监听")
    except Exception as e:
        print(f"\n❌ 连接异常: {e}")
        sys.exit(1)