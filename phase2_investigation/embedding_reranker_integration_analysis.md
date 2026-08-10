# Phase 2 Investigation: Embedding & Reranker Integration Analysis

## 1 概述

本报告对 Feishu LongTerm-Mem 系统中 Embedding 模型和 Reranker 模型的完整集成情况进行分析，识别缺失环节并评估影响。

**关键结论**: 系统包含两个独立的 RAG 框架:

- **F1 — Decision RAG (MCP Server)**: `server.py` 的 `search` 工具，已完整集成 Embedding + Reranker
- **F2 — Hypergraph RAG (Core Engine)**: `HierarchicalRetriever` + `MemoryGraph`，仅使用关键词搜索，未集成 Embedding/Reranker

两者之间互不调用，形成两条并行的检索通道。

---

## 2 MCP Search 完整调用链路分析

### 2.1 当前链路（server.py:247）

```
search(query, topic, top_k)
  └─ EmbeddingProvider.embed([query])          → query_vector (4096d)
  └─ EmbeddingProvider.embed(all_decisions[])   → doc_vectors (N×4096d)
  └─ EmbeddingProvider.cosine_similarity()      → top_k*2 candidates
  └─ RerankerProvider.rerank_single(query, docs) → re-rank top_k*2
  └─ Combine & sort by reranker score → final top_k
```

**当前链路完整且正确**，但存在以下问题:

| 问题 | 位置 | 严重程度 |
|------|------|----------|
| 对整个决策池做全量 Embedding（每次搜索都重新计算） | server.py:262 | **性能问题** — N 条决策 → N 次 Embedding HTTP 请求 |
| 没有 Embedding 缓存/索引 | — | **缺失功能** — 决策数量大时每次搜索 O(N) |
| 批量 Embedding 单次可处理大量文本 | embedding_provider.py:72 | 取决于服务端 max_batch_size |
| 没有向量数据库（FAISS/Annoy 等） | — | **性能缺失** |

### 2.2 应然链路（含向量索引）

```
search(query, topic, top_k)
  └─ 检查向量索引（决策新增时增量构建）
  └─ EmbeddingProvider.embed([query])          → query_vector (1次)
  └─ 向量索引搜索 (cosine_similarity)          → top_k*2 candidates
  └─ RerankerProvider.rerank_single(query, docs) → re-rank
  └─ 最终排序 → final top_k
```

---

## 3 Embedding 索引覆盖范围

### 3.1 已嵌入的层

| 层 | 文件 | 位置 | 嵌入用途 |
|----|------|------|----------|
| Decision 全文 (MCP search) | server.py:260-262 | 运行时对全量决策做 Embedding | 语义相似度搜索 |
| SuspendedEpisode (SuspendPool) | suspend_pool.py:71-85, 40-51 | 每次 suspend 时对消息做 Embedding | Episode 语义边界检测 + 重连 |
| MemoryEngine 相似决策检测 | engine.py:995-1002 | 提取新决策时 Embedding 同 topic 决策 | 相似决策判定 |
| BM25Indexer | indexer.py:25-48 | 仅构建 BM25 索引 | 关键词检索 |

### 3.2 未嵌入的层

| 层 | 缺失影响 |
|----|----------|
| **HierarchicalRetriever** (retrieval.py) | 完全使用关键词，没有向量检索 |
| **MemoryGraph.search_by_keywords** (memory_graph.py:175) | substring 匹配，无语义理解 |
| **Hypergraph 层级** (topic/fact/episode) | 超图内容没有被 Embedding 覆盖 |
| **飞书文档内容** | 文档上下文仅通过飞书搜索 API 获取 |
| **持久化向量索引** (FAISS/HNSW) | 每次搜索都需要全量计算 |

### 3.3 Embedding 提供者的两套 Base URL

| 配置来源 | Base URL | 端口 | 备注 |
|----------|----------|------|------|
| `config.py:31` EMBEDDING_BASE_URL | http://localhost:11810/v1 | 11810 | ModelConfig 配置 |
| `embedding_provider.py:19` EMBEDDING_BASE_URL | http://0.0.0.0:11000/v1/embeddings | 11000 | EmbeddingProvider 默认 |
| 实际部署服务 | http://localhost:9000 | 9000 | research-question-agent 已验证 |
| `reranker_provider.py:31` RERANKER_BASE_URL | http://0.0.0.0:11000 | 11000 | RerankerProvider 默认 |
| `config.py:83` RERANKER_BASE_URL | http://localhost:12810 | 12810 | ModelConfig 配置 |
| 实际部署服务 | http://localhost:9001 | 9001 | research-question-agent 已验证 |

