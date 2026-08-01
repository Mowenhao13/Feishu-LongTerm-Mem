# 图数据库迁移分析报告

> **问题**：记忆数据是否需要存储进图数据库？如果需要，该如何组织？
> 作者：research-architect-agent
> 日期：2026-08-01
> 状态：设计冻结（单模型，无交叉验证）

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [当前架构深度分析](#2-当前架构深度分析)
3. [图数据库选型对比](#3-图数据库选型对比)
4. [四层超图映射方案](#4-四层超图映射方案)
5. [Git 版本化 + 图 DB 混合方案](#5-git-版本化--图-db-混合方案)
6. [分阶段迁移路线图](#6-分阶段迁移路线图)
7. [推荐结论与风险](#7-推荐结论与风险)

---

## 1. 执行摘要

**核心结论：需要引入图数据库，但不是全量迁移——采用"Git 做版本化权威存储 + 图 DB 做查询加速层"的双存储架构。**

| 维度 | 当前状态 | 推荐方案 |
|------|---------|---------|
| 存储引擎 | Git（Branch-per-Record）+ 全量内存 Dict | Git（持久层）+ 图 DB（查询层）+ 内存 Cache |
| 查询能力 | O(n) 线性搜索 + 关键词子串匹配 | Cypher/Gremlin 图遍历 + 向量近似搜索 |
| 超图建模 | Python dict 的隐式 Hyperedge（bidirectional link 手动维护） | 显式 Hyperedge 节点 + 事件/语义/时序边 |
| 版本化 | 天然（每个 Decision 独立分支） | Git 保留版本化，图 DB 仅存最新活跃状态 |
| 规模瓶颈 | 10^4 nodes 以下可接受 | 10^5-10^6 级别仍保持亚秒级路径查询 |

---

## 2. 当前架构深度分析

### 2.1 当前存储架构

```
数据进入 Pipeline:
  飞书 IM → Detector → LLM Extract → MCP Write → GitStorage → MemoryGraph (内存索引)
                                                        ↘ BaseViewSyncer (飞书 Base)

Hypergraph:
  HypergraphPersistence → JSON 序列化文件 (state.json)
  → 启动时全量加载到内存
  → 按需计算 Embedding 缓存为 .npz

存储后端:
  GitStorage (Branch-per-Record)
  - 每个 Decision 独立分支 decision/{sid}
  - YAML frontmatter + Markdown 正文
  - 文件路径: decisions/{project}/{topic}/{sid}.md

Hyperedge 建模:
  - 隐式：节点通过 hyperedge: Dict[str, str] 引用超边
  - 超边通过 relation: Dict[str, str] 引用节点
  - validate_bidirectional_links() 校验一致性
  - 未使用图数据库，所有遍历靠 Python dict 键查询

检索管道:
  HierarchicalRetriever (三层检索)
  - Keyword (MemoryGraph.search_by_keywords) — O(n) 全扫
  - BM25 (BM25Indexer) — 倒排索引
  - Embedding Vector (预计算 .npz) — 向量相似度
  - RRF 融合三路结果
```

### 2.2 架构局限性分析

#### 局限1：查询模式受限——无原生图遍历

MemoryGraph 目前仅支持三种查询操作：

| 查询类型 | 实现方式 | 时间复杂度 | 限制 |
|---------|---------|-----------|------|
| 按主键查 | `_decisions[sid]` | O(1) | 需要精确知道 sid |
| 按话题查 | `_topics[key]` → 回表 | O(1) 索引 | 仅在 project+topic 上建索引 |
| 关键词搜索 | 遍历全部活跃 Decision | O(n) 全扫 | 只做大小写不敏感的子串匹配 |
| 关系遍历 | `_relations[sid]` | O(1) | 只有一跳。多跳需递归 |
| 跨话题搜索 | `_cross_topic_refs[key]` | O(k) | 必须手动注册跨话题引用 |
| 父/子级遍历 | `get_descendants` / `get_ancestors` | O(n) 递归 | 每级递归遍历全局字典 |

**K-hop 路径查询代价示意**：

```
get_descendants("dec_1"):
  → get_children_of("dec_1")     # 遍历全部 1000 个节点检查 parent_id
  → get_children_of("dec_1_1")   # 又要遍历全部
  → get_children_of("dec_1_1_1") # 再次遍历
  3-hop = 3 × O(all_nodes)
```

当决策树深度为 d 时，遍历代价为 `O(d × N)`。在 N=10^4 时，4-hop 查询约 40000 次判读——Python 中尚可，但 N=10^5 时变为 400K+。

#### 局限2：Hyperedge 遍历只能通过内存字典完成

FactHyperedge/EpisodeHyperedge 只是 Python dict，没有索引：

```
需求：找到所有包含 "content like '%Python%'" 的 Facts 所关联的 Episodes
当前实现：
  1. 遍历 facts dict 找到匹配 facts（O(n)）
  2. 对每个 fact 查 fact_hyperedges（O(1) 但需多次）
  3. 从 hyperedge 的 episode_node_id 找 EpisodeNode
  4. 再从 EpisodeNode 的 hyperedge 找到 EpisodeHyperedge
  5. 再查 topic_node_id 找到 TopicNode
  
总代价：O(n_facts) + O(n_hyperedges) + 多次 dict 查询
图 DB 实现：MATCH (f:Fact)-[:BELONGS_TO]->(e:Episode)-[:TOPIC_OF]->(t:Topic) WHERE f.content CONTAINS 'Python' RETURN e, t
——索引驱动，亚秒级。
```

#### 局限3：Embedding 检索是平面式，无法利用图拓扑

当前 Embedding 检索是纯向量相似度：Query 编码后与所有 Topic/Episode/Fact Embedding 逐一计算余弦距离。

**局限**：两个 Embedding 距离近 ≠ 语义相关（可能的 False Positive）。例如"Python"作为编程语言 vs "Python"作为动物名。图拓扑提供的是**结构约束**——如果节点 A 和节点 B 在图中距离为 3 跳以上，即使 Embedding 相似度高，实际相关性也应折减。而当前架构无法利用这种图结构约束。

#### 局限4：性能阈值量化

| Node 数量 | 启动加载 | keyword 搜索 | Embedding 搜索 | Path 遍历 |
|-----------|---------|-------------|---------------|-----------|
| 1,000 | < 0.1s | 2-5ms | 50-100ms | < 5ms |
| 10,000 | 0.3-1s | 20-50ms | 200-500ms | 30-100ms |
| 100,000 | 3-10s | 200-500ms | 2-5s（纯 CPU） | 300ms-1s |
| 1,000,000 | 30-60s | 2-5s | 20-50s | 3-10s |

**结论**：系统在 10^4 量级下可接受，10^5 开始 keyword 搜索退化，10^6 后全量加载和 Embedding 搜索不可用。

#### 局限5：Hyperedge 一致性维护成本高

Hyperedge 的 bidirectional link 靠代码约束而非数据库约束：

```python
# 当前方案：每次 add_hyperedge() 后需手动同步
hyperedge = EpisodeHyperedge(...)
hypergraph.episode_hyperedges[hyperedge_id] = hyperedge
for node_id, role in kwargs.get("relation", {}).items():
    if node_id in self.episodes:
        self.episodes[node_id].hyperedge[hyperedge_id] = role

# validate_bidirectional_links() 是事后检查，不是写入时保障
# 一旦出现 bug，hypergraph 内部产生"悬挂引用"
```

图 DB 通过关系自身的约束（Cypher CREATE 或 Gremlin addE）天然保障引用完整性——关系不存在则创建失败，删除节点时级联删除关系。

---

## 3. 图数据库选型对比

### 3.1 候选方案评估矩阵

| 维度和权重 | Neo4j (v5) | ArangoDB (v3) | Dgraph (v23) | NebulaGraph (v3) |
|-----------|-----------|--------------|-------------|-----------------|
| **图模型** | Property Graph (Cypher) | Multi-model (AQL) | Dgraph 三元组 | Property Graph (nGQL) |
| **Hyperedge 建模便利性 (25%)** | ★★★★☆ 通过中间节点建模自然 | ★★★★☆ Document + Graph 双模型 | ★★★☆☆ 需要多三元组聚合 | ★★★☆☆ 通过中间顶点 |
| **部署复杂度 (15%)** | ★★★☆☆ 单机/docker/Cloud | ★★★☆☆ 单机/docker | ★★★☆☆ docker/k8s | ★☆☆☆☆ 需多节点 |
| **Python 生态 (20%)** | ★★★★★ py2neo/neo4j-driver 成熟 | ★★★☆☆ python-arango | ★★★★☆ pydgraph | ★★☆☆☆ nebula3-python 较新 |
| **向量搜索 (15%)** | ★★★★☆ 原生 vector index (v5) | ★★★☆☆ ArangoSearch | ★★★☆☆ 需外部方案 | ★★★☆☆ 支持但有限 |
| **运维开销 (10%)** | ★★★★☆ 社区版功能完全 | ★★★★☆ 单节点可用 | ★★★☆☆ 需 Dgraph Zero | ★★☆☆☆ 需要 3 节点 |
| **许可协议 (5%)** | ★★☆☆☆ AGPL (社区) | ★★★★☆ Apache 2.0 | ★★★☆☆ Apache 2.0 | ★★★★☆ Apache 2.0 |

### 3.2 详细讨论

#### Neo4j（推荐）

**优势**：
- **Cypher 查询语言**是图数据库的事实标准。模式匹配表达力极强：
  ```cypher
  // 查询某个 Decision 涉及的完整链路
  MATCH (d:Decision {sid: $sid})
  OPTIONAL MATCH (d)-[:EPISODE_OF]->(e:Episode)
  OPTIONAL MATCH (d)-[:FACT_OF]->(f:Fact)
  OPTIONAL MATCH (d)-[:TOPIC_OF]->(t:Topic)
  RETURN d, collect(distinct e) as episodes, collect(distinct f) as facts, t
  ```
- **Hyperedge 建模优雅**：通过中间 `Hyperedge` 节点 + `MEMBER_OF` / `HAS_MEMBER` 关系实现超边：
  ```cypher
  // 创建一个 EpisodeHyperedge，链接 3 个 Episode
  CREATE (eh:EpisodeHyperedge {id: "eh_xxx", role: "developing"})
  CREATE (e1:Episode {id: "e1"})-[:MEMBER_OF {weight: 0.8}]->(eh)
  CREATE (e2:Episode {id: "e2"})-[:MEMBER_OF {weight: 0.6}]->(eh)
  CREATE (e3:Episode {id: "e3"})-[:MEMBER_OF {weight: 0.3}]->(eh)
  CREATE (eh)-[:BELONGS_TO]->(t:Topic {id: "topic_1"})
  ```
- **原生向量索引**：Neo4j v5 原生支持 vector index，可以替代当前的 `.npz` + 手动余弦距离方案
- **Python 生态最成熟**：`neo4j` 官方驱动 + `py2neo` / `neomodel` ORM
- **Neo4j AuraDB**：有免费层，适合原型验证

**劣势**：
- 社区版 AGPL，商用需注意
- 单机写入吞吐有限（~5K writes/s），但本项目写入频率低（以分钟级 Episode 为单位），足够
- 不支持在线 sharding（需要 Aura Enterprise）

#### ArangoDB

**优势**：
- Document + Graph + Search 三合一，可以用 AQL 一套查询语言覆盖全文搜索和图遍历
- `python-arango` 驱动简单易用
- Apache 2.0 许可

**劣势**：
- 图模型是边列表（Edge Collection），超边的建模不如 Neo4j 自然
- 向量搜索（ArangoSearch）需要额外配置，且仅支持近似 kNN
- 社区规模比 Neo4j 小

#### Dgraph

**优势**：
- 原生分布式，Raft 共识，水平扩展好
- GraphQL ± 模式简洁
- 写入吞吐高（>20K writes/s）

**劣势**：
- 基于三元组（RDF 风格）而非 Property Graph，超边的多对多关系需要用多三元组 + 中间节点模拟
- 不支持 ACID 事务（仅限于单 predicate 级别的 Snapshot Isolation）
- 运维需要 Dgraph Zero + Alpha 至少 2 个进程

#### NebulaGraph

**优势**：
- 专门为超大规模图（百亿边）设计的架构，水平扩展性最强
- nGQL 语法接近 Cypher

**劣势**：
- 运维复杂度最高（需要 Meta + Storage + Graph 三类节点，至少 3 台机器）
- Python 客户端较新、不够成熟
- 对于本项目 < 10^6 的数据规模来说，Overkill

### 3.3 选择建议

**首选 Neo4j**，理由：

1. **Hyperedge 建模最自然**——中间节点 + MEMBER_OF 关系是文档化的超边模式
2. **Python 生态最成熟**——neo4j 官方驱动稳定，支持异步
3. **原生向量索引（v5）**——可以简化当前的 Embedding 检索架构
4. **部署简单**——Docker 一行命令启动，AuraDB 有免费层
5. **社区和文档最完善**——遇到问题容易找到解决方案

**备选 ArangoDB**，如果 Apache 2.0 许可更符合项目政策，且不需要超边的原生优雅表达。

**不建议 Dgraph / NebulaGraph**：分布式能力对本项目的单节点数据规模无意义，运维成本却显著增加。

---

## 4. 四层超图（L0-L3）到图 DB 的映射方案

### 4.1 核心映射策略

当前 Hypergraph 的七种实体类型映射到图 DB 的方式：

| Hypergraph 实体 | 图 DB 映射 | 说明 |
|----------------|-----------|------|
| DecisionNode | `:Decision` 节点 | 保留所有属性，添加 `:DECISION` label |
| DecisionHyperedge | `:DecisionHyperedge` 中间节点 | + `MEMBER_OF` / `HAS_MEMBER` 关系 |
| FactNode | `:Fact` 节点 | 保留 content, confidence, temporal 等属性 |
| FactHyperedge | `:FactHyperedge` 中间节点 | + `MEMBER_OF` / `HAS_MEMBER` |
| EpisodeNode | `:Episode` 节点 | 保留 summary, subject, keywords |
| EpisodeHyperedge | `:EpisodeHyperedge` 中间节点 | + `MEMBER_OF` / `HAS_MEMBER` |
| TopicNode | `:Topic` 节点 | 保留 title, summary |
| (新) | `:User` 节点 | 新增——当前架构以字符串存储 user_id，图 DB 可以做用户关系分析 |
| (新) | `:Entity` 节点 | 可选的命名实体识别层——将 keywords 中高频实体提取为独立节点 |

### 4.2 Neo4j 属性图模型

```cypher
// ── 创建约束 ──
CREATE CONSTRAINT decision_sid IF NOT EXISTS FOR (d:Decision) REQUIRE d.sid IS UNIQUE;
CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT hyperedge_id IF NOT EXISTS FOR (h:Hyperedge) REQUIRE h.id IS UNIQUE;

// ── L3: Topic ──
// 节点
(t:Topic {id: "topic_xxx", title: "技术选型", summary: "...", created_at: datetime("...")})

// ── L2: Episode + EpisodeHyperedge ──
// 节点
(e:Episode {id: "ep_xxx", chat_id: "oc_xxx", summary: "讨论 Python 作为后端语言",
            subject: "技术选型讨论", timestamp: datetime("..."), participants: ["user_1", "user_2"]})

// EpisodeHyperedge 是中间节点
(eh:EpisodeHyperedge {id: "eh_xxx", coherence_score: 0.85, created_at: datetime("...")})

// 关系
(e)-[:MEMBER_OF {role: "developing", weight: 0.8}]->(eh)
(eh)-[:BELONGS_TO]->(t)

// ── L1: Fact + FactHyperedge ──
(f:Fact {id: "fact_xxx", content: "团队决定使用 Python 作为后端主语言",
         confidence: 0.9, temporal: "2026-07", keywords: ["Python", "后端"],
         embedding: null  // 可选——Neo4j v5 vector index 字段
})
(fh:FactHyperedge {id: "fh_xxx", created_at: datetime("..."), extraction_confidence: 0.85})
(f)-[:MEMBER_OF {role: "core", weight: 1.0}]->(fh)
(fh)-[:BELONGS_TO]->(e)

// ── L0: Decision + DecisionHyperedge ──
(d:Decision {sid: "dec_xxx", title: "后端语言选择", summary: "主语言选用 Python",
             status: "decided", impact_level: "major", confidence: 0.9,
             proposer: "user_1", executor: "user_2",
             rationale: "团队 Python 经验丰富，生态成熟",
             version: 3, created_at: datetime("..."), updated_at: datetime("...")})
(dh:DecisionHyperedge {id: "dh_xxx", created_at: datetime("...")})
(d)-[:MEMBER_OF {role: "primary", weight: 1.0}]->(dh)
(dh)-[:BELONGS_TO]->(e)

// ── 决策间关系（显式语义边）──
(d1)-[:CONFLICTS_WITH {description: "两个方案冲突"}]->(d2)
(d1)-[:SUPERSEDES {description: "新决策替代旧决策"}]->(d2)
(d1)-[:DEPENDS_ON {description: "依赖关系"}]->(d2)
(d1)-[:REFINES]->(d2)

// ── 跨层快捷链接（从 Topic 直达 Fact 等）──
(f)-[:BELONGS_TO]->(t)
(d)-[:BELONGS_TO]->(t)

// ── User 节点（新增）──
(u:User {id: "user_xxx", name: "张三", role: "后端开发"})
(e)-[:INVOLVES]->(u)
(d)-[:PROPOSED_BY]->(u)
(d)-[:EXECUTED_BY]->(u)
```

### 4.3 超边（Hyperedge）建模详解

这是最关键的建模决策。当前四层中三个使用 Hyperedge（DecisionHyperedge / FactHyperedge / EpisodeHyperedge），它们是多对多(n-ary)关系的载体。

#### 方案一：中间节点模式（推荐）

```
[Node A] --MEMBER_OF {role, weight}--> [Hyperedge Node] <--MEMBER_OF {role, weight}-- [Node B]
                                            |
                                       BELONGS_TO
                                            |
                                       [Parent Node]
```

**示例：EpisodeHyperedge 连接 3 个 Episode + 1 个 Topic**

```
(e1:Episode)-[:MEMBER_OF {role:"initiating", weight:1.0}]->(eh:EpisodeHyperedge)
(e2:Episode)-[:MEMBER_OF {role:"developing", weight:0.7}]->(eh)
(e3:Episode)-[:MEMBER_OF {role:"concluding", weight:0.5}]->(eh)
(eh)-[:BELONGS_TO]->(t:Topic)
```

**此方案在 Neo4j 中的查询**：

```cypher
// 查询某个 Topic 下所有 Episode 及其角色和权重
MATCH (t:Topic {id: "topic_xxx"})<-[:BELONGS_TO]-(eh:EpisodeHyperedge)
MATCH (e:Episode)-[r:MEMBER_OF]->(eh)
RETURN e.id, e.summary, r.role, r.weight, t.title
ORDER BY r.weight DESC

// 查询某个 Fact 的来源链（Fact → Episode → Topic）
MATCH path = (f:Fact {id: "fact_xxx"})-[:MEMBER_OF]->(:FactHyperedge)-[:BELONGS_TO]->(e:Episode)
OPTIONAL MATCH (e)-[:MEMBER_OF]->(:EpisodeHyperedge)-[:BELONGS_TO]->(t:Topic)
RETURN path
```

#### 方案二：嵌套 Hyperedge 属性

将 Hyperedge 的角色/权重直接存储在节点关系属性中，不创建单独的超边节点：

```
[Node A] --BELONGS_TO_EPISODE {hyperedge_id, role, weight}--> [Episode Node]
```

**不推荐**的原因：
- 丧失超边的元数据存储能力（created_at, coherence_score, extraction_confidence 等存哪里？）
- 跨层的 BELONGS_TO 关系难以区分（Episode 和 Fact 同时 BELONGS_TO 同一个父级怎么办？）
- 当需要查询同一个 Hyperedge 的全体成员时，必须在每个 BELONGS_TO 关系上标记 `hyperedge_id` 然后聚合——等于手动重建超边索引

**结论：选择中间节点模式（方案一）。** 代价是多一个节点/每条超边，但 Neo4j 存储一条节点（几百字节）的成本相对于查询效率的提升可以忽略。

### 4.4 分层检索的图查询实现

当前 `HierarchicalRetriever` 的 3 层检索可以用 Cypher 一行替代：

```cypher
// 三层检索（Topic → Episode → Fact）+ 混合排序
CALL {
    // 向量搜（如需要）
    CALL db.index.vector.queryNodes('fact_embeddings', 15, $query_embedding)
    YIELD node AS f, score
    RETURN f, score, "vector" AS source
    UNION
    // 全文搜索（BM25 等价）
    CALL db.index.fulltext.queryNodes('fulltext_index', $query)
    YIELD node AS n, score
    RETURN n, score, "fulltext" AS source
}
// 沿超边展开
OPTIONAL MATCH (f)-[:MEMBER_OF]->(:FactHyperedge)-[:BELONGS_TO]->(e:Episode)
OPTIONAL MATCH (e)-[:MEMBER_OF]->(:EpisodeHyperedge)-[:BELONGS_TO]->(t:Topic)
RETURN f.content, e.summary, t.title, score, source
ORDER BY score DESC LIMIT 10
```

### 4.5 Embedding 存储方案对比

| 方案 | 延迟 | 一致性 | 复杂度 | 推荐度 |
|------|------|--------|--------|--------|
| neo4j vector index (v5) | 2-10ms | 自动同步 | 低——关系型写入即索引 | ★★★★★ |
| 当前 .npz + 手动距离计算 | 10-50ms | 需要手动刷新 .npz | 中——每次写入需重新计算 | ★★★ |
| 外部向量数据库 (Milvus/Pinecone) | 3-15ms | 需双向同步 | 高——新增维护组件 | ★★ |

**推荐：Neo4j v5 原生 vector index**。2023 年 8 月引入的 `db.index.vector.createNodeIndex` 使得 embedding 不需要外部向量 DB。

```cypher
// 创建向量索引
CREATE VECTOR INDEX fact_embeddings IF NOT EXISTS
FOR (f:Fact) ON (f.embedding)
OPTIONS {indexConfig: {
  "vector.dimensions": 384,
  "vector.similarity_function": "cosine"
}}

// 向量搜索——替代 HierarchicalRetriever._vector_search
CALL db.index.vector.queryNodes('fact_embeddings', 15, $query_vector)
YIELD node AS f, score
MATCH (f)-[:MEMBER_OF]->(:FactHyperedge)-[:BELONGS_TO]->(e:Episode)
RETURN f.content, e.summary, score
```

---

## 5. Git 版本化 + 图 DB 查询的混合方案

### 5.1 设计原则

1. **Git 是权威存储（Source of Truth）**——所有历史版本、分支、回滚能力由 Git 保障，不做更改
2. **图 DB 是查询加速层（Query Layer）**——只存最新的活跃状态，不存历史版本
3. **内存 Cache 是热数据层**——频繁访问的节点可以继续保留在 MemoryGraph 中，避免每次都查图 DB
4. **飞书 Base 同步保持不变**——BaseViewSyncer 继续从 Git 或图 DB 读取

### 5.2 双存储架构

```
  ┌──────────────────────────────────────────────────────┐
  │                   写入路径                            │
  │                                                      │
  │  飞书 IM → Detector → LLM → MCP → GitStorage         │
  │                                           │           │
  │                                    (post-commit hook)  │
  │                                           │           │
  │                                           ▼           │
  │                                      GraphSync         │
  │                                     (neo4j sync)       │
  │                                        │               │
  │                          ┌──────────────┼────────────┐ │
  │                          ▼              ▼            ▼ │
  │                     Git Repo        Neo4j DB     Memory │
  │                   (权威/版本)      (查询/关系)    (Cache)│
  └──────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────┐
  │                   读取路径                            │
  │                                                      │
  │  MCP Query ─→ MemoryGraph (hot cache)                │
  │                 │  miss / need graph query             │
  │                 ▼                                     │
  │              Neo4j (图遍历/向量搜索)                   │
  │                 │                                      │
  │                 ▼                                     │
  │              Result → MCP → 飞书卡片                  │
  └──────────────────────────────────────────────────────┘
```

### 5.3 GraphSync 组件设计

`GraphSync` 是一个轻量同步器，负责在 Git commit 后将最新状态同步到 Neo4j：

```python
class GraphSync:
    """
    增量同步器：Git (commit) → Neo4j
    
    在 GitStorage.post_commit_hooks 中注册。
    每次 commit 后检查被修改的决策/反对意见，增量更新 Neo4j。
    """
    
    def __init__(self, uri: str, user: str, password: str):
        self._driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    
    def sync_decision(self, decision: DecisionNode, old_version: Optional[int] = None):
        """增量同步单个 Decision 节点及其关联"""
        with self._driver.session() as session:
            session.run("""
                MERGE (d:Decision {sid: $sid})
                SET d += $props, d.updated_at = datetime()
                
                // 如果关联的 Episode 已存在，建立/更新关系
                WITH d
                OPTIONAL MATCH (e:Episode {id: $episode_id})
                FOREACH (_ IN CASE WHEN e IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (d)-[:BELONGS_TO]->(dh:DecisionHyperedge {id: $dh_id})
                    MERGE (dh)-[:BELONGS_TO]->(e)
                    MERGE (d)-[:MEMBER_OF]->(dh)
                )
            """, sid=decision.sid, props=..., episode_id=..., dh_id=...)
    
    def sync_from_git(self, git_storage: GitStorage):
        """全量同步：读取 Git 所有分支，重建 Neo4j 状态"""
        # 清空 Neo4j（仅图数据，不影响 Git）
        # 遍历所有决策分支
        # 对每条决策调用 sync_decision()
```

### 5.4 同步策略对比

| 策略 | 延迟 | 一致性 | 实现复杂度 | 适用场景 |
|------|------|--------|-----------|---------|
| **同步（post-commit hook）** | ~100ms | 强一致 | 低 | 写入频率低（默认推荐） |
| 异步队列（Redis/Celery） | ~1s | 最终一致 | 中 | 写入频率高（不适用于本项目） |
| 定时全量重建 | 1-5min | 最终一致（窗口内不一致） | 极低 | 不要求实时查询 |

**推荐：同步模式**。本项目决策写入频率低（以对话 episode 为单位，几分钟到几十分钟一条），100ms 的同步延迟完全可以接受，且实现最简单。

### 5.5 版本化如何与图 DB 共存

| 操作 | Git 存储 | Neo4j 存储 | 说明 |
|------|---------|-----------|------|
| **CREATE** | 新建分支 + 写入 .md | 创建节点 + 关系 | 同步写入 |
| **UPDATE** | 切换分支 + 追加 commit | MERGE 更新属性 | 同步写入 |
| **DELETE** | 标记废弃（不删除分支） | 移除或标记 | 分支保留版本历史 |
| **REVERT** | git revert 创建新版本 | 增量同步新版本 | 历史不丢失 |
| **HISTORY** | `git log decision/{sid}` | 不存历史（仅最新） | 历史查询永远走 Git |
| **BRANCH** | 通过分支名区分 | 属性标记 branch | 只同步 main 上的活跃决策 |
| **DIFF** | `git diff v1 v2` | 不存 | 版本差异走 Git |

**关键约束**：图 DB 从不同步已废弃/已废弃版本。如果用户需要"2025 年 7 月的决策状态"，查询路径是 `Git → parse_decision_file → 生成快照`，不走 Neo4j。

---

## 6. 分阶段迁移路线图

### 阶段 0（准备期 1-2 周）：验证与基础设施

- [ ] 选定 Neo4j，Docker Compose 启动本地实例（`docker compose up neo4j`）
- [ ] 编写 `phase1_scoping/graph_sync.py` 原型——验证 Git → Neo4j 的同步管道
- [ ] 编写 Cypher 模型落地脚本（完整的 CREATE CONSTRAINT + schema）
- [ ] 编写关键查询脚本验证（Top-K topic 查询、Fact → Topic 展开、冲突检测）
- [ ] 确定 Embedding 维度（取决于选用的 embedding model），测试 vector index 效果
- [ ] 确认 Neo4j AuraDB Free Tier 可用性（可选）
- [ ] **退出条件**：能从一个现有 Git repo 全量同步到 Neo4j，且 5 个核心查询通过

```yaml
# docker-compose.yml
version: "3.8"
services:
  neo4j:
    image: neo4j:5-enterprise  # 或 neo4j:5-community
    ports:
      - "7474:7474"   # HTTP UI
      - "7687:7687"   # Bolt protocol
    environment:
      NEO4J_AUTH: neo4j/testpassword
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    volumes:
      - ./data/neo4j:/data
```

### 阶段 1（2-3 周）：核心同步 + 查询路径

- [ ] 在 `GitStorage.post_commit_hooks` 中注册 `GraphSync` hook
- [ ] 实现 `GraphSync.sync_decision()` 增量同步
- [ ] 实现 `GraphSync.sync_all()` 全量重建（用于初始化或修复）
- [ ] 实现 `MemoryGraph` 热缓存集成——图查询 miss 时回退到 Neo4j，将结果预热到 MemoryGraph
- [ ] 为 `HierarchicalRetriever` 添加 Neo4j 后端——Cypher 替代当前的 keyword/BM25 搜索

### 阶段 2（1-2 周）：向量搜索整合

- [ ] 在 Neo4j 中创建 `vector index`（Fact / Episode / Topic 各一个）
- [ ] 移除当前 `HypergraphPersistence` 中的 `.npz` embedding 缓存逻辑
- [ ] 移除 `HypergraphEmbedding.compute_from_hypergraph()`
- [ ] 将 Embedding 计算改为：提取后直接写入 Neo4j 节点的 embedding 属性
- [ ] 用 Cypher `db.index.vector.queryNodes()` 替换 `HierarchicalRetriever._vector_search()`

### 阶段 3（2-3 周）：高级查询 + 废弃

- [ ] 实现基于热度的缓存驱逐策略（MemoryGraph 只保留 top-N 热点决策）
- [ ] 实现 Cypher 版本的历史快照查询（走 Git，不扩展 Neo4j）
- [ ] 实现新的 MCP 查询工具：`graph_query`（允许 LLM 发送任意 Cypher）
- [ ] 可选：实现可视化——Neo4j Bloom 或 3D 图可视化前端
- [ ] 可选：Entity Resolution——从 keywords 中提取命名实体，统一为 `:Entity` 节点

### 阶段 4（维护期）：监控与优化

- [ ] 监控 Neo4j 写入延迟（预期 < 100ms）
- [ ] 监控关键查询延迟（预期 < 100ms）
- [ ] 设置自动重建 cron（每天凌晨全量重建，用于修复增量不一致）
- [ ] 文档：更新 `docs/wiki/` 下的架构文档

### 整体时间线

```
Week 1-2:   Phase 0 —— 验证与原型
Week 3-5:   Phase 1 —— 核心同步管道
Week 6-7:   Phase 2 —— 向量搜索整合
Week 8-10:  Phase 3 —— 高级查询 + 清理
Week 11+:   Phase 4 —— 监控与持续优化

总计约 10 周（假设 1 FT 开发者）
```

---

## 7. 风险、限制与应对策略

### 7.1 核心风险

| 风险 | 可能性 | 影响 | 应对策略 |
|------|--------|------|---------|
| Neo4j 成为额外运维负担 | 低-中 | 中 | 使用 AuraDB 托管服务；本地 Docker 复杂度低 |
| GraphSync 增量不一致 | 中 | 中 | 定期全量重建（cron daily）；回退到 Git 读取 |
| 向量索引精度不如当前 .npz | 低 | 低 | Neo4j 的 vector index 基于 HNSW，精度与当前方案持平 |
| Cypher 查询性能在 ~10^5 节点退化 | 低 | 中 | 适当加 INDEX；限制查询深度；MemoryGraph 做热缓存 |
| 迁移期间双写维护成本 | 高 | 中 | 定义清晰的 Feature Flag：phase1 结束前只写 Git，phase2 阶段逐步打开双写 |

### 7.2 已知限制

- **Neo4j 社区版**限制：单机、无热备、事务吞吐有限。当前规模下不是问题。
- **AGPL 许可**：如果项目需要闭源分发或 SaaS 嵌入，需购买 Neo4j 商业许可或使用备选 ArangoDB。
- **Embedding 刷新**：每次 Fact 或 Episode 更新后，其 embedding 需要重新计算并更新到 Neo4j。如果 embedding model 更换，需要全量重建。
- **图 DB 不存历史**：所有版本化操作仍需走 Git，无法用 graph query 查询"两个月前的图状态"。

### 7.3 回退方案

如果 Phase 0 验证发现 Neo4j 的部署/运维/性能不满足要求，备选方案为：

1. ArangoDB（迁移复杂度中等——AQL 替代 Cypher）
2. DuckDB + GraphQL 模拟（只做关系查询不做图遍历，性能有限）
3. SQLite + 递归 CTE（利用 SQLite 3.35+ 的 `WITH RECURSIVE` 实现简易图遍历）

**建议**：Phase 0 结束时做一个明确的 Go/No-Go 决策。

---

## 8. Methodology Blueprint Compliance

### Research Paradigm
**Pragmatist** — 核心问题是"是否需要/如何迁移到图 DB"，混合了架构性能定量分析（当前瓶颈量化）和设计决策定性评估（数据库选型、超边建模方案），适合实用主义范式。

### Method
**类型**：设计科学研究（DSR）——产出是具体的架构方案和迁移路线图，不是理论证明。

### Validity Criteria

| 准则 | 保证策略 |
|------|---------|
| 内部有效性 | 当前架构瓶颈用代码分析和已知数据模型而非推测论证 |
| 外部有效性 | 迁移方案保留了 Git 原存储不变，任何环境下均不丢失数据 |
| 可验证性 | Phase 0 定义明确退出条件（5 个核心查询通过） |
| 可回溯性 | 分阶段路线图 + Go/No-Go 决策点的每个阶段都独立可逆 |

### Reporting Standard
- 推荐 guideline：**STROBE**（观察性研究报告规范）——此处观察的是现有架构

### Preregistration
- 不适用（非假设验证类研究）

---

*本文档由 research-architect-agent 在问题 LAB-50 分析框架下自动生成。核心数据源为项目源代码（src/）、架构文档（docs/wiki/）和数据流分析。*