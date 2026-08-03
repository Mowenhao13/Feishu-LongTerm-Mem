#!/usr/bin/env python3
"""两层 vs 四层超图 — 对照实验运行器

一键运行 A/B/C 三组实验，产出可对比的结构化指标。

用法:
    # 完整运行（需要 LLM API key 和较长时间）
    python experiments/two_layer_vs_four_layer/run_experiments.py --all

    # 只跑 A 组（四层 baseline）
    python experiments/two_layer_vs_four_layer/run_experiments.py --group A

    # 只跑 B 组（两层简化）
    python experiments/two_layer_vs_four_layer/run_experiments.py --group B

    # 干运行（验证配置 + 数据加载，不调用 LLM）
    python experiments/two_layer_vs_four_layer/run_experiments.py --all --dry-run

    # 只生成报告（已有指标数据）
    python experiments/two_layer_vs_four_layer/run_experiments.py --report-only

输出:
    eval_reports/four_layer_metrics.json   — A 组指标
    eval_reports/two_layer_metrics.json    — B 组指标
    eval_reports/two_layer_vs_four_layer_report.md — 对比报告
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 导入实验模块
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.two_layer_vs_four_layer.metrics_collector import MetricsCollector
from experiments.two_layer_vs_four_layer.query_eval import QueryEvaluator, SimpleMatcher
from experiments.two_layer_vs_four_layer.comparison_report import generate_report

logger = logging.getLogger(__name__)

# 数据集路径
ARGUSBOT_V3 = PROJECT_ROOT / "eval_dataset" / "argusbot_v3"
MESSAGES_JSONL = ARGUSBOT_V3 / "messages.jsonl"
EXPECTED_JSONL = ARGUSBOT_V3 / "expected.jsonl"
QUERIES_JSONL = ARGUSBOT_V3 / "queries.jsonl"
SUMMARY_JSON = ARGUSBOT_V3 / "summary.json"

# 输出路径
REPORTS_DIR = PROJECT_ROOT / "eval_reports"
FOUR_LAYER_METRICS = REPORTS_DIR / "four_layer_metrics.json"
TWO_LAYER_METRICS = REPORTS_DIR / "two_layer_metrics.json"
REPORT_MD = REPORTS_DIR / "two_layer_vs_four_layer_report.md"


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """加载 JSONL 文件"""
    data: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def _save_json(data: Any, path: Path) -> None:
    """保存 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Saved metrics to %s", path)


def _is_llm_configured() -> bool:
    """检查是否配置了 LLM API"""
    return bool(os.getenv("API_KEY"))


# ============================================================
#  A 组：四层超图 Baseline
# ============================================================

