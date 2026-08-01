"""LLM 数据生成器 — 大规模有真值标注的群聊对话数据集生成

设计参考 GroupMemBench (https://arxiv.org/pdf/2605.14498)：
- 消息格式：chat_id, msg_id, speaker, role, msg, timestamp, reply_to, phase_name, topic
- 查询类型：multi_hop, knowledge_update, temporal, user_implicit, term_ambiguity, abstention
- 消息分域（domain）/群聊（chat）两级组织
- 线程化对话：reply_to 字段体现消息回复关系
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

DOMAIN_BLUEPRINT_TEMPLATE = """你是一个企业级群聊对话设计师。请为以下域生成群聊场景蓝图。

域名称：{domain_name}
域描述：{domain_description}

要求：
- {num_chats} 个群聊频道（channel），每个讨论 2-3 个技术/业务话题
- 每个频道 {num_participants} 个参与者
- 每个参与者必须有角色（role），如 CTO, Engineering Manager, DevOps Engineer, Product Manager, Security Engineer, Data Scientist 等
- 角色要专业、贴近工作实际，不同参与者角色不同
- 参与者使用英文名
- 每个话题嵌入 1-2 个决策点（decision point）
- 话题之间通过"阶段"（phase）区分：proposal → discussion → decision → implementation

可供选的话题列表（选择 {num_topics} 个）：
{topics_json}

输出 JSON 格式蓝图，格式示例：
{{
  "channels": [
    {{
      "name": "infra-discussion",
      "users": [
        {{"name": "Alice", "role": "CTO", "style": "direct", "expertise": "system architecture"}},
        {{"name": "Bob", "role": "DevOps Engineer", "style": "cautious", "expertise": "infrastructure"}}
      ],
      "topics": ["用PG还是MySQL", "K8s版本升级策略"]
    }}
  ]
}}
只输出 JSON，无额外文字。
"""

CHAT_MESSAGE_TEMPLATE = """根据以下蓝图生成群聊频道的完整对话。

频道名称：{channel_name}
参与者：
{users_json}

本频道讨论的话题：
{topics_json}

消息生成要求（严格遵循）：
- 每条消息长度 5-80 字，句式多变
- 生成至少 {min_msgs} 条消息，覆盖所有话题的充分讨论
- 说话人使用英文名，不允许中文名
- **每条消息必须包含以下所有字段**：
  chat_id, msg_id, speaker, role, msg, timestamp, reply_to, phase_name, topic, is_distractor, expected_decision
- `reply_to`：回复上一条相关的消息 msg_id；如果是新话题开头发言则为 null
- `role`：参与者的角色（如 CTO, DevOps Engineer 等）
- `phase_name`：当前阶段，可选值：proposal, discussion, decision, implementation
- `topic`：所属话题名称
- `timestamp`：ISO 8601 格式，按消息顺序每 5-30 分钟递增
- 参与者之间使用 @用户名 相互回复
- **不同角色用语要体现角色特点**：
  CTO 说话高屋建瓴；Engineer 注重技术细节；PM 关注进度和成本；Security Engineer 关心安全问题
- 每个话题从 proposal 阶段开始，经过 discussion，到达 decision 或 implementation
- 决策点（expected_decision=true）通过共识形成，不要机械
- 嵌入 {noise_per_chat} 条干扰消息（闲聊、天气、午餐等）
- 部分话题只讨论不定论（完成 expected_decision 标注）

输出 JSONL，每行一个消息对象：
{{"chat_id": "infra-discussion", "msg_id": "m001", "speaker": "Alice", "role": "CTO", "msg": "@Bob PG的扩展性你怎么看？我们新项目需要考虑这个", "timestamp": "2026-01-15T09:00:00", "reply_to": null, "phase_name": "proposal", "topic": "用PG还是MySQL", "is_distractor": false, "expected_decision": false}}
"""

QUERY_GEN_TEMPLATE = """根据以下群聊对话，为每个频道生成评估查询。

对话数据（messages.jsonl）：
{all_messages_json}

要求为每个频道生成以下 **6 类查询**（每类至少 1 个）：

1. **multi_hop**（多跳推理）：需要结合 2-3 条不同消息的信息才能回答
2. **knowledge_update**（知识更新）：不同用户持有不同/矛盾的偏好，答案取决于提问者是谁
3. **temporal**（时间推理）：问题涉及"先/后""最近""之前"等时间关系
4. **user_implicit**（用户隐式推理）：问题用第一人称"我"隐藏了提问者身份，需要根据上下文推断
5. **term_ambiguity**（术语歧义）：同一术语（如"token""cache""agent"）不同角色理解不同
6. **abstention**（应拒绝回答）：问题涉及聊天中没有的信息，系统应当回答不知道

输出 JSONL 格式，每行一个查询对象：
{{"chat_id": "infra-discussion", "q_id": "q001", "asker": "Alice", "query_type": "multi_hop", "query": "Bob和Charlie对于PG性能的观点分别是什么？", "gold_answer": "Bob认为PG扩展性很好，Charlie担心线上性能", "source_msg_ids": ["m002", "m006"], "difficulty": "medium"}}

对于 knowledge_update：`gold_answer_per_user` 字段包含按提问者区分的答案
{{"chat_id": "infra-discussion", "q_id": "q002", "asker": "Alice", "query_type": "knowledge_update", "query": "PG和MySQL哪个更好？", "gold_answer_per_user": {{"Alice": "Alice认为PG更好", "Charlie": "Charlie坚持MySQL更稳妥"}}, "source_msg_ids": ["m002", "m009"]}}

对于 abstention：gold_answer 为 "refuse"
{{"chat_id": "infra-discussion", "q_id": "q003", "asker": "Bob", "query_type": "abstention", "query": "新项目的预算是多少？", "gold_answer": "refuse", "source_msg_ids": [], "difficulty": "easy"}}

