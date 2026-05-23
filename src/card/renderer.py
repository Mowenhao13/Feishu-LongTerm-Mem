from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel, RelationType


class HotCategory(str, Enum):
    ACTIVE = "active"
    NORMAL = "normal"
    FUZZY = "fuzzy"
    FORGOTTEN = "forgotten"


_STATUS_TEMPLATE: Dict[str, str] = {
    "decided": "green",
    "in_progress": "blue",
    "completed": "green",
    "pending": "yellow",
    "superseded": "red",
    "rejected": "red",
    "deprecated": "red",
    "shelved": "red",
}

_STATUS_EMOJI: Dict[str, str] = {
    "pending": "\u23f0",
    "decided": "\u2705",
    "in_progress": "\U0001f6e0\ufe0f",
    "completed": "\u2705",
    "shelved": "\U0001f4e6",
    "rejected": "\u274c",
    "superseded": "\U0001f504",
    "deprecated": "\U0001f6ab",
}

_STATUS_LABEL: Dict[str, str] = {
    "pending": "\u5f85\u5904\u7406",
    "decided": "\u5df2\u51b3\u5b9a",
    "in_progress": "\u6267\u884c\u4e2d",
    "completed": "\u5df2\u5b8c\u6210",
    "shelved": "\u5df2\u6401\u7f6e",
    "rejected": "\u5df2\u62d2\u7edd",
    "superseded": "\u5df2\u53d6\u4ee3",
    "deprecated": "\u5df2\u5e9f\u5f03",
}

_IMPACT_EMOJI: Dict[str, str] = {
    "advisory": "\u2139\ufe0f",
    "minor": "\U0001f4ca",
    "major": "\u26a1",
    "critical": "\U0001f525",
}


class CardRenderer:
    """决策卡片渲染器

    对应 ref/card/card.go 的 Renderer，输出 Lark 卡片 JSON + Markdown 文本。
    """

    def render_decision_card(self, node: DecisionNode, hot_score: float) -> Dict[str, Any]:
        """渲染单条决策卡片"""
        category = self._get_hot_category(hot_score)
        status_str = node.status.value
        template = _STATUS_TEMPLATE.get(status_str, "blue")
        emoji = _STATUS_EMOJI.get(status_str, "\u2753")
        label = _STATUS_LABEL.get(status_str, status_str)
        impact_emoji = _IMPACT_EMOJI.get(node.impact_level.value, "")

        elements: List[Any] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{emoji} **\u72b6\u6001**: `{label}` | {impact_emoji} **\u5f71\u54cd**: `{node.impact_level.value}`",
                },
            },
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f4cc \u6807\u9898**\n{node.summary}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f3f7\ufe0f \u8bae\u9898**\n{node.topic_id}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f4cb \u63d0\u8bae\u8005**\n{node.authority or '\u672a\u77e5'}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f4c5 \u521b\u5efa**\n{node.created_at.strftime('%m-%d %H:%M') if node.created_at else '-'}"}},
                ],
            },
        ]

        if node.full_text:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**\U0001f4dd \u5185\u5bb9**\n{node.full_text[:300]}"
                                                       f"{'...' if len(node.full_text) > 300 else ''}"},
            })

        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": f"\U0001f525 \u70ed\u70b9\u503c: {hot_score:.0f}/100 ({self._category_label(category)})"}
            ],
        })

        card = {
            "header": {
                "title": {"tag": "plain_text", "content": f"\U0001f4cb \u51b3\u7b56\u5361\u7247 [{node.sid[:8]}]"},
                "template": template,
            },
            "elements": elements,
        }
        return card

    def render_conflict_card(
        self,
        node_a: DecisionNode,
        node_b: DecisionNode,
        reason: str = "",
    ) -> Dict[str, Any]:
        """渲染冲突解决卡片"""
        card = {
            "header": {
                "title": {"tag": "plain_text", "content": "\u26a0\ufe0f \u51b3\u7b56\u51b2\u7a81\u9700\u8981\u786e\u8ba4"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"\u68c0\u6d4b\u5230\u4ee5\u4e0b\u4e24\u4e2a\u51b3\u7b56\u5b58\u5728\u51b2\u7a81\uff1a\n{reason}\n\u8bf7\u9009\u62e9\u4fdd\u7559\u54ea\u4e00\u4e2a\u3002"},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f4cc A: {node_a.summary}**"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f4ca \u5f71\u54cd**: {node_a.impact_level.value}"}},
                    ],
                },
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**\u51b3\u7b56\u5185\u5bb9**: {node_a.full_text[:200]}{'...' if len(node_a.full_text) > 200 else ''}"},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f4cc B: {node_b.summary}**"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**\U0001f4ca \u5f71\u54cd**: {node_b.impact_level.value}"}},
                    ],
                },
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**\u51b3\u7b56\u5185\u5bb9**: {node_b.full_text[:200]}{'...' if len(node_b.full_text) > 200 else ''}"},
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "\u2705 \u4fdd\u7559 A"},
                            "type": "primary",
                            "value": {"action": "conflict_resolve", "winner_sdr": node_a.sid, "loser_sdr": node_b.sid},
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "\u2705 \u4fdd\u7559 B"},
                            "type": "primary",
                            "value": {"action": "conflict_resolve", "winner_sdr": node_b.sid, "loser_sdr": node_a.sid},
                        },
                    ],
                },
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "\u9009\u62e9\u4fdd\u7559\u4e00\u4e2a\u540e\uff0c\u53e6\u4e00\u4e2a\u5c06\u88ab\u6807\u8bb0\u4e3a superseded\u3002\u4e5f\u53ef\u901a\u8fc7 resolve_conflict MCP \u5de5\u5177\u5904\u7406\u3002"}
                    ],
                },
            ],
        }
        return card

    def render_daily_summary_markdown(
        self,
        date: str,
        new_decisions: List[tuple[str, str, float]],
        forgotten_decisions: List[tuple[str, str, float]],
    ) -> str:
        """渲染每日摘要 Markdown 文本（用于终端输出）"""
        lines = [f"# \U0001f4cb \u51b3\u7b56\u65e5\u62a5 - {date}", ""]
        if new_decisions:
            lines.append(f"## \u2728 \u65b0\u589e\u51b3\u7b56 ({len(new_decisions)} \u4e2a)")
            for sid, summary, hot in new_decisions[:5]:
                lines.append(f"- **{summary}** [{sid[:8]}] - \U0001f525{hot:.0f}")
            lines.append("")
        if forgotten_decisions:
            lines.append(f"## \U0001f4a4 \u9057\u5fd8\u51b3\u7b56\u63d0\u9192 ({len(forgotten_decisions)} \u4e2a)")
            for sid, summary, hot in forgotten_decisions[:3]:
                lines.append(f"- **{summary}** [{sid[:8]}] - \U0001f525{hot:.0f}")
            lines.append("")
        return "\n".join(lines)

    # ==================== 辅助 ====================

    @staticmethod
    def _get_hot_category(score: float) -> HotCategory:
        if score >= 80:
            return HotCategory.ACTIVE
        if score >= 50:
            return HotCategory.NORMAL
        if score >= 20:
            return HotCategory.FUZZY
        return HotCategory.FORGOTTEN

    @staticmethod
    def _category_label(cat: HotCategory) -> str:
        return {
            HotCategory.ACTIVE: "\u6d3b\u8dc3",
            HotCategory.NORMAL: "\u6b63\u5e38",
            HotCategory.FUZZY: "\u6a21\u7cca",
            HotCategory.FORGOTTEN: "\u9057\u5fd8",
        }.get(cat, "\u672a\u77e5")