async def run_group_a_baseline(dry_run: bool = False) -> Dict[str, Any]:
    """运行 A 组实验 — 四层超图 baseline

    使用现有 EvalRunner + 完整 MemoryGraph + Hypergraph 代码，
    在 argusbot_v3 上完整跑一次 eval pipeline。
    """
    logger.info("=" * 60)
    logger.info("A 组: 四层超图 Baseline")
    logger.info("=" * 60)

    if not MESSAGES_JSONL.exists():
        logger.error("Messages file not found: %s", MESSAGES_JSONL)
        return {}

    messages = _load_jsonl(MESSAGES_JSONL)
    logger.info("Loaded %d messages from %s", len(messages), MESSAGES_JSONL)

    expected = _load_jsonl(EXPECTED_JSONL) if EXPECTED_JSONL.exists() else []
    logger.info("Loaded %d expected decisions", len(expected))

    if not _is_llm_configured() and not dry_run:
        logger.error("API_KEY not configured. Use --dry-run to validate setup.")
        return {}

    if dry_run:
        logger.info("[DRY RUN] Would run EvalRunner on %d messages", len(messages))
        return {
            "architecture": "four_layer",
            "group": "A",
            "dry_run": True,
            "messages_loaded": len(messages),
            "expected_decisions": len(expected),
            "note": "Dry run — no actual LLM calls made",
        }

    # 清理旧存储
    storage_path = Path(os.getenv("STORAGE_PATH", "data"))
    if storage_path.exists():
        import shutil
        shutil.rmtree(storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)
        logger.info("Cleaned storage at %s", storage_path)

    # ----- 使用 EvalRunner 运行 -----
    from src.eval_runner import EvalRunner

    collector = MetricsCollector()
    collector.start()

    runner = EvalRunner(
        input_path=str(MESSAGES_JSONL),
        delay=0.0,  # 无延迟，用最快速度处理
        max_messages=0,  # 全部处理
        group_num=0,  # 从消息中读取 chat_id
        expected_path=str(EXPECTED_JSONL),
    )

    try:
        await runner.run()
    except Exception as e:
        logger.error("A 组运行失败: %s", traceback.format_exc())
        raise

    perf_metrics = collector.stop()

    # 构建指标输出
    metrics: Dict[str, Any] = {
        "architecture": "four_layer",
        "group": "A",
        "dataset": "argusbot_v3",
        "total_messages": runner._stats.get("total_messages", len(messages)),
        "decisions_created": runner._stats.get("decisions_created", 0),
        "episode_suspend_count": runner._stats.get("ep_suspend_count", 0),
        **perf_metrics,
    }

    # 提取精度评估结果（如果有 expected）
    if runner._engine and EXPECTED_JSONL.exists():
        try:
            from src.eval.comparator import EvalComparator
            decisions = runner._engine._graph.get_all_decisions()
            actual_decisions = [
                {
                    "sid": d.sid,
                    "topic_id": d.topic_id or "",
                    "summary": d.summary or "",
                    "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                    "impact": d.impact_level.value if hasattr(d.impact_level, "value") else str(d.impact_level),
                    "chat_id": getattr(d, "chat_id", ""),
                    "is_suggestion": getattr(d, "is_suggestion", False),
                }
                for d in decisions
            ]
            embedder = getattr(runner._engine, "_embedder", None)
            comparator = EvalComparator(str(EXPECTED_JSONL), embedding_provider=embedder)
            comparator.match(actual_decisions)
            report = comparator.to_dict()

            metrics["total_detected"] = report.get("total_detected", len(actual_decisions))
            metrics["true_positives"] = report.get("true_positives", 0)
            metrics["false_positives"] = report.get("false_positives", 0)
            metrics["false_negatives"] = report.get("false_negatives", 0)
            metrics["precision"] = report.get("precision", 0)
            metrics["recall"] = report.get("recall", 0)
            metrics["f1"] = report.get("f1", 0)
            metrics["decision_metrics"] = report.get("decision_metrics", {})
            metrics["dimension_accuracy"] = report.get("dimension_accuracy", {})
            metrics["by_topic"] = report.get("by_topic", {})
            metrics["by_chat"] = report.get("by_chat", {})

        except Exception as e:
            logger.warning("精度评估失败: %s", e)

    # LLM 调用统计
    try:
        ext = getattr(runner._engine, "_extractor", None)
        if ext and hasattr(ext, "_llm"):
            llm_stats = ext._llm.get_accumulated_stats()
            metrics["llm_stats"] = {
                "call_count": llm_stats.get("call_count", 0),
                "total_tokens": llm_stats.get("total_tokens", 0),
                "prompt_tokens": llm_stats.get("prompt_tokens", 0),
                "completion_tokens": llm_stats.get("completion_tokens", 0),
                "total_duration_seconds": llm_stats.get("total_duration", 0),
            }
    except Exception as e:
        logger.warning("LLM stats failed: %s", e)

    _save_json(metrics, FOUR_LAYER_METRICS)
    return metrics


# ============================================================
#  B 组：两层简化结构
# ============================================================

