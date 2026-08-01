"""从 argusbot_multi_v2/messages.jsonl 提取 expected_decision 生成 expected.jsonl"""
import json

INPUT_PATH = "eval_dataset/argusbot_multi_v2/messages.jsonl"
OUTPUT_PATH = "eval_dataset/argusbot_multi_v2/expected.jsonl"

with open(INPUT_PATH, "r", encoding="utf-8") as f:
    all_messages = [json.loads(line) for line in f if line.strip()]

expected_decisions = []
for msg in all_messages:
    if msg.get("expected_decision"):
        topic = msg.get("expected_topic", "")
        summary = msg.get("expected_summary", "")
        if topic and summary:
            expected = {
                "msg_id": msg.get("msg_id", ""),
                "chat_id": msg.get("chat_id", ""),
                "expected_topic": topic,
                "expected_summary": summary,
                "expected_status": msg.get("expected_status", ""),
                "expected_impact": msg.get("expected_impact", ""),
                "is_suggestion": msg.get("is_suggestion", False),
                "parent_sid": msg.get("parent_sid", ""),
                "granularity_level": msg.get("granularity_level", 0),
            }
            expected_decisions.append(expected)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    for d in expected_decisions:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

print(f"提取完成: 找到 {len(expected_decisions)} 个预期决策 (已过滤空决策)")
print(f"输出文件: {OUTPUT_PATH}")
