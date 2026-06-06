#!/usr/bin/env python3
"""
将 v2 数据集的决策同步到飞书任务里，按主题分组。
格式参照飞书记忆-决策看板。

用法:
    uv run python scripts/sync_v2_decisions_to_tasks.py

通过环境变量:
    LARK_USER_ACCESS_TOKEN=<token> uv run python scripts/sync_v2_decisions_to_tasks.py
"""
import json
import subprocess
import time
import os
from collections import defaultdict

EXPECTED_PATH = "eval_dataset/argusbot_multi_v2/expected.jsonl"
TASKLIST_NAME = "飞书记忆 - 决策看板 v2"

user_token = os.environ.get("LARK_USER_ACCESS_TOKEN")
if not user_token:
    print("❌ 请设置环境变量 LARK_USER_ACCESS_TOKEN=<token>")
    exit(1)

def lark_task(*args, data=None):
    """调用 lark-cli task 命令，使用 user_access_token"""
    cmd = ["npx", "lark-cli", "task"]
    cmd.extend(args)
    if data:
        cmd.extend(["--data", json.dumps(data)])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LARK_USER_ACCESS_TOKEN": user_token}
    )
    return result

# 1. 读取 expected.jsonl，按主题分组
with open(EXPECTED_PATH, "r", encoding="utf-8") as f:
    decisions = [json.loads(line) for line in f if line.strip()]

topics = defaultdict(list)
for d in decisions:
    topic = d.get("expected_topic", "未分类")
    topics[topic].append(d)

print(f"📊 共 {len(decisions)} 个决策，分为 {len(topics)} 个主题")
for topic, items in topics.items():
    print(f"  - {topic}: {len(items)} 个决策")

# 2. 创建任务清单
print(f"\n📝 创建任务清单: {TASKLIST_NAME}")
result = lark_task("tasklists", "create", data={"name": TASKLIST_NAME})
print(result.stdout)
if result.returncode != 0:
    print(f"❌ 创建任务清单失败: {result.stderr}")
    exit(1)

tasklist_data = json.loads(result.stdout)
tasklist_guid = tasklist_data["data"]["tasklist"]["guid"]
tasklist_url = tasklist_data["data"]["tasklist"]["url"]
print(f"✅ 任务清单已创建: {tasklist_url}")

# 3. 为每个主题创建自定义分组（section）
print("\n📂 创建主题分组...")
topic_section_map = {}
for topic in topics.keys():
    result = lark_task("sections", "create", data={
        "name": topic,
        "resource_type": "tasklist",
        "resource_id": tasklist_guid,
    })
    if result.returncode == 0:
        section_data = json.loads(result.stdout)
        section_guid = section_data["data"]["section"]["guid"]
        topic_section_map[topic] = section_guid
        print(f"  ✅ {topic}: section_guid={section_guid}")
    else:
        print(f"  ❌ {topic} 分组创建失败: {result.stderr}")
    time.sleep(0.5)

# 4. 为每个决策创建任务，放入对应分组
print("\n📋 创建决策任务...")
for topic, items in topics.items():
    print(f"\n  📁 {topic}")
    section_guid = topic_section_map.get(topic)
    
    for i, d in enumerate(items, 1):
        msg_id = d.get("msg_id", "")
        summary = d.get("expected_summary", "")
        status = d.get("expected_status", "")
        impact = d.get("expected_impact", "")
        is_suggestion = d.get("is_suggestion", False)
        parent_sid = d.get("parent_sid", "")
        granularity = d.get("granularity_level", 0)
        chat_id = d.get("chat_id", "")
        
        type_tag = "💡 建议" if is_suggestion else "✅ 决策"
        status_tag = "已确定" if status == "decided" else "待确认"
        impact_tag = {"critical": "🔴 关键", "major": "🟠 重要", "minor": "🟡 一般"}.get(impact, "⚪ 未知")
        
        description_parts = [
            f"{type_tag} | {status_tag} | {impact_tag}",
            f"📍 来源: {chat_id} / m{msg_id}",
        ]
        if parent_sid:
            description_parts.append(f"🔗 父决策: m{parent_sid}")
        description_parts.append(f"📊 粒度等级: L{granularity}")
        
        description = "\n".join(description_parts)
        
        result = lark_task("tasks", "create", data={
            "tasklist_id": tasklist_guid,
            "summary": f"[{topic}] {summary}",
            "description": description,
            "tasklists": [{
                "tasklist_guid": tasklist_guid,
                "section_guid": section_guid,
            }],
        })
        
        if result.returncode == 0:
            task_data = json.loads(result.stdout)
            task_guid = task_data["data"]["task"]["guid"]
            task_url = task_data["data"]["task"]["url"]
            print(f"    ✅ [{i}/{len(items)}] {summary[:30]}... → {task_url}")
            
            if status == "decided":
                result = lark_task("tasks", "patch", data={
                    "guid": task_guid,
                    "is_done": True,
                })
        else:
            print(f"    ❌ 创建失败: {result.stderr[:200]}")
        
        time.sleep(0.3)

print(f"\n🎉 完成！任务清单: {TASKLIST_NAME}")
print(f"🔗 {tasklist_url}")
print(f"\n📊 统计:")
print(f"  - 主题数: {len(topics)}")
print(f"  - 决策总数: {len(decisions)}")
print(f"  - 任务清单 GUID: {tasklist_guid}")