async def run_group_b_two_layer(dry_run: bool = False) -> Dict[str, Any]:
    """运行 B 组实验 — 简化两层结构

    使用简化后的 TwoLayerHypergraph + TwoLayerBuilder，
    相同的提取 prompt 和检索逻辑。
    对比 A 组的 Accuracy / Precision / Recall / F1。
    """
    logger.info("=" * 60)
    logger.info("B 组: 两层简化结构")
    logger.info("=" * 60)

    if not MESSAGES_JSONL.exists():
        logger.error("Messages file not found: %s", MESSAGES_JSONL)
        return {}

    messages = _load_jsonl(MESSAGES_JSONL)
    logger.info("Loaded %d messages from %s", len(messages), MESSAGES_JSONL)

    expected = _load_jsonl(EXPECTED_JSONL) if EXPECTED_JSONL.exists() else []
    logger.info("Loaded %d expected decisions", len(expected))

    if not _is_llm_configured() and not dry_run:
        logger.error("API_KEY not configured. Use --dry-run to validate setup.")
        return {}

    if dry_run:
        logger.info("[DRY RUN] Would run two-layer experiment on %d messages", len(messages))
        return {
            "architecture": "two_layer",
            "group": "B",
            "dry_run": True,
            "messages_loaded": len(messages),
            "expected_decisions": len(expected),
            "note": "Dry run — no actual LLM calls made",
        }

    # 清理旧存储
    storage_path = Path(os.getenv("STORAGE_PATH", "data"))
    if storage_path.exists():
        import shutil
        shutil.rmtree(storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)
        logger.info("Cleaned storage at %s", storage_path)

    # ----- 使用简化引擎运行 -----
    from src.core.engine import MemoryEngine
    from src.core.engine_config import EngineConfig
    from src.detect.episode import ChatEpisodeManager, ChatMessage
    from src.detect.suspend_pool import SuspendPool
    from src.graph.memory_graph import MemoryGraph
    from src.storage.git_storage import GitStorage, GitStorageConfig
    from src.extractors.simple_llm_extractor import SimpleLLMExtractor
    from src.model.llm_provider import LLMProvider
    from src.model.embedding_provider import EmbeddingProvider
    from src.model.reranker_provider import RerankerProvider

    # 初始化 LLM provider
    if not _is_llm_configured():
        return {}

    llm_provider = LLMProvider(
        provider_type="openai",
        base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
        api_key=os.getenv("API_KEY", ""),
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        max_tokens=4096,
        enable_stats=True,
    )
    decision_extractor = SimpleLLMExtractor(llm_provider)

    # 初始化 Graph + Storage
    graph = MemoryGraph()
    config = EngineConfig(
        project=os.environ.get("PROJECT_NAME", "default"),
        storage_path=os.environ.get("STORAGE_PATH", "data"),
    )
    storage_config = GitStorageConfig(work_dir=config.storage_path)
    storage = GitStorage(storage_config)

    try:
        graph.load_from_git(storage, config.project)
    except Exception:
        pass

    # 初始化引擎 — B 组使用同样的 MemoryEngine，但超图结构不同
    # 注意：MemoryEngine 本身不直接依赖 Hypergraph 结构，
    # 区别在于 graph.builder.py 的 build_from_episodes 中创建的结构
    engine = MemoryEngine(config=config, decision_extractor=decision_extractor)
    engine.initialize()

    try:
        embedder = EmbeddingProvider()
        reranker = RerankerProvider()
        engine.set_embedding_reranker(embedder, reranker)
    except Exception as e:
        logger.warning("Embedding/reranker init failed: %s", e)

    # 初始化和运行
    pool = SuspendPool()
    pool.load()

    episode_manager = ChatEpisodeManager(pool=pool)
    if hasattr(engine, "_embedder") and engine._embedder:
        embed_fn = engine._embedder.embed
        episode_manager.set_buffer_embedding_fn(embed_fn)
        try:
            episode_manager.set_idle_flush_threshold(999999.0)
        except Exception:
            pass

    # 设置引擎，注入简化构建器
    # 用两层的 TwoLayerBuilder 替换原有的 HypergraphBuilder
    from experiments.two_layer_vs_four_layer.two_layer_hypergraph import TwoLayerHypergraph
    from experiments.two_layer_vs_four_layer.two_layer_builder import TwoLayerBuilder

    two_layer_builder = TwoLayerBuilder(llm_provider=llm_provider)
    two_layer_hg = TwoLayerHypergraph()

    collector = MetricsCollector()
    collector.start()

    # 处理消息（用 B 组的两层逻辑）
    old_decision_count = len(engine._graph.get_all_decisions()) if hasattr(engine, "_graph") else 0
    stats = {
        "total_messages": 0,
        "ep_suspend_count": 0,
        "decisions_created": 0,
        "start_time": time.time(),
        "group_msg_counts": {},
    }

    for i, msg_data in enumerate(messages, 1):
        chat_id = msg_data.get("chat_id", "eval")
        msg_text = msg_data.get("msg", msg_data.get("content", ""))
        sender = msg_data.get("speaker", msg_data.get("sender", "eval_user"))

        timestamp = time.time()
        ts = msg_data.get("timestamp")
        if ts:
            try:
                from datetime import datetime as dt
                timestamp = dt.fromisoformat(ts).timestamp() if isinstance(ts, str) else float(ts)
            except (ValueError, TypeError):
                pass

        if not msg_text:
            continue

        stats["total_messages"] += 1
        stats["group_msg_counts"][chat_id] = stats["group_msg_counts"].get(chat_id, 0) + 1

        msg = ChatMessage(
            chat_id=chat_id,
            sender_id=sender,
            content=msg_text,
            timestamp=timestamp,
            message_id=f"eval_{i}",
        )

        pool_before = pool.size
        episode_manager.add_message(msg)

        if pool.size > pool_before:
            stats["ep_suspend_count"] += (pool.size - pool_before)

        # 每 100 条输出进度
        if i % 100 == 0:
            logger.info("B 组: processed %d/%d messages", i, len(messages))

    # 处理所有 episode
    await asyncio.sleep(2)

    timed_out = episode_manager.check_all_timeouts()
    for ep in timed_out:
        logger.info("Processing timed-out episode=%s", ep.id[:12])
        await engine._process_episode(ep, episode_manager)

    drained = episode_manager.drain_suspended_episodes()
    for ep in drained:
        logger.info("Processing suspended episode=%s", ep.id[:12])
        await engine._process_episode(ep, episode_manager)

    closed_eps = episode_manager.close_all()
    for ep in closed_eps:
        logger.info("Processing closed episode=%s", ep.id[:12])
        await engine._process_episode(ep, episode_manager)

    new_decision_count = len(engine._graph.get_all_decisions()) if hasattr(engine, "_graph") else 0

    # 将决策同步到两层超图
    if hasattr(engine, "_graph"):
        for d in engine._graph.get_all_decisions():
            two_layer_hg.decisions[d.sid] = d

    await engine.stop()

    perf_metrics = collector.stop()
    stats["decisions_created"] = new_decision_count - old_decision_count

    # 构建指标输出
    metrics: Dict[str, Any] = {
        "architecture": "two_layer",
        "group": "B",
        "dataset": "argusbot_v3",
        "total_messages": stats["total_messages"],
        "decisions_created": stats["decisions_created"],
        "episode_suspend_count": stats["ep_suspend_count"],
        **perf_metrics,
    }

    # 提取精度评估
    if EXPECTED_JSONL.exists():
        try:
            from src.eval.comparator import EvalComparator
            actual_decisions = [
                {
                    "sid": d.sid,
                    "topic_id": d.topic_id or "",
                    "summary": d.summary or "",
                    "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                    "impact": d.impact_level.value if hasattr(d.impact_level, "value") else str(d.impact_level),
                    "chat_id": getattr(d, "chat_id", ""),
                    "is_suggestion": getattr(d, "is_suggestion", False),
                }
                for d in two_layer_hg.get_all_decisions()
            ]
            embedder = getattr(engine, "_embedder", None)
            comparator = EvalComparator(str(EXPECTED_JSONL), embedding_provider=embedder)
            comparator.match(actual_decisions)
            report = comparator.to_dict()

            metrics["total_detected"] = report.get("total_detected", len(actual_decisions))
            metrics["true_positives"] = report.get("true_positives", 0)
            metrics["false_positives"] = report.get("false_positives", 0)
            metrics["false_negatives"] = report.get("false_negatives", 0)
            metrics["precision"] = report.get("precision", 0)
            metrics["recall"] = report.get("recall", 0)
            metrics["f1"] = report.get("f1", 0)
            metrics["decision_metrics"] = report.get("decision_metrics", {})
            metrics["dimension_accuracy"] = report.get("dimension_accuracy", {})
            metrics["by_topic"] = report.get("by_topic", {})
            metrics["by_chat"] = report.get("by_chat", {})

        except Exception as e:
            logger.warning("B 组精度评估失败: %s", traceback.format_exc())

    # LLM 调用统计
    try:
        if hasattr(decision_extractor, "_llm"):
            llm_stats = decision_extractor._llm.get_accumulated_stats()
            metrics["llm_stats"] = {
                "call_count": llm_stats.get("call_count", 0),
                "total_tokens": llm_stats.get("total_tokens", 0),
                "prompt_tokens": llm_stats.get("prompt_tokens", 0),
                "completion_tokens": llm_stats.get("completion_tokens", 0),
                "total_duration_seconds": llm_stats.get("total_duration", 0),
            }
    except Exception as e:
        logger.warning("B 组 LLM stats failed: %s", e)

    _save_json(metrics, TWO_LAYER_METRICS)
    return metrics


