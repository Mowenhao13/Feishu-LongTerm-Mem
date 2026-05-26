"""
管道测试脚本 — 直接调用 MemoryEngine._process_detection

绕过 WS 事件检测，直接向决策提取管线注入消息，
触发 [Engine], [LLM], [Embedding], [Reranker], [Mutation] 日志输出。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

# 确保日志输出到 logs/ 目录
from logging.handlers import RotatingFileHandler
import logging
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"pipeline_test_{time.strftime('%Y%m%d_%H%M%S')}.log"
_file_handler = RotatingFileHandler(
    _log_file, maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8",
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)

from src.core.engine import MemoryEngine
from src.core.engine_config import EngineConfig
from src.detect.types import DetectionResult, DecisionLevel, ScoreBreakdown, SignalDetail, DetectContext
from src.utils.logger import get_logger

logger = get_logger("test_pipeline")

# ==================== 测试消息 ====================
TEST_MESSAGES = [
    "大家好，我是UserOnly，我决定前端使用React框架，组件库用Ant Design，构建工具用Vite",
    "项目排期我决定第一阶段3周完成需求分析和核心功能开发，第二阶段2周完成测试和优化，整体6月1日上线",
]


async def main():
    print(f"{'='*60}")
    print(f"  管道测试 — 直接调用决策提取管线")
    print(f"  消息数: {len(TEST_MESSAGES)}")
    print(f"  日志文件: {_log_file}")
    print(f"{'='*60}")

    # 1. 创建引擎配置
    cfg = EngineConfig(
        project="default",
        storage_path=str(PROJECT_ROOT / "data"),
        llm_base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
        llm_api_key=os.getenv("API_KEY", ""),
        llm_model=os.getenv("MODEL_NAME", "deepseek-chat"),
        detector_enabled=True,
        detector_snapshot_enabled=False,
        graph_auto_sync=True,
        storage_auto_sync=True,
    )
    print(f"  [Config] EngineConfig created: project={cfg.project}")

    # 2. 创建引擎
    engine = MemoryEngine(config=cfg)
    engine.initialize()
    print(f"  [Engine] MemoryEngine initialized")

    # 3. 发送测试消息到管线
    for i, text in enumerate(TEST_MESSAGES, 1):
        print(f"\n  {'─'*58}")
        print(f"  [Test] 消息 #{i}: {text[:60]}...")
        print(f"  {'─'*58}")

        result = SimpleNamespace(
            content=text,
            source="im",
            context=SimpleNamespace(
                source="lark_im",
                chat_id="oc_test_chat",
                sender_id="ou_test_user",
            ),
        )

        proc_start = time.time()
        await engine._process_detection(result)
        elapsed = time.time() - proc_start

        print(f"  [Test] 消息 #{i} 处理完成: {elapsed:.2f}s")

    # 4. 完成
    print(f"\n{'='*60}")
    print(f"  🎉 管道测试完成！")
    print(f"  日志文件: {_log_file}")
    print(f"  data/decisions/ 目录已生成决策文件")
    print(f"  请查看日志文件获取完整的 [Engine]/[LLM]/[Embedding]/[Reranker] 输出")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())