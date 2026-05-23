# Feishu-Mem — 飞书长程协作记忆系统

## 概述

Feishu-Mem 是一个面向飞书（Lark）团队的**长程项目协作记忆系统**。它实时监听飞书群聊、文档、会议等场景，自动提取团队决策、构建超图记忆网络，并通过 Git 版本化存储持久化。系统提供决策冲突检测、热点值管理、主动推送卡片、MCP 工具查询等能力，帮助团队追踪历史决策、避免重复讨论、减少信息流失。

### 核心能力

- **决策提取** — 从 IM 对话中自动识别并提取结构化决策（技术选型、任务分配、参数锁定等）
- **超图记忆** — 5 维索引（决策/议题/关系/跨议题引用/项目）的内存级运行时图
- **8 种决策生命周期 Mutation** — CREATE / UPDATE / STATUS_CHANGE / CONFLICT_MERGE / CONFLICT_KEEP_BOTH / OBJECTION / DEPRECATE / REVERT
- **Git 版本化存储** — 每个决策独立 Git 分支，全文 Markdown + YAML frontmatter 持久化
- **冲突检测** — 基于关系和关键词的运行时冲突识别
- **热点值管理** — 推送递增 + 时间衰减，自动识别遗忘决策
- **决策卡片推送** — 3 通道（飞书 API / 终端 / macOS 通知）× 4 种触发（冲突/更新/热点值/定时）
- **MCP 协议** — 支持 AI Agent（Claude Desktop 等）通过 MCP 工具搜索、查询、推送决策
- **飞书原生集成** — 群聊消息监听、API 调用、事件驱动

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          外部接入层 (MCP / Lark API)                         │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │  Claude Desktop│  │  IM 群聊事件  │  │  飞书开放 API (发送/读取消息)     │ │
│  │  (MCP Client)  │  │  (WS长连接)   │  │  LarkIMClient                  │ │
│  └───────┬───────┘  └──────┬───────┘  └────────────┬─────────────────────┘ │
└──────────┼─────────────────┼────────────────────────┼───────────────────────┘
           │                 │                        │
┌──────────┼─────────────────┼────────────────────────┼───────────────────────┐
│          ▼                 ▼                        ▼                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        信号检测层 (Signal)                            │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐ │  │
│  │  │Lexical   │→│  SignalEmitter│→│Detector  │→│  DecisionLevel    │ │  │
│  │  │Analyzer  │  │  (打分聚合)   │  │Engine    │  │  HIGH/MEDIUM/LOW  │ │  │
│  │  └──────────┘  └──────────────┘  └──────────┘  └──────────────────┘ │  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                             │                                              │
│  ┌──────────────────────────▼───────────────────────────────────────────┐  │
│  │                     LLM 决策提取层                                    │  │
│  │  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐  │  │
│  │  │LLMClient    │→│DecisionExtractor│→│  DecisionNode (结构化)    │  │  │
│  │  │(DeepSeek/   │  │(Prompt-driven) │  │  sid/topic/status/impact │  │  │
│  │  │ OpenAI api) │  └───────────────┘  │  authority/relations/...  │  │  │
│  │  └──────────────┘                    └──────────────────────────┘  │  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                             │                                              │
│  ┌──────────────────────────▼───────────────────────────────────────────┐  │
│  │                      核心引擎层 (Core Engine)                         │  │
│  │                                                                      │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │  PipelineEngine (8 种 Mutation)                              │   │  │
│  │  │  ┌────────┐ ┌────────┐ ┌───────────┐ ┌───────┐ ┌──────────┐ │   │  │
│  │  │  │ CREATE │ │ UPDATE │ │STATUS_CHG │ │MERGE  │ │KEEP_BOTH │ │   │  │
│  │  │  ├────────┤ ├────────┤ ├───────────┤ ├───────┤ ├──────────┤ │   │  │
│  │  │  │OBJECTION│ │DEPRECATE│ │ REVERT    │ │       │ │          │ │   │  │
│  │  │  └────────┘ └────────┘ └───────────┘ └───────┘ └──────────┘ │   │  │
│  │  └──────────────────────────┬───────────────────────────────────┘   │  │
│  │                             │                                       │  │
│  │  ┌──────────────────────────▼───────────────────────────────────┐   │  │
│  │  │  MemoryEngine (长驻后台 asyncio 进程)                         │   │  │
│  │  │  - 检测器循环 │ 决策提取 │ Mutation 应用 │ 存储同步 │ 推送触发 │   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                             │                                              │
│  ┌──────────┬───────────────┼───────────────┬─────────────────┬──────────┐ │
│  │          ▼               ▼               ▼                 ▼          │ │
│  │  ┌──────────┐   ┌────────────┐  ┌────────────┐  ┌─────────────────┐  │ │
│  │  │MemoryGraph│  │SnapshotMgr │  │ PushEngine │  │ 卡片渲染器       │  │ │
│  │  │(5 索引)  │  │(检测快照)   │  │(4 触发)    │  │ CardRenderer    │  │ │
│  │  └──────────┘   └────────────┘  │ 3 通道     │  │ (Lark JSON + MD)│  │ │
│  │                                 └────────────┘  └─────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                             │                                              │
│  ┌──────────────────────────▼───────────────────────────────────────────┐  │
│  │                        存储层 (Storage)                               │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │  GitStorage (文件系统 + Git 版本控制)                          │   │  │
│  │  │  data/decisions/{project}/{topic}/{sid}.md                   │   │  │
│  │  │  每个决策 → 独立 Git 分支 (decision/{sid})                    │   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 模块详解