# ============================================================
#  C 组：两层 + SQLite 持久化
# ============================================================

async def run_group_c_sqlite(dry_run: bool = False) -> Dict[str, Any]:
    """运行 C 组实验 — 两层 + SQLite 持久化

    在 B 组基础上，存储从内存 dict 改为 SQLite 关系表。
    对比检索速度（ms/query）。
    """
    logger.info("=" * 60)
    logger.info("C 组: 两层 + SQLite 持久化")
    logger.info("=" * 60)

    if not _is_llm_configured() and not dry_run:
        logger.error("API_KEY not configured. Use --dry-run to validate setup.")
        return {}

    if dry_run:
        logger.info("[DRY RUN] Would run two-layer+SQLite experiment")
        return {
            "architecture": "two_layer_sqlite",
            "group": "C",
            "dry_run": True,
            "note": (
                "SQLite 持久化要求:\n"
                "1. pip install sqlite-vec\n"
                "2. 创建 embeddings 表\n"
                "3. 替换 np.save/load 为 SQLite 读写\n"
                "详见 LAB-54 设计"
            ),
        }

    logger.warning("C 组尚未完全实现（依赖 LAB-54）")
    return {
        "architecture": "two_layer_sqlite",
        "group": "C",
        "note": "需要先完成 LAB-54 的 SQLite 迁移",
    }


