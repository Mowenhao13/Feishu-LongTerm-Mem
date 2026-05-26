"""
组件连通性测试 — 直接调用 LLM / Embedding / Reranker

测试所有模型组件的连通性并输出详细日志。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

# 日志配置
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"component_test_{time.strftime('%Y%m%d_%H%M%S')}.log"
_file_handler = RotatingFileHandler(
    _log_file, maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8",
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)

from src.utils.logger import get_logger
logger = get_logger("component_test")

# ==================== 测试内容 ====================
TEST_DECISION_TEXT = "我决定前端使用React框架，组件库用Ant Design，构建工具用Vite，后端使用Python FastAPI"
TEST_QUERY = "前端技术选型"
TEST_DOCS = [
    "前端使用React框架和Ant Design组件库",
    "后端使用Python FastAPI框架",
    "数据库使用PostgreSQL",
    "项目使用Docker部署",
    "前端使用Vue框架和Element Plus",
]

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


def step(name: str):
    print(f"\n{CYAN}{'='*60}{RESET}")
    print(f"{CYAN}  {name}{RESET}")
    print(f"{CYAN}{'='*60}{RESET}")


def ok(msg: str):
    print(f"  {GREEN}✅ {msg}{RESET}")


def fail(msg: str):
    print(f"  {RED}❌ {msg}{RESET}")


def warn(msg: str):
    print(f"  {YELLOW}⚠️  {msg}{RESET}")


# ========== Test 1: LLM ==========
async def test_llm():
    step("[1/3] 测试 LLM Provider")

    try:
        from src.model.llm_provider import LLMProvider

        base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
        api_key = os.getenv("API_KEY", "")
        model = os.getenv("MODEL_NAME", "deepseek-chat")

        if not api_key:
            warn("API_KEY 未配置，跳过 LLM 测试")
            return

        llm = LLMProvider(
            provider_type="openai",
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_tokens=4096,
        )
        ok(f"LLMProvider 创建成功: {base_url} model={model}")

        prompt = f"""请从以下文本中提取决策信息，以JSON格式返回：
文本: {TEST_DECISION_TEXT}

请返回格式:
{{
    "has_decision": true,
    "title": "决策标题",
    "content": "决策具体内容",
    "confidence": 0.9,
    "category": "技术选型"
}}"""

        logger.info("[LLM Test] >>> Sending prompt (len=%d)", len(prompt))
        start = time.time()
        resp = await llm.generate(prompt, response_format={"type": "json_object"})
        elapsed = time.time() - start
        logger.info("[LLM Test] <<< Response time=%.2fs len=%d", elapsed, len(resp))
        ok(f"LLM 响应成功 ({elapsed:.2f}s)")
        print(f"    响应预览: {resp[:200]}...")

    except Exception as e:
        fail(f"LLM 测试失败: {e}")
        import traceback
        logger.error("[LLM Test] Failed: %s\n%s", e, traceback.format_exc())


# ========== Test 2: Embedding ==========
async def test_embedding():
    step("[2/3] 测试 Embedding Provider")

    try:
        from src.model.embedding_provider import EmbeddingProvider

        embedder = EmbeddingProvider(
            base_url=os.getenv("EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1/embeddings"),
            model_name=os.getenv("EMBEDDING_MODEL_NAME", "Qwen3-Embedding-4B"),
            timeout=int(os.getenv("EMBEDDING_TIMEOUT", "120")),
            max_retries=int(os.getenv("EMBEDDING_MAX_RETRIES", "5")),
        )
        ok(f"EmbeddingProvider 创建成功: {embedder.base_url} model={embedder.model_name}")

        texts = TEST_DOCS + [TEST_DECISION_TEXT]
        logger.info("[Embedding Test] >>> Encoding %d texts", len(texts))
        start = time.time()
        vectors = embedder.embed(texts)
        elapsed = time.time() - start
        ok(f"Embedding 编码成功: {len(vectors)} 个向量, 维度={len(vectors[0]) if vectors else 0} ({elapsed:.2f}s)")

    except Exception as e:
        fail(f"Embedding 测试失败: {e}")
        import traceback
        logger.error("[Embedding Test] Failed: %s\n%s", e, traceback.format_exc())


# ========== Test 3: Reranker ==========
async def test_reranker():
    step("[3/3] 测试 Reranker Provider")

    try:
        from src.model.reranker_provider import RerankerProvider

        reranker = RerankerProvider(
            base_url=os.getenv("RERANKER_BASE_URL", "http://127.0.0.1:8001"),
            model_name=os.getenv("RERANKER_MODEL_NAME", "Qwen3-Reranker-4B"),
            timeout=int(os.getenv("RERANKER_TIMEOUT", "120")),
            max_retries=int(os.getenv("RERANKER_MAX_RETRIES", "10")),
        )
        ok(f"RerankerProvider 创建成功: {reranker.base_url} model={reranker.model_name}")

        logger.info("[Reranker Test] >>> Reranking query='%s' with %d docs", TEST_QUERY, len(TEST_DOCS))
        start = time.time()
        scores = reranker.rerank_single(TEST_QUERY, TEST_DOCS)
        elapsed = time.time() - start
        ok(f"Reranker 重排序成功: {len(scores)} 个分数 ({elapsed:.2f}s)")
        for i, (doc, score) in enumerate(zip(TEST_DOCS, scores)):
            print(f"    [{i+1}] score={score:.4f}  {doc}")

    except Exception as e:
        fail(f"Reranker 测试失败: {e}")
        import traceback
        logger.error("[Reranker Test] Failed: %s\n%s", e, traceback.format_exc())


async def main():
    print(f"{'='*60}")
    print(f"  组件连通性测试")
    print(f"  日志文件: {_log_file}")
    print(f"{'='*60}")

    await test_llm()
    await test_embedding()
    await test_reranker()

    print(f"\n{'='*60}")
    print(f"  测试完成！")
    print(f"  日志文件: {_log_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())