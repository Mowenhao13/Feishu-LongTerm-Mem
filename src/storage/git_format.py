"""
Decision file rendering and parsing - YAML frontmatter + Markdown.

Translates ref/git/format.go to Python.
Each decision is stored as a .md file with YAML frontmatter between --- markers.

File structure:
  ---
  # YAML frontmatter (decision metadata)
  ---
  # Title
  ## Decision body
  ...
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, Optional

import yaml


class GitFormatError(Exception):
    pass


def render_decision_file(data: Dict[str, Any]) -> str:
    """Render a decision dict to YAML frontmatter + Markdown.

    Translates ref/git/format.go RenderDecisionFile.
    """
    buf = io.StringIO()

    buf.write("---\n")
    yaml.dump(data, buf, allow_unicode=True, indent=2, default_flow_style=False)
    buf.write("---\n\n")

    title = data.get("title", "") or data.get("Title", "")
    if title:
        buf.write(f"# {title}\n\n")

    decision_text = data.get("decision", "") or data.get("Decision", "") or data.get("content", "")
    if decision_text:
        buf.write("## 决策\n\n")
        buf.write(decision_text)
        buf.write("\n\n")

    rationale = data.get("rationale", "") or data.get("Rationale", "")
    if rationale:
        buf.write("## 依据\n\n")
        buf.write(rationale)
        buf.write("\n\n")

    buf.write("## 元数据\n\n")
    for key in ("topic", "status", "impact_level", "proposer", "executor", "decision_role"):
        val = data.get(key, "") or data.get(key.title(), "")
        if val:
            label = {"decision_role": "决策角色"}.get(key, key.replace("_", " ").title())
            buf.write(f"- **{label}**: {val}\n")

    return buf.getvalue()


def parse_decision_file(data: str) -> Dict[str, Any]:
    """Parse a YAML frontmatter + Markdown decision file.

    Translates ref/git/format.go ParseDecisionFile.
    Returns the YAML frontmatter as a dict.
    """
    frontmatter = _extract_frontmatter(data)
    if not frontmatter:
        raise GitFormatError("no frontmatter found")
    return yaml.safe_load(frontmatter)


def render_objection_file(data: Dict[str, Any]) -> str:
    """Render an objection dict to YAML frontmatter + Markdown.

    Translates ref/git/format.go RenderObjectionFile.
    """
    buf = io.StringIO()

    buf.write("---\n")
    yaml.dump(data, buf, allow_unicode=True, indent=2, default_flow_style=False)
    buf.write("---\n\n")

    content = data.get("objection_content", "") or data.get("ObjectionContent", "")
    if content:
        buf.write(f"# Objection: {content}\n\n")

    rationale = data.get("rationale", "") or data.get("Rationale", "")
    if rationale:
        buf.write("## 理由\n\n")
        buf.write(rationale)
        buf.write("\n\n")

    alternative = data.get("alternative", "") or data.get("Alternative", "")
    if alternative:
        buf.write("## 替代方案\n\n")
        buf.write(alternative)
        buf.write("\n\n")

    for key in ("objector", "status", "references_decision", "source_type"):
        val = data.get(key, "") or data.get(
            "".join(part.title() for part in key.split("_")), ""
        )
        if val:
            label = {
                "objector": "反对人",
                "references_decision": "关联决策",
                "source_type": "来源",
            }.get(key, key.replace("_", " ").title())
            buf.write(f"- **{label}**: {val}\n")

    return buf.getvalue()


def parse_objection_file(data: str) -> Dict[str, Any]:
    """Parse a YAML frontmatter + Markdown objection file.

    Translates ref/git/format.go ParseObjectionFile.
    """
    frontmatter = _extract_frontmatter(data)
    if not frontmatter:
        raise GitFormatError("no frontmatter found")
    return yaml.safe_load(frontmatter)


def format_decision_summary(data: Dict[str, Any]) -> str:
    """Format a decision dict into a concise summary line.

    Translates ref/git/format.go FormatDecisionNode.
    """
    sid = data.get("sid", "") or data.get("SDRID", "") or data.get("id", "")
    title = data.get("title", "") or data.get("Title", "")
    topic = data.get("topic_id", "") or data.get("topic", "") or data.get("Topic", "")
    status = data.get("status", "") or data.get("Status", "")
    impact = data.get("impact_level", "") or data.get("ImpactLevel", "")

    return f"[{sid}] {title}\n  Topic: {topic} | Status: {status} | Impact: {impact}"


def _extract_frontmatter(data: str) -> Optional[str]:
    in_frontmatter = False
    lines = []
    for line in data.split("\n"):
        stripped = line.strip()
        if stripped == "---":
            if not in_frontmatter:
                in_frontmatter = True
            else:
                break
        elif in_frontmatter:
            lines.append(line)
    return "\n".join(lines) if lines else None