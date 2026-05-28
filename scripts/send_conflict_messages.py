#!/usr/bin/env python3
"""将 conflict_chat_data.txt 中的消息逐条发送到指定飞书群聊"""

import json
import os
import sys
import time
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

# 读取 .env 获取凭据
env_path = Path(__file__).resolve().parent.parent / ".env"
app_id = ""
app_secret = ""
chat_id = "oc_fbf3f0d351e33ead43a4c5be0138a0a6"

for line in env_path.read_text().splitlines():
    line = line.strip()
    if line.startswith("LARK_APP_ID=") and not line.startswith("#"):
        app_id = line.split("=", 1)[1].strip().strip('"').strip("'")
    elif line.startswith("LARK_APP_SECRET=") and not line.startswith("#"):
        app_secret = line.split("=", 1)[1].strip().strip('"').strip("'")

if not app_id or not app_secret:
    print("Error: LARK_APP_ID or LARK_APP_SECRET not found in .env")
    sys.exit(1)

client = (
    lark.Client.builder()
    .app_id(app_id)
    .app_secret(app_secret)
    .log_level(lark.LogLevel.ERROR)
    .build()
)

msg_file = Path(__file__).resolve().parent.parent / "eval_data" / "conflict_chat_data.txt"
messages = [line.strip() for line in msg_file.read_text().splitlines() if line.strip()]

print(f"准备发送 {len(messages)} 条消息到群聊 {chat_id}")
print("---")

for i, text in enumerate(messages, 1):
    body = (
        CreateMessageRequestBody.builder()
        .receive_id(chat_id)
        .msg_type("text")
        .content(json.dumps({"text": text}, ensure_ascii=False))
        .build()
    )
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(body)
        .build()
    )
    resp = client.im.v1.message.create(request)

    if resp.success():
        msg_id = resp.data.message_id
        print(f"[{i:02d}/{len(messages)}] ✅ 已发送 | {text[:40]}... | msg_id={msg_id}")
    else:
        print(f"[{i:02d}/{len(messages)}] ❌ 失败 | {text[:40]}... | code={resp.code} msg={resp.msg}")

    time.sleep(0.3)

print("---")
print("全部发送完成")