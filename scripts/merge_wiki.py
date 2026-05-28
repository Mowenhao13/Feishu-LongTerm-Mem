#!/usr/bin/env python3
"""将 docs/wiki 下所有 md 文件按 wiki.json 顺序合并为单文件技术报告书"""

import json
import re
import sys
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parent.parent / "docs" / "wiki"
JSON_PATH = WIKI_DIR / "wiki.json"
OUTPUT = WIKI_DIR / "technical-report.md"


def load_index() -> list[dict]:
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("pages", [])


def file_for(page: dict) -> Path | None:
    title = page["title"]
    base_stem = title.replace(":", " -").replace("/", " ")
    for d in WIKI_DIR.iterdir():
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix != ".md":
                continue
            fs = f.stem
            if fs == base_stem or fs.startswith(base_stem[:15]):
                return f
    return None


def make_anchor(title: str) -> str:
    """生成与主流 Markdown 渲染器兼容的锚点 ID"""
    s = title.lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    s = s.strip("-")
    return s


def strip_cross_refs(text: str) -> str:
    """移除 markdown 中的跨文档链接（相对路径引用），仅保留显示文本"""
    return re.sub(r'\[([^\]]+)\]\((?![a-zA-Z][a-zA-Z0-9+.-]*://)[^)]+\)', r'\1', text)


def main():
    if not WIKI_DIR.is_dir():
        print(f"Error: {WIKI_DIR} not found", file=sys.stderr)
        sys.exit(1)

    ordered = load_index()
    parts: list[str] = []
    toc_lines: list[str] = []

    parts.append("# 飞书长期记忆系统 - 技术报告书\n")
    parts.append("\n> 基于 Feishu-LongTerm-Mem 项目的完整技术说明\n")
    parts.append("---\n")

    toc_lines.append("## 目录\n")
    for i, p in enumerate(ordered):
        anchor = make_anchor(p["title"])
        toc_lines.append(f"{i+1}. [{p['title']}](#{anchor})")
    toc_lines.append("")
    parts.append("\n".join(toc_lines))
    parts.append("---\n")

    for page in ordered:
        fpath = file_for(page)
        if fpath is None:
            parts.append(f'\n## {page["title"]}\n\n*（文件未找到）*\n')
            continue

        raw = fpath.read_text(encoding="utf-8")
        raw = strip_cross_refs(raw)

        merged = [f'\n# {page["title"]}\n']
        for line in raw.splitlines():
            if re.match(r"^#{1,6}\s", line):
                lvl = len(line.split()[0])
                new_lvl = 1 + lvl
                if new_lvl > 6:
                    new_lvl = 6
                merged.append("#" * new_lvl + line[lvl:])
            else:
                merged.append(line)
        merged.append("")
        parts.append("\n".join(merged))

    OUTPUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"✅ 已生成：{OUTPUT}")
    print(f"   共 {len(ordered)} 个章节，{OUTPUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()