### 1. 超图记忆层 (`src/graph/`)

运行时内存级决策图，提供**5 维索引**加速检索：

| 索引 | 类型 | 说明 |
|------|------|------|
| `_decisions` | `Dict[str, DecisionNode]` | SDR ID → 决策节点 |
| `_topics` | `Dict[str, List[str]]` | 议题 → SDR ID 列表 |
| `_relations` | `Dict[str, List[Relation]]` | SDR ID → 关联关系 |
| `_cross_topic_refs` | `Dict[str, List[str]]` | 跨议题引用映射 |
| `_projects` | `Dict[str, List[str]]` | 项目 → SDR ID 列表 |

- **MemoryGraph** — 核心内存图，支持 upsert / query / search / conflict detection / hot score / dirty tracking
- **HypergraphBuilder** — 超图构建器，从内容/对话/决策列表构建超图结构
- **HierarchicalRetriever** — 3 层层次检索（Topic → Fact → Episode）+ RRF 融合
- **SnapshotManager** — 检测器状态快照，JSON 格式持久化到 `{STORAGE_PATH}/snapshots/`
- **BM25Indexer** — BM25 索引骨架（等待 Embedding 模型接入）

### 2. 决策管道引擎 (`src/core/`)

**PipelineEngine** — 决策变更的原子化执行单元。接收 `DecisionMutation` 并按类型分发到对应处理器，保证 MemoryGraph + GitStorage 的**双写一致性**。

8 种 Mutation：

| MutationType | 说明 | 处理器 |
|---|---|---|
| `CREATE` | 新建决策 | `_apply_create` |
| `UPDATE` | 更新决策 | `_apply_update` |
| `STATUS_CHANGE` | 状态变更 | `_apply_status_change` |
| `CONFLICT_MERGE` | 合并冲突 | `_apply_conflict_merge` |
| `CONFLICT_KEEP_BOTH` | 保留双方冲突 | `_apply_conflict_keep_both` |
| `OBJECTION` | 添加异议 | `_apply_objection` |
| `DEPRECATE` | 废弃决策 | `_apply_deprecate` |
| `REVERT` | 回退版本 | `_apply_revert` |

**MemoryEngine** — 长驻后台的 asyncio 进程，完整生命周期：

```
initialize()
  ├── GitStorage 初始化
  ├── PipelineEngine 初始化
  ├── 从 Git 加载已有决策到 MemoryGraph
  ├── 快照管理器初始化
  └── PushEngine 初始化
start()
  ├── 检测器循环（持续监听信号）
  ├── 存储同步循环（定期刷脏数据）
  └── 推送调度器（热点值扫描 + 定时摘要）
stop()
  └── 清理 async 任务 → 推送停止 → 脏数据同步
```

