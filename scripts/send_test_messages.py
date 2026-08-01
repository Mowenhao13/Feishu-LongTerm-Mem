#!/usr/bin/env python3
"""
测试消息发送脚本
功能:
  1. 列出 Git 仓库中所有决策（遍历 decision/* 分支）
  2. 将 data/test_messages_topic*.txt 转成 JSON 发送到指定飞书群聊

用法:
  python scripts/send_test_messages.py [--list-only]

注意:
  - 发送目标: oc_fbf3f0d351e33ead43a4c5be0138a0a6
  - 不会发送到 GROUP_CHAT_IDS 配置的群聊
  - 通过 --list-only 仅列出决策不发送消息
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_storage_path
from src.storage.git_storage import GitStorage, GitStorageConfig, GitStorageError
from src.adapter.lark_im import LarkIMClient, LarkIMConfig, MessageContent


TARGET_CHAT_ID = "oc_fbf3f0d351e33ead43a4c5be0138a0a6"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def create_storage() -> GitStorage:
    return GitStorage(GitStorageConfig(work_dir=get_storage_path()))


def list_all_decisions() -> list[dict]:
    """遍历 decision/* 分支，读取每个分支最新版本的决策，按树形结构展示"""
    storage = create_storage()
    branches = storage.list_decision_branches()
    print(f"\n{'='*60}")
    print(f"所有决策（共 {len(branches)} 条）")
    print(f"{'='*60}")

    decisions = []
    for branch in sorted(branches):
        sid = branch.replace("decision/", "", 1)
        try:
            d = storage.read_decision_from_branch(branch, sid)
            decisions.append(d)
        except GitStorageError as e:
            print(f"  [ERR] {branch}: {e}")

    # 按 parent_id 构建树
    parent_map: dict[str, list[dict]] = {}
    root_nodes: list[dict] = []
    for d in decisions:
        pid = d.get("parent_id", "") or ""
        if pid:
            parent_map.setdefault(pid, []).append(d)
        else:
            root_nodes.append(d)

    def print_tree(node: dict, depth: int = 0, prefix: str = ""):
        sid = node.get("sid", "")
        v = node.get("version", "?")
        if isinstance(v, str):
            try:
                v = int(v.lstrip("v").split(".")[0])
            except (ValueError, IndexError):
                v = "?"
        status = node.get("status", "")
        title = node.get("title", "") or node.get("summary", "") or "(无标题)"
        topic = node.get("topic_id", "")
        indent = "  " * depth
        marker = "├── " if depth > 0 else ""
        print(f"  {indent}{marker}v{v:<3} [{status:<10}] {sid[:12]:<14} {topic:<16} {title[:50]}")
        for child in parent_map.get(node.get("sid", ""), []):
            print_tree(child, depth + 1)

    for root in root_nodes:
        print_tree(root, 0)

    # 打印独立节点（非树中但已有 parent_id 指向不存在的父节点）
    all_in_tree = {d.get("sid") for d in decisions}
    in_tree_sids = set()
    for d in decisions:
        pid = d.get("parent_id", "")
        if pid and pid in parent_map:
            in_tree_sids.add(d.get("sid"))
    orphans = [d for d in decisions if d.get("sid") not in {r.get("sid") for r in root_nodes}
               and d.get("sid") not in in_tree_sids]
    if orphans:
        for d in orphans:
            sid = d.get("sid", "")
            v = d.get("version", "?")
            if isinstance(v, str):
                try:
                    v = int(v.lstrip("v").split(".")[0])
                except (ValueError, IndexError):
                    v = "?"
            status = d.get("status", "")
            title = d.get("title", "") or d.get("summary", "") or "(无标题)"
            topic = d.get("topic_id", "")
            print(f"  (孤立) v{v:<3} [{status:<10}] {sid[:12]:<14} {topic:<16} {title[:50]}")

    return decisions


def load_messages(txt_path: Path) -> list[str]:
    with open(txt_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def save_messages_as_json(txt_path: Path) -> Path:
    """将 txt 消息转为 JSON 文件并保存"""
    messages = load_messages(txt_path)
    json_path = txt_path.with_suffix(".json")
    data = {
        "source": txt_path.stem,
        "total": len(messages),
        "messages": [{"seq": i + 1, "content": msg} for i, msg in enumerate(messages)],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[JSON] 已保存: {json_path} ({len(messages)} 条)")
    return json_path


def create_lark_client() -> LarkIMClient:
    config = LarkIMConfig(
        app_id=os.environ.get("LARK_APP_ID", ""),
        app_secret=os.environ.get("LARK_APP_SECRET", ""),
        encrypt_key=os.environ.get("LARK_ENCRYPT_KEY", ""),
        verification_token=os.environ.get("LARK_VERIFICATION_TOKEN", ""),
    )
    if not config.app_id or not config.app_secret:
        print("[ERR] LARK_APP_ID 和 LARK_APP_SECRET 必须在 .env 中设置")
        sys.exit(1)
    return LarkIMClient(config)


def send_messages_to_chat(messages: list[str], label: str = ""):
    """将消息逐条发送到指定飞书群聊"""
    client = create_lark_client()
    total = len(messages)
    sent = 0

    print(f"\n{'='*60}")
    print(f"发送 {label} ({total} 条) → {TARGET_CHAT_ID}")
    print(f"{'='*60}")

    for i, msg in enumerate(messages):
        try:
            content = MessageContent.text(msg)
            client.send_message(
                receive_id=TARGET_CHAT_ID,
                msg_content=content,
                receive_id_type="chat_id",
            )
            sent += 1
            print(f"  [{i+1}/{total}] ✓ {msg[:50]}{'…' if len(msg) > 50 else ''}")
        except Exception as e:
            print(f"  [{i+1}/{total}] ✗ 发送失败: {e}")

        if (i + 1) % 5 == 0 and i + 1 < total:
            time.sleep(2)

    print(f"\n{label}: 成功 {sent}/{total} 条")
    return sent


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list-only":
        list_all_decisions()
        return

    # 1. 列出所有决策
    list_all_decisions()

    # 2. 将 txt 转为 JSON
    topic1_txt = DATA_DIR / "test_messages_topic1.txt"
    topic2_txt = DATA_DIR / "test_messages_topic2.txt"

    for txt in [topic1_txt, topic2_txt]:
        if not txt.exists():
            print(f"[ERR] 文件不存在: {txt}")
            continue
        save_messages_as_json(txt)

    # 3. 发送消息到飞书
    print(f"\n{'#'*60}")
    print(f"即将发送测试消息到群聊 {TARGET_CHAT_ID}")
    print(f"按 Enter 继续，Ctrl+C 取消...")
    print(f"{'#'*60}")
    try:
        input()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)

    for txt, label in [(topic1_txt, "话题1-后端服务架构升级"), (topic2_txt, "话题2-前端监控与性能优化")]:
        if txt.exists():
            messages = load_messages(txt)
            send_messages_to_chat(messages, label)

    print(f"\n全部完成")


if __name__ == "__main__":
    main()