只输出 JSONL，不要输出其他文字。
"""


class EvalDatasetGenerator:
    """大规模评估数据集生成器

    设计参考 GroupMemBench：
    - 多域/多频道/角色分类
    - 线程化回复结构
    - 6 类评估查询
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config = self._load_config(config_path)
        self._llm: Optional[LLMClient] = None
        # Model: prefer MODEL_NAME from env, then config.yaml, then default
        import os
        self._model = (
            os.getenv("MODEL_NAME")
            or self._config.get("generation", {}).get("model")
            or "deepseek-chat"
        )
        self._temperature = self._config.get("generation", {}).get("temperature", 0.7)
        self._base_time = datetime(2026, 1, 15, 9, 0, 0)

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    @staticmethod
    def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        if config_path and Path(config_path).exists():
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        default = Path(__file__).resolve().parent.parent.parent / "eval_dataset" / "config.yaml"
        if default.exists():
            import yaml
            with open(default, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {"generation": {"method": "llm", "model": "deepseek-chat", "temperature": 0.7}}

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        llm = self._get_llm()
        response = llm.client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def _parse_jsonl(raw: str) -> List[Dict]:
        messages: List[Dict] = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            try:
                obj = json.loads(line)
                messages.append(obj)
            except json.JSONDecodeError:
                logger.warning("Skipping unparseable line: %s", line[:80])
        return messages

    def _parse_messages(self, raw: str, chat_id: str) -> Tuple[List[Dict], List[Dict]]:
        """解析消息 JSONL，返回 (messages, expected_decisions)"""
        messages: List[Dict] = []
        expected: List[Dict] = []
        idx = 0
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            try:
                obj = json.loads(line)
                obj["chat_id"] = chat_id
                if "msg_id" not in obj or not obj["msg_id"]:
                    idx += 1
                    obj["msg_id"] = f"m{idx:03d}"
                messages.append(obj)
                if obj.get("expected_decision"):
                    expected.append({
                        "chat_id": chat_id,
                        "msg_id": obj.get("msg_id", ""),
                        "expected_topic": obj.get("topic", obj.get("expected_topic", "")),
                        "expected_summary": obj.get("msg", "")[:100],
                        "expected_status": "decided",
                        "expected_impact": obj.get("expected_impact", "major"),
                        "difficulty": obj.get("difficulty", "medium"),
                    })
            except json.JSONDecodeError:
                logger.warning("Skipping line: %s", line[:60])
        return messages, expected

    @staticmethod
    def _fix_reply_to(messages: List[Dict]) -> List[Dict]:
        """确保 reply_to 字段一致性"""
        if not messages:
            return messages
        msg_ids = {m.get("msg_id") for m in messages}
        for m in messages:
            rt = m.get("reply_to")
            if rt and rt not in msg_ids:
                m["reply_to"] = None
        return messages

    def _generate_domain(self, domain: Dict, output_dir: Path,
                         batch_idx: int) -> Tuple[List[Dict], List[Dict]]:
        """生成一个域（domain）的全部消息

        Returns:
            (all_messages, all_expected)
        """
        domain_name = domain["name"]
        domain_desc = domain.get("description", "")
        num_chats = domain.get("num_chats", 3)
        participants_per_chat = domain.get("participants_per_chat", 4)
        topics = domain.get("topics", [])
        noise_per_chat = domain.get("noise_per_chat", 3)
        styles = self._config.get("speaker_styles", [])

        logger.info("=== Domain %d: %s ===", batch_idx + 1, domain_name)

        # Layer 1: 域蓝图
        layer1_prompt = DOMAIN_BLUEPRINT_TEMPLATE.format(
            domain_name=domain_name,
            domain_description=domain_desc,
            num_chats=num_chats,
            num_participants=participants_per_chat,
            num_topics=min(len(topics), num_chats * 3),
            topics_json=json.dumps(topics, ensure_ascii=False),
        )
        logger.info("  [Blueprint] Generating...")
        blueprint_raw = self._call_llm(layer1_prompt)
        logger.info("  [Blueprint] done (%d chars)", len(blueprint_raw))

        # 解析蓝图
        channels = self._try_parse_blueprint(blueprint_raw)
        if not channels:
            logger.warning("  Failed to parse blueprint, using fallback")
            channels = self._fallback_blueprint(domain_name, topics, num_chats)

        all_messages: List[Dict] = []
        all_expected: List[Dict] = []

        for ch_idx, channel in enumerate(channels):
            ch_name = channel.get("name", f"{domain_name}_ch{ch_idx}")
            users = channel.get("users", [])
            ch_topics = channel.get("topics", topics[:2])
            ch_topics_text = json.dumps(ch_topics, ensure_ascii=False)

            users_text = json.dumps(users, ensure_ascii=False)
            if len(users_text) > 2000:
                users_text = json.dumps([{k: v for k, v in u.items() if k != "expertise"}
                                         for u in users], ensure_ascii=False)

            prompt = CHAT_MESSAGE_TEMPLATE.format(
                channel_name=ch_name,
                users_json=users_text,
                topics_json=ch_topics_text,
                noise_per_chat=noise_per_chat,
                min_msgs=30,
            )
            logger.info("  [Chat %d/%d] %s generating...", ch_idx + 1, len(channels), ch_name)
            messages_raw = self._call_llm(prompt)
            logger.info("  [Chat %d] done (%d chars)", ch_idx + 1, len(messages_raw))

            msgs, expected = self._parse_messages(messages_raw, ch_name)
            msgs = self._fix_reply_to(msgs)

            # 清理过多的 expected：有些 LLM 会把每条带决策的消息都标为 expected_decision=true
            # 只保留确实形成共识的决策点
            cleaned_expected = self._deduplicate_decisions(expected)

            logger.info("  -> %d messages, %d decisions", len(msgs), len(cleaned_expected))
            all_messages.extend(msgs)
            all_expected.extend(cleaned_expected)

        return all_messages, all_expected

    def _try_parse_blueprint(self, raw: str) -> List[Dict]:
        """尝试解析 LLM 输出的蓝图 JSON"""
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line.startswith("```") or line.startswith("'''"):
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    continue
                if "channels" in obj and isinstance(obj["channels"], list):
                    return obj["channels"]
                # 也可能嵌套
                for v in obj.values():
                    if isinstance(v, dict) and "channels" in v:
                        return v["channels"]
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and "name" in v[0]:
                        return v
            except (json.JSONDecodeError, TypeError):
                continue
        return []

    def _fallback_blueprint(self, domain_name: str, topics: List[str],
                            num_chats: int) -> List[Dict]:
        """蓝图解析失败时的降级方案"""
        roles_pool = [
            {"name": "Alice", "role": "CTO", "style": "direct"},
            {"name": "Bob", "role": "DevOps Engineer", "style": "cautious"},
            {"name": "Charlie", "role": "Engineering Manager", "style": "analytical"},
            {"name": "David", "role": "Product Manager", "style": "pragmatic"},
            {"name": "Emma", "role": "Security Engineer", "style": "thorough"},
            {"name": "Frank", "role": "Data Scientist", "style": "analytical"},
        ]
        channels = []
        topics_per_chat = max(2, len(topics) // num_chats)
        for i in range(num_chats):
            ch_topics = topics[i * topics_per_chat: (i + 1) * topics_per_chat]
            if not ch_topics:
                ch_topics = topics[-topics_per_chat:]
            users = roles_pool[i * 2: i * 2 + 4]
            channels.append({
                "name": f"{domain_name}_channel_{i}",
                "users": users,
                "topics": ch_topics,
            })
        return channels

    @staticmethod
    def _deduplicate_decisions(expected: List[Dict]) -> List[Dict]:
        """去重并合并相同 topic 的决策"""
        seen_topics: Dict[str, Dict] = {}
        for e in expected:
            t = e.get("expected_topic", "")
            if t not in seen_topics:
                seen_topics[t] = e
            else:
                if len(e.get("expected_summary", "")) > len(seen_topics[t].get("expected_summary", "")):
                    seen_topics[t] = e
        return list(seen_topics.values())

    def _generate_queries(self, messages: List[Dict], output_dir: Path) -> List[Dict]:
        """根据生成的消息生成 6 类评估查询"""
        chat_groups: Dict[str, List[Dict]] = {}
        for m in messages:
            cid = m.get("chat_id", "unknown")
            chat_groups.setdefault(cid, []).append(m)

        all_queries: List[Dict] = []

        for chat_id, msgs in chat_groups.items():
            sample = msgs[:30]
            if len(sample) < 5:
                continue

            msgs_json = json.dumps(sample, ensure_ascii=False, indent=2)
            prompt = QUERY_GEN_TEMPLATE.format(all_messages_json=msgs_json)

            logger.info("  [Queries] %s generating...", chat_id)
            raw = self._call_llm(prompt)
            logger.info("  [Queries] done (%d chars)", len(raw))

            queries = self._parse_jsonl(raw)
            for q in queries:
                q["chat_id"] = chat_id
            all_queries.extend(queries)
            logger.info("  -> %d queries", len(queries))

        return all_queries

    def generate_benchmark(self, output_dir: str,
                           domains: Optional[List[Dict]] = None) -> None:
        """生成 GroupMemBench 风格的 benchmark 数据

        Args:
            output_dir: 输出目录
            domains: 域列表，每个域包含 name/description/topics/num_chats/participants_per_chat
                     不提供则使用默认域配置
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        if domains is None:
            domains = [
                {
                    "name": "infrastructure",
                    "description": "基础设施团队讨论数据库、容器化、监控等技术选型",
                    "num_chats": 5,
                    "participants_per_chat": 4,
                    "noise_per_chat": 5,
                    "topics": [
                        "用PG还是MySQL", "Redis缓存key规范", "分库分表方案",
                        "K8s版本升级策略", "Docker镜像体积优化",
                    ],
                },
                {
                    "name": "frontend",
                    "description": "前端团队讨论框架迁移、构建工具、组件库等",
                    "num_chats": 5,
                    "participants_per_chat": 4,
                    "noise_per_chat": 5,
                    "topics": [
                        "Next.js App Router迁移", "组件库选Antd还是Semi",
                        "构建工具切Vite",
                    ],
                },
                {
                    "name": "monitoring",
                    "description": "SRE团队讨论监控、告警、日志等系统",
                    "num_chats": 5,
                    "participants_per_chat": 4,
                    "noise_per_chat": 5,
                    "topics": [
                        "告警阈值调多少", "Grafana大盘重构", "日志采样率",
                    ],
                },
                {
                    "name": "messaging",
                    "description": "中间件团队讨论消息队列选型与调优",
                    "num_chats": 5,
                    "participants_per_chat": 4,
                    "noise_per_chat": 5,
                    "topics": [
                        "Kafka分区数调整", "RabbitMQ死信队列", "Pulsar Topic管理",
                    ],
                },
                {
                    "name": "backend",
                    "description": "后端团队讨论API设计、微服务架构、性能优化",
                    "num_chats": 5,
                    "participants_per_chat": 4,
                    "noise_per_chat": 5,
                    "topics": [
                        "API版本管理策略", "gRPC vs REST", "服务网格选型",
                        "缓存策略设计", "数据库连接池优化",
                    ],
                },
                {
                    "name": "security",
                    "description": "安全团队讨论漏洞扫描、权限管理、加密方案等",
                    "num_chats": 5,
                    "participants_per_chat": 4,
                    "noise_per_chat": 5,
                    "topics": [
                        "API安全认证方案", "密钥管理策略", "零信任架构",
                        "代码安全扫描流程", "数据脱敏方案",
                    ],
                },
                {
                    "name": "mobile",
                    "description": "移动端团队讨论跨平台框架、性能优化、CI/CD等",
                    "num_chats": 5,
                    "participants_per_chat": 4,
                    "noise_per_chat": 5,
                    "topics": [
                        "Flutter vs React Native", "移动端包体积优化",
                        "APP更新策略", "移动端监控方案",
                    ],
                },
            ]

        all_messages: List[Dict] = []
        all_expected: List[Dict] = []
        total_llm_calls = 0

        for i, domain in enumerate(domains):
            start_time = time.time()
            msgs, expected = self._generate_domain(domain, out, i)

            # Count LLM calls for this domain: 1 blueprint + num_chats chat calls
            domain_llm_calls = 1 + domain.get("num_chats", 3)
            total_llm_calls += domain_llm_calls

            all_messages.extend(msgs)
            all_expected.extend(expected)
            elapsed = time.time() - start_time
            logger.info("Domain '%s' done: %d msgs, %d dec, %d LLM calls, %.1fs",
                        domain["name"], len(msgs), len(expected), domain_llm_calls, elapsed)

            # 中间写入，防止生成失败丢失已生成数据
            self._write_outputs(out, all_messages, all_expected)
            with open(out / "generation_progress.json", "w", encoding="utf-8") as f:
                json.dump({
                    "messages": len(all_messages),
                    "expected": len(all_expected),
                    "llm_calls": total_llm_calls,
                    "current_domain": i,
                    "total_domains": len(domains),
                }, f)

        # 生成 queries
        logger.info("=" * 40)
        logger.info("Generating evaluation queries...")
        start_time = time.time()
        all_queries = self._generate_queries(all_messages, out)
        query_llm_calls = len(set(m.get("chat_id", "") for m in all_messages))
        total_llm_calls += query_llm_calls

        with open(out / "queries.jsonl", "w", encoding="utf-8") as f:
            for q in all_queries:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")

        elapsed = time.time() - start_time
        logger.info("Queries done: %d queries, %d LLM calls, %.1fs",
                    len(all_queries), query_llm_calls, elapsed)

        # 最终写入
        self._write_outputs(out, all_messages, all_expected)

        # 报告
        chat_count = len(set(m.get("chat_id", "") for m in all_messages))
        user_count = len(set(m.get("speaker", "") for m in all_messages))
        decision_count = len(all_expected)
        distractor_count = sum(1 for m in all_messages if m.get("is_distractor"))

        summary = {
            "total_messages": len(all_messages),
            "total_decisions": decision_count,
            "total_queries": len(all_queries),
            "chat_count": chat_count,
            "user_count": user_count,
            "distractor_count": distractor_count,
            "total_llm_calls": total_llm_calls,
            "domains": len(domains),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(out / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(f"\n{'=' * 50}")
        print(f"  生成完成！")
        print(f"  消息数:     {len(all_messages)}")
        print(f"  决策点:     {decision_count}")
        print(f"  查询数:     {len(all_queries)}")
        print(f"  群聊数:     {chat_count}")
        print(f"  用户数:     {user_count}")
        print(f"  干扰消息:   {distractor_count}")
        print(f"  LLM调用:    {total_llm_calls}")
        print(f"  输出目录:   {out}")
        print(f"{'=' * 50}")

    @staticmethod
    def _write_outputs(out: Path, all_messages: List[Dict], all_expected: List[Dict]) -> None:
        with open(out / "messages.jsonl", "w", encoding="utf-8") as f:
            for msg in all_messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        with open(out / "expected.jsonl", "w", encoding="utf-8") as f:
            for exp in all_expected:
                f.write(json.dumps(exp, ensure_ascii=False) + "\n")
        logger.info("Wrote %d messages, %d expected to %s",
                     len(all_messages), len(all_expected), out)

    # ════════════════════════════════════════════════════════════════
    # Expanded Dataset Generation Methods (Phase 2+)
    # ════════════════════════════════════════════════════════════════

    # ── Multi-Session Scenario Generator ────────────────────────────

    MULTI_SESSION_TOPICS = [
        {
            "topic": "微服务架构拆分方案",
            "session1": {"summary": "决定按业务域拆分为6个微服务", "status": "decided"},
            "session2": {"summary": "确认拆分方案，补充API网关层", "status": "in_progress"},
        },
        {
            "topic": "数据库统一选型",
            "session1": {"summary": "统一使用PostgreSQL作为主数据库", "status": "decided"},
            "session2": {"summary": "增加Redis作为缓存层", "status": "decided"},
        },
        {
            "topic": "前端框架标准化",
            "session1": {"summary": "新项目统一使用React 18 + TypeScript", "status": "decided"},
            "session2": {"summary": "评估引入Next.js用于SSR场景", "status": "discussion"},
        },
        {
            "topic": "CI/CD流水线改造",
            "session1": {"summary": "从Jenkins迁移到GitHub Actions", "status": "decided"},
            "session2": {"summary": "增加自动部署到预发布环境", "status": "in_progress"},
        },
        {
            "topic": "监控体系升级",
            "session1": {"summary": "采用Grafana + Prometheus作为监控方案", "status": "decided"},
            "session2": {"summary": "补充分布式追踪系统Jaeger", "status": "decided"},
        },
        {
            "topic": "缓存策略设计",
            "session1": {"summary": "采用Redis Cluster模式部署", "status": "decided"},
            "session2": {"summary": "增加本地缓存层Caffeine", "status": "decided"},
        },
        {
            "topic": "容器编排平台选型",
            "session1": {"summary": "统一使用Kubernetes管理容器编排", "status": "decided"},
            "session2": {"summary": "评估K3s用于边缘节点部署", "status": "discussion"},
        },
        {
            "topic": "API设计规范",
            "session1": {"summary": "采用RESTful API设计规范", "status": "decided"},
            "session2": {"summary": "新增gRPC用于内部服务间通信", "status": "decided"},
        },
        {
            "topic": "日志管理方案",
            "session1": {"summary": "采用ELK Stack作为日志平台", "status": "decided"},
            "session2": {"summary": "增加日志采样策略：错误全量，普通10%", "status": "in_progress"},
        },
        {
            "topic": "安全认证体系",
            "session1": {"summary": "采用OAuth 2.0 + JWT认证方案", "status": "decided"},
            "session2": {"summary": "补充SSO单点登录和企业LDAP集成", "status": "discussion"},
        },
    ]

    SPEAKER_POOL = [
        {"name": "Alice", "role": "CTO"},
        {"name": "Bob", "role": "Tech Lead"},
        {"name": "Charlie", "role": "Senior Engineer"},
        {"name": "Diana", "role": "PM"},
        {"name": "Eve", "role": "DevOps Engineer"},
        {"name": "Frank", "role": "Data Engineer"},
        {"name": "Grace", "role": "Frontend Lead"},
        {"name": "Henry", "role": "Security Engineer"},
    ]

    def generate_multi_session_scenarios(
        self, output_dir: str, num_topics: int = 10, sessions_per_topic: int = 2,
        day_gaps: Optional[List[int]] = None,
        messages_per_session: int = 5,
    ) -> Dict[str, Any]:
        """生成多 session 场景数据 — 同一话题跨多个 session（间隔数天）的决策演变

        Args:
            output_dir: 输出目录
            num_topics: 话题数量
            sessions_per_topic: 每个话题的 session 数
            day_gaps: session 间的时间间隔（天）
            messages_per_session: 每个 session 的消息数

        Returns:
            生成报告 dict
        """
        if day_gaps is None:
            day_gaps = [1, 3, 7, 14]  # 1天、3天、1周、2周

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        topics = self.MULTI_SESSION_TOPICS[:num_topics]

        all_messages: List[Dict] = []
        all_expected: List[Dict] = []
        session_breakdown: List[Dict] = []

        for t_idx, topic_def in enumerate(topics):
            topic_name = topic_def["topic"]
            chat_id = f"multi_session_{t_idx:02d}"

            # 为该话题选择一组固定的参与者
            rng = random.Random(hash(topic_name) & 0xFFFFFFFF)
            participants = rng.sample(self.SPEAKER_POOL, k=min(5, len(self.SPEAKER_POOL)))

            base_ts = datetime(2026, 1, 15, 9, 0, 0)

            session_msgs: List[Dict] = []
            session_decisions: List[Dict] = []

            for s_idx in range(sessions_per_topic):
                # Session 间 gap
                day_gap = day_gaps[s_idx % len(day_gaps)] if s_idx > 0 else 0
                session_date = base_ts + timedelta(days=day_gap * s_idx)

                # 生成该 session 的消息
                for m_idx in range(messages_per_session):
                    ts = session_date + timedelta(minutes=m_idx * 15)
                    speaker = participants[m_idx % len(participants)]

                    # 生成消息内容
                    if s_idx == 0:
                        # Session 1: 初始讨论和决策
                        msg_templates = [
                            f"关于{topic_name}，我建议大家讨论一下方案。",
                            f"我建议{topic_def['session1']['summary'].lower()}。",
                            f"这个方案看起来可行，大家怎么看？",
                            f"我同意这个方向，技术上没有问题。",
                            f"好，那就确定{topic_def['session1']['summary'].lower()}。",
                        ]
                    else:
                        # 后续 Session: 回顾 + 推进
                        prev_summary = topic_def.get(f"session{s_idx}", {}).get("summary", "") or \
                                       topic_def["session1"]["summary"]
                        prev_status = topic_def.get(f"session{s_idx}", {}).get("status", "") or \
                                      topic_def["session1"]["status"]
                        msg_templates = [
                            f"回顾一下上次的决定：{prev_summary}。进展如何？",
                            f"关于{topic_name}，我们需要继续推进。{prev_summary}这个方向对吗？",
                            f"好的，我们在此基础上再讨论{prev_summary}的具体细节。",
                            f"确认：{prev_summary}，同时需要补充新的考虑。",
                            f"{prev_summary}。现在应该{prev_status}阶段了，我们需要{prev_summary}的后续步骤。",
                        ]

                    msg = {
                        "chat_id": chat_id,
                        "msg_id": f"s{s_idx + 1}_m{m_idx + 1:03d}",
                        "speaker": speaker["name"],
                        "role": speaker["role"],
                        "msg": msg_templates[m_idx % len(msg_templates)],
                        "timestamp": ts.isoformat(),
                        "reply_to": None if m_idx == 0 else f"s{s_idx + 1}_m{m_idx:03d}",
                        "phase_name": "decision" if m_idx >= messages_per_session - 2 else "discussion",
                        "topic": topic_name,
                        "is_distractor": False,
                        "expected_decision": False,
                        "session_id": s_idx + 1,
                        "day_gap_from_previous": day_gap,
                    }
                    session_msgs.append(msg)

                # 每个 session 最后一个消息为决策点
                session_summary_key = f"session{s_idx + 1}" if s_idx > 0 else "session1"
                session_summary = topic_def.get(session_summary_key, {}).get("summary",
                    topic_def["session1"]["summary"])
                session_status = topic_def.get(session_summary_key, {}).get("status",
                    topic_def["session1"]["status"])

                session_decisions.append({
                    "chat_id": chat_id,
                    "msg_id": f"s{s_idx + 1}_m{messages_per_session:03d}",
                    "session_id": s_idx + 1,
                    "expected_topic": topic_name,
                    "expected_summary": session_summary,
                    "expected_status": session_status,
                    "expected_impact": "major",
                    "difficulty": "medium",
                    "is_multi_session": True,
                    "cross_session_order": s_idx + 1,
                })

            all_messages.extend(session_msgs)
            all_expected.extend(session_decisions)

            session_breakdown.append({
                "topic": topic_name,
                "chat_id": chat_id,
                "sessions": sessions_per_topic,
                "messages": len(session_msgs),
                "decisions": len(session_decisions),
            })

        # 写入
        self._write_outputs(out, all_messages, all_expected)

        # 写入 session 分界信息
        session_boundaries = []
        for sbd in session_breakdown:
            topic_name = sbd["topic"]
            chat_id = sbd["chat_id"]
            for s_idx in range(sessions_per_topic):
                day_gap = day_gaps[s_idx % len(day_gaps)] if s_idx > 0 else 0
                session_boundaries.append({
                    "topic": topic_name,
                    "chat_id": chat_id,
                    "session_id": s_idx + 1,
                    "day_gap": day_gap,
                    "start_msg_id": f"s{s_idx + 1}_m001",
                    "end_msg_id": f"s{s_idx + 1}_m{messages_per_session:03d}",
                })

        with open(out / "session_boundaries.json", "w", encoding="utf-8") as f:
            json.dump(session_boundaries, f, ensure_ascii=False, indent=2)

        report = {
            "type": "multi_session",
            "num_topics": len(topics),
            "sessions_per_topic": sessions_per_topic,
            "total_messages": len(all_messages),
            "total_decisions": len(all_expected),
            "total_sessions": len(topics) * sessions_per_topic,
            "session_boundaries_file": "session_boundaries.json",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(out / "generation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # ── Temporal Precision Query Generator ───────────────────────────

    def generate_temporal_queries(
        self, output_dir: str, num_queries: int = 50,
    ) -> Dict[str, Any]:
        """生成时间精确定位查询 — 测试跨时间维度的事实检索精度

        Query types:
        - "event_anchor": 事件锚定查询（"X决定之前/之后发生了什么"）
        - "relative_recency": 相对新近度（"最近的决定是哪个"）
        - "absolute_time": 绝对时间查询（"X月X日的决定是什么"）
        - "time_range": 时间范围查询（"上个月做了什么决定"）
        - "before_after_seq": 时序先后（"A决定是在B决定之前还是之后"）
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        queries: List[Dict] = []
        query_types = ["event_anchor", "relative_recency", "absolute_time", "time_range", "before_after_seq"]
        difficulty_dist = {"easy": 0.25, "medium": 0.40, "hard": 0.35}

        base_ts = datetime(2026, 2, 1, 9, 0, 0)
        topic_pool = self.MULTI_SESSION_TOPICS

        q_idx = 0
        while len(queries) < num_queries:
            topic_def = topic_pool[q_idx % len(topic_pool)]
            topic_name = topic_def["topic"]
            qt = query_types[q_idx % len(query_types)]

            # Determine difficulty
            cumsum = 0.0
            rand = random.random()
            difficulty = "easy"
            for d, p in difficulty_dist.items():
                cumsum += p
                if rand < cumsum:
                    difficulty = d
                    break

            session_summary = topic_def["session1"]["summary"]
            s2_summary = topic_def.get("session2", {}).get("summary", "")

            if qt == "event_anchor":
                query = f"在团队确定{session_summary.lower()}之后，后续做了什么补充决定？"
                gold = s2_summary if s2_summary else "暂无后续补充决定"
                source_info = f"session1: {session_summary}; session2: {s2_summary}"
            elif qt == "relative_recency":
                query = f"关于{topic_name}，团队最近作出的决定是什么？"
                gold = s2_summary if s2_summary else session_summary
                source_info = f"最近的决策: {gold}"
            elif qt == "absolute_time":
                query = f"2026年1月团队关于{topic_name}讨论后做了什么决定？"
                gold = session_summary
                source_info = f"2026年1月决策: {gold}"
            elif qt == "time_range":
                query = f"在过去一个月中，团队关于{topic_name}的决策变化是什么？"
                if s2_summary:
                    gold = f"从{session_summary.lower()}演进到{s2_summary.lower()}"
                else:
                    gold = session_summary
                source_info = f"时间范围查询: {gold}"
            else:  # before_after_seq
                if s2_summary:
                    query = f"{session_summary.lower()}这个决定是在{s2_summary.lower()}之前做出的吗？"
                    gold = "是"
                    source_info = f"{session_summary} → {s2_summary}"
                else:
                    query = f"关于{topic_name}的第一个决定是什么？"
                    gold = session_summary
                    source_info = f"初始决策: {gold}"

            queries.append({
                "q_id": f"temporal_{q_idx:03d}",
                "query_type": qt,
                "query": query,
                "gold_answer": gold,
                "difficulty": difficulty,
                "topic": topic_name,
                "source_info": source_info,
            })
            q_idx += 1

        self._write_jsonl_lines(out / "temporal_queries.jsonl", queries)

        report = {
            "type": "temporal_queries",
            "num_queries": len(queries),
            "query_types": {
                qt: sum(1 for q in queries if q["query_type"] == qt)
                for qt in query_types
            },
            "difficulty_distribution": {
                d: sum(1 for q in queries if q["difficulty"] == d)
                for d in ["easy", "medium", "hard"]
            },
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(out / "generation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # ── Ambiguous / Abstention Query Generator ───────────────────────

    def generate_ambiguous_queries(
        self, output_dir: str, num_queries: int = 40,
    ) -> Dict[str, Any]:
        """生成模糊查询和应拒绝回答查询

        - ambiguous: 查询包含模糊/歧义术语，需要澄清
        - abstention: 查询涉及对话中不存在的信息
        - cross_context: 同一术语在不同上下文中含义不同
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        ambiguous_queries = [
            {
                "context": "团队讨论了多个关于token的话题：安全token(JWT)、支付token、LLM token",
                "query": "token的过期时间是多少？",
                "clarification_needed": True,
                "gold_response": "请明确您指的是哪种token：JWT认证token、支付token还是LLM token？",
            },
            {
                "context": "有人提到了'agent'，但有的指LLM Agent，有的指运维Agent",
                "query": "agent的性能如何？",
                "clarification_needed": True,
                "gold_response": "请明确是LLM对话Agent还是运维监控Agent？",
            },
            {
                "context": "cache一词在架构讨论中既指Redis缓存也指浏览器缓存",
                "query": "cache的TTL应该设多少？",
                "clarification_needed": True,
                "gold_response": "请问是指Redis缓存还是浏览器缓存？",
            },
            {
                "context": "团队讨论了多个'gateway'：API Gateway、Payment Gateway、IoT Gateway",
                "query": "gateway的并发上限是多少？",
                "clarification_needed": True,
                "gold_response": "请明确是API Gateway、Payment Gateway还是IoT Gateway？",
            },
            {
                "context": "cluster既指Kubernetes集群也指Redis集群还指数据库集群",
                "query": "cluster的节点数应该配置多少？",
                "clarification_needed": True,
                "gold_response": "请明确是K8s集群、Redis集群还是数据库集群？",
            },
            {
                "context": "deployment既指K8s的Deployment资源也指代码部署流程",
                "query": "deployment的回滚策略是什么？",
                "clarification_needed": True,
                "gold_response": "请明确是K8s Deployment资源的回滚还是代码部署的回滚策略？",
            },
        ]

        abstention_queries = [
            {"context": "对话只讨论了技术架构，没有提及预算", "query": "项目的详细预算是多少？"},
            {"context": "没有讨论过人员配置", "query": "谁负责这个项目的交付？"},
            {"context": "对话中没有提到具体的时间安排", "query": "这个版本什么时候上线？"},
            {"context": "团队只讨论了后端技术，没有提前端", "query": "前端用什么UI框架？"},
            {"context": "没有谈论过客户信息", "query": "这个功能的客户反馈是什么？"},
            {"context": "对话中没有涉及到测试", "query": "测试覆盖率要求是多少？"},
            {"context": "没有讨论过运维排班", "query": "周末的on-call值班安排是怎样的？"},
            {"context": "对话中没有提到外部供应商", "query": "合作的第三方厂商是哪家？"},
            {"context": "没有讨论过法务合规", "query": "这个方案通过了法务审核吗？"},
            {"context": "没有涉及具体版本号", "query": "现在使用的是哪个具体版本号？"},
        ]

        cross_context_queries = [
            {
                "context_1": "在K8s集群扩容讨论中：'我们需要更多的节点来处理工作负载'",
                "context_2": "在图数据库讨论中：'每个节点的边不能超过1000条'",
                "query": "节点的限制是什么？",
                "gold_response": "在K8s上下文中节点指计算节点，在图数据库上下文中节点指图节点。请明确问题上下文。",
            },
            {
                "context_1": "在成本讨论中：'这个功能的花费太高了'",
                "context_2": "在延迟讨论中：'这个操作的时间花费太大了'",
                "query": "花费是多少？",
                "gold_response": "'花费'可能指金钱成本或时间成本，请明确。",
            },
            {
                "context_1": "在数据库迁移中：'需要做全量迁移'",
                "context_2": "在代码仓库迁移中：'需要做全量迁移'",
                "query": "迁移的进度如何？",
                "gold_response": "请明确是数据库迁移还是代码仓库迁移？",
            },
        ]

        all_queries: List[Dict] = []

        # Generate ambiguous queries
        for q_idx, q_def in enumerate(ambiguous_queries):
            all_queries.append({
                "q_id": f"ambig_{q_idx:03d}",
                "query_type": "ambiguous",
                "context": q_def["context"],
                "query": q_def["query"],
                "gold_answer": q_def["gold_response"],
                "difficulty": "medium",
                "clarification_needed": q_def["clarification_needed"],
            })

        # Generate abstention queries
        for q_idx, q_def in enumerate(abstention_queries):
            all_queries.append({
                "q_id": f"abstain_{q_idx:03d}",
                "query_type": "abstention",
                "context": q_def["context"],
                "query": q_def["query"],
                "gold_answer": "refuse",
                "difficulty": "easy",
            })

        # Generate cross-context queries
        for q_idx, q_def in enumerate(cross_context_queries):
            all_queries.append({
                "q_id": f"crossctx_{q_idx:03d}",
                "query_type": "cross_context",
                "context_1": q_def["context_1"],
                "context_2": q_def["context_2"],
                "query": q_def["query"],
                "gold_answer": q_def["gold_response"],
                "difficulty": "hard",
            })

        self._write_jsonl_lines(out / "ambiguous_queries.jsonl", all_queries)

        report = {
            "type": "ambiguous_abstention_queries",
            "total_queries": len(all_queries),
            "ambiguous": len(ambiguous_queries),
            "abstention": len(abstention_queries),
            "cross_context": len(cross_context_queries),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(out / "generation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # ── User-Specific Memory Partitioning Generator ──────────────────

    def generate_user_partitioning(
        self, output_dir: str, num_partitions: int = 8,
    ) -> Dict[str, Any]:
        """生成用户级记忆分区测试数据

        每个分区模拟一个用户或角色的独立记忆空间，
        测试系统是否能正确隔离和维护不同用户的记忆。

        Scenarios:
        - 同一事实不同用户持有不同版本（user_polarized）
        - 用户A知道某事实，用户B不知道（user_asymmetric）
        - 用户只能看到自己参与讨论的决策（user_scope）
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        all_messages: List[Dict] = []
        all_expected: List[Dict] = []

        scenarios = [
            {
                "name": "user_polarized_a",
                "topic": "前端框架选择",
                "speakers": {
                    "Alice": {"view": "推荐使用React", "role": "Frontend Lead"},
                    "Bob": {"view": "推荐使用Vue", "role": "Senior Engineer"},
                    "Charlie": {"view": "推荐使用Svelte", "role": "Architect"},
                },
                "final_decision": "团队决定继续使用React",
            },
            {
                "name": "user_polarized_b",
                "topic": "数据库方案",
                "speakers": {
                    "Diana": {"view": "推荐PostgreSQL", "role": "CTO"},
                    "Eve": {"view": "推荐MongoDB", "role": "Data Engineer"},
                    "Frank": {"view": "推荐MySQL", "role": "DevOps Engineer"},
                },
                "final_decision": "团队决定使用PostgreSQL",
            },
            {
                "name": "user_asymmetric_a",
                "topic": "API版本管理",
                "speakers": {
                    "Alice": {"view": "讨论并决定使用URL路径版本", "role": "Tech Lead"},
                    "Bob": {"view": "不知道此讨论", "role": "Junior Engineer"},
                },
                "final_decision": "使用URL路径版本管理如/v1/",
            },
            {
                "name": "user_asymmetric_b",
                "topic": "日志采样策略",
                "speakers": {
                    "Grace": {"view": "讨论并决定错误日志全量采集", "role": "SRE Lead"},
                    "Henry": {"view": "不知道此讨论", "role": "Backend Developer"},
                },
                "final_decision": "错误日志全量采集，普通日志10%采样",
            },
            {
                "name": "user_scope_a",
                "topic": "微服务拆分范围",
                "speakers": {
                    "Alice": {"view": "参与用户服务拆分讨论", "role": "Tech Lead"},
                    "Charlie": {"view": "参与支付服务拆分讨论", "role": "Senior Engineer"},
                    "Diana": {"view": "统筹整体拆分方案", "role": "CTO"},
                },
                "final_decision": "按业务域拆分为6个微服务",
            },
            {
                "name": "user_scope_b",
                "topic": "缓存策略",
                "speakers": {
                    "Frank": {"view": "参与Redis方案讨论", "role": "DevOps Engineer"},
                    "Bob": {"view": "参与本地缓存讨论", "role": "Backend Developer"},
                },
                "final_decision": "Redis作为分布式缓存，Caffeine作为本地缓存",
            },
            {
                "name": "user_polarized_c",
                "topic": "CI/CD工具",
                "speakers": {
                    "Eve": {"view": "推荐保留Jenkins", "role": "DevOps Engineer"},
                    "Grace": {"view": "推荐迁移GitHub Actions", "role": "Frontend Lead"},
                    "Henry": {"view": "推荐GitLab CI", "role": "Backend Developer"},
                },
                "final_decision": "迁移到GitHub Actions",
            },
            {
                "name": "user_asymmetric_c",
                "topic": "灾备方案",
                "speakers": {
                    "Alice": {"view": "讨论并决定跨区域异步复制", "role": "Tech Lead"},
                    "Bob": {"view": "不知道此讨论", "role": "Junior Engineer"},
                },
                "final_decision": "采用跨区域异步复制做灾备",
            },
        ]

        for sc_idx, scenario in enumerate(scenarios[:num_partitions]):
            chat_id = f"user_part_{sc_idx:02d}"
            base_ts = datetime(2026, 3, 1, 9, 0, 0)

            msg_idx = 0
            speaker_names = list(scenario["speakers"].keys())

            # 每个角色先陈述自己的观点
            for speaker_name, speaker_data in scenario["speakers"].items():
                speaker_role = speaker_data["role"]
                view = speaker_data["view"]
                ts = base_ts + timedelta(minutes=msg_idx * 15)

                msg = {
                    "chat_id": chat_id,
                    "msg_id": f"m{msg_idx + 1:03d}",
                    "speaker": speaker_name,
                    "role": speaker_role,
                    "msg": f"关于{scenario['topic']}，{view}。",
                    "timestamp": ts.isoformat(),
                    "reply_to": None if msg_idx == 0 else f"m{msg_idx:03d}",
                    "phase_name": "proposal",
                    "topic": scenario["topic"],
                    "is_distractor": False,
                    "expected_decision": False,
                    "user_partition": scenario["name"],
                    "speaker_view": view,
                }
                all_messages.append(msg)
                msg_idx += 1

            # 额外讨论消息
            for m_i in range(3):
                speaker_name = speaker_names[m_i % len(speaker_names)]
                speaker_data = scenario["speakers"][speaker_name]
                ts = base_ts + timedelta(minutes=msg_idx * 15)

                discussion_lines = [
                    f"我觉得{speaker_data['view']}的理由更充分。",
                    f"大家来讨论一下各自的方案优劣。",
                    f"我们需要在性能和成本之间做权衡。",
                ]
                msg = {
                    "chat_id": chat_id,
                    "msg_id": f"m{msg_idx + 1:03d}",
                    "speaker": speaker_name,
                    "role": speaker_data["role"],
                    "msg": discussion_lines[m_i],
                    "timestamp": ts.isoformat(),
                    "reply_to": f"m{msg_idx:03d}",
                    "phase_name": "discussion",
                    "topic": scenario["topic"],
                    "is_distractor": False,
                    "expected_decision": False,
                    "user_partition": scenario["name"],
                }
                all_messages.append(msg)
                msg_idx += 1

            # 最终决策消息
            ts = base_ts + timedelta(minutes=msg_idx * 15)
            final_speaker = speaker_names[-1]
            final_role = scenario["speakers"][final_speaker]["role"]

            msg = {
                "chat_id": chat_id,
                "msg_id": f"m{msg_idx + 1:03d}",
                "speaker": final_speaker,
                "role": final_role,
                "msg": f"好，{scenario['final_decision']}。",
                "timestamp": ts.isoformat(),
                "reply_to": f"m{msg_idx:03d}",
                "phase_name": "decision",
                "topic": scenario["topic"],
                "is_distractor": False,
                "expected_decision": True,
                "user_partition": scenario["name"],
            }
            all_messages.append(msg)

            all_expected.append({
                "chat_id": chat_id,
                "msg_id": f"m{msg_idx + 1:03d}",
                "expected_topic": scenario["topic"],
                "expected_summary": scenario["final_decision"],
                "expected_status": "decided",
                "expected_impact": "major",
                "difficulty": "medium",
                "user_partition": scenario["name"],
            })

        self._write_outputs(out, all_messages, all_expected)

        report = {
            "type": "user_partitioning",
            "num_partitions": len(scenarios[:num_partitions]),
            "total_messages": len(all_messages),
            "total_decisions": len(all_expected),
            "scenario_types": {
                "user_polarized": sum(1 for s in scenarios[:num_partitions] if "polarized" in s["name"]),
                "user_asymmetric": sum(1 for s in scenarios[:num_partitions] if "asymmetric" in s["name"]),
                "user_scope": sum(1 for s in scenarios[:num_partitions] if "scope" in s["name"]),
            },
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(out / "generation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # ── Cross-Session Conflict Resolution Generator ──────────────────

    def generate_cross_session_conflicts(
        self, output_dir: str, num_conflicts: int = 10,
    ) -> Dict[str, Any]:
        """生成跨 session 冲突解决场景

        同一话题在不同 session 中产生矛盾决策，
        测试系统是否能检测冲突并正确解决。

        Types:
        - direct_overrule: session 2 明确推翻 session 1 的决策
        - incremental_refine: session 2 在 session 1 基础上优化
        - context_change: 外部条件变化导致决策变更
        - revert: session 2 回到 session 1 之前的决策
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        conflict_defs = [
            {
                "topic": "容器运行时方案",
                "type": "direct_overrule",
                "session1_decision": "使用Docker作为容器运行时",
                "session2_decision": "切换到containerd，放弃Docker",
                "reason": "containerd更轻量，且K8s已弃用Docker Shim",
            },
            {
                "topic": "服务间通信协议",
                "type": "incremental_refine",
                "session1_decision": "内部服务统一使用RESTful API",
                "session2_decision": "改为gRPC作为主要内部通信协议",
                "reason": "性能测试显示gRPC比REST快3倍",
            },
            {
                "topic": "部署策略",
                "type": "context_change",
                "session1_decision": "使用蓝绿部署策略",
                "session2_decision": "改为滚动更新策略以节约资源",
                "reason": "基础设施预算缩减，需要更经济的部署方案",
            },
            {
                "topic": "日志存储方案",
                "type": "revert",
                "session1_decision": "使用ELK Stack",
                "session2_decision": "先改为Loki然后回退到ELK",
                "reason": "Loki查询性能不满足需求，退回ELK",
            },
            {
                "topic": "数据备份策略",
                "type": "direct_overrule",
                "session1_decision": "每天全量备份",
                "session2_decision": "改为每天增量+每周全量",
                "reason": "全量备份存储成本太高",
            },
            {
                "topic": "认证方案",
                "type": "incremental_refine",
                "session1_decision": "使用Session认证",
                "session2_decision": "迁移到JWT Token认证",
                "reason": "微服务架构需要无状态认证",
            },
            {
                "topic": "消息队列选型",
                "type": "context_change",
                "session1_decision": "使用RabbitMQ",
                "session2_decision": "Kafka更适合高吞吐场景，改用Kafka",
                "reason": "业务量增长10倍，RabbitMQ吞吐不够",
            },
            {
                "topic": "监控告警工具",
                "type": "revert",
                "session1_decision": "使用Zabbix",
                "session2_decision": "改为Prometheus然后回退",
                "reason": "团队Prometheus运维经验不足，暂时回退",
            },
            {
                "topic": "API文档方案",
                "type": "incremental_refine",
                "session1_decision": "手动维护Swagger文档",
                "session2_decision": "采用OpenAPI + 代码自动生成",
                "reason": "手动文档维护成本高且容易过时",
            },
            {
                "topic": "代码仓库策略",
                "type": "direct_overrule",
                "session1_decision": "单仓库（Monorepo）",
                "session2_decision": "多仓库（Multi-repo）",
                "reason": "单仓库在CI/CD和权限控制上遇到瓶颈",
            },
        ]

        all_messages: List[Dict] = []
        all_expected: List[Dict] = []
        conflict_records: List[Dict] = []

        for c_idx, cdef in enumerate(conflict_defs[:num_conflicts]):
            chat_id = f"cross_conflict_{c_idx:02d}"
            base_ts = datetime(2026, 4, 1, 9, 0, 0)

            # Session 1
            s1_speakers = ["Alice", "Bob", "Charlie"]
            for m_idx in range(4):
                ts = base_ts + timedelta(minutes=m_idx * 20)
                if m_idx == 0:
                    msg = f"关于{cdef['topic']}，我们来讨论一下方案。"
                elif m_idx == 1:
                    msg = f"我建议{cdef['session1_decision'].lower()}。"
                elif m_idx == 2:
                    msg = "这个方案在技术上可行吗？"
                else:
                    msg = f"好，确认{cdef['session1_decision'].lower()}。"

                all_messages.append({
                    "chat_id": chat_id,
                    "msg_id": f"s1_m{m_idx + 1:03d}",
                    "speaker": s1_speakers[m_idx % len(s1_speakers)],
                    "role": "Team Member",
                    "msg": msg,
                    "timestamp": ts.isoformat(),
                    "reply_to": None if m_idx == 0 else f"s1_m{m_idx:03d}",
                    "phase_name": "decision" if m_idx == 3 else "discussion",
                    "topic": cdef["topic"],
                    "is_distractor": False,
                    "expected_decision": m_idx == 3,
                    "session_id": 1,
                    "conflict_type": cdef["type"],
                })

            all_expected.append({
                "chat_id": chat_id,
                "msg_id": "s1_m004",
                "expected_topic": cdef["topic"],
                "expected_summary": cdef["session1_decision"],
                "expected_status": "decided",
                "expected_impact": "major",
                "session_id": 1,
                "is_conflict": False,
            })

            # Session 2 (7 days later — conflict)
            s2_speakers = ["Diana", "Eve", "Frank"]
            s2_day_gap = 7
            s2_base = base_ts + timedelta(days=s2_day_gap)

            for m_idx in range(5):
                ts = s2_base + timedelta(minutes=m_idx * 20)
                if m_idx == 0:
                    msg = f"关于{cdef['topic']}，我们需要重新评估。{cdef['reason']}"
                elif m_idx == 1:
                    msg = f"所以我们需要{cdef['session2_decision']}，这和之前的{cdef['session1_decision'].lower()}不同。"
                elif m_idx == 2:
                    msg = f"这是一个重大变更，冲突点在于之前已经确定了方案。"
                elif m_idx == 3:
                    msg = f"同意，虽然和之前决定冲突，但{cdef['reason']}，所以必须调整。"
                else:
                    msg = f"好，确认{cdef['session2_decision']}。"

                all_messages.append({
                    "chat_id": chat_id,
                    "msg_id": f"s2_m{m_idx + 1:03d}",
                    "speaker": s2_speakers[m_idx % len(s2_speakers)],
                    "role": "Team Member",
                    "msg": msg,
                    "timestamp": ts.isoformat(),
                    "reply_to": None if m_idx == 0 else f"s2_m{m_idx:03d}",
                    "phase_name": "decision" if m_idx == 4 else "discussion",
                    "topic": cdef["topic"],
                    "is_distractor": False,
                    "expected_decision": m_idx == 4,
                    "session_id": 2,
                    "conflict_type": cdef["type"],
                    "conflict_with_session1": True,
                    "day_gap_from_session1": s2_day_gap,
                })

            all_expected.append({
                "chat_id": chat_id,
                "msg_id": "s2_m005",
                "expected_topic": cdef["topic"],
                "expected_summary": cdef["session2_decision"],
                "expected_status": "decided",
                "expected_impact": "major",
                "session_id": 2,
                "is_conflict": True,
                "conflict_type": cdef["type"],
                "conflict_overrides_session1": True,
                "conflict_reason": cdef["reason"],
            })

            conflict_records.append({
                "chat_id": chat_id,
                "topic": cdef["topic"],
                "type": cdef["type"],
                "session1_decision": cdef["session1_decision"],
                "session2_decision": cdef["session2_decision"],
                "reason": cdef["reason"],
                "session1_msg_id": "s1_m004",
                "session2_msg_id": "s2_m005",
                "s2_day_gap": s2_day_gap,
            })

        self._write_outputs(out, all_messages, all_expected)

        with open(out / "conflict_records.json", "w", encoding="utf-8") as f:
            json.dump(conflict_records, f, ensure_ascii=False, indent=2)

        report = {
            "type": "cross_session_conflict",
            "num_conflicts": len(conflict_records),
            "total_messages": len(all_messages),
            "total_decisions": len(all_expected),
            "conflict_types": {
                t: sum(1 for c in conflict_records if c["type"] == t)
                for t in ["direct_overrule", "incremental_refine", "context_change", "revert"]
            },
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(out / "generation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # ── Variable Noise Ratio Generator ───────────────────────────────

    def generate_variable_noise(
        self, output_dir: str, num_chats: int = 12,
        noise_ratios: Tuple[float, ...] = (0.1, 0.3, 0.5, 0.7),
    ) -> Dict[str, Any]:
        """生成不同噪声比例的数据集

        测试在各种噪声水平下系统的决策提取鲁棒性。
        每个噪声级别生成 num_chats 个对话。
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        all_messages: List[Dict] = []
        all_expected: List[Dict] = []
        noise_stats: List[Dict] = []

        topic_pool = self.MULTI_SESSION_TOPICS

        for nr_idx, noise_ratio in enumerate(noise_ratios):
            for c_idx in range(num_chats):
                topic_def = topic_pool[(nr_idx * num_chats + c_idx) % len(topic_pool)]
                topic_name = topic_def["topic"]
                chat_id = f"noise_{int(noise_ratio * 100):02d}_{c_idx:02d}"
                base_ts = datetime(2026, 5, 1, 9, 0, 0) + timedelta(hours=nr_idx * 24 + c_idx * 2)

                speakers = random.sample(self.SPEAKER_POOL, k=min(4, len(self.SPEAKER_POOL)))
                num_decisions = 3  # 每个 chat 的决策数
                total_msgs_per_chat = int(num_decisions / (1 - noise_ratio) * 4) if noise_ratio < 1 else 20
                total_msgs_per_chat = min(total_msgs_per_chat, 30)
                num_noise = int(total_msgs_per_chat * noise_ratio)
                num_core = total_msgs_per_chat - num_noise

                chat_msgs: List[Dict] = []
                msg_idx = 0

                # 核心消息（产生决策）
                for d_idx in range(num_decisions):
                    for m_i in range(num_core // num_decisions):
                        ts = base_ts + timedelta(minutes=msg_idx * 12)
                        speaker = speakers[msg_idx % len(speakers)]
                        is_decision = (m_i == num_core // num_decisions - 1)

                        if m_i == 0:
                            content = f"关于{topic_name}继续讨论方案。"
                        elif is_decision:
                            content = f"好，确定了{topic_def['session1']['summary'].lower()}。"
                        else:
                            content = f"这个方案需要进一步评估。"

                        chat_msgs.append({
                            "chat_id": chat_id,
                            "msg_id": f"m{msg_idx + 1:03d}",
                            "speaker": speaker["name"],
                            "role": speaker["role"],
                            "msg": content,
                            "timestamp": ts.isoformat(),
                            "reply_to": None if msg_idx == 0 else f"m{msg_idx:03d}",
                            "phase_name": "decision" if is_decision else "discussion",
                            "topic": topic_name,
                            "is_distractor": False,
                            "expected_decision": is_decision,
                            "noise_ratio": noise_ratio,
                        })

                        if is_decision:
                            all_expected.append({
                                "chat_id": chat_id,
                                "msg_id": f"m{msg_idx + 1:03d}",
                                "expected_topic": topic_name,
                                "expected_summary": topic_def["session1"]["summary"],
                                "expected_status": "decided",
                                "expected_impact": "major",
                                "difficulty": "medium",
                                "noise_ratio": noise_ratio,
                            })
                        msg_idx += 1

                # 噪声消息
                noise_templates = [
                    "今天天气不错啊",
                    "午饭吃什么？",
                    "周末有人去爬山吗？",
                    "公司年会下个月举行",
                    "有人用拼多多吗？",
                    "新来的同事今天入职",
                    "办公室空调太冷了",
                    "下班一起打球？",
                    "你们看那个新电影了吗？",
                    "推荐一个好吃的餐厅",
                    "小区在修路，导致我迟到了",
                    "双十一买了什么好东西？",
                    "这个周末有马拉松比赛",
                    "你家的猫好可爱",
                    "附近新开了一家奶茶店",
                ]

                for n_idx in range(num_noise):
                    ts = base_ts + timedelta(minutes=msg_idx * 8)
                    speaker = speakers[msg_idx % len(speakers)]

                    chat_msgs.append({
                        "chat_id": chat_id,
                        "msg_id": f"m{msg_idx + 1:03d}",
                        "speaker": speaker["name"],
                        "role": speaker["role"],
                        "msg": noise_templates[n_idx % len(noise_templates)],
                        "timestamp": ts.isoformat(),
                        "reply_to": None,
                        "phase_name": "idle",
                        "topic": topic_name,
                        "is_distractor": True,
                        "expected_decision": False,
                        "noise_ratio": noise_ratio,
                    })
                    msg_idx += 1

                # 排序：按时间戳排列
                chat_msgs.sort(key=lambda m: m["timestamp"])
                # 重新分配 msg_id
                for mi, m in enumerate(chat_msgs):
                    m["msg_id"] = f"m{mi + 1:03d}"
                all_messages.extend(chat_msgs)

                noise_stats.append({
                    "chat_id": chat_id,
                    "noise_ratio": noise_ratio,
                    "total_messages": len(chat_msgs),
                    "core_messages": num_core,
                    "noise_messages": num_noise,
                    "decisions": num_decisions,
                })

        self._write_outputs(out, all_messages, all_expected)

        with open(out / "noise_stats.json", "w", encoding="utf-8") as f:
            json.dump(noise_stats, f, ensure_ascii=False, indent=2)

        report = {
            "type": "variable_noise",
            "num_chats_per_ratio": num_chats,
            "noise_ratios": list(noise_ratios),
            "total_messages": len(all_messages),
            "total_decisions": len(all_expected),
            "distractor_count": sum(m.get("is_distractor", False) for m in all_messages),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(out / "generation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _write_jsonl_lines(path: Path, items: List[Dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")