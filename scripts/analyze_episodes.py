"""
分析 Hypergraph 中所有 episode 的详情
输出每个 episode 的内容摘要、时间、类型、话题等信息
帮助找出为何有 58 个 episode
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_hypergraph() -> dict:
    path = PROJECT_ROOT / "data" / "hypergraph" / "state.json"
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_content_text(msg: dict) -> str:
    """从 original_data 的消息中提取纯文本内容"""
    content = msg.get("content", "")
    if isinstance(content, str):
        # 尝试解析 JSON 格式
        if content.startswith("{") and '"text"' in content:
            try:
                return json.loads(content).get("text", content)
            except json.JSONDecodeError:
                pass
        return content
    return str(content)


def summarize_episode(ep: dict) -> str:
    """生成 episode 的内容摘要（取前几条消息）"""
    msgs = ep.get("original_data", [])
    texts = [extract_content_text(m) for m in msgs[:3]]
    if not texts:
        return "(empty)"
    summary = " | ".join(texts)
    if len(summary) > 120:
        summary = summary[:120] + "..."
    return summary


def main():
    data = load_hypergraph()
    episodes: dict = data.get("episodes", {})

    print("=" * 80)
    print(f"总共 {len(episodes)} 个 Episode")
    print("=" * 80)

    # 按 type/ 话题分组统计
    type_groups: dict = defaultdict(list)
    subject_groups: dict = defaultdict(list)
    hyperedge_groups: dict = defaultdict(list)
    hourly_dist: dict = defaultdict(int)

    ep_list = []
    for ep_id, ep in sorted(episodes.items()):
        ep_type = ep.get("type") or "None"
        subject = ep.get("subject") or "(无主题)"
        msg_count = len(ep.get("original_data", []))
        ts_str = ep.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else None
        except Exception:
            ts = None

        # hyperedge 信息
        he = ep.get("hyperedge", {})

        summary = summarize_episode(ep)

        ep_info = {
            "id": ep_id,
            "type": ep_type,
            "subject": subject,
            "msg_count": msg_count,
            "timestamp": ts,
            "hyperedge": he,
            "summary": summary,
        }
        ep_list.append(ep_info)

        type_groups[ep_type].append(ep_id)
        subject_groups[subject].append(ep_id)
        for he_id, he_role in he.items():
            hyperedge_groups[he_id].append(ep_id)

        if ts:
            hour_key = f"{ts.strftime('%Y-%m-%d %H:00')}"
            hourly_dist[hour_key] += 1

    # --- 按时间输出 ---
    print("\n## 1. 按时间排序输出\n")
    ep_list_sorted = sorted(ep_list, key=lambda x: x["timestamp"] or datetime.min)
    for i, ep in enumerate(ep_list_sorted, 1):
        ts_str = ep["timestamp"].strftime("%m-%d %H:%M:%S") if ep["timestamp"] else "N/A"
        he_str = "; ".join(f"{k}={v}" for k, v in ep["hyperedge"].items()) if ep["hyperedge"] else "no hyperedge"
        print(f"[{i:2d}] {ep['id']:<24s} | {ts_str} | type={ep['type']:<12s} | msgs={ep['msg_count']:2d} | {he_str}")
        print(f"     主题={ep['subject']:<20s} | {ep['summary']}")
        print()

    # --- 按 type 分组统计 ---
    print("\n## 2. 按 type 分组统计\n")
    for t, ids in sorted(type_groups.items(), key=lambda x: -len(x[1])):
        print(f"  {t:<15s}: {len(ids):2d} 个 episode")

    # --- 按 subject 分组统计 ---
    print("\n## 3. 按 subject 分组统计\n")
    for s, ids in sorted(subject_groups.items(), key=lambda x: -len(x[1])):
        print(f"  {s:<30s}: {len(ids):2d} 个 episode")

    # --- 按 hyperedge 分组统计 ---
    print("\n## 4. 按 hyperedge（话题分组）统计\n")
    for he_id, ids in sorted(hyperedge_groups.items(), key=lambda x: -len(x[1])):
        # 打印每个 hyperedge 的第一个和最后一个 episode 的时间
        ep_times = []
        for ep in ep_list:
            if ep["id"] in ids and ep["timestamp"]:
                ep_times.append(ep["timestamp"])
        time_range = f"{min(ep_times).strftime('%m-%d %H:%M')} ~ {max(ep_times).strftime('%m-%d %H:%M')}" if ep_times else "N/A"
        print(f"  {he_id:<30s}: {len(ids):2d} 个 episode | {time_range}")

    # --- 按小时分布 ---
    print("\n## 5. 按小时分布\n")
    for hour, count in sorted(hourly_dist.items()):
        bar = "#" * count
        print(f"  {hour}: {count:2d} {bar}")

    # --- 消息总量 ---
    total_msgs = sum(len(ep.get("original_data", [])) for ep in episodes.values())
    print(f"\n## 6. 消息总量: {total_msgs}\n")

    # --- 分析：可能重复的场景 ---
    print("\n## 7. 可能重复/相似的分析\n")
    
    # 7a. 相同 subject + 相同 type 的
    print("### 7a. 相同 subject+type 的可能重复\n")
    combo_groups = defaultdict(list)
    for ep in ep_list:
        key = (ep["subject"], ep["type"])
        combo_groups[key].append(ep)
    for (subj, typ), eps in sorted(combo_groups.items(), key=lambda x: -len(x[1])):
        if len(eps) < 2:
            continue
        print(f"  subject='{subj}' type='{typ}': {len(eps)} 个 episode")
        for e in eps:
            ts_str = e["timestamp"].strftime("%m-%d %H:%M:%S") if e["timestamp"] else "N/A"
            print(f"    - {e['id']} ({ts_str}, msgs={e['msg_count']})")
        print()

    # 7b. 消息内容高度相似的
    print("### 7b. 内容相似度高的\n")
    from difflib import SequenceMatcher
    summaries = [(ep["id"], ep["summary"]) for ep in ep_list if ep["summary"] != "(empty)"]
    for i in range(len(summaries)):
        for j in range(i + 1, len(summaries)):
            id1, s1 = summaries[i]
            id2, s2 = summaries[j]
            ratio = SequenceMatcher(None, s1, s2).ratio()
            if ratio > 0.4:
                print(f"  相似度 {ratio:.2f}:")
                print(f"    [{id1}] {s1}")
                print(f"    [{id2}] {s2}")
                print()


if __name__ == "__main__":
    main()