**存在三套不一致的端口配置**（11000/11810/9000 和 11000/12810/9001），运行时实际连接取决于环境变量设置。

---

## 4 Reranker 集成分析

### 4.1 已集成的调用点

| 调用点 | 位置 | 条件 |
|--------|------|------|
| MCP search 工具 | server.py:268 | 每次搜索 — **无条件的** |
| MemoryEngine._find_similar_decision | engine.py:1007-1012 | 当 `self._reranker` 被设置时 |
| ModelConfig | config.py:80-84 | `use_reranker` 默认 **false** |
| EmbeddingProvider.set_embedding_reranker | engine.py:928-935 | 未被任何启动路径调用 |

### 4.2 未集成的调用点

| 调用点 | 问题 |
|--------|------|
| **HierarchicalRetriever.retrieve** (retrieval.py:53) | 完全不调用 EmbeddingProvider 或 RerankerProvider |
| **MemoryGraph.search_by_keywords** | 纯字符串匹配，没有重排入口 |
| **MemoryEngine.retrieve** (engine.py:1440) | 代理调用 search_by_keywords |
| **BM25Indexer.search** (indexer.py:51) | 仅有 BM25 分数，无重排 |
| **核心推理管道** | EngineConfig.use_reranker=false |

### 4.3 Reranker 配置的悖论

config.py:80 中 `use_reranker` 默认 false，但 server.py:255-268 在 search 工具中无条件创建和使用 RerankerProvider。这意味着：

- **MCP search** 总是使用 Reranker（忽略 config.py 配置）
- **Core Engine** 仅在 `use_reranker=true` 时使用 Reranker，但默认不启用
- `MemoryEngine.set_embedding_reranker` 从未被任何启动代码调用过

---

## 5 HierarchicalRetriever 缺失分析

### 5.1 当前 retrieve() 流程

```
retrieve(query)
  └─ memory_graph.search_by_keywords(query)   → substring 匹配
  └─ 按 topic 分组
  └─ 去重
  └─ 返回
```

### 5.2 缺失的 3 层检索

HierarchicalRetriever 宣称支持：
```
3层检索（Topic → Episode/Decision → Fact），支持 BM25 + 向量融合
```

但实际实现只有：
```
1层检索（Decision），仅关键词匹配
```

**缺失的层**：
- Topic 层语义检索（目前 topic 分组完全依赖 decision 层面的 topic_id 字段）
- Episode 层检索（Hypergraph 中的 episode 节点未被纳入）
- Fact 层检索（Hypergraph 中的 fact 节点未被纳入）
- BM25 + 向量融合（BM25Indexer 未被调用，reciprocal_rank_fusion 是死代码）
- RRF 融合（reciprocal_rank_fusion 是静态方法，没有任何调用点）

### 5.3 BM25Indexer 与 HierarchicalRetriever 的隔离

BM25Indexer 从 hypergraph 构建索引（facts + episodes），而 HierarchicalRetriever 从 MemoryGraph 检索 decisions。两者操作不同的数据源，无集成点。

---

## 6 启动流程中的 Embedding/Reranker 初始化

### 6.1 当前启动路径

```
scripts/mcp_server.py
  └─ EmbeddingProvider()  ← 在 search 工具中惰性创建
  └─ RerankerProvider()   ← 在 search 工具中惰性创建

MemoryEngine.initialize()
  └─ self._embedder = None  (line 441)
  └─ self._reranker = None  (line 442)
  └─ set_embedding_reranker()  ← 从未被调用
```

### 6.2 启动路径缺失

- `scripts/mcp_server.py` **没有**创建 EmbeddingProvider/RerankerProvider 并注入 MemoryEngine 的逻辑
- MemoryEngine.set_embedding_reranker 方法已定义但**无调用者**
- 无统一的 Embedding+Reranker 初始化入口

---

## 7 缺失总结与影响评估

### 缺失 1: HierarchicalRetriever 缺少向量检索（严重）
- **位置**: retrieval.py:53
- **影响**: Hypergraph RAG 通道的检索质量仅取决于关键词匹配
- **修复**: 在 retrieve() 中添加向量相似度分支，使用 EmbeddingProvider

