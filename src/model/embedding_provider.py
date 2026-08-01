from typing import List
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import numpy as np
import time
import os
from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)


class EmbeddingProvider:
    def __init__(self, base_url: str = None, model_name: str = None, timeout: int = 120, max_retries: int = 5):
        self.base_url = base_url or os.getenv("EMBEDDING_BASE_URL", "http://0.0.0.0:11000/v1/embeddings")
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL_NAME", "Qwen3-Embedding-4B")
        self.api_key = os.getenv("EMBEDDING_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries

        logger.info("[Embedding] Init: url=%s model=%s timeout=%d retries=%d",
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

    def cosine_similarity(self, query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
        dot_product = np.dot(doc_vecs, query_vec)
        query_norm = np.linalg.norm(query_vec)
        doc_norms = np.linalg.norm(doc_vecs, axis=1)
        denominator = query_norm * doc_norms
        denominator[denominator == 0] = 1e-9
        similarity_scores = dot_product / denominator
        return similarity_scores

    def check_connection(self, timeout: int = 5) -> bool:
        """检查 embedding 服务连接是否正常"""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            response = self.session.post(
                self.base_url,
                json={"input": ["test"], "model": self.model_name},
                timeout=timeout,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("data") and len(result["data"]) > 0:
                logger.info("[Embedding] Connection check: OK (dim=%d)",
                            len(result["data"][0]["embedding"]))
                return True
            logger.warning("[Embedding] Connection check: unexpected response format")
            return False
        except Exception as e:
            logger.warning("[Embedding] Connection check FAILED: %s", str(e)[:80])
            return False

    def embed(self, texts: List[str]) -> List[List[float]]:
        if 'qwen3' not in self.model_name.lower():
            raise ValueError(f"Model {self.model_name} is not supported, only Qwen3-Embedding series models is supported")

        n_texts = len(texts)
        total_chars = sum(len(t) for t in texts)
        logger.info("[Embedding] >>> Request: texts=%d chars=%d model=%s",
                    n_texts, total_chars, self.model_name)

        for i, t in enumerate(texts):
            preview = t[:80].replace("\n", " ")
            logger.info("[Embedding]     text[%d/%d] len=%d preview=%.60s",
                        i + 1, n_texts, len(t), preview)

        start = time.time()
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                response = self.session.post(
                    self.base_url,
                    json={"input": texts, "model": self.model_name},
                    timeout=self.timeout,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                vectors = [item['embedding'] for item in result['data']]
                elapsed = time.time() - start
                dims = len(vectors[0]) if vectors else 0
                arr = np.array(vectors)
                logger.info("[Embedding] <<< Response: vectors=%d dim=%d time=%.2fs "
                            "value_range=[%.4f, %.4f] mean=%.4f std=%.4f",
                            len(vectors), dims, elapsed,
                            float(arr.min()), float(arr.max()),
                            float(arr.mean()), float(arr.std()))
                return vectors
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                last_exception = e
                wait_time = 2 ** attempt
                logger.warning("[Embedding] Connection failed (attempt %d/%d): %s, retry in %ds",
                               attempt + 1, self.max_retries, str(e)[:50], wait_time)
                time.sleep(wait_time)
            except Exception as e:
                elapsed = time.time() - start
                logger.error("[Embedding] Request failed after %.2fs: %s", elapsed, str(e)[:100])
                raise e

        elapsed = time.time() - start
        logger.error("[Embedding] All %d retries exhausted after %.2fs", self.max_retries, elapsed)
        raise last_exception