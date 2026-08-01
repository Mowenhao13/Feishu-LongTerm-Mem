"""Convert eval_dataset JSONL files to test_data.txt format for --eval mode.

Adds simulated timestamps to mimic real group chat message timing:
- Normal messages: 30-120s apart (within same topic burst)
- Topic boundaries: inserted before expected_decision messages and chat_id switches
- Multi-chat: separate chat_ids get independent timestamps
"""

import argparse
import json
import os
import sys
import random

# Default time gap between messages (seconds)
NORMAL_GAP_MIN = 30
NORMAL_GAP_MAX = 120
# Gap at topic/decision boundaries — small enough to keep discussion + decision
# in the same episode (episode time threshold is 30min = 1800s)
TOPIC_GAP_MIN = 300
TOPIC_GAP_MAX = 600


def convert_jsonl_to_test_data(messages_path, output_path, add_timestamps: bool = True):
    """Convert messages.jsonl to test_data.txt format with optional timestamps."""
    with open(messages_path, "r", encoding="utf-8") as fin:
        lines = fin.readlines()

    # Parse all messages
    messages = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        messages.append(msg)

    # Add simulated timestamps using expected_decision as topic boundary markers
    if add_timestamps:
        base_ts = 1700000000  # Fixed base timestamp
        chat_ts: dict[str, int] = {}

        for msg in messages:
            chat_id = msg.get("chat_id", "chat_0")

            if chat_id not in chat_ts:
                chat_ts[chat_id] = base_ts

            prev_ts = chat_ts[chat_id]
            is_decision = msg.get("expected_decision", False)

            if is_decision:
                gap = random.randint(TOPIC_GAP_MIN, TOPIC_GAP_MAX)
            else:
                gap = random.randint(NORMAL_GAP_MIN, NORMAL_GAP_MAX)

            chat_ts[chat_id] += gap
            msg["timestamp"] = chat_ts[chat_id]
            prev_msg = msg.get("msg", "")

    # Write in test_data.txt format: each line is a JSON dict with msg + timestamp
    with open(output_path, "w", encoding="utf-8") as fout:
        for msg in messages:
            fout.write(json.dumps(msg, ensure_ascii=False) + "\n")

    print(f"Converted {len(messages)} messages from {messages_path} -> {output_path}")
    if add_timestamps:
        first_ts = messages[0].get("timestamp", 0)
        last_ts = messages[-1].get("timestamp", 0)
        span_min = (last_ts - first_ts) / 60.0
        decision_count = sum(1 for m in messages if m.get("expected_decision", False))
        print(f"  Timestamp span: {span_min:.0f} min ({last_ts - first_ts}s)")
        print(f"  Topic boundaries (expected_decision markers): {decision_count}")
    return len(messages)


def count_expected_decisions(expected_path):
    """Count expected decisions from expected.jsonl."""
    with open(expected_path, "r", encoding="utf-8") as fin:
        lines = fin.readlines()

    decisions = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        dec = json.loads(line)
        decisions.append(dec)

    print(f"  Expected decisions: {len(decisions)}")
    for d in decisions[:10]:
        print(f"    - [{d.get('chat_id', 'N/A')}] {d['expected_topic']}: {d['expected_summary'][:60]}...")
    if len(decisions) > 10:
        print(f"    ... and {len(decisions) - 10} more")
    return decisions


def main():
    parser = argparse.ArgumentParser(description="Convert eval_dataset to eval format")
    parser.add_argument("--dataset", required=True, help="Dataset name (e.g., test_small, single_chat, multi_chat)")
    parser.add_argument("--base-dir", default=os.path.join(os.path.dirname(__file__), "..", "eval_dataset"), help="Base directory for eval_dataset")
    parser.add_argument("--output-dir", default=os.path.join(os.path.dirname(__file__), "..", "eval_data"), help="Output directory")
    args = parser.parse_args()

    dataset_dir = os.path.join(args.base_dir, args.dataset)
    messages_path = os.path.join(dataset_dir, "messages.jsonl")
    expected_path = os.path.join(dataset_dir, "expected.jsonl")

    if not os.path.exists(messages_path):
        print(f"Error: {messages_path} not found")
        sys.exit(1)

    output_txt = os.path.join(args.output_dir, f"{args.dataset}_converted.jsonl")

    print(f"=== Converting {args.dataset} ===")
    msg_count = convert_jsonl_to_test_data(messages_path, output_txt)

    if os.path.exists(expected_path):
        print(f"  Standard answers:")
        count_expected_decisions(expected_path)

    print(f"\n  Run eval with:")
    print(f"    python main.py --eval --input {output_txt} --delay 0 --group-num 1")


if __name__ == "__main__":
    main()
