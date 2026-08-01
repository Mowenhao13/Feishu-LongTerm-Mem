#!/usr/bin/env python3
"""修复 index.html 的 data-index 为 0-N 顺序（基于位置替换，避免重复值问题）"""
import re

HTML_PATH = "docs/ppt/index.html"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Find all matches with their positions
matches = list(re.finditer(r'(data-index=")([^"]+)(")', html))
print(f"Found {len(matches)} data-index attributes")

# Replace from end to start to preserve positions
for i, m in enumerate(reversed(matches)):
    idx = len(matches) - 1 - i
    start = m.start()
    end = m.end()
    old_text = m.group(0)
    new_text = f'data-index="{idx}"'
    html = html[:start] + new_text + html[end:]

# Update page indicator
html = re.sub(r'1 / \d+', f'1 / {len(matches)}', html)

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

# Verify
indices = [m.group(1) for m in re.finditer(r'data-index="([^"]+)"', html)]
print(f"New indices: {indices}")
print(f"Total pages: {len(indices)}")
print(f"Expected range: 0-{len(indices)-1}")
assert indices == [str(i) for i in range(len(indices))], "INDICES NOT SEQUENTIAL!"
print("✅ All data-index values are sequential 0 to N-1")
