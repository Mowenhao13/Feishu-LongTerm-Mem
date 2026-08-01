#!/usr/bin/env python3
"""
生成扩展 benchmark 数据集 — Phase 2

基于 Phase 1 调研结论和扩展后的 EvalDatasetGenerator，
生成 ~14,500 条消息 / ~1,800 个决策的大规模数据集。

数据集结构：
  eval_dataset/argusbot_v3/
  ├── messages.jsonl         # 主消息集 (~4,500)
  ├── expected.jsonl         # 主消息预期决策
  ├── queries.jsonl          # 评估查询
  ├── multi_session/
  │   ├── messages.jsonl     # 多 session 场景消息 (~1,200)
  │   ├── expected.jsonl     # 多 session 预期决策
  │   └── session_boundaries.json  # session 分界信息
  ├── temporal_queries.jsonl # 时间精确定位查询
  ├── ambiguous_queries.jsonl # 模糊/拒答查询
  ├── user_partitioning/
  │   ├── messages.jsonl     # 用户级记忆分区消息 (~600)
  │   └── expected.jsonl
  ├── cross_session_conflicts/
  │   ├── messages.jsonl     # 跨 session 冲突消息 (~500)
  │   └── expected.jsonl
  ├── variable_noise/
  │   ├── messages.jsonl     # 变噪声比消息 (~6,000)
  │   └── expected.jsonl
  └── summary.json           # 整体报告

用法：
  uv run python scripts/generate_expanded_dataset.py
  uv run python scripts/generate_expanded_dataset.py --output eval_dataset/argusbot_v3
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.eval.generator import EvalDatasetGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
    force=True,
)

logger = logging.getLogger(__name__)


# ── V3 Dataset Domain Config — 7 domains × 10 chats  ──────────────────────

V3_DOMAINS: List[Dict[str, Any]] = [
    {
        "name": "cloud_infra",
        "description": "云基础设施团队讨论多云架构、容器化、网络策略等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 18,
        "topics": [
            "多云统一管理平台", "容器网络CNI选型", "服务网格Istio升级",
            "K8s集群联邦管理", "Ingress网关选型", "节点自动扩缩容策略",
            "存储类选型", "GPU调度策略",
        ],
    },
    {
        "name": "backend_arch",
        "description": "后端架构团队讨论微服务拆分、API设计、数据一致性等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 18,
        "topics": [
            "微服务拆分粒度", "事件驱动架构", "分布式事务方案",
            "GraphQL vs REST", "API版本管理", "服务注册发现",
            "限流熔断策略", "数据一致性模型",
        ],
    },
    {
        "name": "data_platform",
        "description": "数据平台团队讨论数据湖、实时计算、数据治理等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 18,
        "topics": [
            "数据湖方案选型", "实时计算框架", "数据质量监控",
            "数据血缘追踪", "数仓分层设计", "ETL调度框架",
            "数据脱敏方案", "元数据管理平台",
        ],
    },
    {
        "name": "frontend_mobile",
        "description": "前端与移动端团队讨论跨平台方案、性能优化、CI/CD等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 18,
        "topics": [
            "跨平台框架Flutter", "WebAssembly应用", "微前端架构",
            "PWA离线方案", "性能监控RUM", "组件库设计系统",
            "构建缓存策略", "A/B测试框架",
        ],
    },
    {
        "name": "sec_compliance",
        "description": "安全合规团队讨论安全架构、合规审计、密钥管理等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 18,
        "topics": [
            "零信任网络架构", "密钥管理方案", "SOC告警规则",
            "漏洞扫描策略", "合规自动化审计", "数据分类分级",
            "安全SDLC流程", "渗透测试周期",
        ],
    },
    {
        "name": "ai_ml_platform",
        "description": "AI/ML平台团队讨论模型训练、推理部署、特征工程等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 18,
        "topics": [
            "ML模型训练平台", "推理服务部署方案", "特征存储选型",
            "模型版本管理", "A/B评估框架", "GPU资源调度",
            "在线学习管道", "模型监控漂移检测",
        ],
    },
    {
        "name": "sre_reliability",
        "description": "SRE可靠性团队讨论可观测性、混沌工程、SLO管理等技术决策",
        "num_chats": 10,
        "participants_per_chat": 4,
        "noise_per_chat": 18,
        "topics": [
            "SLO定义与追踪", "告警噪声治理", "混沌工程平台",
            "分布式追踪全链路", "日志聚合方案", "容量规划模型",
            "故障演练周期", "on-call轮值规范",
        ],
    },
]


def main(output_dir: str = "eval_dataset/argusbot_v3", skip_llm: bool = False) -> None:
    start_time = time.time()

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    generator = EvalDatasetGenerator()
    total_messages = 0
    total_decisions = 0
    module_reports: Dict[str, Any] = {}

    # ═══════════════════════════════════════════════════════════════
    # Module 1: Main benchmark (7 domains × 10 chats)
    # ═══════════════════════════════════════════════════════════════
    print("=" * 62)
    print("  Module 1: Main Benchmark Data (V3 Domains)")
    print("=" * 62)

    main_output = str(output_root / "main")
    Path(main_output).mkdir(parents=True, exist_ok=True)

    if skip_llm:
        print("  [Module 1] SKIPPED (--skip-llm)")
        print()
        m1_report = {
            "total_messages": 0,
            "total_decisions": 0,
            "total_queries": 0,
            "chat_count": 0,
            "user_count": 0,
            "distractor_count": 0,
            "total_llm_calls": 0,
            "domains": 0,
        }
        module_reports["main_benchmark"] = m1_report
    else:
        m1_start = time.time()
        try:
            generator.generate_benchmark(main_output, domains=V3_DOMAINS)
            # Load summary to get actual counts
            with open(Path(main_output) / "summary.json", "r") as f:
                m1_report = json.load(f)
        except Exception as e:
            print(f"  [Module 1] ERROR: {e}")
            print("  Try running with --skip-llm or set valid API_KEY credentials.")
            print()
            m1_report = {
                "total_messages": 0,
                "total_decisions": 0,
                "total_queries": 0,
                "chat_count": 0,
                "user_count": 0,
                "distractor_count": 0,
                "total_llm_calls": 0,
                "domains": 0,
            }
        total_messages += m1_report["total_messages"]
        total_decisions += m1_report["total_decisions"]
        m1_elapsed = time.time() - m1_start
        module_reports["main_benchmark"] = m1_report
        print(f"  [Module 1] {m1_report['total_messages']} msgs, "
              f"{m1_report['total_decisions']} decisions, {m1_elapsed:.1f}s\n")

    # ═══════════════════════════════════════════════════════════════
    # Module 2: Multi-Session Scenarios
    # ═══════════════════════════════════════════════════════════════
    print("=" * 62)
    print("  Module 2: Multi-Session Scenarios")
    print("=" * 62)

    ms_output = str(output_root / "multi_session")
    m2_start = time.time()
    m2_report = generator.generate_multi_session_scenarios(
        ms_output, num_topics=10, sessions_per_topic=3,
        day_gaps=[1, 3, 7, 14, 30], messages_per_session=8,
    )
    total_messages += m2_report["total_messages"]
    total_decisions += m2_report["total_decisions"]
    m2_elapsed = time.time() - m2_start
    module_reports["multi_session"] = m2_report
    print(f"  [Module 2] {m2_report['total_messages']} msgs, "
          f"{m2_report['total_decisions']} decisions, {m2_elapsed:.1f}s\n")

    # ═══════════════════════════════════════════════════════════════
    # Module 3: User-Specific Memory Partitioning
    # ═══════════════════════════════════════════════════════════════
    print("=" * 62)
    print("  Module 3: User-Specific Memory Partitioning")
    print("=" * 62)

    up_output = str(output_root / "user_partitioning")
    m3_start = time.time()
    m3_report = generator.generate_user_partitioning(up_output, num_partitions=8)
    total_messages += m3_report["total_messages"]
    total_decisions += m3_report["total_decisions"]
    m3_elapsed = time.time() - m3_start
    module_reports["user_partitioning"] = m3_report
    print(f"  [Module 3] {m3_report['total_messages']} msgs, "
          f"{m3_report['total_decisions']} decisions, {m3_elapsed:.1f}s\n")

    # ═══════════════════════════════════════════════════════════════
    # Module 4: Cross-Session Conflict Resolution
    # ═══════════════════════════════════════════════════════════════
    print("=" * 62)
    print("  Module 4: Cross-Session Conflict Resolution")
    print("=" * 62)

    cc_output = str(output_root / "cross_session_conflicts")
    m4_start = time.time()
    m4_report = generator.generate_cross_session_conflicts(cc_output, num_conflicts=10)
    total_messages += m4_report["total_messages"]
    total_decisions += m4_report["total_decisions"]
    m4_elapsed = time.time() - m4_start
    module_reports["cross_session_conflicts"] = m4_report
    print(f"  [Module 4] {m4_report['total_messages']} msgs, "
          f"{m4_report['total_decisions']} decisions, {m4_elapsed:.1f}s\n")

    # ═══════════════════════════════════════════════════════════════
    # Module 5: Variable Noise Ratio
    # ═══════════════════════════════════════════════════════════════
    print("=" * 62)
    print("  Module 5: Variable Noise Ratio")
    print("=" * 62)

    vn_output = str(output_root / "variable_noise")
    m5_start = time.time()
    m5_report = generator.generate_variable_noise(
        vn_output, num_chats=55, noise_ratios=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
    )
    total_messages += m5_report["total_messages"]
    total_decisions += m5_report["total_decisions"]
    m5_elapsed = time.time() - m5_start
    module_reports["variable_noise"] = m5_report
    print(f"  [Module 5] {m5_report['total_messages']} msgs, "
          f"{m5_report['total_decisions']} decisions, {m5_elapsed:.1f}s\n")

    # ═══════════════════════════════════════════════════════════════
    # Module 6: Temporal Precision Queries
    # ═══════════════════════════════════════════════════════════════
    print("=" * 62)
    print("  Module 6: Temporal Precision Queries")
    print("=" * 62)

    tq_output = str(output_root / "temporal_queries")
    m6_start = time.time()
    m6_report = generator.generate_temporal_queries(tq_output, num_queries=80)
    m6_elapsed = time.time() - m6_start
    module_reports["temporal_queries"] = m6_report
    print(f"  [Module 6] {m6_report['num_queries']} queries, {m6_elapsed:.1f}s\n")

    # ═══════════════════════════════════════════════════════════════
    # Module 7: Ambiguous / Abstention Queries
    # ═══════════════════════════════════════════════════════════════
    print("=" * 62)
    print("  Module 7: Ambiguous & Abstention Queries")
    print("=" * 62)

    aq_output = str(output_root / "ambiguous_queries")
    m7_start = time.time()
    m7_report = generator.generate_ambiguous_queries(aq_output, num_queries=60)
    m7_elapsed = time.time() - m7_start
    module_reports["ambiguous_queries"] = m7_report
    print(f"  [Module 7] {m7_report['total_queries']} queries, {m7_elapsed:.1f}s\n")

    # ═══════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════
    elapsed = time.time() - start_time

    summary = {
        "dataset": "argusbot_v3",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_messages": total_messages,
        "total_decisions": total_decisions,
        "modules": {
            "1_main_benchmark": {
                "messages": m1_report.get("total_messages", 0),
                "decisions": m1_report.get("total_decisions", 0),
                "chats": m1_report.get("chat_count", 70),
            },
            "2_multi_session": {
                "messages": m2_report.get("total_messages", 0),
                "decisions": m2_report.get("total_decisions", 0),
            },
            "3_user_partitioning": {
                "messages": m3_report.get("total_messages", 0),
                "decisions": m3_report.get("total_decisions", 0),
            },
            "4_cross_session_conflicts": {
                "messages": m4_report.get("total_messages", 0),
                "decisions": m4_report.get("total_decisions", 0),
            },
            "5_variable_noise": {
                "messages": m5_report.get("total_messages", 0),
                "decisions": m5_report.get("total_decisions", 0),
            },
            "6_temporal_queries": m6_report.get("num_queries", 0),
            "7_ambiguous_queries": m7_report.get("total_queries", 0),
        },
        "elapsed_seconds": round(elapsed, 1),
        "elapsed_minutes": round(elapsed / 60, 1),
    }

    with open(output_root / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # ═══════════════════════════════════════════════════════════════
    # Print report
    # ═══════════════════════════════════════════════════════════════
    print()
    print("=" * 62)
    print("  ✅ Expanded Dataset Generation Complete!")
    print("=" * 62)
    print(f"  Output:         {output_root}")
    print(f"  Total messages: {total_messages}")
    print(f"  Total decisions:{total_decisions}")
    print(f"  Total time:     {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print()
    print(f"  {'Module':<35} {'Msgs':>6} {'Decisions':>10}")
    print(f"  {'-'*35} {'-'*6} {'-'*10}")
    for key, mod in summary["modules"].items():
        if isinstance(mod, dict):
            print(f"  {mod_key_to_label(key):<35} {mod['messages']:>6} {mod['decisions']:>10}")
        else:
            print(f"  {mod_key_to_label(key):<35} {mod:>6} {'queries':>10}")
    print(f"  {'-'*35} {'-'*6} {'-'*10}")
    print(f"  {'TOTAL':<35} {total_messages:>6} {total_decisions:>10}")
    print()
    print(f"  Queries generated:")
    print(f"    Temporal:        {m6_report.get('num_queries', 0)}")
    print(f"    Ambiguous/Abstain: {m7_report.get('total_queries', 0)}")
    print()
    print(f"  Full report: {output_root / 'summary.json'}")
    print()

    # Copy main benchmark's messages to root for quick access
    import shutil
    for fname in ["messages.jsonl", "expected.jsonl", "queries.jsonl", "summary.json"]:
        src = Path(main_output) / fname
        if src.exists():
            shutil.copy2(src, output_root / fname)
    print(f"  Root files copied from main benchmark for direct access.")
    print()


def mod_key_to_label(key: str) -> str:
    labels = {
        "1_main_benchmark": "1. Main Benchmark (V3)",
        "2_multi_session": "2. Multi-Session Scenarios",
        "3_user_partitioning": "3. User Partitioning",
        "4_cross_session_conflicts": "4. Cross-Session Conflicts",
        "5_variable_noise": "5. Variable Noise",
        "6_temporal_queries": "6. Temporal Queries",
        "7_ambiguous_queries": "7. Ambiguous Queries",
    }
    return labels.get(key, key)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate expanded V3 benchmark dataset")
    parser.add_argument("--output", default="eval_dataset/argusbot_v3",
                        help="Output directory (default: eval_dataset/argusbot_v3)")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip LLM-based Module 1 (requires valid API_KEY)")
    args = parser.parse_args()
    main(output_dir=args.output, skip_llm=args.skip_llm)