### 缺失 2: 缺少持久化向量索引（严重）
- **影响**: MCP search 每次做全量 Embedding，O(N) 不可扩展
- **修复**: 在数据写入时构建向量索引（增量维护），检索时仅 embedding query

### 缺失 3: Embedding/Reranker 端口三套不一致（中等）
- **位置**: config.py:31,83; embedding_provider.py:19; reranker_provider.py:31
- **影响**: 配置混乱，容易连错服务
- **修复**: 统一为单一来源的环境变量，去除默认值硬编码

### 缺失 4: MemoryEngine 启动时未注入 Embedding/Reranker（中等）
- **位置**: engine.py:928-935, 441-442
- **影响**: Core Engine 的相似决策检测无法使用语义检索
- **修复**: 在 MemoryEngine.initialize() 中添加 EmbeddingProvider/RerankerProvider 的创建和注入

### 缺失 5: Hypergraph 内容未被 Embedding 覆盖（中等）
- **位置**: graph/builder.py, graph/indexer.py
- **影响**: 超图中的 topic/fact/episode 节点无法语义检索
- **修复**: 在 HypergraphBuilder 构建时对节点内容做 Embedding 并存储

### 缺失 6: BM25 索引未被 HierarchicalRetriever 调用（低）
- **位置**: retrieval.py:33, indexer.py:25
- **影响**: BM25Indexer 已构建但无人使用
- **修复**: 在 HierarchicalRetriever 中添加 BM25 分支

### 缺失 7: reciprocal_rank_fusion 是死代码（低）
- **位置**: retrieval.py:106-128
- **影响**: RRF 方法已定义但无调用者
- **修复**: 集成到 HierarchicalRetriever 的融合检索流程中

### 缺失 8: use_reranker 配置未实际控制任何行为（低）
- **位置**: config.py:80
- **影响**: 该配置项除影响 experiment_name 构建外无实际作用
- **修复**: 使其控制 Core Engine 的 reranker 启用

---

## 8 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    System Architecture                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐    ┌──────────────────────────────┐   │
│  │  MCP Server   │    │       Core Engine            │   │
│  │  (server.py)  │    │     (engine.py)               │   │
│  │               │    │                               │   │
│  │  search() ────┼───►│  ✓ Embedding + Reranker      │   │
│  │  ✓ Embedding  │    │  (每请求全量计算)              │   │
│  │  ✓ Reranker   │    │                               │   │
│  │  ✗ 无向量索引  │    │  ✗ MemoryEngine.retrieve()   │   │
│  └──────────────┘    │    = search_by_keywords          │   │
│                       │                               │   │
│  ┌──────────────┐    │  _find_similar_decision() ──►  │   │
│  │ SuspendPool   │    │  ✓ Embedding + Reranker       │   │
│  │  ✓ Embedding  │    │  (需注入 embedder)             │   │
│  │  (语义边界)    │    │                               │   │
│  └──────────────┘    │  ┌──────────────────────┐      │   │
│                       │  │ HierarchicalRetriever│      │   │
│  ┌──────────────┐    │  │  (retrieval.py)      │      │   │
│  │ BM25Indexer   │    │  │  ✗ vector search     │      │   │
│  │  (indexer.py) │    │  │  ✗ BM25              │      │   │
│  │  ✗ 未被调用    │    │  │  ✗ RRF               │      │   │
│  └──────────────┘    │  │  ✗ Hierarchical       │      │   │
│                       │  │  = keyword only       │      │   │
│                       │  └──────────────────────┘      │   │
│                       │                               │   │
│                  启动时: set_embedding_reranker() ←┘   │
│                  从不被调用                            │
└─────────────────────────────────────────────────────────┘
```

---

## 9 修复优先级建议

| 优先级 | 缺失项 | 预期收益 |
|--------|--------|----------|
| P0 | HierarchicalRetriever + 向量检索 | 核心 RAG 质量提升 |
| P0 | 持久化向量索引 | MCP search 性能保障 |
| P1 | 统一 Embedding/Reranker 端口配置 | 运维可靠性 |
| P1 | MemoryEngine 启动时注入 | 相似决策检测语义化 |
| P2 | Hypergraph Embedding | 超图语义检索 |
| P2 | BM25 集成到 HierarchicalRetriever | 混合检索能力 |
| P3 | RRF 集成 | 多通道融合能力 |
| P3 | use_reranker 配置有效化 | 配置体系完整 |