### 3. 信号检测 (`src/signal/`)

基于**词法分析 + 信号聚合**的决策识别引擎，不依赖 LLM 即可快速筛选潜在决策内容。

- **LexicalAnalyzer** — 三权重关键词库（高/中/低），匹配决策信号片段
- **SignalEmitter** — 聚合原始信号，结合上下文产生 `SignalDetail`
- **Detector** — 决策检测器，输出 `DetectionResult`（含 `DecisionLevel` 分数）
- **ContextProvider** — 提供对话上下文、历史记录等辅助检测
- **Emitter** — 信号事件发射器，支持 async 事件流

**决策检测分数维度**：

| 分数段 | 级别 | 含义 |
|--------|------|------|
| ≥ 0.8 | HIGH | 明确决策（"决定了"、"最终决定"） |
| ≥ 0.5 | MEDIUM | 可能决策（"建议"、"选型"） |
| ≥ 0.3 | LOW | 弱信号（纯讨论） |
| < 0.3 | NONE | 非决策（闲聊） |

### 4. 决策节点模型 (`src/node/`)

- **DecisionNode** — Pydantic BaseModel，含 sid / topic_id / summary / full_text / status / impact_level / confidence / authority / assignee / relations / objections / access_stats 等
- **DecisionStatus** — 8 种状态：`PENDING → DECIDED → IN_PROGRESS → COMPLETED / SUPERSEDED / REJECTED / DEPRECATED / SHELVED`
- **ImpactLevel** — 4 级影响：`ADVISORY → MINOR → MAJOR → CRITICAL`
- **Relation** — 6 种关系类型：`DEPENDS_ON / SUPERSEDES / REFINES / CONFLICTS_WITH / RELATES_TO / OBJECTION`
- **AccessStats** — 热点值追踪：`hot_score / access_count / last_accessed / last_calculated`

### 5. 存储层 (`src/storage/`)

基于 Git 版本控制的文件系统存储：

```
data/
└── decisions/
    └── <project>/
        └── <topic>/
            └── <sid>.md     # 每个决策一个 Markdown 文件
```

- **GitStorage** — 高层 CRUD API（write_decision / read_decision / list_decisions / list_topics / list_branches / search_content）
- **GitFormat** — Markdown + YAML frontmatter 序列化/反序列化
- **GitCLI** — 底层 git 命令封装（init / add / commit / branch / checkout / log / grep）
- **分支策略**：每个决策写入独立 `decision/{sid}` 分支，主分支（main）仅包含索引和汇总

### 6. 决策卡片推送 (`src/card/`)

**PushEngine** — 推送引擎，3 通道 × 4 触发：

**通道**（按配置优先级）：
1. **飞书 API** — `LarkIMClient.send_message()`，发送交互式 Lark 卡片（异常自动降级到终端）
2. **终端输出** — 格式化 Markdown 文本 stdout 输出
3. **macOS osascript** — 系统通知（`display notification`）

**触发时机**：
1. **冲突检测** — MemoryEngine 检测到冲突时自动推送冲突解决卡片
2. **决策更新** — CREATE / UPDATE / STATUS_CHANGE 时推送决策卡片
3. **热点值过低** — 定期扫描，热点值低于阈值时推送遗忘提醒
4. **定时摘要** — 每日 08:00 / 每周六 21:00 推送决策摘要

**热点值机制**：
- 每次推送 → 热点值 +10（上限 100）
- 每次扫描 → 热点值 ×0.95（时间衰减）
- 热点值 < 20 → `FORGOTTEN` 分类，触发低热点推送

### 7. 外部 API 适配器 (`src/adapter/`)

飞书原生 API 集成：
- **LarkIMClient** — 完整消息 CRUD（发送/回复/编辑/转发/撤回），支持 text / post / card / image / file 等多种消息类型
- **NoiseFilter** — 消息噪音过滤（emoji / 链接 / 噪音话题检测）
- **MessageBatcher** — 对话分批聚合（按时间和关键词重叠分组）
- **ContextMessage** — 上下文消息提取
- **LarkDocClient** — 飞书文档读取

### 8. MCP 服务器 (`src/mcp_server/`)

