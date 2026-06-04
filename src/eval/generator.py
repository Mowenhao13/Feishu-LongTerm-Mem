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
        self._model = self._config.get("generation", {}).get("model", "deepseek-chat")
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