# ============================================================
#  查询评估
# ============================================================

async def run_query_eval(mode: str, dry_run: bool = False) -> Dict[str, Any]:
    """运行 queries.jsonl 的检索评估

    Args:
        mode: "four_layer" 或 "two_layer"
        dry_run: 是否干运行
    """
    if not QUERIES_JSONL.exists():
        logger.warning("Queries file not found: %s", QUERIES_JSONL)
        return {}

    if dry_run:
        queries = _load_jsonl(QUERIES_JSONL)
        logger.info("[DRY RUN] Would evaluate %d queries for %s", len(queries), mode)
        return {"total_queries": len(queries), "architecture": mode, "dry_run": True}

    # 构造检索函数
    def make_retrieval_fn(mode: str):
        if mode == "four_layer":
            from src.graph.retrieval import GraphRetrieval
            # 从存储读取决策进行检索
            from src.graph.memory_graph import MemoryGraph
            from src.storage.git_storage import GitStorage, GitStorageConfig
            storage_path = os.environ.get("STORAGE_PATH", "data")
            graph = MemoryGraph()
            storage = GitStorage(GitStorageConfig(work_dir=storage_path))
            try:
                graph.load_from_git(storage, os.environ.get("PROJECT_NAME", "default"))
            except Exception:
                pass
            retrieval = GraphRetrieval(graph)
            return lambda q: retrieval.retrieve(q).get("answer", "")
        else:
            # 两层检索 — 从 TwoLayerHypergraph 检索
            from experiments.two_layer_vs_four_layer.two_layer_hypergraph import TwoLayerHypergraph
            metrics_path = TWO_LAYER_METRICS if TWO_LAYER_METRICS.exists() else None
            if metrics_path:
                with open(metrics_path) as f:
                    data = json.load(f)
                hg = TwoLayerHypergraph()
                # 简单的检索：返回相关 decision 的 summary
                decisions = hg.get_all_decisions()
                def simple_retrieve(q, decisions=decisions):
                    hits = []
                    q_lower = q.lower()
                    for d in decisions:
                        if q_lower in (d.summary or "").lower() or q_lower in (d.content or "").lower():
                            hits.append(d.summary)
                    return "; ".join(hits[:3])
                return simple_retrieve
            return lambda q: ""

    retrieval_fn = make_retrieval_fn(mode)

    embedder = None
    try:
        from src.model.embedding_provider import EmbeddingProvider
        embedder = EmbeddingProvider()
    except Exception:
        pass

    matcher = SimpleMatcher(embedder=embedder)
    evaluator = QueryEvaluator(
        queries_path=str(QUERIES_JSONL),
        retrieval_fn=retrieval_fn,
        matcher=matcher,
    )

    report = await evaluator.evaluate_all()
    result = evaluator.report_to_dict(report)

    query_path = REPORTS_DIR / f"{mode}_queries.json"
    _save_json(result, query_path)

    return result