基于 `FastMCP` 协议实现，供 AI Agent（如 Claude Desktop）通过标准 MCP 工具调用：

| 工具 | 说明 |
|------|------|
| `search` | 关键词搜索决策记录 |
| `decision` | 获取单个决策详情，支持 `push` 参数被动推送卡片 |
| `extract_decision` | 从文本中智能提取决策 |
| `classify_topic` | 决策议题分类 |
| `detect_crosstopic` | 跨议题影响检测 |
| `check_conflict` | 两个决策间的冲突评估 |
| `list_topics` | 列出所有议题 |
| `stats` | 系统统计信息 |
| `timeline` | 决策历史时间线 |

### 9. LLM 集成 (`src/llm/`)

- **LLMClient** — 统一 LLM API 客户端（支持 chat / chat_json / streaming）
- **TokenTracker** — Token 消耗追踪
- **CircuitBreaker** — 熔断保护（基于 pybreaker）
- **Guardrails** — 输出格式护栏
- **Recovery** — 自动重试（基于 tenacity）

### 10. 评估系统 (`src/eval/`)

- **Evaluator** — 端到端评估框架，支持 12 个场景的数据集
- **评估维度**：detection / content / status / conflict / impact_level / proposer / executor
- **决策提取准确率**：整体 92.1%（基于 DeepSeek v4 模型）

## 配置

### 环境变量（`.env`）

```env
# ===== LLM 配置 =====
BASE_URL=https://api.deepseek.com
API_KEY=sk-xxxxx
MODEL_NAME=deepseek-chat

# ===== 飞书应用配置 =====
LARK_APP_ID=cli_xxxxxxxx
LARK_APP_SECRET=xxxxx
GROUP_CHAT_IDS=oc_xxxxx    # 监听的群聊 ID
CARD_CHAT_IDS=oc_xxxxx     # 推送目标群聊 ID

# ===== 存储路径 =====
STORAGE_PATH=data

# ===== Embedding / Reranker（可选）=====
EMBEDDING_BASE_URL=http://0.0.0.0:11000/v1/embeddings
EMBEDDING_MODEL_NAME=Qwen3-Embedding-4B
RERANKER_BASE_URL=http://0.0.0.0:11000
RERANKER_MODEL_NAME=Qwen3-Reranker-4B

# ===== 推送配置 =====
PUSH_FEISHU_ENABLED=false      # 飞书 API 推送（配额保护）
PUSH_TERMINAL_ENABLED=true     # 终端输出
PUSH_OSASCRIPT_ENABLED=false   # macOS 通知
PUSH_TRIGGER_CONFLICT=true     # 冲突触发
PUSH_TRIGGER_UPDATE=true       # 更新触发
PUSH_TRIGGER_HOT_SCORE=true    # 低热点值触发
PUSH_HOT_SCORE_THRESHOLD=20.0  # 热点值低阈值
PUSH_DAILY_SUMMARY=true        # 每日摘要
PUSH_DAILY_TIME=08:00          # 摘要时间
PUSH_WEEKLY_DAY=6              # 每周六摘要
PUSH_WEEKLY_TIME=21:00
PUSH_HOT_SCORE_INCREMENT=10.0  # 推送递增
PUSH_HOT_SCORE_DECAY=0.95      # 时间衰减率
```

## 快速开始

### 安装

```bash
git clone https://github.com/Mowenhao13/Feishu-LongTerm-Mem
cd feishu-mem
uv sync
cp .env.example .env   # 编辑配置
```

### 配置飞书应用

