import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# ==================== Path Configuration ====================
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"


class ModelConfig:
    # ==================== General ====================
    experiment_name: str = os.environ.get("HYPERMEM_EXPERIMENT_NAME", "HyperMem-v3")
    dataset_path: str = str(DATA_DIR / "locomo10.json")
    num_conv: int = 1

    # ==================== Stage 2: Index Building ====================
    hyperedge_emb_aggregate_type: str = "sum"
    node_emb_update_weight: float = 0.5

    embedding_config: dict = {
        "model_name": "Qwen3-Embedding-4B",
        "base_url": os.environ.get("EMBEDDING_BASE_URL", "http://localhost:11810/v1"),
    }
    embedding_max_retries: int = 10

    # ==================== Stage 3: Retrieval ====================
    retrieval_type: str = "rrf"
    rerank_type: str = "fix"
    hypergraph_retrieval_output_type: str = "011"

    retrieval_config: dict = {
        "initial_candidates": int(os.environ.get("HYPERMEM_INITIAL_CANDIDATES", "100")),
        "topic_top_k": int(os.environ.get("HYPERMEM_TOPIC_TOP_K", "15")),
        "episode_top_k": int(os.environ.get("HYPERMEM_EPISODE_TOP_K", "20")),
        "fact_top_k": int(os.environ.get("HYPERMEM_FACT_TOP_K", "30")),
    }
    adaptive_retrieval_config: dict = {
        "factual": {
            "initial_candidates": 180,
            "topic_top_k": 8,
            "episode_top_k": 16,
            "fact_top_k": 24,
        },
        "temporal": {
            "initial_candidates": 200,
            "topic_top_k": 10,
            "episode_top_k": 20,
            "fact_top_k": 30,
        },
        "reasoning": {
            "initial_candidates": 250,
            "topic_top_k": 12,
            "episode_top_k": 25,
            "fact_top_k": 35,
        },
        "commonsense": {
            "initial_candidates": 180,
            "topic_top_k": 8,
            "episode_top_k": 16,
            "fact_top_k": 24,
        },
        "default": {
            "initial_candidates": 200,
            "topic_top_k": 10,
            "episode_top_k": 20,
            "fact_top_k": 30,
        }
    }

    temporal_enhancement: bool = True

    use_reranker: bool = os.environ.get("HYPERMEM_USE_RERANKER", "false").lower() == "true"
    reranker_config: dict = {
        "model_name": "Qwen3-Reranker-4B",
        "base_url": os.environ.get("RERANKER_BASE_URL", "http://localhost:12810"),
    }
    reranker_max_retries: int = 10

    # ==================== Stage 4: Response Generation ====================
    answer_type: str = "cot"
    llm_service: str = os.environ.get("HYPERMEM_LLM_SERVICE", "openai")

    llm_config: dict = {
        "openai": {
            "llm_provider": "openai",
            "model": os.environ.get("HYPERMEM_LLM_MODEL", "deepseek-chat"),
            "base_url": os.environ.get("HYPERMEM_LLM_BASE_URL", "https://api.deepseek.com"),
            "api_key": os.environ.get("HYPERMEM_LLM_API_KEY", os.environ.get("DEEPSEEK_API_KEY", "")),
            "temperature": float(os.environ.get("HYPERMEM_LLM_TEMPERATURE", "0")),
            "max_tokens": int(os.environ.get("HYPERMEM_LLM_MAX_TOKENS", "16384")),
        },
        "gemini": {
            "llm_provider": "openai",
            "model": "google/gemini-2.5-flash",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
            "temperature": 0.3,
            "max_tokens": 16384,
        },
        "vllm": {
            "llm_provider": "openai",
            "model": "Qwen3-30B",
            "base_url": os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1"),
            "api_key": "unused",
            "temperature": 0,
            "max_tokens": 20000,
        },
        "vllm_local": {
            "llm_provider": "openai",
            "model": os.environ.get("HYPERMEM_LOCAL_LLM_MODEL", "Qwen3-8B"),
            "base_url": os.environ.get("HYPERMEM_LOCAL_LLM_BASE_URL", "http://localhost:8000/v1"),
            "api_key": "unused",
            "temperature": float(os.environ.get("HYPERMEM_LOCAL_LLM_TEMPERATURE", "0")),
            "max_tokens": int(os.environ.get("HYPERMEM_LOCAL_LLM_MAX_TOKENS", "4096")),
        }
    }

    judge_llm_config: dict = {
        "model": os.environ.get("HYPERMEM_JUDGE_MODEL", os.environ.get("HYPERMEM_LOCAL_LLM_MODEL", "deepseek-chat")),
        "base_url": os.environ.get("HYPERMEM_JUDGE_BASE_URL", os.environ.get("HYPERMEM_LOCAL_LLM_BASE_URL", "https://api.deepseek.com")),
        "api_key": os.environ.get("HYPERMEM_JUDGE_API_KEY", os.environ.get("HYPERMEM_LLM_API_KEY", os.environ.get("DEEPSEEK_API_KEY", ""))),
        "temperature": 0,
    }

    llm_max_retries: int = 10
    max_concurrent_requests: int = 10

    # ==================== Derived Paths ====================
    @classmethod
    def experiment_dir(cls) -> Path:
        return RESULTS_DIR / cls.experiment_name

    @classmethod
    def episodes_dir(cls) -> Path:
        return cls.experiment_dir() / "episodes"

    @classmethod
    def hypergraph_dir(cls) -> Path:
        return cls.experiment_dir() / "hypergraphs"

    @classmethod
    def facts_dir(cls) -> Path:
        return cls.experiment_dir() / "facts"

    @classmethod
    def topics_dir(cls) -> Path:
        return cls.experiment_dir() / "topics"

    @classmethod
    def token_stats_dir(cls) -> Path:
        return cls.experiment_dir() / "token_stats"

    @classmethod
    def bm25_index_dir(cls) -> Path:
        return cls.experiment_dir() / "bm25_index"

    @classmethod
    def vectors_dir(cls) -> Path:
        return cls.experiment_dir() / "vectors"


def _build_experiment_name():
    parts = [ModelConfig.experiment_name]

    if ModelConfig.retrieval_type in ('vector', 'rrf'):
        parts.append(ModelConfig.hyperedge_emb_aggregate_type)
        parts.append(f"alpha{ModelConfig.node_emb_update_weight}")

    if ModelConfig.retrieval_type in ('vector', 'rrf'):
        parts.append(f"{ModelConfig.retrieval_type.upper()}")
        if ModelConfig.rerank_type == "ada":
            parts.append(ModelConfig.rerank_type)
        else:
            rc = ModelConfig.retrieval_config
            parts.append(f"{ModelConfig.rerank_type}-{rc['initial_candidates']}-{rc['topic_top_k']}-{rc['episode_top_k']}-{rc['fact_top_k']}")
    else:
        parts.append(ModelConfig.retrieval_type)
    parts.append(f"r{ModelConfig.hypergraph_retrieval_output_type}")

    if ModelConfig.use_reranker:
        parts.append("rerank")
    else:
        parts.append("wo-rerank")

    parts.append(f"{ModelConfig.answer_type}")

    return "_".join(parts)

ModelConfig.experiment_name = _build_experiment_name()
