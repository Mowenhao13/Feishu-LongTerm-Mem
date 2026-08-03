"""对比报告生成器

读取两组实验的结构化指标 JSON，生成 markdown 对比报告。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _pct_change(old: float, new: float) -> str:
    """计算百分比变化，返回格式化的字符串"""
    if old == 0:
        return "N/A"
    change = (new - old) / old * 100
    prefix = "+" if change > 0 else ""
    return f"{prefix}{change:.1f}%"


def _bar(value: float, max_value: float, width: int = 20) -> str:
    """生成 ASCII 柱状图"""
    bar_len = int(value / max_value * width) if max_value > 0 else 0
    bar_len = max(1, min(bar_len, width))
    return "█" * bar_len + "░" * (width - bar_len)


def _metric_row(
    label: str,
    baseline_val: Any,
    two_layer_val: Any,
    unit: str = "",
    higher_is_better: bool = True,
) -> List[str]:
    """生成一行指标对比"""
    try:
        b = float(baseline_val) if baseline_val is not None else 0.0
        t = float(two_layer_val) if two_layer_val is not None else 0.0
    except (ValueError, TypeError):
        return [label, str(baseline_val), str(two_layer_val), "—"]

    pct = _pct_change(b, t)
    # 判断正负方向
    is_improvement = (pct.startswith("+") if higher_is_better else pct.startswith("-")) if pct != "0.0%" else True
    emoji = "✅" if (t > b and higher_is_better) or (t < b and not higher_is_better) else "❌" if t != b else "➡️"
    change_str = f"{emoji} {pct}" if pct != "N/A" else "N/A"

    b_str = f"{b:.4f}" if isinstance(b, float) and b != int(b) else str(baseline_val)
    t_str = f"{t:.4f}" if isinstance(t, float) and t != int(t) else str(two_layer_val)

    return [label, f"{b_str}{unit}", f"{t_str}{unit}", change_str]


def generate_report(
    baseline_metrics: Dict[str, Any],
    two_layer_metrics: Dict[str, Any],
    baseline_queries: Optional[Dict[str, Any]] = None,
    two_layer_queries: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
) -> str:
    """生成对比实验报告 Markdown"""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 两层 vs 四层超图 — 对比实验报告",
        "",
        f"**生成时间**: {now}",
        f"**数据集**: argusbot_v3 (2373 messages, 132 expected decisions, 717 queries)",
        "",
        "---",
        "",
        "## 1. 实验组概览",
        "",
        "| 组别 | 架构 | 描述 |",
        "|------|------|------|",
        "| **A 组** | 四层超图 (L0-L3) | 当前完整架构：Decision → Fact → Episode → Topic + 三层 Hyperedge |",
        "| **B 组** | 两层结构 | 简化架构：Raw Data (Episode) → Knowledge (Decision/Topic)，无 Hyperedge |",
        "| **C 组** | 两层 + SQLite | B 组基础上，存储从内存 dict 改为 SQLite 关系表 |",
        "",
        "---",
        "",
        "## 2. 提取准确率对比",
        "",
        "| 指标 | 四层 (A 组) | 两层 (B 组) | 变化 |",
        "|------|------------|------------|------|",
    ]

    # Extract accuracy metrics
    for label, key, higher_better in [
        ("Precision", "precision", True),
        ("Recall", "recall", True),
        ("F1 Score", "f1", True),
    ]:
        lines.append("| " + " | ".join(_metric_row(
            label,
            baseline_metrics.get(key, 0),
            two_layer_metrics.get(key, 0),
            higher_is_better=higher_better,
        )) + " |")

    b_tp = baseline_metrics.get("true_positives", 0)
    t_tp = two_layer_metrics.get("true_positives", 0)
    b_fp = baseline_metrics.get("false_positives", 0)
    t_fp = two_layer_metrics.get("false_positives", 0)
    b_fn = baseline_metrics.get("false_negatives", 0)
    t_fn = two_layer_metrics.get("false_negatives", 0)

    lines += [
        "",
        "### 详细计数",
        "",
        f"- **TP (True Positives)**: A={b_tp} → B={t_tp} ({_pct_change(b_tp, t_tp)})",
        f"- **FP (False Positives)**: A={b_fp} → B={t_fp} ({_pct_change(b_fp, t_fp)})",
        f"- **FN (False Negatives)**: A={b_fn} → B={t_fn} ({_pct_change(b_fn, t_fn)})",
    ]

    # Decision/Suggestion split
    b_dm = baseline_metrics.get("decision_metrics", {})
    t_dm = two_layer_metrics.get("decision_metrics", {})
    if b_dm and t_dm:
        lines += [
            "",
            "### 决策与建议分类",
            "",
            "| 指标 | 四层 (A 组) | 两层 (B 组) | 变化 |",
            "|------|------------|------------|------|",
        ]
        for label, key, higher_better in [
            ("决策 Recall", "decision_recall", True),
            ("建议 Recall", "suggestion_recall", True),
        ]:
            lines.append("| " + " | ".join(_metric_row(
                label,
                b_dm.get(key, 0),
                t_dm.get(key, 0),
                higher_is_better=higher_better,
            )) + " |")

    # 检索准确率
    if baseline_queries and two_layer_queries:
        lines += [
            "",
            "## 3. 检索准确率对比",
            "",
            "| 指标 | 四层 (A 组) | 两层 (B 组) | 变化 |",
            "|------|------------|------------|------|",
        ]
        for label, key, higher_better in [
            ("Query Match Rate", "match_rate", True),
        ]:
            lines.append("| " + " | ".join(_metric_row(
                label,
                baseline_queries.get(key, 0),
                two_layer_queries.get(key, 0),
                higher_is_better=higher_better,
            )) + " |")

        b_latency = baseline_queries.get("retrieval_latency_ms", {})
        t_latency = two_layer_queries.get("retrieval_latency_ms", {})
        lines += [
            "",
            "### 检索延迟 (ms)",
            "",
            "| 指标 | 四层 (A 组) | 两层 (B 组) | 变化 |",
            "|------|------------|------------|------|",
        ]
        for label in ["avg", "p50", "p95"]:
            lines.append("| " + " | ".join(_metric_row(
                f"  {label}",
                b_latency.get(label, 0),
                t_latency.get(label, 0),
                unit="ms",
                higher_is_better=False,
            )) + " |")

        # 按难度拆分
        b_diff = baseline_queries.get("by_difficulty", {})
        t_diff = two_layer_queries.get("by_difficulty", {})
        if b_diff and t_diff:
            lines += [
                "",
                "### 按难度分组",
                "",
                "| 难度 | 四层 Match Rate | 两层 Match Rate | 变化 |",
                "|------|----------------|----------------|------|",
            ]
            for diff in sorted(set(list(b_diff.keys()) + list(t_diff.keys()))):
                b_rate = b_diff.get(diff, {}).get("match_rate", 0)
                t_rate = t_diff.get(diff, {}).get("match_rate", 0)
                lines.append("| " + " | ".join(_metric_row(
                    diff, b_rate, t_rate, higher_is_better=True,
                )) + " |")

        # 按类型拆分
        b_type = baseline_queries.get("by_type", {})
        t_type = two_layer_queries.get("by_type", {})
        if b_type and t_type:
            lines += [
                "",
                "### 按查询类型分组",
                "",
                "| 类型 | 四层 Match Rate | 两层 Match Rate | 变化 |",
                "|------|----------------|----------------|------|",
            ]
            for qt in sorted(set(list(b_type.keys()) + list(t_type.keys()))):
                b_rate = b_type.get(qt, {}).get("match_rate", 0)
                t_rate = t_type.get(qt, {}).get("match_rate", 0)
                lines.append("| " + " | ".join(_metric_row(
                    qt, b_rate, t_rate, higher_is_better=True,
                )) + " |")

    # 系统延迟
    lines += [
        "",
        "## 4. 系统延迟对比",
        "",
        "| 指标 | 四层 (A 组) | 两层 (B 组) | 变化 |",
        "|------|------------|------------|------|",
    ]
    b_timing = baseline_metrics.get("timing_ms", {})
    t_timing = two_layer_metrics.get("timing_ms", {})
    for label in ["mean", "median", "p95", "max"]:
        lines.append("| " + " | ".join(_metric_row(
            f"  {label} ms/msg",
            b_timing.get(label, 0),
            t_timing.get(label, 0),
            unit="ms",
            higher_is_better=False,
        )) + " |")

    b_elapsed = baseline_metrics.get("total_elapsed_seconds", 0)
    t_elapsed = two_layer_metrics.get("total_elapsed_seconds", 0)
    lines += [
        "",
        f"- **总耗时**: A={b_elapsed}s → B={t_elapsed}s ({_pct_change(b_elapsed, t_elapsed)})",
    ]

    # 消息处理速率
    b_rate = baseline_metrics.get("processing_rate_msgs_per_sec", 0)
    t_rate = two_layer_metrics.get("processing_rate_msgs_per_sec", 0)
    lines.append(f"- **处理速率**: A={b_rate} msg/s → B={t_rate} msg/s ({_pct_change(b_rate, t_rate)})")

    # 内存使用
    lines += [
        "",
        "## 5. 内存使用对比",
        "",
        "| 指标 | 四层 (A 组) | 两层 (B 组) | 变化 |",
        "|------|------------|------------|------|",
    ]
    b_mem = baseline_metrics.get("memory_mb", {})
    t_mem = two_layer_metrics.get("memory_mb", {})
    for label in ["rss_mean", "rss_peak", "rss_final"]:
        lines.append("| " + " | ".join(_metric_row(
            f"  {label}",
            b_mem.get(label, 0),
            t_mem.get(label, 0),
            unit="MB",
            higher_is_better=False,
        )) + " |")

    # LLM 调用统计
    b_llm = baseline_metrics.get("llm_stats", {})
    t_llm = two_layer_metrics.get("llm_stats", {})
    if b_llm and t_llm:
        lines += [
            "",
            "## 6. LLM 调用统计",
            "",
            "| 指标 | 四层 (A 组) | 两层 (B 组) | 变化 |",
            "|------|------------|------------|------|",
        ]
        for label, key in [
            ("调用次数", "call_count"),
            ("总 Token", "total_tokens"),
        ]:
            lines.append("| " + " | ".join(_metric_row(
                label,
                b_llm.get(key, 0),
                t_llm.get(key, 0),
                higher_is_better=False,
            )) + " |")

    # 话题级对比
    b_topic = baseline_metrics.get("by_topic", {})
    t_topic = two_layer_metrics.get("by_topic", {})
    if b_topic and t_topic:
        lines += [
            "",
            "## 7. 话题级对比",
            "",
            "| 话题 | 四层 F1 | 两层 F1 | 变化 |",
            "|------|--------|--------|------|",
        ]
        all_topics = sorted(set(list(b_topic.keys()) + list(t_topic.keys())))
        for topic in all_topics:
            b_f1 = b_topic.get(topic, {}).get("f1", 0)
            t_f1 = t_topic.get(topic, {}).get("f1", 0)
            lines.append("| " + " | ".join(_metric_row(
                topic, b_f1, t_f1, higher_is_better=True,
            )) + " |")

    # 综合评分
    lines += [
        "",
        "---",
        "",
        "## 8. 综合评分",
        "",
    ]

    # 计算综合评分
    b_f1 = float(baseline_metrics.get("f1", 0) or 0)
    t_f1 = float(two_layer_metrics.get("f1", 0) or 0)

    if baseline_queries and two_layer_queries:
        b_qr = baseline_queries.get("match_rate", 0)
        t_qr = two_layer_queries.get("match_rate", 0)
    else:
        b_qr = t_qr = 0.0

    # 加权评分
    w_extraction = 0.45
    w_retrieval = 0.35
    w_efficiency = 0.20

    a_score = b_f1 * w_extraction + b_qr * w_retrieval
    b_score = t_f1 * w_extraction + t_qr * w_retrieval

    lines += [
        f"| 维度 | 权重 | 四层 (A 组) | 两层 (B 组) |",
        f"|------|------|------------|------------|",
        f"| 提取准确率 (F1) | {w_extraction:.0%} | {b_f1:.1%} | {t_f1:.1%} |",
        f"| 检索准确率 (Match Rate) | {w_retrieval:.0%} | {b_qr:.1%} | {t_qr:.1%} |",
        f"| **加权综合** | **100%** | **{a_score:.1%}** | **{b_score:.1%}** |",
        "",
        f"**结论**: "
        f"{'两层架构表现更优 ✅' if b_score > a_score else '四层架构表现更优 ✅' if a_score > b_score else '两者表现相当 ➡️'}",
        "",
    ]

    # SQLite 组对比（如有数据）
    sqlite_metrics = two_layer_metrics.get("sqlite", {})
    if sqlite_metrics:
        lines += [
            "---",
            "",
            "## 9. SQLite 持久化 (C 组)",
            "",
            "| 指标 | 两层 (B 组 - 内存) | 两层+SQLite (C 组) | 变化 |",
            "|------|-------------------|-------------------|------|",
        ]
        for label, key, higher_better in [
            ("Query Latency avg", "avg_retrieval_time_ms", False),
            ("Query Latency p50", "p50_retrieval_time_ms", False),
            ("Query Latency p95", "p95_retrieval_time_ms", False),
        ]:
            b_val = two_layer_metrics.get(key, 0)
            c_val = sqlite_metrics.get(key, 0)
            lines.append("| " + " | ".join(_metric_row(
                label, b_val, c_val, unit="ms", higher_is_better=higher_better,
            )) + " |")

    lines += [
        "",
        "---",
        "",
        "## 附录",
        "",
        "### 数据集信息",
        "",
        f"- `messages.jsonl`: 2373 条消息，70 个 chat",
        f"- `expected.jsonl`: 132 条预期决策标注",
        f"- `queries.jsonl`: 717 条查询（含 gold answer）",
        f"- 配置参考: `eval_dataset/config.yaml` → `argusbot_v3`",
        "",
        "### 基线 (v2 数据集参考)",
        "",
        f"- argusbot_multi_v2 (1500 msgs / 92 expected decisions): F1={47.4:.1f}%",
    ]

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

    return report