1. 在[飞书开放平台](https://open.feishu.cn)创建应用
2. 开启 `im:message` 权限
3. 获取 App ID / App Secret → 填入 `.env`
4. 将机器人加入目标群聊

### 运行

```bash
# 运行评估测试（无需飞书 API）
uv run python scripts/eval_nostorage.py

# E2E 冲突决策测试（MemoryGraph + PipelineEngine + GitStorage 全链路）
uv run python scripts/test_conflict_graph.py

# 启动 MCP 服务器
uv run python -c "from src.mcp_server.server import run_server; run_server()"

# 启动完整引擎（需要飞书配置）
uv run python -c "from src.core.engine import MemoryEngine; import asyncio; e=MemoryEngine(); e.initialize(); asyncio.run(e.start())"

# 运行测试
uv run pytest tests/ -v
```

## 评估结果

### 决策提取准确率

| 场景 | 准确率 |
|------|--------|
| 技术选型 (01) | 88.3% |
| 任务分配 (02) | 94.4% |
| 参数锁定 (03) | 88.3% |
| 冲突决策 (05) | 97.1% |
| **整体** | **92.1%** |

### 维度准确率

| 维度 | 准确率 | 说明 |
|------|--------|------|
| detection | 100% | 是否做出决策 |
| content | 95.0% | 决策内容提取 |
| status | 93.3% | 状态判断 |
| conflict | 97.1% | 冲突检测 |
| impact_level | 86.7% | 影响级别 |
| proposer | 78.6% | 提议者识别 |
| executor | 93.3% | 执行者识别 |

## 项目结构

```
src/
├── adapter/           # 飞书 API 适配器（IM / 文档 / 消息处理）
├── card/              # 决策卡片渲染 + 推送引擎
├── core/              # 核心引擎（MemoryEngine / PipelineEngine）
├── eval/              # 端到端评估框架
├── extractors/        # 决策 / 事实 / 对话提取器
├── graph/             # 超图记忆（MemoryGraph / Builder / Retrieval / Snapshot）
├── llm/               # LLM 客户端（支持降级、熔断、重试）
├── mcp_server/        # MCP 协议服务器
├── model/             # Embedding / Reranker 模型接入
├── node/              # 决策节点模型（DecisionNode / Relation / Objection）
├── prompts/           # 决策提取 / 分类 / 冲突检测 Prompt 模板
├── signal/            # 信号检测引擎（词法分析 + 信号聚合）
├── storage/           # Git 版本化存储后端
└── utils/             # 工具库（日志 / 时间 / Markdown 分片）

ref/                   # Go 版参考实现（架构参考）
├── card/              # 卡片渲染（Go 原版）
├── core/              # Pipeline / MemoryGraph（Go 原版）
├── decision/          # 决策节点（Go 原版）
├── git/               # Git 存储（Go 原版）
├── lark-adapter/      # 飞书适配器（Go 原版）
├── llm/               # LLM 集成（Go 原版）
├── main/              # Stage1-6 处理流程（Python）
└── signal/            # 检测器（Go 原版）

scripts/               # 运行脚本
├── eval_nostorage.py       # 无存储评估
├── eval_storage.py         # 带存储评估
└── test_conflict_graph.py  # E2E 冲突决策测试

tests/                 # 测试
├── test_graph.py      # 超图 + 构建器 + 快照 + 检索（15 tests）
├── test_push.py       # 推送引擎（7 tests）
├── test_storage.py    # Git 存储
├── test_signal.py     # 信号检测
└── ...
```

## 数据流

```
飞书群聊消息
    │
    ▼
NoiseFilter ─── 过滤噪音（emoji/链接/系统消息）
    │
    ▼
MessageBatcher ── 按时间窗口 + 话题分组
    │
    ▼
LexicalAnalyzer ── 词法匹配检测决策信号
    │
    ▼
SignalEmitter ──── 聚合信号，计算 DecisionLevel
    │
    ▼
Detector ───────── 判断 is_decision
    │
    ├─ false → 跳过
    │
    └─ true
         │
         ▼
    SnapshotManager ── 保存检测快照
         │
         ▼
    LLMClient ──────── 调用 LLM 提取结构化决策
         │
         ▼
    DecisionNode ───── 结构化决策节点
         │
         ▼
    MemoryGraph.detect_conflicts()
         │
         ├─ 有冲突 → CONFLICT_KEEP_BOTH Mutation → PushEngine.push_conflict_card()
         │
         ▼
    PipelineEngine.apply_mutation()
         │
         ├─ CREATE  → push_decision_card()
         ├─ UPDATE  → push_decision_update_card()
         └─ ...
              │
              ▼
    GitStorage.write_decision()  ── 写入独立 Git 分支
              │
              ▼
    PushEngine ── 定时任务：热点值衰减 → 低热点推送 → 每日摘要
```
