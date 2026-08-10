# Feishu-LongTerm-Mem

飞书长期记忆系统 — 从团队聊天会话中提取结构化知识，构建带本体约束的知识图谱，提供多模态决策检索。

## 架构概览

```
飞书消息 / 文档
    │
    ▼
┌──────────────────────────────┐
│         Pipeline Engine       │  决策管道引擎
│  (mutation → dedup → merge)   │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│       Memory Extractor       │  记忆提取（两阶段）
│  Stage 1: 实体/关系/事实      │  ← 受本体(Ontology)约束
│  Stage 2: 带实体上下文的决策   │
└──────┬───────────────────────┘
       ▼
┌──────────────────────────────┐
│    Neo4j Graph Database      │  知识图谱：实体节点、决策节点
│  (Entity / Decision / Episode)│  关系: MENTIONS, BELONGS_TO,
│                               │        REFERENCES, RELATES, …
└──────┬───────────────────────┘
       ▼
┌──────────────────────────────┐
│   Hierarchical Retriever     │  层次化检索（RRF 融合）
│  EntityGraph + Vector + BM25 │  Neo4j 图信号 + 向量相似度
└──────────────────────────────┘
```

## 架构定位：Ontology-Guided Knowledge Graph（本体约束的知识图谱）

本项目**采用本体（Ontology）约束知识图谱**的混合架构，而非纯粹的简单知识图谱或完整形式化本体：

| 维度 | 本项目的定位 |
|------|-------------|
| **实体类型** | 由 YAML 定义（5 种：Person, Technology, Project, Service, Concept），每个类型带属性 schema |
| **关系类型** | 由 YAML 定义（Person→Technology: USES/ADOPTED/…，Person→Person: REPORTS_TO/…，等 9 组关系约束） |
| **约束检查** | 运行时可校验实体/关系是否符合类型定义和属性枚举 |
| **存储** | Neo4j 图数据库，按类型标签查询（:Entity, :Decision, :Episode, :Document, :Topic） |
| **动态本体** | 支持热加载 + YAML 链式合并（默认 + 自定义扩展） |

### 与纯知识图谱的区别

- **纯知识图谱**（如标准 Neo4j schema-lite）：只有节点标签和关系类型，不约束属性和关系合法性
- **本项目**的 Ontology Manager + YAML 本体定义提供了**运行时约束**和**LLM prompt 注入**，确保提取的实体和关系符合领域模型

### 与完整形式化本体的区别

- **完整形式化本体**（如 OWL/RDF）：支持推理、约束传播、一致性检查
- **本项目**的 Ontology 更轻量：只有实体类型定义和关系约束，不做推理，定位为**LLM 提取的 Schema 约束**

### 实体类型

| 类型 | 描述 | 关键属性 |
|------|------|---------|
| `Person` | 团队成员 | role |
| `Technology` | 技术栈/工具/框架 | version, category (database/framework/language/tool/platform/service/library) |
| `Project` | 项目/模块/子系统 | status (active/planning/evaluating/deprecated) |
| `Service` | 服务/微服务实例 | type, provider |
| `Concept` | 抽象概念/架构模式 | description |

### 关系类型

| 源 → 目标 | 关系 |
|-----------|------|
| Person → Technology | USES, ADOPTED, RECOMMENDS, REJECTED, EVALUATING |
| Person → Project | OWNS, CONTRIBUTES_TO, DECIDES, REVIEWS |
| Person → Person | REPORTS_TO, COLLABORATES_WITH, MENTORS |
| Project → Technology | USES_TECHNOLOGY, EVALUATING, MIGRATING_TO, DEPENDS_ON |
| Technology → Technology | DEPENDS_ON, REPLACES, COMPATIBLE_WITH, INCOMPATIBLE_WITH |
| Service → Service | DEPENDS_ON, COMMUNICATES_WITH |
| 任意 → 任意 | ASSOCIATED_WITH, SAME_AS |

本体定义位于 `configs/ontology/default.yaml`，用户可通过 `configs/ontology/custom.yaml` 扩展。

## 核心组件

### 1. 记忆提取管道（两阶段）

- **Stage 1 — MemoryExtractor** (`src/extractors/memory_extractor.py`)：单次 LLM 调用提取实体、关系和事实，受 Ontology 约束
- **Stage 2 — Decision Extractor** (`src/extractors/simple_llm_extractor.py`)：基于实体上下文提取决策，输出带 evidence 引用的 `DecisionNode`
- 支持 `decision_kind` 类型过滤（choice / execution_commitment / policy_constraint / suggestion / status / discussion 等），过滤非决策输出

### 2. Pipeline Engine（`src/core/engine.py`）

- 接收 mutation（决策变化），执行去重（LLM dedup）、合并、冲突检测
- 支持实时推送（Card Push / MCP Bridge）

### 3. Neo4j 图存储（`src/storage/neo4j_client.py`）

- **节点类型**: Entity, Decision, Episode, Document, Topic
- **关系类型**: MENTIONS, BELONGS_TO, REFERENCES, RELATES, SUPERSEDES, DEPENDS_ON, CONFLICTS_WITH, REFINES, OBJECTION
- 实体去重通过 `MERGE` 和唯一 name 约束实现
- 实体→决策检索：`(Entity)←[:MENTIONS]-(Episode)-[:REFERENCES]->(Decision)`

### 4. 层次化检索（`src/graph/retrieval.py`）

- **3 路信号 RRF 融合**: Entity Graph（Neo4j 遍历）+ 向量相似度（Embedding）+ 稀疏检索（BM25）
- 可选 Cohere/Dense reranker 精排
- 结果按 topic 分组输出

### 5. 文档/项目检测与文件桥接（`src/detect/`）

- 监听到文件变更时，自动触发 MemoryExtractor 提取实体
- 支持文档→实体→决策的跨模态关联

### 6. 评估框架

- 三态 adjudicator（match_gt / valid_extra / invalid），区分"未命中 GT"和"有效但未标注"
- 70 chat 全量消融实验，Phase 3 后 F1 从 0.566 提升至 0.755（+0.189）
- A/B 测试脚本：`experiments/ablation/run_ablation.py`、`experiments/production_ablation/`

## 快速开始

```bash
# 安装
pip install -e .

# 运行测试
pytest tests/

# 消融实验
uv run python experiments/ablation/run_ablation.py --mode ablation --sample 3

# 生产路径评估
uv run python experiments/production_ablation/run.py --sample 3 --adjudicate
```

## 依赖

- **LLM 提供方**: OpenAI / DeepSeek / Anthropic
- **图数据库**: Neo4j (v5.28+)
- **增量处理**: CocoIndex (memoization)
- **向量嵌入**: OpenAI Embeddings / Qwen Embedding
- **观测**: Langfuse