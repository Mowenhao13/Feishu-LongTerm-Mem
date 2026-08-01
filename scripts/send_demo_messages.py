#!/usr/bin/env python3
"""
发送演示消息到飞书群聊 — 演示新增决策提取效果

主题：多智能体循环架构 — gRPC通信协议选型
父决策：分层架构方案 (m006)
预期提取决策：采用gRPC作为Agent间通信协议

用法:
    uv run python scripts/send_demo_messages.py [--chat-id CHAT_ID] [--delay DELAY]

默认发送到 chat_0，消息间隔 3 秒。
"""
import argparse
import json
import subprocess
import sys
import time

# 演示消息序列（基于v2数据集chat_0的决策链风格）
MESSAGES = [
    {"speaker": "Alice", "msg": "@Bob @Charlie 刚才我们定了分层架构和错误处理，现在来定Agent间的通信协议。用gRPC还是消息队列？"},
    {"speaker": "Bob", "msg": "我建议用gRPC，Proto定义接口，性能比REST好，而且支持流式通信，适合Agent间的实时状态同步。"},
    {"speaker": "Charlie", "msg": "gRPC选型的话，我们用Python原生grpcio库，还是用grpcio-tools生成代码？考虑到我们需要动态注册Agent，原生库更灵活。"},
    {"speaker": "Eve", "msg": "前端侧，如果后端用gRPC，我需要用gRPC-Web来对接，或者中间加一层Envoy做协议转换。"},
    {"speaker": "Diana", "msg": "用户角度无所谓协议，只要API文档写清楚就行。"},
    {"speaker": "Alice", "msg": "好，就用gRPC，Bob你负责proto文件定义，Charlie准备grpcio环境，Eve评估gRPC-Web方案。"},
]

def send_via_lark_cli(chat_id: str, msg: str, delay: float):
    """通过 lark-cli 发送消息"""
    cmd = [
        "npx", "lark-cli", "im", "send",
        "--chat-id", chat_id,
        "--content", json.dumps({
            "msg_type": "text",
            "content": {"text": msg}
        }, ensure_ascii=False)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ 发送成功: {msg[:50]}...")
        else:
            print(f"❌ 发送失败: {result.stderr}")
    except subprocess.TimeoutExpired:
        print(f"⏰ 发送超时: {msg[:50]}...")
    except Exception as e:
        print(f"❌ 发送异常: {e}")
    
    time.sleep(delay)

def send_via_api(chat_id: str, msg: str, delay: float):
    """通过飞书 OpenAPI 发送消息（需要 lark-oapi）"""
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest, CreateMessageRequestBody
    )
    
    client = lark.ws.Client(
        app_id=os.getenv("LARK_APP_ID"),
        app_secret=os.getenv("LARK_APP_SECRET"),
    )
    
    req = CreateMessageRequest.builder()         .receive_id_type("chat_id")         .request_body(
            CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": msg}, ensure_ascii=False))
                .build()
        )         .build()
    
    try:
        resp = client.im.v1.message.create(req)
        if resp.success():
            print(f"✅ 发送成功: {msg[:50]}...")
        else:
            print(f"❌ 发送失败: {resp.code} {resp.msg}")
    except Exception as e:
        print(f"❌ 发送异常: {e}")
    
    time.sleep(delay)

def main():
    parser = argparse.ArgumentParser(description="发送演示消息到飞书群聊")
    parser.add_argument("--chat-id", default="oc_xxx", help="飞书群聊ID")
    parser.add_argument("--delay", type=float, default=3.0, help="消息间隔(秒)")
    parser.add_argument("--method", choices=["cli", "api"], default="cli",
                       help="发送方式: cli=使用lark-cli, api=使用OpenAPI")
    args = parser.parse_args()
    
    print(f"📤 开始发送 {len(MESSAGES)} 条消息到群聊 {args.chat_id}")
    print(f"   方法: {args.method}, 间隔: {args.delay}s")
    print(f"   主题: 多智能体循环架构 — gRPC通信协议选型")
    print()
    
    send_func = send_via_api if args.method == "api" else send_via_lark_cli
    
    for i, item in enumerate(MESSAGES, 1):
        print(f"[{i}/{len(MESSAGES)}] [{item['speaker']}]")
        send_func(args.chat_id, item["msg"], args.delay)
    
    print()
    print("=" * 60)
    print("✅ 所有消息已发送完成！")
    print()
    print("📊 预期提取的决策:")
    print("   topic: 多智能体循环架构")
    print("   summary: 采用gRPC作为Agent间通信协议")
    print("   status: decided")
    print("   impact_level: major")
    print("   parent_sid: m006 (分层架构方案)")
    print("   granularity_level: 3")
    print("=" * 60)

if __name__ == "__main__":
    main()