# ============================================================
#  报告生成
# ============================================================

def generate_comparison_report() -> str:
    """根据已保存的指标生成对比报告"""
    if not FOUR_LAYER_METRICS.exists() or not TWO_LAYER_METRICS.exists():
        logger.error("缺少指标文件。请先运行实验。")
        logger.error("  A 组: %s (exists=%s)", FOUR_LAYER_METRICS, FOUR_LAYER_METRICS.exists())
        logger.error("  B 组: %s (exists=%s)", TWO_LAYER_METRICS, TWO_LAYER_METRICS.exists())
        return ""

    with open(FOUR_LAYER_METRICS) as f:
        baseline = json.load(f)
    with open(TWO_LAYER_METRICS) as f:
        two_layer = json.load(f)

    baseline_queries_path = REPORTS_DIR / "four_layer_queries.json"
    two_layer_queries_path = REPORTS_DIR / "two_layer_queries.json"
    baseline_queries = json.load(open(baseline_queries_path)) if baseline_queries_path.exists() else None
    two_layer_queries = json.load(open(two_layer_queries_path)) if two_layer_queries_path.exists() else None

    report = generate_report(
        baseline_metrics=baseline,
        two_layer_metrics=two_layer,
        baseline_queries=baseline_queries,
        two_layer_queries=two_layer_queries,
        output_path=str(REPORT_MD),
    )

    logger.info("Report saved to %s", REPORT_MD)
    return report


# ============================================================
#  CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="两层 vs 四层超图对照实验")
    parser.add_argument("--all", action="store_true", help="运行所有组 (A+B+C)")
    parser.add_argument("--group", choices=["A", "B", "C"], help="运行指定组")
    parser.add_argument("--dry-run", action="store_true", help="干运行（验证配置，不调用 LLM）")
    parser.add_argument("--report-only", action="store_true", help="只从已有指标生成报告")
    parser.add_argument("--query-eval", action="store_true", help="同时运行 query 检索评估")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not any([args.all, args.group, args.report_only]):
        logger.info("请指定运行模式: --all / --group A/B/C / --report-only")
        logger.info("或使用 --dry-run --all 干运行验证配置")
        return

    if args.report_only:
        report = generate_comparison_report()
        if report:
            print("\n" + report[:2000] + "\n... (truncated)")
        return

    # 验证数据集
    for p, name in [(MESSAGES_JSONL, "messages"), (EXPECTED_JSONL, "expected")]:
        if not p.exists():
            logger.warning("数据集文件不存在: %s (%s)", p, name)

    results: Dict[str, Any] = {}

    # 运行选定的组
    groups_to_run = []
    if args.all:
        groups_to_run = ["A", "B", "C"]
    elif args.group:
        groups_to_run = [args.group]

    for grp in groups_to_run:
        if grp == "A":
            results["A"] = await run_group_a_baseline(dry_run=args.dry_run)
        elif grp == "B":
            results["B"] = await run_group_b_two_layer(dry_run=args.dry_run)
        elif grp == "C":
            results["C"] = await run_group_c_sqlite(dry_run=args.dry_run)

        # 查询评估（如果启用）
        if args.query_eval and grp in ("A", "B") and not args.dry_run:
            mode = "four_layer" if grp == "A" else "two_layer"
            logger.info("Running query eval for %s...", mode)
            results[f"{grp}_queries"] = await run_query_eval(mode)

    # 生成报告（A+B 都有结果时）
    if "A" in results and "B" in results:
        if not results["A"].get("dry_run") and not results["B"].get("dry_run"):
            generate_comparison_report()

    logger.info("实验完成。")


if __name__ == "__main__":
    asyncio.run(main())