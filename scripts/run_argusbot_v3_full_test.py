"""argusbot_v3 数据集 + ArgusBot 仓库 — SimpleLLMExtractor 直接测试 (非 pipeline)

注意: 本脚本直接调用 SimpleLLMExtractor.extract_with_context()，跳过 MemoryEngine
pipeline（无 MemoryExtractor Stage 1、无 EntityStore、无超图、无 Neo4j）。

全链路 pipeline 测试请改用:
    uv run python scripts/run_e2e_pipeline_test.py

遍历 argusbot_v3 全部 70 个 chat：
1. 读取 messages.jsonl，按 chat_id 分组
2. 对每个 chat 构建对话文本（前 20 条消息）
3. 用 ProjectWatcher 对 ref/ArgusBot 仓库做快照 + MemoStore 去重验证
4. LLM 提取两次：
   - 有 project context（注入 ArgusBot 仓库真实文件变更）
   - 无 project context（baseline）
5. 汇总结果写入 JSON 报告

用法:
    LANGFUSE_ENABLE=false uv run python scripts/run_argusbot_v3_full_test.py

输出:
    eval_results/argusbot_v3_full_test_report.json

需要环境变量: API_KEY, BASE_URL, MODEL_NAME
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# 确保 src 可导入
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.detect.project_detector import ProjectDetector
from src.detect.conv_file_bridge import ConversationFileBridge, ConvFileBridgeLevel
from src.detect.project_watcher import ProjectWatcher
from src.extractors.project_types import (
    ProjectDevelopmentContext,
    ProjectFileChange,
)
from src.extractors.simple_llm_extractor import SimpleLLMExtractor
from src.model.llm_provider import LLMProvider

ARGUSBOT_DIR = str(_REPO / "ref" / "ArgusBot")
ARGUSBOT_V3_DIR = str(_REPO / "eval_dataset" / "argusbot_v3")
REPORT_PATH = str(_REPO / "eval_results" / "argusbot_v3_full_test_report.json")

MAX_MSGS_PER_CHAT = 20
MAX_LLM_CONCURRENCY = 8


def load_dataset() -> dict:
    """加载 messages.jsonl，按 chat_id 分组。"""
    chats = defaultdict(list)
    messages_path = Path(ARGUSBOT_V3_DIR) / "messages.jsonl"
    with open(messages_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msg = json.loads(line)
                chats[msg["chat_id"]].append(msg)

    # 排序每个 chat 的消息按时间
    for cid in chats:
        chats[cid].sort(key=lambda m: m.get("timestamp", ""))

    return {
        "chats": dict(chats),
        "total_messages": sum(len(v) for v in chats.values()),
        "total_chats": len(chats),
    }


def build_episode(messages: list) -> dict:
    """从 chat 消息构建 episode（取前 N 条，记录 expected_decision 数）。"""
    msgs = messages[:MAX_MSGS_PER_CHAT]
    lines = []
    n_expected = 0
    for m in msgs:
        speaker = m.get("speaker", "?")
        text = m.get("msg", "")
        lines.append(f"{speaker}: {text}")
        exp = m.get("expected_decision", "False")
        if exp is True or str(exp).lower() == "true":
            n_expected += 1

    return {
        "chat_id": msgs[0]["chat_id"] if msgs else "?",
        "message_count": len(msgs),
        "n_expected": n_expected,
        "conversation_text": "\n".join(lines),
        "topics": list({m.get("topic", "") for m in msgs}),
    }


async def test_watcher_and_snapshot() -> dict:
    """验证 ProjectWatcher 监控 ArgusBot 仓库 + MemoStore 去重。"""
    bridge = ConversationFileBridge(ConvFileBridgeLevel.KEYWORD)
    detector = ProjectDetector(ARGUSBOT_DIR, bridge=bridge, watcher_debounce=0.5)
    await detector.start()
    await asyncio.sleep(0.3)

    # 快照
    snapshot = await detector._watcher.take_snapshot()

    # 文件变更检测 + MemoStore 去重
    test_file = Path(ARGUSBOT_DIR) / "tmp_fulltest.py"
    test_file.write_text("def fulltest():\n    pass\n")
    await asyncio.sleep(1.0)
    r1 = await detector.detect()
    create_detected = r1.has_changes

    # 相同内容再写 → 应去重
    test_file.write_text("def fulltest():\n    pass\n")
    await asyncio.sleep(1.0)
    r2 = await detector.detect()
    dedup_detected = len(r2.changes) == 0

    # 修改内容 → 应重新检测
    test_file.write_text("def fulltest():\n    return 42\n")
    await asyncio.sleep(1.0)
    r3 = await detector.detect()
    modified_detected = r3.has_changes

    # 删除
    test_file.unlink()
    await asyncio.sleep(1.0)
    await detector.detect()

    bridge_stats = detector.get_bridge_stats()
    await detector.stop()

    return {
        "snapshot_files": snapshot.total_files,
        "snapshot_py_files": snapshot.file_type_counts.get(".py", 0),
        "create_detected": create_detected,
        "dedup_detected": dedup_detected,
        "modified_detected": modified_detected,
        "bridge_level": bridge_stats["level"],
    }


async def build_project_context() -> ProjectDevelopmentContext:
    """用 ArgusBot 仓库真实文件构建 project context。"""
    pw = ProjectWatcher(ARGUSBOT_DIR)
    snapshot = await pw.take_snapshot()
    recent_py = [f for f in snapshot.recent_files if f.endswith(".py")][:5]

    ctx = ProjectDevelopmentContext(
        recent_changes=[
            ProjectFileChange(
                file_path=f,
                change_type="modified",
                content_hash=f"h{i}",
                extension=".py",
                language="Python",
                diff_summary="+50 lines; -15 lines",
                timestamp=time.time(),
                size_bytes=3000,
            )
            for i, f in enumerate(recent_py)
        ],
        detected_at=time.time(),
    )
    ctx.linked_conversation_snippets = [
        "Related keywords: codex, loop, agent, feishu, adapter, test"
    ]
    return ctx


async def extract_one(extractor, text: str, project_ctx) -> tuple:
    """单次对话两次提取：有/无 project context。返回 (n_with, n_without, t_with, t_without)。"""
    t0 = time.time()
    try:
        r_with = await extractor.extract_with_context(content=text, project_context=project_ctx)
        n_with = len(r_with) if r_with else 0
    except Exception as e:
        n_with = -1
        t_with = time.time() - t0
    else:
        t_with = time.time() - t0

    t0 = time.time()
    try:
        r_without = await extractor.extract_with_context(content=text)
        n_without = len(r_without) if r_without else 0
    except Exception as e:
        n_without = -1
        t_without = time.time() - t0
    else:
        t_without = time.time() - t0

    return n_with, n_without, t_with, t_without


async def main() -> None:
    print("=" * 60)
    print("argusbot_v3 全量全流程测试")
    print("=" * 60)

    # ── Step 1: 加载数据集 ──
    data = load_dataset()
    print(f"数据集: {data['total_messages']} 条消息, {data['total_chats']} 个 chat")

    episodes = [
        build_episode(msgs)
        for msgs in data["chats"].values()
        if msgs
    ]
    episodes = [ep for ep in episodes if ep["message_count"] >= 3]
    print(f"有效对话片段: {len(episodes)} 个 (>=3 条消息)")

    # ── Step 2: Watcher 验证 ──
    print("\n[1/3] ProjectWatcher 验证 (ArgusBot 仓库)...")
    watcher_info = await test_watcher_and_snapshot()
    print(f"  快照: {watcher_info['snapshot_files']} 文件, "
          f"{watcher_info['snapshot_py_files']} 个 .py")
    print(f"  创建检测: {watcher_info['create_detected']}")
    print(f"  MemoStore 去重: {watcher_info['dedup_detected']}")
    print(f"  修改检测: {watcher_info['modified_detected']}")

    # ── Step 3: LLM 提取 ──
    api_key = os.getenv("API_KEY", "")
    llm_results = []
    llm_stats = {"total_episodes": 0, "failed": 0, "decisions_with": 0,
                 "decisions_without": 0, "expected_total": 0,
                 "msg_processed": 0, "total_time": 0.0, "details": []}

    if not api_key:
        print("\n[2/3] ⚠️  无 API_KEY，跳过 LLM 提取")
    else:
        print(f"\n[2/3] LLM 提取 ({len(episodes)} 个对话, 并发={MAX_LLM_CONCURRENCY})...")

        provider = LLMProvider(
            provider_type="openai",
            base_url=os.getenv("BASE_URL"),
            api_key=api_key,
            model=os.getenv("MODEL_NAME", "deepseek-chat"),
            max_tokens=4096,
            enable_stats=False,
        )
        extractor = SimpleLLMExtractor(provider)
        project_ctx = await build_project_context()
        print(f"  project context: {len(project_ctx.recent_changes)} 个文件变更")
        for c in project_ctx.recent_changes:
            print(f"    - {c.file_path}")

        # 并发提取
        sem = asyncio.Semaphore(MAX_LLM_CONCURRENCY)

        async def run_episode(ep):
            async with sem:
                n_with, n_without, t_with, t_without = await extract_one(
                    extractor, ep["conversation_text"], project_ctx
                )
                return {
                    "chat_id": ep["chat_id"],
                    "message_count": ep["message_count"],
                    "n_expected": ep["n_expected"],
                    "topic": ep["topics"][0] if ep["topics"] else "",
                    "with_count": n_with,
                    "without_count": n_without,
                    "with_time_sec": round(t_with, 1),
                    "without_time_sec": round(t_without, 1),
                    "ok": n_with >= 0 and n_without >= 0,
                }

        t_start = time.time()
        llm_results = await asyncio.gather(*[run_episode(ep) for ep in episodes])
        elapsed_total = time.time() - t_start

        for r in llm_results:
            llm_stats["total_episodes"] += 1
            llm_stats["msg_processed"] += r["message_count"]
            llm_stats["expected_total"] += r["n_expected"]
            if not r["ok"]:
                llm_stats["failed"] += 1
                continue
            llm_stats["decisions_with"] += r["with_count"]
            llm_stats["decisions_without"] += r["without_count"]
            llm_stats["total_time"] += r["with_time_sec"] + r["without_time_sec"]
            if r["with_count"] != r["without_count"]:
                llm_stats["details"].append(r)

        print(f"  完成: {llm_stats['total_episodes']} 个对话, "
              f"{elapsed_total:.0f}s 总耗时")

    # ── 汇总报告 ──
    print("\n[3/3] 生成报告...")
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "dataset": "argusbot_v3",
            "project_dir": ARGUSBOT_DIR,
            "model": os.getenv("MODEL_NAME", "deepseek-chat"),
            "max_msgs_per_chat": MAX_MSGS_PER_CHAT,
            "concurrency": MAX_LLM_CONCURRENCY,
        },
        "dataset": {
            "total_messages": data["total_messages"],
            "total_chats": data["total_chats"],
            "episodes": len(episodes),
        },
        "watcher": watcher_info,
        "llm": llm_stats,
        "per_episode": llm_results,
    }

    Path(REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ── 打印摘要 ──
    print("\n" + "=" * 60)
    print("测试摘要")
    print("=" * 60)
    print(f"数据集: {data['total_messages']} 消息 / {data['total_chats']} chat / "
          f"{len(episodes)} 对话片段")
    print(f"Watcher: {watcher_info['snapshot_files']} 文件, "
          f"去重={watcher_info['dedup_detected']}")
    if api_key:
        print(f"LLM: {llm_stats['total_episodes']} 对话, "
              f"失败 {llm_stats['failed']}")
        print(f"  期望决策 (ground truth): {llm_stats['expected_total']}")
        print(f"  有 project context: {llm_stats['decisions_with']} 条")
        print(f"  无 project context: {llm_stats['decisions_without']} 条")
        print(f"  差异: {llm_stats['decisions_with'] - llm_stats['decisions_without']:+d}")
    print(f"\n报告已保存: {REPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
