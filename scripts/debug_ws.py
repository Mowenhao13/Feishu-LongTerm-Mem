"""
WS 调试脚本 — 直接连接飞书 WS，打印所有收到的事件
"""

from __future__ import annotations

import logging
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

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client as WSClient

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.getLogger("Lark").setLevel(logging.DEBUG)

IMPORTANT_EVENTS = []


def on_message(event: P2ImMessageReceiveV1) -> None:
    IMPORTANT_EVENTS.append(("im.message.receive_v1", time.time()))
    print(f"\n{'='*60}")
    print(f"  📩 im.message.receive_v1 事件到达！")
    event_data = getattr(event, "event", None)
    if event_data:
        msg = getattr(event_data, "message", None)
        if msg:
            content = getattr(msg, "content", "?")
            chat_id = getattr(msg, "chat_id", "?")
            sender = getattr(msg, "sender", None)
            sender_id = str(getattr(sender, "id", "")) if sender else "?"
            print(f"  chat_id: {chat_id}")
            print(f"  sender: {sender_id}")
            print(f"  content: {content[:200]}")
            print(f"{'='*60}\n")


app_id = os.getenv("LARK_APP_ID", "")
app_secret = os.getenv("LARK_APP_SECRET", "")

if not app_id or not app_secret:
    print("❌ LARK_APP_ID or LARK_APP_SECRET not set")
    sys.exit(1)

encrypt_key = os.getenv("LARK_ENCRYPT_KEY", "")
verification_token = os.getenv("LARK_VERIFICATION_TOKEN", "")

event_dispatcher = EventDispatcherHandler.builder(
    encrypt_key, verification_token,
).register_p2_im_message_receive_v1(on_message).build()

print(f"{'='*60}")
print(f"  WS 调试 — 监听所有事件")
print(f"  App ID: {app_id[:8]}...")
print(f"  {'='*60}")
print(f"\n  请在群聊中发送一条消息...")
print(f"  等待事件中...")
print(f"  {'='*60}\n")

client = WSClient(
    app_id=app_id,
    app_secret=app_secret,
    log_level=lark.LogLevel.DEBUG if os.getenv("DEBUG") else lark.LogLevel.INFO,
    event_handler=event_dispatcher,
    auto_reconnect=False,
)

import threading
thread = threading.Thread(target=client.start, daemon=True)
thread.start()

try:
    for i in range(120):
        time.sleep(1)
        if IMPORTANT_EVENTS:
            print(f"\n  ✅ 已收到 {len(IMPORTANT_EVENTS)} 个重要事件")
            break
        if i % 10 == 0 and i > 0:
            print(f"  已等待 {i} 秒...")
    if not IMPORTANT_EVENTS:
        print(f"\n  等待超时，未收到 im.message.receive_v1 事件")
finally:
    print(f"\n  调试结束")