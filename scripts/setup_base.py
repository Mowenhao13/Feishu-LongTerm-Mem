"""
创建飞书多维表格 Base 和数据表

如果 Base 已存在（检测到 .view_meta.json），则直接输出 Base 信息。
否则自动创建一个新的 Base 和决策数据表。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.view import is_bitable_enabled
from src.view.client import BaseViewClient


def main():
    print("=" * 60)
    print("  飞书多维表格 — 决策看板初始化")
    print("=" * 60)

    if not is_bitable_enabled():
        print("\n  ❌ BITABLE_ENABLED=false，跳过多维表格操作")
        print("  如需启用，在 .env 中设置 BITABLE_ENABLED=true")
        sys.exit(1)

    client = BaseViewClient()

    print("\n[1/2] 创建/检测 Base...")
    try:
        base_token = client.ensure_base("feishu-mem-决策看板")
        print(f"  ✅ Base token: {base_token}")
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    print("\n[2/2] 创建/检测数据表...")
    try:
        table_id = client.ensure_table()
        print(f"  ✅ Table ID: {table_id}")
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    print("\n" + "-" * 60)
    print("  Base 创建/就绪！")
    print(f"  链接: https://bytedance.feishu.cn/base/{client._base_token}")
    print(f"  表名: 决策列表")
    print("-" * 60)


if __name__ == "__main__":
    main()