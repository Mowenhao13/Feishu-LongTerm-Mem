from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.core.engine import MemoryEngine
from src.core.engine_config import EngineConfig
from src.detect.episode import ChatEpisode, ChatEpisodeManager, ChatMessage
from src.detect.suspend_pool import SuspendPool
from src.graph.memory_graph import MemoryGraph
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)

_REALTIME_COLORS = {
    "reopen": "\033[36m",     # cyan
    "suspend": "\033[33m",    # yellow
    "new": "\033[32m",        # green
    "decision": "\033[35m",   # magenta
    "skip": "\033[90m",       # gray
    "reset": "\033[0m",
    "bold": "\033[1m",
}


class EvalRunner:
    def __init__(self, input_path: str = "eval_data/test_data.txt",
                 delay: float = 1.0,
                 max_messages: int = 0,
                 group_num: int = 1,
                 expected_path: str = ""):
        self._input_path = str(PROJECT_ROOT / input_path) if not os.path.isabs(input_path) else input_path
        self._delay = delay
        self._max_messages = max_messages
        self._group_num = max(1, group_num)
        self._expected_path = str(PROJECT_ROOT / expected_path) if expected_path and not os.path.isabs(expected_path) else expected_path
        self._engine: Optional[MemoryEngine] = None
        self._episode_manager: Optional[ChatEpisodeManager] = None
        self._pool: Optional[SuspendPool] = None
        self._stats: Dict[str, Any] = {
            "total_messages": 0,
            "decisions_extracted": 0,
            "decisions_created": 0,
            "decisions_updated": 0,
            "decisions_skipped": 0,
            "decisions_noop": 0,
            "ep_suspend_count": 0,
            "ep_reopen_count": 0,
            "ep_force_close_count": 0,
            "start_time": 0.0,
            "group_msg_counts": {},
        }

    async def run(self) -> None:
        self._stats["start_time"] = time.time()
        sep = "=" * 62
        print()
        print(f"{_REALTIME_COLORS['bold']}{sep}")
        print("  Eval 模式")
        print(f"{sep}{_REALTIME_COLORS['reset']}")
        print(f"  输入: {self._input_path}")
        print(f"  延迟: {self._delay}s")
        if self._group_num > 1:
            print(f"  群聊: {self._group_num} 个 (round-robin)")
        print()

        # 1. 加载消息
        messages = self._load_messages()
        self._stats["total_messages"] = len(messages)
        if not messages:
            print(f"  {_REALTIME_COLORS['skip']}错误: 文件为空或无法读取{_REALTIME_COLORS['reset']}")
            return
        print(f"  加载 {len(messages)} 条消息\n")

        # 2. 初始化引擎
        graph, storage = self._init_storage()
        engine = self._init_engine(graph, storage)
        if engine is None:
            print(f"  {_REALTIME_COLORS['skip']}错误: 引擎初始化失败 (API_KEY 未配置?){_REALTIME_COLORS['reset']}")
            return
        self._engine = engine

        # 3. 初始化 SuspendPool + EpisodeManager
        self._pool = SuspendPool()
        self._pool.load()
        print(f"  SuspendPool 已加载: {self._pool.size} 个暂停 episode\n")
        self._episode_manager = ChatEpisodeManager(pool=self._pool)

        # 注入 embedding 函数到 episode buffer（支持语义边界检测和 reopen）
        if hasattr(engine, '_embedder') and engine._embedder:
            try:
                # Eval mode: use timestamps from messages, not wall-clock.
                # Disable idle-flush to avoid spurious timeouts when simulated timestamps
                # differ hugely from time.time().
                self._episode_manager.set_idle_flush_threshold(999999.0)  # effectively disabled
                logger.info("[Eval] Idle flush disabled (simulated timestamps)")
            except Exception:
                pass
            embed_fn = engine._embedder.embed
            self._episode_manager.set_buffer_embedding_fn(embed_fn)
            print(f"  Embedding 函数已注入 episode buffer\n")

        # 4. 处理每条消息
        messages_to_process = messages[:self._max_messages] if self._max_messages > 0 else messages
        print(f"{_REALTIME_COLORS['bold']}─" * 70)
        print(f"  开始处理 {len(messages_to_process)} 条消息{_REALTIME_COLORS['reset']}")
        print()

        for i, content in enumerate(messages_to_process, 1):
            await self._process_one_message(i, len(messages_to_process), content)

        # 5. 等待所有消息缓冲完成，然后以 episode 级别处理决策提取
        await asyncio.sleep(2)

        if self._episode_manager and self._engine:
            old_decision_count = len(self._engine._graph.get_all_decisions()) if hasattr(self._engine, "_graph") else 0

            # 5a. 检查超时边界，获取已 idle-flush 的 episode
            timed_out = self._episode_manager.check_all_timeouts()
            for ep in timed_out:
                logger.info("[Eval] Processing timed-out episode=%s (msgs=%d)", ep.id[:12], ep.message_count)
                await self._engine._process_episode(ep, self._episode_manager)

            # 5b. 从 SuspendPool 取出所有已挂起的 episode（time-gap 拆分的）
            drained = self._episode_manager.drain_suspended_episodes()
            for ep in drained:
                logger.info("[Eval] Processing suspended episode=%s chat=%s (msgs=%d)",
                            ep.id[:12], ep.chat_id, ep.message_count)
                await self._engine._process_episode(ep, self._episode_manager)

            # 5c. 关闭所有 buffer，获取剩余的 episode
            closed_eps = self._episode_manager.close_all()
            for ep in closed_eps:
                logger.info("[Eval] Processing closed episode=%s chat=%s (msgs=%d)",
                            ep.id[:12], ep.chat_id, ep.message_count)
                await self._engine._process_episode(ep, self._episode_manager)

            new_decision_count = len(self._engine._graph.get_all_decisions()) if hasattr(self._engine, "_graph") else 0
            self._stats["decisions_created"] = new_decision_count - old_decision_count

        # 6. 停止引擎
        await engine.stop()

        # 7. 精度评估（如有 expected 文件）
        if self._expected_path:
            self._run_comparison()

        # 8. 打印报告
        self._print_report()

    def _load_messages(self) -> List[Union[str, Dict[str, Any]]]:
        path = Path(self._input_path)
        if not path.exists():
            logger.error("Input file not found: %s", self._input_path)
            return []
        if path.suffix == ".json":
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [item.get("content", "") for item in data if item.get("content")]
            return []
        if path.suffix == ".jsonl":
            import json
            messages: List[Dict[str, Any]] = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
            return messages
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def _init_storage(self):
        cfg = self._load_config()
        storage = GitStorage(GitStorageConfig(work_dir=cfg["storage_path"]))
        graph = MemoryGraph()
        try:
            graph.load_from_git(storage, cfg["project"])
            logger.info("MemoryGraph loaded: %d decisions", len(graph.get_all_decisions()))
        except Exception as e:
            logger.info("No existing data: %s", e)
        return graph, storage

    def _init_engine(self, graph: MemoryGraph, storage: GitStorage) -> Optional[MemoryEngine]:
        cfg = self._load_config()
        engine_cfg = EngineConfig(
            project=cfg["project"],
            storage_path=cfg["storage_path"],
        )

        from src.model.llm_provider import LLMProvider
        from src.extractors.simple_llm_extractor import SimpleLLMExtractor

        llm_provider = None
        if os.getenv("API_KEY"):
            llm_provider = LLMProvider(
                provider_type="openai",
                base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
                api_key=os.getenv("API_KEY", ""),
                model=os.getenv("MODEL_NAME", "deepseek-chat"),
                max_tokens=4096,
                enable_stats=True,
            )
        else:
            logger.warning("API_KEY not configured")
            return None

        decision_extractor = SimpleLLMExtractor(llm_provider) if llm_provider else None
        engine = MemoryEngine(config=engine_cfg, decision_extractor=decision_extractor)
        engine.initialize()

        try:
            from src.model.embedding_provider import EmbeddingProvider
            from src.model.reranker_provider import RerankerProvider
            embedder = EmbeddingProvider()
            reranker = RerankerProvider()
            engine.set_embedding_reranker(embedder, reranker)
        except Exception as e:
            logger.warning("Embedding/reranker init failed (non-fatal): %s", e)

        try:
            from src.memory_graph.doc_context_provider import DocContextProvider
            wiki_space_id = os.getenv("EVAL_WIKI_SPACE_ID", "")
            if wiki_space_id:
                doc_ctx = DocContextProvider(wiki_space_id=wiki_space_id)
                engine.set_doc_context_provider(doc_ctx)
                logger.info("[Eval] DocContextProvider configured (wiki_space=%s)", wiki_space_id[:12])
        except Exception as e:
            logger.warning("DocContextProvider init failed (non-fatal): %s", e)

        return engine

    def _load_config(self) -> Dict[str, Any]:
        return {
            "project": os.environ.get("PROJECT_NAME", "default"),
            "storage_path": os.environ.get("STORAGE_PATH", "data"),
        }

    async def _process_one_message(self, idx: int, total: int,
                                 content: Union[str, Dict[str, Any]]) -> None:
        if self._engine is None or self._episode_manager is None:
            return

        if isinstance(content, dict):
            msg_text = content.get("msg", content.get("content", ""))
            chat_id = content.get("chat_id", f"eval_{(idx - 1) % self._group_num}")
            sender = content.get("speaker", content.get("sender", "eval_user"))
            # Use provided timestamp if available, otherwise use current time
            msg_ts = content.get("timestamp")
            if msg_ts is not None:
                timestamp = float(msg_ts)
            else:
                timestamp = time.time()
        else:
            msg_text = content
            chat_id = f"eval_{(idx - 1) % self._group_num}" if self._group_num > 1 else "eval"
            sender = "eval_user"
            timestamp = time.time()

        if not msg_text:
            return

        preview = msg_text[:60].replace("\n", " ")

        self._stats["group_msg_counts"][chat_id] = self._stats["group_msg_counts"].get(chat_id, 0) + 1

        msg = ChatMessage(
            chat_id=chat_id,
            sender_id=sender,
            content=msg_text,
            timestamp=timestamp,
            message_id=f"eval_{idx}",
        )

        pool_before = self._pool.size if self._pool else 0

        # 1. 送入 EpisodeBuffer
        self._episode_manager.add_message(msg)

        pool_after = self._pool.size if self._pool else 0

        # 2. 检测池变化
        pool_changed = ""
        if pool_after > pool_before:
            self._stats["ep_suspend_count"] += (pool_after - pool_before)
            pool_changed = f" {_REALTIME_COLORS['suspend']}⏸ suspend{_REALTIME_COLORS['reset']}"

        # 3. 实时输出
        episode_info = ""
        if hasattr(self._episode_manager, "_buffers"):
            for cid, buf in self._episode_manager._buffers.items():
                ep = getattr(buf, "_current", None)
                if ep is not None and getattr(ep, "id", None):
                    group_label = f"[{cid}] " if self._group_num > 1 else ""
                    episode_info = f"{group_label}ep={ep.id[:12]} ({getattr(ep, 'message_count', 0)} msgs)"

        pool_info = f"pool={pool_after}/{self._pool._max_size}" if self._pool else ""

        print(f"  [{idx:03d}/{total}] {preview}")
        status_parts = [s for s in [episode_info, pool_info, pool_changed] if s]
        if status_parts:
            print(f"          {' | '.join(status_parts)}")

        await asyncio.sleep(self._delay)

    def _print_report(self) -> None:
        elapsed = time.time() - self._stats["start_time"]
        pool_stats = self._pool.stats() if self._pool else {}

        from src.model.llm_provider import LLMProvider
        llm_stats = None
        if self._engine:
            try:
                ext = getattr(self._engine, "_extractor", None)
                if ext and hasattr(ext, "_llm"):
                    llm_stats = ext._llm.get_accumulated_stats()
            except Exception:
                pass

        print()
        print(f"{_REALTIME_COLORS['bold']}{'=' * 62}")
        print(f"  Eval 模式测试报告")
        print(f"{'=' * 62}{_REALTIME_COLORS['reset']}")

        print(f"\n  {_REALTIME_COLORS['bold']}概况{_REALTIME_COLORS['reset']}")
        print(f"    输入文件:     {self._input_path}")
        print(f"    消息总数:     {self._stats['total_messages']}")
        if self._group_num > 1:
            print(f"    群聊数量:     {self._group_num}")
        print(f"    模拟延迟:     {self._delay}s")
        print(f"    总耗时:       {elapsed:.1f}s")
        print(f"    处理速率:     {self._stats['total_messages'] / max(elapsed, 0.1):.1f} msg/s")

        if self._group_num > 1:
            print(f"\n  {_REALTIME_COLORS['bold']}群聊分布{_REALTIME_COLORS['reset']}")
            for cid in sorted(self._stats["group_msg_counts"], key=lambda x: int(x.split("_")[1]) if "_" in x else 0):
                count = self._stats["group_msg_counts"][cid]
                bar = "█" * int(count / max(self._stats['total_messages'], 1) * 30)
                print(f"    {cid:<8} {count:>4} msgs  {bar}")

        print(f"\n  {_REALTIME_COLORS['bold']}Episode{_REALTIME_COLORS['reset']}")
        print(f"    Suspend:       {self._stats['ep_suspend_count']} 次")
        print(f"    Reopen:        {pool_stats.get('reopen_count', 0)} 次")
        print(f"    池大小:        {pool_stats.get('pool_size', 0)} / {pool_stats.get('max_size', 20)}")

        if self._group_num > 1 and hasattr(self._episode_manager, "_buffers"):
            print(f"\n  {_REALTIME_COLORS['bold']}每群 Buffer 状态{_REALTIME_COLORS['reset']}")
            for cid in sorted(self._episode_manager._buffers.keys(),
                              key=lambda x: int(x.split("_")[1]) if "_" in x else 0):
                buf = self._episode_manager._buffers[cid]
                ep_id = ""
                ep_msgs = 0
                if hasattr(buf, "_current") and buf._current and hasattr(buf._current, "id"):
                    ep_id = buf._current.id[:12]
                    ep_msgs = getattr(buf._current, "message_count", 0)
                print(f"    {cid:<8} 当前ep={ep_id} ({ep_msgs} msgs)")

        pool_chat_ids = pool_stats.get("chat_ids", [])
        if self._group_num > 1 and pool_chat_ids:
            print(f"\n  {_REALTIME_COLORS['bold']}池中群聊分布{_REALTIME_COLORS['reset']}")
            from collections import Counter
            cid_counter = Counter(pool_chat_ids)
            for cid, count in sorted(cid_counter.items(),
                                     key=lambda x: int(x[0].split("_")[1]) if "_" in x[0] else 0):
                print(f"    {cid:<8} {count} 个 episode")

        print(f"\n  {_REALTIME_COLORS['bold']}决策{_REALTIME_COLORS['reset']}")
        print(f"    新创建:        {self._stats['decisions_created']}")

        if llm_stats and llm_stats.get("call_count", 0) > 0:
            avg_dur = llm_stats["total_duration"] / llm_stats["call_count"]
            print(f"\n  {_REALTIME_COLORS['bold']}LLM 调用{_REALTIME_COLORS['reset']}")
            print(f"    调用次数:     {llm_stats['call_count']}")
            print(f"    总 Token:     {llm_stats['total_tokens']:,}  (输入 {llm_stats['prompt_tokens']:,} / 输出 {llm_stats['completion_tokens']:,})")
            print(f"    总耗时:       {llm_stats['total_duration']:.1f}s")
            print(f"    平均耗时:     {avg_dur:.2f}s/次")
        else:
            print(f"\n  {_REALTIME_COLORS['bold']}LLM 调用{_REALTIME_COLORS['reset']}")
            print(f"    无调用记录")

        print(f"\n  {_REALTIME_COLORS['bold']}{'=' * 62}")
        print(f"  {'✅ 测试完成' if self._stats['decisions_created'] > 0 else '⚠️  无新决策 (可能全部为重复)'}")
        print(f"{'=' * 62}{_REALTIME_COLORS['reset']}")
        print()

    def _run_comparison(self) -> None:
        from src.eval.comparator import EvalComparator
        decisions = self._engine._graph.get_all_decisions() if self._engine else []
        actual = [
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
        embedder = getattr(self._engine, "_embedder", None) if self._engine else None
        comparator = EvalComparator(self._expected_path, embedding_provider=embedder)
        comparator.match(actual)
        report = comparator.to_dict()

        # Print colored report
        print()
        print(f"\033[1m{'=' * 62}")
        print(f"  精度评估报告")
        print(f"{'=' * 62}\033[0m")
        print(f"  预期:          {report['total_expected']}")
        print(f"  实际检测:      {report['total_detected']}")
        print(f"  TP:            {report['true_positives']}")
        print(f"  FP:            {report['false_positives']}")
        print(f"  FN:            {report['false_negatives']}")
        p, r, f = report["precision"], report["recall"], report["f1"]
        print(f"\n  \033[1mPrecision:  {p:.1%}   Recall:  {r:.1%}   F1:  {f:.1%}\033[0m")

        # 决策/建议分类统计
        dm = report.get("decision_metrics", {})
        if dm:
            print(f"\n  {_REALTIME_COLORS['bold']}决策与建议分类{_REALTIME_COLORS['reset']}")
            print(f"    决策:  TP={dm.get('decision_tp', 0)}  FN={dm.get('decision_fn', 0)}  Recall={dm.get('decision_recall', 0):.1%}")
            print(f"    建议:  TP={dm.get('suggestion_tp', 0)}  FN={dm.get('suggestion_fn', 0)}  Recall={dm.get('suggestion_recall', 0):.1%}")

        if report.get("by_topic"):
            print(f"\n  按话题:")
            for t, v in report["by_topic"].items():
                print(f"    {t:<12}  P={v['precision']:.1%}  R={v['recall']:.1%}  F1={v['f1']:.1%}")
        if report.get("by_chat"):
            iso = report["by_chat"].get("_isolation", {})
            if iso:
                print(f"\n  跨群隔离:  score={iso.get('score', 1.0):.1%}  issues={iso.get('issues', 0)}")
        print(f"\n  {'=' * 62}\033[0m")
        print()

        # Save report to JSON
        report_path = Path(self._input_path).parent / "eval_report.json"
        import json
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  报告已保存: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eval 模式 — 从文件模拟消息处理")
    parser.add_argument("--eval", action="store_true", help="启用 eval 模式")
    parser.add_argument("--input", default="eval_data/test_data.txt",
                        help="输入文件路径 (.txt 或 .json)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="消息间延迟 (秒)")
    parser.add_argument("--max-messages", type=int, default=0,
                        help="最大处理消息数 (0=全部)")
    parser.add_argument("--group-num", type=int, default=1,
                        help="群聊数量 (>1 启用多群聊 round-robin 模式)")
    parser.add_argument("--expected", default="",
                        help="expected.jsonl 路径，启用精度评估")
    return parser.parse_args()


async def run_eval() -> None:
    args = parse_args()
    runner = EvalRunner(input_path=args.input, delay=args.delay,
                        max_messages=args.max_messages,
                        group_num=args.group_num,
                        expected_path=args.expected)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(run_eval())