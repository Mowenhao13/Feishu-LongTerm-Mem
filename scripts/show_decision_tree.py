"""展示完整的决策森林 — 所有根决策及其递归后代，无需参数

用法:
  python scripts/show_decision_tree.py           # 树状格式
  python scripts/show_decision_tree.py --json    # 原始 JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

import os

from src.mcp_server.server import _loader, show_tree


def _tree_lines(sid: str, graph, indent: int = 0, prefix: str = "", is_last: bool = True) -> List[str]:
    node = graph.get_decision(sid)
    if not node:
        return []
    connector = "└─ " if is_last else "├─ "
    label = f"{prefix}{connector}" if indent > 0 else ""
    summary = node.summary[:55] if node.summary else "(无摘要)"
    hot = f" 🔥{node.access_stats.hot_score:.0f}" if node.access_stats and node.access_stats.hot_score else ""
    if indent == 0:
        line = f"🟢 {node.sid[:12]}  {summary}{hot}  ← 根决策"
    else:
        line = f"{label}{node.sid[:12]}  {summary}{hot}"

    children = graph.get_children_of(sid)
    lines = [line]

    for i, child in enumerate(children):
        child_is_last = i == len(children) - 1
        child_prefix = prefix + ("    " if is_last else "│   ")
        sub_lines = _tree_lines(child.sid, graph, indent + 1, child_prefix, child_is_last)
        lines.extend(sub_lines)
    return lines


def render_tree(decisions: List, graph) -> str:
    roots = [d for d in decisions if not d.parent_id]
    lines = []
    lines.append(f"  总决策: {len(decisions)}  根决策: {len(roots)}")
    lines.append("")
    for root in roots:
        root_lines = _tree_lines(root.sid, graph)
        lines.extend(root_lines)
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="展示完整决策森林")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = parser.parse_args()

    _loader.ensure_loaded()
    graph = _loader.graph
    all_decisions = graph.get_all_decisions()

    if args.json:
        print(show_tree())
        return

    if not all_decisions:
        print("❌ 没有决策数据")
        sys.exit(1)

    tree_str = render_tree(all_decisions, graph)
    print()
    print("=" * 70)
    print("  决策森林")
    print("=" * 70)
    print()
    print(tree_str)
    print("=" * 70)
    print(f"  工具: decision_children / decision_descendants / decision_ancestors / show_tree")
    print("=" * 70)


if __name__ == "__main__":
    main()