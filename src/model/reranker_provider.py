"""
Qwen3-Reranker provider — 支持两种 API 模式:

1. **简单 REST API** (推荐): POST {base_url}/v1/rerank
   {"query": "...", "documents": ["..."], "model": "..."}
   → 优先使用，服务端需部署对应的 rerank 封装

2. **vLLM completions API** (官方): POST {base_url}/v1/completions
   prompt + logprobs 方式，需 vLLM 原生部署
   Reference: https://huggingface.co/Qwen/Qwen3-Reranker-4B
"""

from typing import List
import requests
import math
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import os
from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)


class RerankerProvider:
    def __init__(self, base_url: str = None, model_name: str = None, timeout: int = 120, max_retries: int = 10):
        self.base_url = base_url or os.getenv("RERANKER_BASE_URL", "http://0.0.0.0:11000")
        self.model_name = model_name or os.getenv("RERANKER_MODEL_NAME", "Qwen3-Reranker-4B")
        self.api_key = os.getenv("RERANKER_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries

        logger.info("[Reranker] Init: url=%s model=%s timeout=%d retries=%d",
                    self.base_url, self.model_name, timeout, max_retries)

        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def rerank(self, queries: List[str], docs: List[str], instruction: str = None) -> List[float]:
        if 'Qwen3' not in self.model_name:
            raise ValueError(f"Model {self.model_name} is not supported, only Qwen3-Reranker series models is supported")

        n_queries = len(queries)
        n_docs = len(docs)
        logger.info("[Reranker] >>> Request: queries=%d docs=%d model=%s",
                    n_queries, n_docs, self.model_name)

        for i, q in enumerate(queries):
            logger.info("[Reranker]     query[%d/%d] len=%d preview=%.60s",
                        i + 1, n_queries, len(q), q[:80].replace("\n", " "))
        for i, d in enumerate(docs):
            logger.info("[Reranker]     doc[%d/%d] len=%d preview=%.60s",
                        i + 1, n_docs, len(d), d[:80].replace("\n", " "))

        if n_queries == 1:
            try:
                return self._rerank_via_api(queries[0], docs)
            except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError, TypeError, KeyError) as e:
                logger.warning("[Reranker] /v1/rerank failed, falling back to completions: %s", str(e)[:60])

        return self._rerank_via_completions(queries, docs, instruction)

    def rerank_single(self, query: str, docs: List[str]) -> List[float]:
        return self.rerank([query], docs)

    def check_connection(self, timeout: int = 5) -> bool:
        """检查 reranker 服务连接是否正常"""
        try:
            url = self.base_url.rstrip('/') + '/v1/rerank'
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            response = self.session.post(
                url,
                json={
                    "query": "test",
                    "documents": ["test document"],
                    "top_n": 1,
                    "model": self.model_name,
                },
                timeout=timeout,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("results") and len(result["results"]) > 0:
                score = result["results"][0].get("score", 0)
                logger.info("[Reranker] Connection check: OK (score=%.4f)", score)
                return True
            logger.warning("[Reranker] Connection check: unexpected response format")
            return False
        except Exception as e:
            logger.warning("[Reranker] Connection check FAILED: %s", str(e)[:80])
            return False

    def _rerank_via_api(self, query: str, docs: List[str]) -> List[float]:
        url = self.base_url.rstrip('/') + '/v1/rerank'
        logger.info("[Reranker] POST %s query=%.60s docs=%d", url, query, len(docs))

        start = time.time()
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                response = self.session.post(
                    url,
                    json={
                        "query": query,
                        "documents": docs,
                        "top_n": len(docs),
                        "model": self.model_name,
                    },
                    timeout=self.timeout,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()

                results = result.get("results", [])
                scores = [0.0] * len(docs)
                for item in results:
                    idx = item.get("index")
                    if idx is not None and 0 <= idx < len(docs):
                        scores[idx] = item.get("score", 0.0)
                elapsed = time.time() - start
                ranked = sorted(
                    [(scores[i], i, docs[i]) for i in range(len(docs))],
                    key=lambda x: x[0], reverse=True
                )
                top3 = "; ".join(
                    f"[{idx}]{s:.4f}:{d[:40]}"
                    for s, idx, d in ranked[:3]
                )
                logger.info("[Reranker] <<< Response: scores=%s time=%.2fs top3=%s",
                           [round(s, 4) for s in scores], elapsed, top3)
                return scores

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                if attempt == self.max_retries - 1:
                    elapsed = time.time() - start
                    logger.error("[Reranker] All %d retries exhausted after %.2fs: %s",
                                 self.max_retries, elapsed, str(e)[:60])
                    raise
                wait_time = 2 ** attempt
                logger.warning("[Reranker] API connection failed (attempt %d/%d): %s, retry in %ds",
                               attempt + 1, self.max_retries, str(e)[:50], wait_time)
                time.sleep(wait_time)
            except Exception as e:
                elapsed = time.time() - start
                logger.error("[Reranker] API error after %.2fs: %s", elapsed, str(e)[:80])
                raise e

        raise ConnectionError(f"Reranker API connection failed after {self.max_retries} retries")

    def _rerank_via_completions(self, queries: List[str], docs: List[str], instruction: str = None) -> List[float]:
        prefix = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
        suffix = "<|im_end|>\n<|im_start|>assistant\n thinking\n\n response\n\n"
        if instruction is None:
            instruction = "Given a user's question and a text passage, determine if the passage contains specific information that directly answers the question."

        prompts = []
        for query, doc in zip(queries, docs):
            prompt = f"{prefix}<Instruct>: {instruction}\n\n<Query>: {query}\n\n<Document>: {doc}{suffix}"
            prompts.append(prompt)

        completions_url = self.base_url.rstrip('/') + '/v1/completions'
        logger.info("[Reranker] POST %s completions prompts=%d", completions_url, len(prompts))

        start = time.time()
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                response = self.session.post(
                    completions_url,
                    json={
                        "model": self.model_name,
                        "prompt": prompts,
                        "max_tokens": 1,
                        "logprobs": 20,
                        "temperature": 0,
                    },
                    timeout=self.timeout,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()

                scores = []
                for choice in result['choices']:
                    top_logprobs = choice.get('logprobs', {}).get('top_logprobs', [{}])[0]
                    yes_logprob = top_logprobs.get('yes', -10)
                    no_logprob = top_logprobs.get('no', -10)
                    yes_prob = math.exp(yes_logprob)
                    no_prob = math.exp(no_logprob)
                    score = yes_prob / (yes_prob + no_prob) if (yes_prob + no_prob) > 0 else 0
                    scores.append(score)
                elapsed = time.time() - start
                ranked = sorted(
                    [(scores[i], i, docs[i]) for i in range(len(docs))],
                    key=lambda x: x[0], reverse=True
                )
                top3 = "; ".join(
                    f"[{idx}]{s:.4f}:{d[:40]}"
                    for s, idx, d in ranked[:3]
                )
                logger.info("[Reranker] <<< Completions response: scores=%s time=%.2fs top3=%s",
                           [round(s, 4) for s in scores], elapsed, top3)
                return scores

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning("[Reranker] Completions failed (attempt %d/%d): %s, retry in %ds",
                               attempt + 1, self.max_retries, str(e)[:50], wait_time)
                time.sleep(wait_time)
            except Exception as e:
                elapsed = time.time() - start
                logger.error("[Reranker] Completions error after %.2fs: %s", elapsed, str(e)[:80])
                raise e

        elapsed = time.time() - start
        logger.error("[Reranker] Completions all %d retries exhausted after %.2fs", self.max_retries, elapsed)
        raise ConnectionError(f"Reranker completions connection failed after {self.max_retries} retries: {str(last_exception)}")