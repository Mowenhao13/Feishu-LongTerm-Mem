"""
Pipeline A/B 测试 — 对比单阶段 (direct) 和两阶段 (two_stage) 提取管道

测试维度：
1. 实体/关系提取质量
2. 决策提取质量 (Precision / Recall / F1)
3. LLM 调用成本
4. 端到端延迟

用法：
    uv run python experiments/pipeline_ab_test/run.py --all
    uv run python experiments/pipeline_ab_test/run.py --group direct
    uv run python experiments/pipeline_ab_test/run.py --group two_stage
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Test data — episode format compatible with the extraction pipeline
TEST_EPISODES = [
    {
        "id": "test_ep_001",
        "chat_id": "test_chat",
        "full_text": (
            "张三：我建议后端用 Python + FastAPI，前端用 React\n"
            "李四：同意后端用 Python，但框架我觉得 Gin 更好\n"
            "张三：Gin 是 Go 的框架，我们需要统一技术栈\n"
            "王五：我们团队 Go 经验更多，我建议用 Gin\n"
            "李四：好，那就定 Gin 作为后端框架\n"
            "张三：数据库用 PostgreSQL 15 吧，生产环境已经在了\n"
            "王五：确认，不引入新数据库。Redis 缓存要不要一起定？\n"
            "李四：先不用，后续评估"
        ),
        "message_count": 8,
        "expected_entities": ["张三", "李四", "王五", "PostgreSQL 15", "Gin", "React", "Python"],
        "expected_decisions": [
            {"summary": "后端框架确认为 Gin", "confidence_min": 0.7},
            {"summary": "数据库使用 PostgreSQL 15", "confidence_min": 0.7},
        ],
        "expected_relationships": ["张三:RECOMMENDS:Gin", "李四:USES:PostgreSQL 15"],
    },
    {
        "id": "test_ep_002",
        "chat_id": "test_chat",
        "full_text": (
            "李四：API 网关用 Kong 吧，开源成熟\n"
            "张三：Kong 学习成本有点高，用 Nginx 自己配？\n"
            "李四：Nginx 做网关不够，我们需要鉴权、限流、路由\n"
            "王五：那就用 APISIX 吧，国产的，功能比 Kong 全\n"
            "李四：APISIX 我看下... 行，APISIX 可以\n"
            "张三：好，那 API 网关就用 APISIX\n"
            "李四：部署方式用 Docker Compose 还是 K8s?\n"
            "王五：先用 Docker Compose 快速上线，Q4 再迁 K8s"
        ),
        "message_count": 7,
        "expected_entities": ["Kong", "Nginx", "APISIX", "Docker Compose", "K8s", "张三", "李四", "王五"],
        "expected_decisions": [
            {"summary": "API 网关使用 APISIX", "confidence_min": 0.7},
            {"summary": "部署先用 Docker Compose，Q4 迁 K8s", "confidence_min": 0.5},
        ],
        "expected_relationships": ["项目:USES_TECHNOLOGY:APISIX"],
    },
]


@dataclass
class TestResult:
    """A/B 测试结果记录"""
    group: str
    episode_id: str
    entities_found: List[str] = field(default_factory=list)
    relationships_found: List[str] = field(default_factory=list)
    decisions_found: List[str] = field(default_factory=list)
    llm_calls: int = 0
    elapsed_ms: float = 0.0
    entity_recall: float = 0.0
    decision_precision: float = 0.0
    decision_recall: float = 0.0
    decision_f1: float = 0.0


@dataclass
class ABTestReport:
    """A/B 测试汇总报告"""
    timestamp: str = ""
    direct_results: List[TestResult] = field(default_factory=list)
    two_stage_results: List[TestResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "direct": [asdict(r) for r in self.direct_results],
            "two_stage": [asdict(r) for r in self.two_stage_results],
            "summary": self.summary,
        }


def _calc_token_overlap(a: str, b: str) -> float:
    """计算两个文本的语义匹配度（基于关键词重叠）

    用于 LLM 输出与 expected decision 的模糊匹配。
    token 分割时保留组合词（如 Gin, PostgreSQL 15）。
    """
    import re
    def tokens(s):
        # 匹配中文词 + 英文单词（含数字）+ 组合词
        return set(re.findall(r'[一-鿿]+|[A-Za-z][A-Za-z0-9]*|\d', s.lower()))
    a_tok = tokens(a)
    b_tok = tokens(b)
    if not a_tok or not b_tok:
        return 0.0
    return len(a_tok & b_tok) / min(len(a_tok), len(b_tok))


def _match_decisions(found: List[str], expected: List[Dict[str, Any]]) -> int:
    """模糊匹配 found 决策与 expected 决策，返回匹配数"""
    hits = 0
    for exp in expected:
        exp_text = exp["summary"]
        for found_text in found:
            if _calc_token_overlap(exp_text, found_text) >= 0.30:
                hits += 1
                break
    return hits


async def _create_llm_provider():
    """创建 LLM Provider（与 main.py 一致）"""
    from src.model.llm_provider import LLMProvider
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        logger.warning("API_KEY not set, LLM calls will fail")
        return None
    return LLMProvider(
        provider_type="openai",
        base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
        api_key=api_key,
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        max_tokens=4096,
        enable_stats=False,
    )


async def run_direct(episode: Dict[str, Any]) -> TestResult:
    """运行单阶段 (direct) 提取管道"""
    from src.extractors.simple_llm_extractor import SimpleLLMExtractor

    provider = await _create_llm_provider()
    if provider is None:
        return TestResult(group="direct", episode_id=episode["id"],
                          llm_calls=0, elapsed_ms=0.0)
    extractor = SimpleLLMExtractor(provider)

    result = TestResult(group="direct", episode_id=episode["id"])

    start = time.time()
    decisions = await extractor.extract_decision(episode["full_text"])
    elapsed = time.time() - start

    # Calculate metrics with fuzzy matching
    expected_decisions = episode["expected_decisions"]
    expected_count = len(expected_decisions)
    if decisions:
        found_texts = [
            (d.get("title", "") or d.get("summary", "") or "")[:80]
            for d in decisions
        ]
        hits = _match_decisions(found_texts, expected_decisions)
        found_count = len(found_texts)
        result.decision_precision = hits / found_count if found_count else 1.0
        result.decision_recall = hits / expected_count if expected_count else 1.0
        result.decision_f1 = (2 * result.decision_precision * result.decision_recall /
                              (result.decision_precision + result.decision_recall)) if (result.decision_precision + result.decision_recall) > 0 else 0.0
    else:
        result.decision_precision = 0.0
        result.decision_recall = 0.0
        result.decision_f1 = 0.0

    result.decisions_found = [d.get("summary", "")[:50] for d in (decisions or [])]
    result.llm_calls = 1
    result.elapsed_ms = round(elapsed * 1000, 2)

    return result


async def run_two_stage(episode: Dict[str, Any]) -> TestResult:
    """运行两阶段 (two_stage) 提取管道"""
    from src.extractors.simple_llm_extractor import SimpleLLMExtractor
    from src.extractors.memory_extractor import MemoryExtractor
    from src.storage.entity_store import EntityStore
    from src.ontology.manager import OntologyManager

    provider = await _create_llm_provider()
    if provider is None:
        return TestResult(group="two_stage", episode_id=episode["id"],
                          llm_calls=0, elapsed_ms=0.0)
    memory_extractor = MemoryExtractor(provider, OntologyManager.get_instance())
    entity_store = EntityStore()
    decision_extractor = SimpleLLMExtractor(provider)

    result = TestResult(group="two_stage", episode_id=episode["id"])
    llm_calls = 0

    start = time.time()

    # Stage 1: Memory extraction
    mem_result = await memory_extractor.extract(
        episode["full_text"],
        episode_id=episode["id"],
    )
    llm_calls += 1

    result.entities_found = [e.name for e in mem_result.entities]
    result.relationships_found = [
        f"{r.source_name}:{r.relationship_type}:{r.target_name}"
        for r in mem_result.relationships
    ]

    # Store
    entity_store.add_entities(mem_result.entities)
    entity_store.add_relationships(mem_result.relationships)

    # Stage 2: Decision extraction with entity context
    entity_context = entity_store.build_extraction_context()
    decisions = await decision_extractor.extract_with_context(
        episode["full_text"],
        entity_context=entity_context,
    )
    llm_calls += 1

    result.decisions_found = [d.get("summary", "")[:50] for d in (decisions or [])]
    result.llm_calls = llm_calls
    result.elapsed_ms = round((time.time() - start) * 1000, 2)

    # Entity recall
    expected_entities = set(episode.get("expected_entities", []))
    found_entity_names = {e.name for e in mem_result.entities}
    if expected_entities:
        entity_hits = found_entity_names & expected_entities
        result.entity_recall = len(entity_hits) / len(expected_entities)
    else:
        result.entity_recall = 1.0

    # Decision metrics (fuzzy matching)
    expected_decisions = episode["expected_decisions"]
    expected_count = len(expected_decisions)
    if decisions:
        found_texts = [
            (d.get("title", "") or d.get("summary", "") or "")[:80]
            for d in decisions
        ]
        hits = _match_decisions(found_texts, expected_decisions)
        found_count = len(found_texts)
        result.decision_precision = hits / found_count if found_count else 1.0
        result.decision_recall = hits / expected_count if expected_count else 1.0
        result.decision_f1 = (2 * result.decision_precision * result.decision_recall /
                              (result.decision_precision + result.decision_recall)) if (result.decision_precision + result.decision_recall) > 0 else 0.0
    else:
        result.decision_precision = 0.0
        result.decision_recall = 0.0
        result.decision_f1 = 0.0

    return result


async def run_group(group: str) -> List[TestResult]:
    """运行一组测试"""
    logger.info("Running group: %s (%d episodes)", group, len(TEST_EPISODES))
    results: List[TestResult] = []

    for ep in TEST_EPISODES:
        try:
            if group == "direct":
                result = await run_direct(ep)
            else:
                result = await run_two_stage(ep)
            results.append(result)
            logger.info(
                "  %s: entities=%d decisions=%d llm=%d elapsed=%.0fms",
                ep["id"], len(result.entities_found), len(result.decisions_found),
                result.llm_calls, result.elapsed_ms,
            )
        except Exception as e:
            logger.error("  %s FAILED: %s", ep["id"], e)

    return results


async def run_all() -> ABTestReport:
    """运行所有组的测试"""
    report = ABTestReport(timestamp=datetime.now().isoformat())

    report.direct_results = await run_group("direct")
    report.two_stage_results = await run_group("two_stage")

    # Compute summary
    for group_name, results in [("direct", report.direct_results), ("two_stage", report.two_stage_results)]:
        if not results:
            continue
        avg_llm = sum(r.llm_calls for r in results) / len(results)
        avg_time = sum(r.elapsed_ms for r in results) / len(results)
        avg_precision = sum(r.decision_precision for r in results) / len(results)
        avg_recall = sum(r.decision_recall for r in results) / len(results)
        avg_f1 = sum(r.decision_f1 for r in results) / len(results)

        report.summary[group_name] = {
            "avg_llm_calls": round(avg_llm, 2),
            "avg_elapsed_ms": round(avg_time, 2),
            "avg_decision_precision": round(avg_precision, 4),
            "avg_decision_recall": round(avg_recall, 4),
            "avg_decision_f1": round(avg_f1, 4),
        }

        # Additional entity metrics for two_stage
        if group_name == "two_stage":
            entity_recalls = [r.entity_recall for r in results]
            report.summary["two_stage"]["avg_entity_recall"] = round(
                sum(entity_recalls) / len(entity_recalls), 4
            ) if entity_recalls else 0.0

    # Print summary
    print("\n" + "=" * 60)
    print("Pipeline A/B Test Summary")
    print("=" * 60)
    for group, stats in report.summary.items():
        print(f"\n[{group}]")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    print("\n" + "=" * 60)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline A/B Test")
    parser.add_argument("--all", action="store_true", help="Run all groups")
    parser.add_argument("--group", choices=["direct", "two_stage"], default=None, help="Run specific group")
    parser.add_argument("--output", default="", help="Output path for report JSON")
    args = parser.parse_args()

    import asyncio

    async def _run():
        if args.group:
            results = await run_group(args.group)
            report = ABTestReport(timestamp=datetime.now().isoformat())
            if args.group == "direct":
                report.direct_results = results
            else:
                report.two_stage_results = results
            return report
        else:
            return await run_all()

    report = asyncio.run(_run())

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        logger.info("Report saved to %s", output_path)
    else:
        # Print to stdout
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()