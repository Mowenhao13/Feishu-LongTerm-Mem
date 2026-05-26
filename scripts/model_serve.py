"""
model_serve.py — 远程模型服务启动脚本

在远程 GPU 服务器上启动 Embedding / Reranker 模型服务。

用法:
    # 启动 Embedding 服务 (GPU 1, 端口 8000)
    uv run python scripts/model_serve.py --mode embedding --gpu 1 --port 8000

    # 启动 Reranker 服务 (GPU 5, 端口 8001)
    uv run python scripts/model_serve.py --mode reranker --gpu 5 --port 8001

    # 本地测试连接
    curl http://127.0.0.1:8000/v1/embeddings -X POST \
      -H "Content-Type: application/json" \
      -d '{"input": ["test"], "model": "Qwen3-Embedding-4B"}'
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

import torch
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer

app = FastAPI()

# 全局模型实例（在 startup 时加载）
_model = None
_tokenizer = None
_mode: str = ""
_device: str = ""


# ==================== 请求/响应模型 ====================


class EmbeddingRequest(BaseModel):
    input: List[str]
    model: str = "Qwen3-Embedding-4B"


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: List[float]


class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: EmbeddingUsage


class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_n: int = -1
    model: str = "Qwen3-Reranker-4B"


class RerankResult(BaseModel):
    index: int
    score: float


class RerankResponse(BaseModel):
    model: str
    results: List[RerankResult]
    usage: Dict[str, Any]


# ==================== Embedding 端点 ====================


@app.post("/v1/embeddings")
async def embed(req: EmbeddingRequest):
    global _model, _tokenizer, _device

    t0 = time.time()
    print(f"[Embedding] >>> Request: texts={len(req.input)} model={req.model}", flush=True)

    encoded = _tokenizer(
        req.input,
        padding=True,
        truncation=True,
        return_tensors="pt",
        max_length=8192,
    ).to(_device)

    with torch.no_grad():
        output = _model(**encoded)

    # Qwen3-Embedding: use the last hidden state of the last token
    last_hidden = output.last_hidden_state
    # [batch, seq_len, hidden] -> [batch, hidden] using last token
    # This is typically how embedding models extract the sentence embedding
    embeddings = last_hidden[:, -1, :].cpu().numpy().tolist()

    data = []
    for i, emb in enumerate(embeddings):
        data.append(EmbeddingData(index=i, embedding=emb))

    elapsed = time.time() - t0
    print(f"[Embedding] <<< Response: vectors={len(data)} dim={len(data[0].embedding) if data else 0} time={elapsed:.2f}s", flush=True)

    return EmbeddingResponse(data=data, model=req.model, usage=EmbeddingUsage(total_tokens=len(req.input)))


# ==================== Reranker 端点 ====================


@app.post("/v1/rerank")
async def rerank(req: RerankRequest):
    global _model, _tokenizer, _device

    t0 = time.time()
    n_docs = len(req.documents)
    top_n = req.top_n if req.top_n > 0 else n_docs

    print(f"[Reranker] >>> Request: query={req.query[:60]} docs={n_docs} top_n={top_n}", flush=True)

    pairs = [[req.query, doc] for doc in req.documents]
    encoded = _tokenizer(
        pairs,
        padding=True,
        truncation=True,
        return_tensors="pt",
        max_length=8192,
    ).to(_device)

    with torch.no_grad():
        if hasattr(_model, 'model') and hasattr(_model, 'lm_head'):
            base_out = _model.model(**encoded)
            logits = _model.lm_head(base_out.last_hidden_state)
        else:
            outputs = _model(**encoded)
            if hasattr(outputs, 'logits'):
                logits = outputs.logits
            else:
                logits = outputs.last_hidden_state

        # Compute average log-probability of each sequence as relevance score
        # Higher log-prob = more coherent pair = more relevant
        shift_logits = logits[:, :-1, :].contiguous()
        shift_labels = encoded.input_ids[:, 1:].contiguous()
        shift_attn = encoded.attention_mask[:, 1:].contiguous()

        token_log_probs = torch.gather(
            torch.log_softmax(shift_logits, dim=-1),
            2,
            shift_labels.unsqueeze(-1),
        ).squeeze(-1)  # [batch, seq_len-1]

        # Mask out padding positions
        token_log_probs = token_log_probs * shift_attn
        token_count = shift_attn.sum(dim=-1).clamp(min=1)
        scores = (token_log_probs.sum(dim=-1) / token_count).cpu().numpy().tolist()

    indexed = [(i, scores[i]) for i in range(n_docs)]
    indexed.sort(key=lambda x: x[1], reverse=True)

    results = [RerankResult(index=idx, score=score) for idx, score in indexed[:top_n]]

    elapsed = time.time() - t0
    top3 = "; ".join(f"[{idx}]{s:.4f}" for idx, s in indexed[:3])
    print(f"[Reranker] <<< Response: results={len(results)} time={elapsed:.2f}s top3={top3}", flush=True)

    return RerankResponse(model=req.model, results=results, usage={"total_tokens": n_docs})


# ==================== 启动事件 ====================


@app.on_event("startup")
async def startup():
    global _model, _tokenizer, _device, _mode, _model_path

    print(f"[{_mode.upper()}] Loading model: {_model_path}", flush=True)
    t0 = time.time()

    _tokenizer = AutoTokenizer.from_pretrained(_model_path, trust_remote_code=True)
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token

    if _mode == "embedding":
        _model = AutoModel.from_pretrained(
            _model_path,
            trust_remote_code=True,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        ).to(_device).eval()
    else:
        _model = AutoModelForCausalLM.from_pretrained(
            _model_path,
            trust_remote_code=True,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        ).to(_device).eval()

    elapsed = time.time() - t0
    print(f"[{_mode.upper()}] Model loaded on {_device} in {elapsed:.1f}s", flush=True)


@app.get("/health")
async def health():
    return {"status": "ok", "mode": _mode, "device": str(_device)}


# ==================== 入口 ====================


def main():
    parser = argparse.ArgumentParser(description="Embedding / Reranker 模型服务")
    parser.add_argument("--mode", type=str, required=True, choices=["embedding", "reranker"], help="服务模式")
    parser.add_argument("--gpu", type=int, default=0, help="GPU 索引 (默认: 0)")
    parser.add_argument("--port", type=int, default=8000, help="服务端口 (默认: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--model-path", type=str, default="", help="模型路径 (默认自动选择)")
    args = parser.parse_args()

    global _mode, _model_path, _device

    _mode = args.mode
    if args.mode == "embedding":
        _model_path = args.model_path or "/home/ubuntu/data/models/Qwen/Qwen3-Embedding-4B"
    else:
        _model_path = args.model_path or "/home/ubuntu/data/models/Qwen/Qwen3-Reranker-4B"

    _device = f"cuda:{args.gpu}"

    print(f"[{_mode.upper()}] Starting server on {args.host}:{args.port} (GPU={args.gpu})", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()