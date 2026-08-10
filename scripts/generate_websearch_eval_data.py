#!/usr/bin/env python3
"""WebSearch 评测测试数据生成脚本 — Phase 3

基于 methodology_blueprint.md 定义的 6 个场景和 JSONL schema，
生成 ~100 条合成测试用例，覆盖全部 websearch 记忆评测场景。

Usage:
    # 全量生成（~100 条用例，seed=42）
    python -m scripts.generate_websearch_eval_data

    # 指定 seed 和输出目录
    python -m scripts.generate_websearch_eval_data --seed 123 --output eval_dataset/argusbot_websearch

    # 只生成指定场景（场景编号 1-6）
    python -m scripts.generate_websearch_eval_data --scenarios 1 3 5

    # 只生成场景 4（跨 session，会产出 session1/session2 双文件）
    python -m scripts.generate_websearch_eval_data --scenarios 4

    # 查看统计数据不生成文件
    python -m scripts.generate_websearch_eval_data --dry-run
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Schema Helpers ──────────────────────────────────────────────────────────

SCENARIO_IDS = {
    1: "web_simple_extract",
    2: "web_fact_update",
    3: "web_stale_rejection",
    4: "web_cross_session",
    5: "web_multi_source_merge",
    6: "web_distractor_tolerance",
}

SCENARIO_NAMES = {
    1: "simple_extract",
    2: "fact_update",
    3: "stale_rejection",
    4: "cross_session",
    5: "multi_source_merge",
    6: "distractor_tolerance",
}

SCENARIO_LABELS = {
    1: "简单事实提取",
    2: "事实更新（冲突检测）",
    3: "过时事实拒绝",
    4: "跨 session 召回",
    5: "多源合并（冲突解决）",
    6: "干扰容错（噪声过滤）",
}


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    full_content: str
    source_type: str
    relevance_score: float
    timestamp: float
    expiry_after_turns: Optional[int] = None
    expiry_after_seconds: Optional[float] = None


@dataclass
class PriorMemoryState:
    expected_topic: str
    expected_summary: str
    expected_status: str
    override_status: Optional[str] = None
    memorized_at: float = 0.0


@dataclass
class ExpectedEffect:
    type: str
    expected_topic: str
    expected_summary: str
    expected_status: str = "decided"
    conflict_detection_expected: Optional[bool] = None
    conflict_resolution_expected_turns: Optional[int] = None


@dataclass
class WebsearchContext:
    scenario_id: str
    search_results: List[SearchResult]
    search_intent: str
    expected_effect: ExpectedEffect
    conflict_with_prior: bool = False
    prior_memory_state: Optional[PriorMemoryState] = None


@dataclass
class TestMessage:
    chat_id: str
    msg_id: str
    speaker: str
    msg: str
    expected_decision: bool = True
    is_distractor: bool = False
    timestamp: float = 0.0
    topic: str = ""
    phase_name: str = "decision"
    websearch_context: Optional[WebsearchContext] = None


# ── Data Pools ──────────────────────────────────────────────────────────────

SPEAKERS = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"]

# 话题池（20 个话题 × 3 facts = 60 个可用的 fact）
TOPIC_POOL = [
    {"topic": "Kubernetes版本升级策略", "domain": "infra",
     "facts": [
         ("Kubernetes 1.29 已发布，包含新的调度功能", "k8s129"),
         ("Kubernetes 1.28 是当前生产环境推荐版本", "k8s128"),
         ("Kubernetes 1.30 正在开发中，预计支持 GPU 分区调度", "k8s130"),
     ]},
    {"topic": "数据库迁移：PG到MySQL", "domain": "infra",
     "facts": [
         ("PostgreSQL 16 引入增量备份与逻辑复制增强", "pg16"),
         ("MySQL 8.4 长期支持版提供 JSON 优化", "mysql84"),
         ("Amazon Aurora 最新版兼容 MySQL 8.4", "aurora"),
     ]},
    {"topic": "Redis缓存策略", "domain": "infra",
     "facts": [
         ("Redis 7.4 支持向量搜索功能", "redis_v"),
         ("Redis Stack 提供 JSON 和搜索模块", "redis_stack"),
         ("Redis 集群模式支持多分片自动故障转移", "redis_clu"),
     ]},
    {"topic": "服务网格选型：Istio vs Linkerd", "domain": "infra",
     "facts": [
         ("Istio 1.22 引入 Ambient Mesh GA", "istio22"),
         ("Linkerd 2.16 性能提升 30%", "linkerd16"),
         ("Istio 与 Knative 集成最佳实践", "istio_kn"),
     ]},
    {"topic": "API 网关选型", "domain": "infra",
     "facts": [
         ("Kong 3.8 支持 AI Gateway 插件", "kong38"),
         ("Apache APISIX 3.12 新增 WASM 插件支持", "apisix12"),
         ("Envoy Gateway 1.2 达到生产就绪状态", "envoy12"),
     ]},
    {"topic": "CI/CD 工具链升级", "domain": "infra",
     "facts": [
         ("GitHub Actions 支持 Arm64 自托管 Runner", "gha_arm"),
         ("GitLab 17.0 弃用 CI/CD 模板旧语法", "gitlab17"),
         ("ArgoCD 2.14 引入 ApplicationSet 生成器增强", "argocd14"),
     ]},
    {"topic": "Next.js App Router迁移", "domain": "frontend",
     "facts": [
         ("Next.js 15 全量支持 App Router", "next15"),
         ("App Router 的 Server Components 减少客户端 JS 40%", "next_sc"),
         ("Pages Router 在 Next.js 15 中仍受支持到 LTS 结束", "next_pr"),
     ]},
    {"topic": "构建工具迁移：Webpack到Vite", "domain": "frontend",
     "facts": [
         ("Vite 6 支持 RSC 和服务端渲染", "vite6"),
         ("Turbopack 在 Next.js 中集成度最高", "turbopack"),
         ("Webpack 5 模块联邦微前端方案成熟", "wp5mf"),
     ]},
    {"topic": "CSS 方案选型", "domain": "frontend",
     "facts": [
         ("Tailwind CSS 4.0 引入 CSS-first 配置", "tw4"),
         ("CSS Modules 已被主流框架原生支持", "css_m"),
         ("Panda CSS 提供运行时零开销的类型安全样式", "panda"),
     ]},
    {"topic": "前端状态管理方案升级", "domain": "frontend",
     "facts": [
         ("Zustand 4.5 引入持久化中间件增强", "zustand45"),
         ("Jotai 2.10 支持 Server Components 兼容模式", "jotai210"),
         ("Redux Toolkit 3.0 移除对 createStore 的旧 API 支持", "rtk30"),
     ]},
    {"topic": "告警阈值设置", "domain": "ops",
     "facts": [
         ("P99 延迟告警阈值建议设为 500ms", "alert500"),
         ("P99 延迟告警阈值建议设为 200ms", "alert200"),
         ("CPU 使用率告警阈值建议 80%", "alert_cpu"),
     ]},
    {"topic": "日志采样策略", "domain": "ops",
     "facts": [
         ("全量日志采样影响性能，建议改成 10% 采样率", "log10"),
         ("错误日志必须全量采集不采样", "log_err"),
         ("关键业务日志改为 50% 采样以平衡成本和排查", "log50"),
     ]},
    {"topic": "Docker镜像体积优化", "domain": "ops",
     "facts": [
         ("基于 Alpine 的基础镜像比 Debian 小 80%", "dock_alp"),
         ("多阶段构建可将 Go 应用镜像缩小到 15MB", "dock_ms"),
         ("Distroless 镜像比 Alpine 更安全", "dock_dist"),
     ]},
    {"topic": "容器运行时迁移", "domain": "ops",
     "facts": [
         ("containerd 2.0 移除对 cri-api v1alpha2 的支持", "ctrd2"),
         ("Podman 5.0 支持 pod 级别资源限制", "podman5"),
         ("Docker Desktop 的替代方案中 Rancher Desktop 最成熟", "rancher"),
     ]},
    {"topic": "可观测性方案评估", "domain": "ops",
     "facts": [
         ("OpenTelemetry Collector 1.0 达到生产稳定", "otel1"),
         ("Grafana 11 引入统一的可观测性查询语言", "graf11"),
         ("Datadog 价格调整后，自建 Prometheus 成本优势明显", "ddog"),
     ]},
    {"topic": "Kafka分区数调整", "domain": "middleware",
     "facts": [
         ("Kafka 3.7 支持弹性分区重平衡", "kf37"),
         ("单分区吞吐约 10MB/s，建议按峰值吞吐的 2 倍规划", "kf_tp"),
         ("Kafka 3.8 引入分区分组管理新 API", "kf38"),
     ]},
    {"topic": "消息队列选型", "domain": "middleware",
     "facts": [
         ("RabbitMQ 4.0 引入 Quorum Queue 替代镜像队列", "rmq40"),
         ("Pulsar 3.4 支持分层存储和 Geo-replication 增强", "puls34"),
         ("Kafka 最适合高吞吐日志场景，RabbitMQ 适合事务消息", "mq_cmp"),
     ]},
    {"topic": "API 网关配置管理", "domain": "middleware",
     "facts": [
         ("Nginx 1.27 支持 HTTP/3 和 QUIC 上游", "ngx127"),
         ("Traefik 3.2 原生支持 K8s Gateway API", "tr32"),
         ("HAProxy 3.0 引入了 QUIC 负载均衡", "hap30"),
     ]},
    {"topic": "API认证方案", "domain": "security",
     "facts": [
         ("OAuth 2.1 废弃了 implicit grant 和 resource owner password grant", "oa21"),
         ("API Key 简单但难以轮换和撤销", "apik"),
         ("JWT 配合 OAuth 2.0 是推荐的企业 API 认证方案", "jwt"),
     ]},
    {"topic": "零信任架构实施", "domain": "security",
     "facts": [
         ("BeyondCorp 模型在 Google 内部已验证 10 年以上", "bc"),
         ("Zero Trust 网络访问（ZTNA）工具如 Cloudflare 成熟", "ztna"),
         ("零信任架构需要身份感知代理和持续验证", "zta"),
     ]},
]

# 跨 session 话题（场景 4）
CROSS_SESSION_TOPICS = [
    {"topic": "团队年度技术栈决策",
     "session1_facts": [
         ("团队决定全面迁移到 Go 语言作为后端主力语言", "lang_go"),
         ("前端统一使用 React 18 + TypeScript", "front_react"),
     ],
     "session2_recall_facts": ["lang_go", "front_react"]},
    {"topic": "CI/CD 基础设施规划",
     "session1_facts": [
         ("CI 工具决定从 Jenkins 切换到 GitHub Actions", "cicd_gha"),
         ("部署环境统一使用 Kubernetes + ArgoCD", "cicd_argocd"),
     ],
     "session2_recall_facts": ["cicd_gha", "cicd_argocd"]},
    {"topic": "监控体系标准化",
     "session1_facts": [
         ("采用 OpenTelemetry 作为统一可观测标准", "otel_std"),
         ("Grafana + Prometheus 作为指标可视化方案", "graf_prom"),
     ],
     "session2_recall_facts": ["otel_std"]},
    {"topic": "云成本优化方案",
     "session1_facts": [
         ("采用预留实例降低 30% 云成本", "ri_30"),
         ("按需实例与 Spot 实例混合使用策略", "spot_mix"),
         ("每月进行云成本审计和资源清理", "cost_audit"),
     ],
     "session2_recall_facts": ["ri_30", "spot_mix"]},
    {"topic": "数据备份与灾备方案",
     "session1_facts": [
         ("数据库每天全量备份 + 每 6h 增量备份", "db_backup"),
         ("跨区域灾备采用异步复制", "dr_async"),
     ],
     "session2_recall_facts": ["db_backup"]},
]

# 冲突事实对（场景 2）
CONFLICT_PAIRS = [
    ("P99 延迟告警阈值设为 500ms", "P99 延迟告警阈值改为 200ms", "alert_p99"),
    ("全量日志采样", "10% 采样率采样", "log_sample"),
    ("使用 Alpine 基础镜像", "使用 Distroless 基础镜像", "base_img"),
    ("Kafka 分区数固定为 12", "Kafka 分区数改为 24", "kf_part"),
    ("Redis 单节点部署", "Redis 集群模式部署", "redis_dep"),
    ("使用 OAuth 2.0 + JWT", "使用 API Key 简化认证", "auth_sch"),
    ("Nginx 作为 API 网关", "Kong 作为 API 网关", "api_gw"),
    ("基于 Alpine 的镜像", "基于 Ubuntu 的镜像", "base_alp"),
    ("GitHub Actions 作为 CI", "GitLab CI 作为 CI", "ci_tool"),
    ("使用 containerd 运行时", "使用 Podman 运行时", "ctr_run"),
]

# 多源合并场景（场景 5）
MERGE_SCENARIOS = [
    {
        "topic": "数据库方案决策",
        "sources": [("official", "AWS 官方文档"), ("community", "开源社区博客")],
        "fact_a": "Amazon Aurora 提供 MySQL 8.4 完全兼容，推荐生产使用",
        "fact_b": "Aurora 对 MySQL 8.4 不完全兼容，部分 JSON 函数有差异",
        "resolved": "Aurora 基本兼容 MySQL 8.4，部分 JSON 函数需验证后使用",
    },
    {
        "topic": "GPU 实例选型",
        "sources": [("vendor", "云厂商定价页"), ("community", "技术评测报告")],
        "fact_a": "A100 GPU 实例 $3.50/小时，推荐训练使用",
        "fact_b": "H100 比 A100 快 2-3 倍，$5/小时算力效率更高",
        "resolved": "短期实验用 A100，长期训练任务规划 H100",
    },
    {
        "topic": "React 状态管理方案",
        "sources": [("official", "React 官方文档"), ("community", "社区技术对比")],
        "fact_a": "React 19 推荐使用 use() 和 Server Components",
        "fact_b": "Zustand 在客户端状态管理方面比内置 Context 性能更好",
        "resolved": "新项目用 React Server Components + Zustand 组合方案",
    },
    {
        "topic": "容器镜像仓库方案",
        "sources": [("official", "Harbor 官方文档"), ("vendor", "云厂商报价单")],
        "fact_a": "Harbor 开源版提供完整的镜像扫描和复制功能",
        "fact_b": "使用云厂商托管仓库（ACR/ECR/GCR）运维成本更低",
        "resolved": "自建 Harbor 用于核心生产，ACR/ECR 用于灾备和海外",
    },
    {
        "topic": "API 版本管理策略",
        "sources": [("official", "RESTful API 设计规范"), ("community", "企业级 API 实践")],
        "fact_a": "推荐 URL 路径版本管理如 /v1/ /v2/ 语义清晰",
        "fact_b": "推荐 Header 版本管理减少 URL 污染，后端灵活路由",
        "resolved": "公共 API 用 URL 路径版本，内部 API 用 Header 版本",
    },
    {
        "topic": "微服务监控方案",
        "sources": [("official", "OTel 官方最佳实践"), ("vendor", "商业 APM 厂商")],
        "fact_a": "OTel 提供统一标准，避免厂商锁定",
        "fact_b": "商业 APM（如 Datadog）开箱即用，降低团队维护成本",
        "resolved": "核心链路用 OTel 标准采集，结合商业 APM 的可视化能力",
    },
]

NOISE_TEMPLATES = [
    ("https://news.example.com/today", "今日科技新闻汇总", "多家科技公司发布财报..."),
    ("https://weather.example.com/city", "城市天气预报", "今天晴转多云，气温15-22度..."),
    ("https://sports.example.com/game", "体育赛事结果", "昨晚的篮球比赛以..."),
    ("https://recipes.example.com/dish", "食谱推荐", "教你做一道经典的家常菜..."),
    ("https://market.example.com/stock", "股市行情", "今日大盘指数小幅上涨..."),
    ("https://travel.example.com/spot", "旅游景点推荐", "十大必去景点排行榜..."),
    ("https://movie.example.com/review", "电影动态", "新上映的科幻片获得好评..."),
    ("https://music.example.com/top", "本周热歌榜", "最新音乐排行榜出炉..."),
    ("https://book.example.com/new", "新书推荐", "技术管理类书籍推荐..."),
]

SECURITY_INCIDENT_TEMPLATES = [
    "关于这个漏洞的补丁已经发布，建议尽快升级到最新版本以修复安全问题。",
    "新发现的零日漏洞影响所有 v2.x 版本，需要立即重启隔离措施。",
    "这个 CVE 的 CVSS 评分是 9.8，属于严重级别，我们需在 48 小时内完成修复。",
    "公司安全团队建议所有关键系统在应用安全补丁前不要暴露公网。",
]


# ── Generator Class ─────────────────────────────────────────────────────────


class WebsearchEvalDataGenerator:
    """生成 WebSearch 记忆评测测试数据集"""

    def __init__(self, seed: int = 42, output_dir: str = "eval_dataset/argusbot_websearch"):
        self.seed = seed
        self.rng = random.Random(seed)
        self.output_dir = Path(output_dir)
        self.base_ts: float = 1705300000.0  # 2024-01-15T00:00:00 UTC
        self.base_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

    # ── Scenario 1: Simple Fact Extraction ─────────────────────────────────

    def _gen_scene1(self) -> List[TestMessage]:
        """场景 1：简单事实提取 — websearch → 对话 → 决策。

        生成 20 条用例：覆盖 control variables clarity (clear/ambiguous)
        × directness (explicit/implicit) × 5 个不同话题。easy/medium/hard。
        """
        cases: List[TestMessage] = []

        # 20 variations: 5 topics × 2 clarity × 2 directness = 20
        base_topics = [1, 2, 4, 6, 8]  # topic pool indices
        clarity_vals = ["clear", "ambiguous"]
        directness_vals = ["explicit", "implicit"]

        for idx, topic_idx in enumerate(base_topics):
            for clarity in clarity_vals:
                for directness in directness_vals:
                    topic_info = TOPIC_POOL[topic_idx]
                    topic_name = topic_info["topic"]
                    fact_text, fact_key = topic_info["facts"][0]

                    chat_id = f"web_simple_{idx * 4 + clarity_vals.index(clarity) * 2 + directness_vals.index(directness):02d}"
                    ts = self.base_ts + len(cases) * 7200

                    search_result = SearchResult(
                        url=f"https://example.com/{fact_key}",
                        title=f"关于{topic_name}的最新信息",
                        snippet=fact_text[:60] + "...",
                        full_content=fact_text,
                        source_type="official" if clarity == "clear" else "community",
                        relevance_score=0.95 if clarity == "clear" else 0.70,
                        timestamp=ts,
                    )

                    msg_text = self._build_scene1_message(fact_text, clarity, directness)

                    websearch = WebsearchContext(
                        scenario_id=SCENARIO_IDS[1],
                        search_results=[search_result],
                        search_intent=f"查找{topic_name}相关信息",
                        expected_effect=ExpectedEffect(
                            type="new_decision",
                            expected_topic=topic_name,
                            expected_summary=fact_text,
                            expected_status="decided",
                        ),
                        conflict_with_prior=False,
                    )

                    msg = TestMessage(
                        chat_id=chat_id,
                        msg_id="m001",
                        speaker=self.rng.choice(SPEAKERS),
                        msg=msg_text,
                        timestamp=ts,
                        topic=topic_name,
                        phase_name="decision",
                        websearch_context=websearch,
                    )
                    cases.append(msg)

        return cases

    def _build_scene1_message(self, fact: str, clarity: str, directness: str) -> str:
        if directness == "explicit":
            if clarity == "clear":
                variants = [
                    f"刚查到信息：{fact}。这个很明确，就定这个吧。",
                    f"搜到了明确的资料：{fact}。大家没问题的话就这么办。",
                    f"官方文档写得很清楚：{fact}。我建议就按这个执行。",
                    f"确认了：{fact}。没什么疑问，直接推进。",
                ]
            else:
                variants = [
                    f"搜到一些信息：{fact}。虽然不是百分百确定，但应该是这个方向。",
                    f"查到几个说法，其中一个是：{fact}。大家再核实一下。",
                    f"有个结果提到{fact}，但来源不太官方，各位怎么看？",
                ]
        else:
            if clarity == "clear":
                variants = [
                    f"查了一下资料，关于这个话题的最新消息已经出来了。大家讨论一下？",
                    f"刚看到了一份相关资料，信息很新且权威，我们应该参考一下。",
                ]
            else:
                variants = [
                    f"我找了几个来源，信息不太一致。其中一个说法是{fact}，大家帮忙确认一下哪边是对的。",
                    f"有个搜索结果说{fact}，但我不确定是否最新，你们有了解的吗？",
                ]
        return self.rng.choice(variants)

    # ── Scenario 2: Fact Update ────────────────────────────────────────────

    def _gen_scene2(self) -> List[TestMessage]:
        """场景 2：事实更新 — 新旧 fact 冲突，对话内解决。

        每条冲突对生成 2 条用例（1 条用户直接发现冲突 + 1 条 search 直接返回更新）。
        共 10 × 2 = 20 条。
        """
        cases: List[TestMessage] = []

        for idx, (old_fact, new_fact, fact_key) in enumerate(CONFLICT_PAIRS):
            chat_id = f"web_update_{idx:02d}"
            ts = self.base_ts + 100000 + idx * 3600
            topic_name = f"系统配置：{fact_key}"
            old_ts = ts - 86400 * self.rng.choice([1, 3, 7])  # 1/3/7 天前

            search_result = SearchResult(
                url=f"https://docs.example.com/{fact_key}/new",
                title=f"{topic_name} — 最新更新",
                snippet=new_fact[:60],
                full_content=new_fact,
                source_type="official",
                relevance_score=0.98,
                timestamp=ts + 120,
            )

            prior_memory = PriorMemoryState(
                expected_topic=topic_name,
                expected_summary=old_fact,
                expected_status="decided",
                override_status="superseded",
                memorized_at=old_ts,
            )

            websearch = WebsearchContext(
                scenario_id=SCENARIO_IDS[2],
                search_results=[search_result],
                search_intent=f"查看{topic_name}是否有更新",
                expected_effect=ExpectedEffect(
                    type="update_decision",
                    expected_topic=topic_name,
                    expected_summary=new_fact,
                    expected_status="decided",
                    conflict_detection_expected=True,
                    conflict_resolution_expected_turns=self.rng.choice([1, 2, 3]),
                ),
                conflict_with_prior=True,
                prior_memory_state=prior_memory,
            )

            msg_text = self.rng.choice([
                f"我刚查到最新资料说{new_fact}，和我们之前定的{old_fact}不一样了，需要更新一下。",
                f"刚发现原来我们记错了，应该是{new_fact}，不是{old_fact}。",
                f"检查发现信息有更新：{new_fact}，覆盖之前的{old_fact}。",
            ])

            msg = TestMessage(
                chat_id=chat_id,
                msg_id="m001",
                speaker=self.rng.choice(SPEAKERS),
                msg=msg_text,
                timestamp=ts,
                topic=topic_name,
                phase_name="decision",
                websearch_context=websearch,
            )
            cases.append(msg)

        return cases

    # ── Scenario 3: Stale Fact Rejection ───────────────────────────────────

    def _gen_scene3(self) -> List[TestMessage]:
        """场景 3：过时事实拒绝 — 陈旧结果不应被重新采纳。

        5 种过期条件 × 3 个话题 = 15 条。
        """
        cases: List[TestMessage] = []

        conditions = [
            ("expired_by_turns", 12, "easy"),
            ("expired_by_time", 172800, "medium"),
            ("fresh_by_turns", 3, "easy"),
            ("fresh_by_time", 3600, "medium"),
            ("superseded_by_event", None, "hard"),
        ]

        topic_indices = [0, 10, 15]  # K8s, 告警阈值, Kafka

        for t_idx, topic_idx in enumerate(topic_indices):
            topic_info = TOPIC_POOL[topic_idx]
            base_topic = topic_info["topic"]

            for cond_idx, (cond_type, param, difficulty) in enumerate(conditions):
                idx = t_idx * len(conditions) + cond_idx
                chat_id = f"web_stale_{idx:02d}"
                ts = self.base_ts + 200000 + idx * 1800

                fact_stale, _ = topic_info["facts"][0]
                fact_fresh, _ = topic_info["facts"][1]

                search_result = SearchResult(
                    url="https://example.com/stale_info",
                    title=f"{base_topic} - 旧信息",
                    snippet=fact_stale[:60],
                    full_content=fact_stale,
                    source_type="community",
                    relevance_score=0.85,
                    timestamp=ts - 7200,
                    expiry_after_turns=10 if cond_type in ("expired_by_turns", "fresh_by_turns") else None,
                    expiry_after_seconds=86400.0 if cond_type in ("expired_by_time", "fresh_by_time") else None,
                )

                prior_memory = PriorMemoryState(
                    expected_topic=base_topic,
                    expected_summary=fact_fresh,
                    expected_status="decided",
                    override_status="superseded" if cond_type == "superseded_by_event" else "active",
                    memorized_at=ts - 3600,
                )

                expected_type = "reject_decision" if cond_type in ("expired_by_turns", "expired_by_time", "superseded_by_event") else "no_change"

                websearch = WebsearchContext(
                    scenario_id=SCENARIO_IDS[3],
                    search_results=[search_result],
                    search_intent=f"检查{base_topic}是否仍然适用",
                    expected_effect=ExpectedEffect(
                        type=expected_type,
                        expected_topic=base_topic,
                        expected_summary=fact_fresh,
                        expected_status="decided",
                    ),
                    conflict_with_prior=True,
                    prior_memory_state=prior_memory,
                )

                if cond_type in ("expired_by_turns", "expired_by_time"):
                    msg_text = self.rng.choice([
                        f"搜到了旧信息：{fact_stale}。不过我们已经更新到{fact_fresh}了，这个已经过时了。",
                        f"有个搜索结果说{fact_stale}，但这已经是过时的信息了，忽略吧。",
                    ])
                elif cond_type == "superseded_by_event":
                    msg_text = f"搜索结果显示{fact_stale}，但我们已经更新到{fact_fresh}了，旧的信息不再适用。"
                else:
                    msg_text = f"查了一下还是{fact_fresh}，没有变化，保持一致。"

                msg = TestMessage(
                    chat_id=chat_id,
                    msg_id="m001",
                    speaker=self.rng.choice(SPEAKERS),
                    msg=msg_text,
                    timestamp=ts,
                    topic=base_topic,
                    phase_name="decision",
                    websearch_context=websearch,
                )
                cases.append(msg)

        return cases

    # ── Scenario 4: Cross-session Recall ────────────────────────────────────

    def _gen_scene4(self) -> Tuple[List[TestMessage], List[TestMessage], List[TestMessage]]:
        """场景 4：跨 session 召回。

        5 组话题 → session1 建记忆 + session2 从记忆检索。
        预计 ~12-15 条 session1, ~9 条 session2, ~9 条 cross_expected。
        """
        session1_msgs: List[TestMessage] = []
        session2_msgs: List[TestMessage] = []
        cross_expected: List[TestMessage] = []

        for idx, topic_def in enumerate(CROSS_SESSION_TOPICS):
            chat_id = f"web_cross_{idx:02d}"
            base_ts = self.base_ts + 300000 + idx * 10000
            topic_name = topic_def["topic"]

            # Session 1: websearch -> memory building
            for fact_idx, (fact_text, fact_key) in enumerate(topic_def["session1_facts"]):
                s1_ts = base_ts + fact_idx * 1200
                search_result = SearchResult(
                    url=f"https://example.com/{fact_key}",
                    title=topic_name + " - 参考资料",
                    snippet=fact_text[:60],
                    full_content=fact_text,
                    source_type="official",
                    relevance_score=0.95,
                    timestamp=s1_ts,
                )
                websearch = WebsearchContext(
                    scenario_id=SCENARIO_IDS[4],
                    search_results=[search_result],
                    search_intent=f"确定{topic_name}的具体方案",
                    expected_effect=ExpectedEffect(
                        type="new_decision",
                        expected_topic=topic_name,
                        expected_summary=fact_text,
                        expected_status="decided",
                    ),
                    conflict_with_prior=False,
                )

                msg_s1 = TestMessage(
                    chat_id=chat_id,
                    msg_id=f"s1_m{fact_idx + 1:03d}",
                    speaker=SPEAKERS[fact_idx % len(SPEAKERS)],
                    msg=f"查到了：{fact_text}，就这个方案吧。",
                    timestamp=s1_ts,
                    topic=topic_name,
                    phase_name="decision",
                    websearch_context=websearch,
                )
                session1_msgs.append(msg_s1)

            # Session 2: pure conversation, recall from memory
            for recall_idx, recall_key in enumerate(topic_def["session2_recall_facts"]):
                recall_text = next((ft for ft, fk in topic_def["session1_facts"] if fk == recall_key), None)
                if recall_text is None:
                    continue

                s2_ts = base_ts + 7200 + recall_idx * 600
                msg_s2 = TestMessage(
                    chat_id=chat_id,
                    msg_id=f"s2_m{recall_idx + 1:03d}",
                    speaker=SPEAKERS[(recall_idx + 2) % len(SPEAKERS)],
                    msg=f"我们之前是不是决定过{recall_text}？我记得上次会上说过。",
                    timestamp=s2_ts,
                    topic=topic_name,
                    phase_name="decision",
                )
                session2_msgs.append(msg_s2)

            # cross_session_expected
            for recall_key in topic_def["session2_recall_facts"]:
                recall_text = next(ft for ft, fk in topic_def["session1_facts"] if fk == recall_key)
                cross_expected.append(TestMessage(
                    chat_id=chat_id,
                    msg_id=f"expect_recall_{recall_key}",
                    speaker="system",
                    msg=f"Expected recall from session 1: {recall_text}",
                    timestamp=base_ts + 7200,
                    topic=topic_name,
                    phase_name="evaluation",
                    websearch_context=WebsearchContext(
                        scenario_id=SCENARIO_IDS[4],
                        search_results=[],
                        search_intent="跨 session 记忆检索验证",
                        expected_effect=ExpectedEffect(
                            type="no_change",
                            expected_topic=topic_name,
                            expected_summary=recall_text,
                            expected_status="decided",
                        ),
                        conflict_with_prior=False,
                    ),
                ))

        return session1_msgs, session2_msgs, cross_expected

    # ── Scenario 5: Multi-source Merge ──────────────────────────────────────

    def _gen_scene5(self) -> List[TestMessage]:
        """场景 5：多源合并 — 冲突搜索结果，对话解决。

        6 个场景 × 每个 2 条（不同消息风格）= 12 条。
        """
        cases: List[TestMessage] = []

        for idx, scenario in enumerate(MERGE_SCENARIOS):
            chat_id_a = f"web_merge_{idx * 2:02d}"
            chat_id_b = f"web_merge_{idx * 2 + 1:02d}"
            ts = self.base_ts + 400000 + idx * 3600

            res_a = SearchResult(
                url=f"https://docs.example.com/merge_a_{idx}",
                title=scenario["sources"][0][1] + " — " + scenario["topic"],
                snippet=scenario["fact_a"][:60],
                full_content=scenario["fact_a"],
                source_type=scenario["sources"][0][0],
                relevance_score=0.92 if scenario["sources"][0][0] == "official" else 0.70,
                timestamp=ts + 60,
            )
            res_b = SearchResult(
                url=f"https://community.example.com/merge_b_{idx}",
                title=scenario["sources"][1][1] + " — " + scenario["topic"],
                snippet=scenario["fact_b"][:60],
                full_content=scenario["fact_b"],
                source_type=scenario["sources"][1][0],
                relevance_score=0.80 if scenario["sources"][1][0] == "community" else 0.95,
                timestamp=ts + 120,
            )

            websearch = WebsearchContext(
                scenario_id=SCENARIO_IDS[5],
                search_results=[res_a, res_b],
                search_intent=f"确定{scenario['topic']}的最佳方案",
                expected_effect=ExpectedEffect(
                    type="new_decision",
                    expected_topic=scenario["topic"],
                    expected_summary=scenario["resolved"],
                    expected_status="decided",
                    conflict_detection_expected=True,
                    conflict_resolution_expected_turns=3,
                ),
                conflict_with_prior=False,
            )

            # 消息风格 A：直接引用 2 个搜索结果并建议综合
            msg_a = TestMessage(
                chat_id=chat_id_a,
                msg_id="m001",
                speaker=self.rng.choice(SPEAKERS),
                msg=f"查到了两个说法：\n1. {scenario['fact_a']}\n2. {scenario['fact_b']}\n两个有点矛盾，综合来看{scenario['resolved']}",
                timestamp=ts,
                topic=scenario["topic"],
                phase_name="decision",
                websearch_context=websearch,
            )

            # 消息风格 B：提到冲突并引导讨论
            msg_b = TestMessage(
                chat_id=chat_id_b,
                msg_id="m001",
                speaker=self.rng.choice(SPEAKERS),
                msg=f"我搜到两个不同来源的结果：一个说{scenario['fact_a']}，另一个说{scenario['fact_b']}。大家讨论一下该怎么定？",
                timestamp=ts + 600,
                topic=scenario["topic"],
                phase_name="discussion",
                websearch_context=websearch,
            )

            cases.append(msg_a)
            cases.append(msg_b)

        return cases

    # ── Scenario 6: Distractor Tolerance ────────────────────────────────────

    def _gen_scene6(self) -> List[TestMessage]:
        """场景 6：干扰容错 — 无关搜索结果的噪声过滤。

        3 noise_ratio 级别 × 5 topics × 2 (有结果/纯噪声) = 30 条。
        """
        cases: List[TestMessage] = []

        noise_ratios = [(0.3, "easy"), (0.5, "medium"), (0.7, "hard")]

        scene6_topics = [
            ("Go 1.22 泛型特性", "Go 1.22 支持 range over int 和泛型类型推断改进", "go_gen"),
            ("gRPC 流式传输性能", "gRPC 双向流传输吞吐量比 REST 高 10 倍", "grpc"),
            ("Terraform 状态管理最佳实践", "Terraform 远程状态后端推荐使用 S3 + DynamoDB", "tf"),
            ("Elasticsearch 分片策略调整", "ES 8.12 新增分片自动均衡功能", "es"),
            ("Rust 异步运行时选型", "Tokio 是 Rust 生态中最成熟的异步运行时", "tokio"),
        ]

        # 上下文相关但无关的噪声（语义上和技术相关但不是用户要找的）
        context_noise_signals = [
            "对于这个话题的看法", "招聘相关职位", "社区讨论帖",
        ]

        for nr_idx, (noise_ratio, difficulty) in enumerate(noise_ratios):
            for top_idx, (topic_name, fact_text, fact_key) in enumerate(scene6_topics):
                idx = nr_idx * len(scene6_topics) * 2 + top_idx * 2
                base_ts = self.base_ts + 500000 + idx * 1800

                for variant in range(2):  # 0 = has_relevant, 1 = pure_noise
                    chat_id = f"web_noise_{idx + variant:02d}"
                    ts = base_ts + variant * 300
                    has_relevant = (variant == 0)

                    search_results: List[SearchResult] = []

                    if has_relevant:
                        search_results.append(SearchResult(
                            url=f"https://docs.example.com/{fact_key}",
                            title=f"{topic_name}的技术文档",
                            snippet=fact_text[:60],
                            full_content=fact_text,
                            source_type="official",
                            relevance_score=0.93,
                            timestamp=ts,
                        ))

                    # 上下文相关噪声
                    for sig in context_noise_signals:
                        search_results.append(SearchResult(
                            url=f"https://blog.example.com/{fact_key}_{sig[:8]}",
                            title=f"{topic_name} - {sig}",
                            snippet=f"关于{topic_name}的{sig}",
                            full_content=f"社区关于{topic_name}的{sig}",
                            source_type="community",
                            relevance_score=0.40,
                            timestamp=ts + 60,
                        ))

                    # 纯噪声
                    max_noise = max(1, int(5 * noise_ratio))
                    for n_i in range(max_noise):
                        nu, nt, ns = NOISE_TEMPLATES[n_i % len(NOISE_TEMPLATES)]
                        search_results.append(SearchResult(
                            url=f"{nu}?n={n_i}",
                            title=nt,
                            snippet=ns[:60],
                            full_content=ns,
                            source_type="community",
                            relevance_score=self.rng.uniform(0.10, 0.35),
                            timestamp=ts + 90 + n_i * 30,
                        ))

                    self.rng.shuffle(search_results)

                    expected_type = "new_decision" if has_relevant else "no_change"

                    if has_relevant:
                        msg_text = self.rng.choice([
                            f"搜到了相关资料：{fact_text}，这个信息有用，我们看一下吧。",
                            f"在搜索结果中找到了这条：{fact_text}，感觉很重要，讨论下。",
                        ])
                    else:
                        msg_text = self.rng.choice([
                            "搜了一圈没有找到有用的信息，结果都不相关。",
                            "搜索结果都是无关内容，没什么可用的。",
                        ])

                    websearch = WebsearchContext(
                        scenario_id=SCENARIO_IDS[6],
                        search_results=search_results,
                        search_intent=f"查找{topic_name}的参考资料",
                        expected_effect=ExpectedEffect(
                            type=expected_type,
                            expected_topic=topic_name,
                            expected_summary=fact_text if has_relevant else "无相关决策",
                            expected_status="decided" if has_relevant else "rejected",
                        ),
                        conflict_with_prior=False,
                    )

                    msg = TestMessage(
                        chat_id=chat_id,
                        msg_id="m001",
                        speaker=self.rng.choice(SPEAKERS),
                        msg=msg_text,
                        timestamp=ts,
                        topic=topic_name,
                        phase_name="decision",
                        expected_decision=has_relevant,
                        websearch_context=websearch,
                    )
                    cases.append(msg)

        return cases

    # ── Edge Case Supplement ────────────────────────────────────────────────

    def _gen_edge_cases(self) -> List[TestMessage]:
        """边缘场景补充 — 覆盖蓝图未明确但实际重要的场景。

        生成 ~8 条：
        - 搜索结果为 0（空搜索）
        - 搜索 relevance_score 接近 0
        - 搜索内容包含安全漏洞警告 vs 正常技术信息
        - 同一事实多次被搜索（去重检测）
        """
        cases: List[TestMessage] = []

        # 1. 空搜索结果
        empty_search = WebsearchContext(
            scenario_id="web_edge_empty",
            search_results=[],
            search_intent="查找不存在的主题",
            expected_effect=ExpectedEffect(
                type="no_change",
                expected_topic="未知主题",
                expected_summary="搜索无结果",
                expected_status="rejected",
            ),
            conflict_with_prior=False,
        )
        cases.append(TestMessage(
            chat_id="web_edge_00", msg_id="m001", speaker=self.rng.choice(SPEAKERS),
            msg="搜了一下没找到任何相关的信息，算了吧。",
            timestamp=self.base_ts + 600000, topic="未知主题",
            expected_decision=False, phase_name="decision",
            websearch_context=empty_search,
        ))

        # 2. 低 relevance 结果（所有结果都不可信）
        low_rel = WebsearchContext(
            scenario_id="web_edge_lowrel",
            search_results=[
                SearchResult(
                    url="https://unknown.example.com/unverified",
                    title="不确定来源的信息",
                    snippet="未经证实的内容...",
                    full_content="来源不可靠的内容",
                    source_type="community",
                    relevance_score=0.15,
                    timestamp=self.base_ts + 600600,
                )
            ],
            search_intent="查找某项技术信息",
            expected_effect=ExpectedEffect(
                type="no_change",
                expected_topic="不确定技术信息",
                expected_summary="低可信度结果不采纳",
                expected_status="rejected",
            ),
            conflict_with_prior=False,
        )
        cases.append(TestMessage(
            chat_id="web_edge_01", msg_id="m001", speaker=self.rng.choice(SPEAKERS),
            msg="搜到一个结果但来源看起来不太可靠，大家有其他资料吗？",
            timestamp=self.base_ts + 600600, topic="不确定技术信息",
            expected_decision=False, phase_name="decision",
            websearch_context=low_rel,
        ))

        # 3-4. 安全漏洞警告 vs 正常更新
        vuln_topic = "Log4j 安全漏洞处理"
        vuln_fact = "Log4j 2.17.1 是修复 CVE-2021-44832 的安全版本"
        normal_fact = "Log4j 2.20.0 发布，包含性能和内存优化"

        for vi, (is_vuln, fact, key) in enumerate([
            (True, vuln_fact, "log4j_cve"),
            (False, normal_fact, "log4j_perf"),
        ]):
            vuln_websearch = WebsearchContext(
                scenario_id="web_edge_vuln" if is_vuln else "web_edge_normal",
                search_results=[
                    SearchResult(
                        url=f"https://security.example.com/{key}",
                        title=(
                            f"[安全公告] {fact}" if is_vuln else f"版本发布：{fact}"
                        ),
                        snippet=fact[:60],
                        full_content=self.rng.choice(SECURITY_INCIDENT_TEMPLATES) if is_vuln else fact,
                        source_type="official",
                        relevance_score=0.97 if is_vuln else 0.90,
                        timestamp=self.base_ts + 600000 + (vi + 1) * 1800,
                    )
                ],
                search_intent=f"查看{fact}",
                expected_effect=ExpectedEffect(
                    type="new_decision",
                    expected_topic=vuln_topic,
                    expected_summary=fact,
                    expected_status="decided",
                ),
                conflict_with_prior=False,
            )
            cases.append(TestMessage(
                chat_id=f"web_edge_0{vi + 2}",
                msg_id="m001",
                speaker=self.rng.choice(SPEAKERS),
                msg=(
                    f"安全通告：{fact}。这是严重安全问题，必须马上处理！"
                    if is_vuln else
                    f"看到版本更新：{fact}。不是安全相关的，可以排进常规发布计划。"
                ),
                timestamp=self.base_ts + 600000 + (vi + 1) * 1800,
                topic=vuln_topic,
                phase_name="decision",
                websearch_context=vuln_websearch,
            ))

        # 5-6. 多轮对话中同一事实重复搜索（去重）
        for ri in range(2):
            cases.append(TestMessage(
                chat_id=f"web_edge_0{vi + 2 + ri}",
                msg_id="m001",
                speaker=self.rng.choice(SPEAKERS),
                msg=f"又搜了一遍还是同样的结果，和上次一样，没有更新。",
                timestamp=self.base_ts + 601000 + (vi + ri + 1) * 7200,
                topic="重复搜索结果验证",
                phase_name="decision",
                websearch_context=WebsearchContext(
                    scenario_id="web_edge_dup",
                    search_results=[
                        SearchResult(
                            url="https://example.com/no_change",
                            title="无更新",
                            snippet="和上次结果一致",
                            full_content="信息没有变化",
                            source_type="official",
                            relevance_score=0.80,
                            timestamp=self.base_ts + 601000,
                        )
                    ],
                    search_intent="确认信息是否有更新",
                    expected_effect=ExpectedEffect(
                        type="no_change",
                        expected_topic="重复搜索结果验证",
                        expected_summary="信息无变化，无需重复记忆",
                        expected_status="pending",
                    ),
                    conflict_with_prior=False,
                ),
            ))

        return cases

    # ── Serialization ────────────────────────────────────────────────────────

    def _msg_to_dict(self, msg: TestMessage) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "chat_id": msg.chat_id,
            "msg_id": msg.msg_id,
            "speaker": msg.speaker,
            "msg": msg.msg,
            "expected_decision": msg.expected_decision,
            "is_distractor": msg.is_distractor,
            "timestamp": msg.timestamp,
            "topic": msg.topic,
            "phase_name": msg.phase_name,
        }
        if msg.websearch_context:
            ws = msg.websearch_context
            ws_dict: Dict[str, Any] = {
                "scenario_id": ws.scenario_id,
                "search_results": [
                    {
                        "url": sr.url,
                        "title": sr.title,
                        "snippet": sr.snippet,
                        "full_content": sr.full_content,
                        "source_type": sr.source_type,
                        "relevance_score": sr.relevance_score,
                        "timestamp": sr.timestamp,
                    }
                    for sr in ws.search_results
                ],
                "search_intent": ws.search_intent,
                "expected_effect": {
                    "type": ws.expected_effect.type,
                    "expected_topic": ws.expected_effect.expected_topic,
                    "expected_summary": ws.expected_effect.expected_summary,
                    "expected_status": ws.expected_effect.expected_status,
                },
                "conflict_with_prior": ws.conflict_with_prior,
            }
            # expiry fields
            for sr in ws.search_results:
                sr_dict = ws_dict["search_results"][ws.search_results.index(sr)]
                if sr.expiry_after_turns is not None:
                    sr_dict["expiry_after_turns"] = sr.expiry_after_turns
                if sr.expiry_after_seconds is not None:
                    sr_dict["expiry_after_seconds"] = sr.expiry_after_seconds

            # optional conflict fields in expected_effect
            ee = ws.expected_effect
            if ee.conflict_detection_expected is not None:
                ws_dict["expected_effect"]["conflict_detection_expected"] = ee.conflict_detection_expected
            if ee.conflict_resolution_expected_turns is not None:
                ws_dict["expected_effect"]["conflict_resolution_expected_turns"] = ee.conflict_resolution_expected_turns

            # prior_memory_state
            if ws.prior_memory_state:
                pm = ws.prior_memory_state
                pm_dict: Dict[str, Any] = {
                    "expected_topic": pm.expected_topic,
                    "expected_summary": pm.expected_summary,
                    "expected_status": pm.expected_status,
                    "memorized_at": pm.memorized_at,
                }
                if pm.override_status:
                    pm_dict["override_status"] = pm.override_status
                ws_dict["prior_memory_state"] = pm_dict

            d["websearch_context"] = ws_dict

        return d

    def _to_expected_dict(self, msg: TestMessage) -> Dict[str, Any]:
        exp: Dict[str, Any] = {
            "chat_id": msg.chat_id,
            "msg_id": msg.msg_id,
            "expected_topic": msg.topic,
            "expected_summary": msg.msg[:100],
            "expected_status": "decided",
            "expected_impact": "major",
        }
        if msg.websearch_context:
            ws = msg.websearch_context
            exp["websearch_scenario_id"] = ws.scenario_id
            exp["expected_effect_type"] = ws.expected_effect.type
            exp["expected_effect_topic"] = ws.expected_effect.expected_topic
            exp["expected_effect_summary"] = ws.expected_effect.expected_summary
            exp["conflict_with_prior"] = ws.conflict_with_prior
        return exp

    # ── Main Generation ─────────────────────────────────────────────────────

    def generate(self, scenarios: Optional[List[int]] = None) -> Dict[str, Any]:
        """生成测试数据。

        Args:
            scenarios: 要生成的场景编号列表（1-6），None 表示全量。

        Returns:
            generation_report dict
        """
        if scenarios is None:
            scenarios = [1, 2, 3, 4, 5, 6, 7]  # 7 = edge cases

        report: Dict[str, Any] = {
            "seed": self.seed,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S+00:00", time.gmtime()),
            "scenarios": {},
            "total_test_cases": 0,
            "total_files": 0,
        }

        main_msgs: List[TestMessage] = []
        session1_msgs: List[TestMessage] = []
        session2_msgs: List[TestMessage] = []
        cross_expected: List[TestMessage] = []

        # Scenario 1: 简单事实提取
        if 1 in scenarios:
            s1 = self._gen_scene1()
            report["scenarios"]["1_simple_extract"] = {
                "name": SCENARIO_LABELS[1],
                "count": len(s1),
            }
            main_msgs.extend(s1)

        # Scenario 2: 事实更新
        if 2 in scenarios:
            s2 = self._gen_scene2()
            report["scenarios"]["2_fact_update"] = {
                "name": SCENARIO_LABELS[2],
                "count": len(s2),
            }
            main_msgs.extend(s2)

        # Scenario 3: 过时事实拒绝
        if 3 in scenarios:
            s3 = self._gen_scene3()
            report["scenarios"]["3_stale_rejection"] = {
                "name": SCENARIO_LABELS[3],
                "count": len(s3),
            }
            main_msgs.extend(s3)

        # Scenario 4: 跨 session
        if 4 in scenarios:
            s4_s1, s4_s2, s4_cross = self._gen_scene4()
            total_s4 = len(s4_s1) + len(s4_s2)
            report["scenarios"]["4_cross_session"] = {
                "name": SCENARIO_LABELS[4],
                "count": total_s4,
                "session1_messages": len(s4_s1),
                "session2_messages": len(s4_s2),
                "cross_session_expected": len(s4_cross),
            }
            session1_msgs.extend(s4_s1)
            session2_msgs.extend(s4_s2)
            cross_expected.extend(s4_cross)
            main_msgs.extend(s4_s1)
            main_msgs.extend(s4_s2)

        # Scenario 5: 多源合并
        if 5 in scenarios:
            s5 = self._gen_scene5()
            report["scenarios"]["5_multi_source_merge"] = {
                "name": SCENARIO_LABELS[5],
                "count": len(s5),
            }
            main_msgs.extend(s5)

        # Scenario 6: 干扰容错
        if 6 in scenarios:
            s6 = self._gen_scene6()
            report["scenarios"]["6_distractor_tolerance"] = {
                "name": SCENARIO_LABELS[6],
                "count": len(s6),
            }
            main_msgs.extend(s6)

        # Edge cases (scenario id 7 in internal routing)
        if 7 in scenarios:
            s7 = self._gen_edge_cases()
            report["scenarios"]["7_edge_cases"] = {
                "name": "边缘场景补充",
                "count": len(s7),
            }
            main_msgs.extend(s7)

        # Summary
        total_unique = len(main_msgs)
        report["total_test_cases"] = total_unique
        report["files"] = {}

        # ── Write files ──
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._write_jsonl(self.output_dir / "messages.jsonl", main_msgs)
        main_expected = [self._to_expected_dict(m) for m in main_msgs]
        self._write_dicts_jsonl(self.output_dir / "expected.jsonl", main_expected)
        report["files"]["messages.jsonl"] = len(main_msgs)
        report["files"]["expected.jsonl"] = len(main_expected)

        if 4 in scenarios:
            self._write_jsonl(self.output_dir / "session1_messages.jsonl", session1_msgs)
            s1_exp = [self._to_expected_dict(m) for m in session1_msgs]
            self._write_dicts_jsonl(self.output_dir / "session1_expected.jsonl", s1_exp)
            report["files"]["session1_messages.jsonl"] = len(session1_msgs)
            report["files"]["session1_expected.jsonl"] = len(s1_exp)

            self._write_jsonl(self.output_dir / "session2_messages.jsonl", session2_msgs)
            s2_exp = [self._to_expected_dict(m) for m in session2_msgs]
            self._write_dicts_jsonl(self.output_dir / "session2_expected.jsonl", s2_exp)
            report["files"]["session2_messages.jsonl"] = len(session2_msgs)
            report["files"]["session2_expected.jsonl"] = len(s2_exp)

            self._write_jsonl(self.output_dir / "cross_session_expected.jsonl", cross_expected)
            report["files"]["cross_session_expected.jsonl"] = len(cross_expected)

        report["total_files"] = len(report["files"])

        with open(self.output_dir / "generation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    def _write_jsonl(self, path: Path, msgs: List[TestMessage]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for msg in msgs:
                f.write(json.dumps(self._msg_to_dict(msg), ensure_ascii=False) + "\n")

    @staticmethod
    def _write_dicts_jsonl(path: Path, dicts: List[Dict[str, Any]]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for d in dicts:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")


# ── CLI ──────────────────────────────────────────────────────────────────────


def _dry_run(scenarios: Optional[List[int]] = None) -> None:
    if scenarios is None:
        scenarios = [1, 2, 3, 4, 5, 6, 7]

    gen = WebsearchEvalDataGenerator(seed=42)

    print("=" * 60)
    print("  WebSearch 评测数据生成 — Dry Run")
    print("=" * 60)

    sizes: Dict[str, int] = {}

    if 1 in scenarios:
        s1 = gen._gen_scene1()
        sizes[f"1. {SCENARIO_LABELS[1]}"] = len(s1)
    if 2 in scenarios:
        s2 = gen._gen_scene2()
        sizes[f"2. {SCENARIO_LABELS[2]}"] = len(s2)
    if 3 in scenarios:
        s3 = gen._gen_scene3()
        sizes[f"3. {SCENARIO_LABELS[3]}"] = len(s3)
    if 4 in scenarios:
        s4_s1, s4_s2, s4_cross = gen._gen_scene4()
        sizes[f"4. {SCENARIO_LABELS[4]} (S1+S2)"] = len(s4_s1) + len(s4_s2)
        sizes[f"4. {SCENARIO_LABELS[4]} (cross_expected)"] = len(s4_cross)
    if 5 in scenarios:
        s5 = gen._gen_scene5()
        sizes[f"5. {SCENARIO_LABELS[5]}"] = len(s5)
    if 6 in scenarios:
        s6 = gen._gen_scene6()
        sizes[f"6. {SCENARIO_LABELS[6]}"] = len(s6)
    if 7 in scenarios:
        s7 = gen._gen_edge_cases()
        sizes[f"7. 边缘场景补充"] = len(s7)

    total = sum(sizes.values())
    print(f"\n{'场景':<45} {'生成量':>6}")
    print("-" * 55)
    for name, count in sizes.items():
        print(f"{name:<45} {count:>6}")
    print("-" * 55)
    print(f"{'总计':<45} {total:>6}")

    # 预计 messages.jsonl（不含 cross_expected）
    main_total = sum(v for k, v in sizes.items() if "(cross_expected)" not in k)
    print(f"\n  messages.jsonl (主文件): ~{main_total} 条")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WebSearch 记忆评测测试数据生成脚本 (Phase 3)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="随机种子 (默认: 42)"
    )
    parser.add_argument(
        "--output", type=str, default="eval_dataset/argusbot_websearch",
        help="输出目录 (默认: eval_dataset/argusbot_websearch)"
    )
    parser.add_argument(
        "--scenarios", type=int, nargs="+", choices=range(1, 8),
        help="只生成指定场景编号 (1-7)，不指定则全量生成"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览生成量，不写入文件"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        _dry_run(args.scenarios)
        return

    generator = WebsearchEvalDataGenerator(seed=args.seed, output_dir=args.output)
    report = generator.generate(scenarios=args.scenarios)

    print(f"\n{'=' * 60}")
    print(f"  WebSearch 评测数据生成完成")
    print(f"  输出目录: {generator.output_dir.resolve()}")
    print(f"  Seed:     {args.seed}")
    print(f"{'=' * 60}")
    print(f"{'文件':<42} {'条目':>6}")
    print("-" * 50)
    for fname, count in report["files"].items():
        print(f"{fname:<42} {count:>6}")
    print("-" * 50)
    print(f"{'总文件数':<42} {report['total_files']:>6}")
    print(f"{'总测试用例 (主文件)':<42} {report['total_test_cases']:>6}")
    print()
    print("场景分布:")
    for key, sc in report["scenarios"].items():
        print(f"  - {sc['name']}: {sc['count']} 条")
    print(f"\n完整报告: {generator.output_dir / 'generation_report.json'}")
    print()


if __name__ == "__main__":
    main()