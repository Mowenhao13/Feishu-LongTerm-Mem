# feishu-mem — 飞书协作记忆系统

通过飞书 WebSocket 监听群聊消息，自动提取团队决策并持久化存储，支持 MCP 协议接入 AI 客户端进行语义检索。

---

## 核心架构

```
飞书群聊消息 → WebSocket/Poll → 检测器(EnhancedDetector) → Episode Buffer → SuspendPool
                                                                          ↓
    MCP Server ←── MemoryGraph (内存索引) ←── LLM 提取 (DeepSeek/Qwen) ←── 引擎分发
         ↓                     ↓
    AI 客户端              Git 版本化存储 (Branch-per-Record)
```

## MCP Server

MCP (Model Context Protocol) 服务器通过 stdio 传输协议暴露决策查询与写入工具，供 OpenClaw 等 MCP 客户端使用。

### 注册的工具 (tools)

**39 个工具**全部注册在 [src/mcp_server/server.py](src/mcp_server/server.py)，分 4 类：

#### 查询工具 (18)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `list_decisions` | 列出所有决策（推荐，无需参数） | `top_k` (默认50) |
| `search` | 语义搜索（Embedding+Reranker，降级关键词） | `query`, `topic`, `top_k` |
| `topic` | 按议题查询决策 | `topic_id`, `top_k` |
| `decision` | 获取单个决策详情 | `sid` |
| `timeline` | 决策时间线（按创建时间倒序） | `top_k` |
| `list_topics` | 列出所有议题 | — |
| `get_relations` | 获取指定决策的关系网络 | `sid` |
| `stats` | 系统统计（总数、状态分布、影响分布） | — |
| `hot_decisions` | 热点决策排名（按热度值） | `min_score`, `top_k` |
| `forgotten_decisions` | 被遗忘的决策（低热度值） | `max_score`, `top_k` |
| `related_decisions` | 获取与指定决策相关的其他决策 | `sid` |
| `recent_decisions` | 最近创建的决策（按小时筛选） | `hours`, `top_k` |
| `fulltext_search` | 全文搜索（关键词匹配） | `query`, `topic`, `top_k` |
| `decision_children` | 获取指定决策的直接子决策 | `sid` |
| `decision_descendants` | 递归获取所有后代决策 | `sid` |
| `decision_ancestors` | 获取祖先路径（根→父→当前） | `sid` |
| `decision_tree` | 获取完整层级树（递归嵌套 children） | `sid` |
| `show_tree` | 展示完整决策森林（无需参数） | — |

#### 写入与变更工具 (6)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `create_decision` | 创建新决策 | `summary`, `content`, `topic_id`, `impact_level` |
| `update_decision` | 更新已有决策 | `sid`, `summary`, `content`, `status` |
| `confirm_decision` | 确认（批准）决策 | `sid` |
| `reject_decision` | 拒绝决策 | `sid`, `reason` |
| `revert_decision` | 回滚到指定 Git 版本 | `sid`, `commit_hash` |
| `resolve_conflict` | 标记冲突已解决 | `decision_a`, `decision_b`, `resolution` |

#### LLM 辅助工具 (7)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `extract_decision` | 从文本提取决策信息 | `text` |
| `extract_and_create` | 提取决策并自动创建 | `text`, `topic_id` |
| `check_conflict` | 检查与现有决策的冲突 | `summary`, `content`, `topic_id` |
| `evaluate_dedup` | 评估决策重复或冲突 | `sid_a`, `sid_b` |
| `classify_topic` | 重新归类到指定议题 | `sid`, `topic_id` |
| `detect_crosstopic` | 检测跨议题影响 | `sid` |
| `resolve_conflict_action` | 获取冲突解决建议 | `sid_a`, `sid_b` |

#### Git & 系统工具 (8)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `git_history` | Git 提交历史 | `limit` |
| `git_search` | Git 内容搜索 | `query` |
| `git_blame` | Git 追溯（每行最后修改人） | `sid`, `topic_id` |
| `conflict_list` | 列出所有已记录的决策冲突 | `top_k` |
| `objection_list` | 列出异议 | `topic_id` |
| `decision_card` | 获取决策的飞书卡片格式 JSON | `sid` |
| `decision_history` | 决策版本变更历史 | `sid`, `topic_id` |
| `refresh` | 从 Git 重新加载所有决策 | — |

**启动方式**:
```bash
uv run python scripts/mcp_server.py
```

---

## 接入 OpenClaw

### 1. 配置 MCP Server

```bash
openclaw mcp set feishu-mem '{
  "command": "uv",
  "args": ["run", "python", "scripts/mcp_server.py"],
  "cwd": "/Users/halllo/projects/local/feishu-mem"
}'
```

### 2. 验证配置

```bash
openclaw mcp list
```

### 3. 在对话中使用

在 OpenClaw 中直接询问：

> "查一下我们的技术决策"
> "搜索阿里云相关的决策记忆"
> "查看决策 3309244b260d 的详情"
> "展示完整的决策树"

OpenClaw 会自动拉起 MCP server 并调用对应工具。

---

## 数据存储

- **目录**: `data/decisions/{project}/{topic}/{sid}.md`
- **格式**: YAML 前置元数据 + Markdown 正文
- **版本控制**: 每次决策变更自动 Git commit + push

---

## 模型服务 (可选)

语义检索需要运行 Embedding 和 Reranker 模型服务：

| 服务 | 端口 | 模型 |
|---|---|---|
| Embedding | `127.0.0.1:8000` | Qwen3-Embedding-4B |
| Reranker | `127.0.0.1:8001` | Qwen3-Reranker-4B |

模型不可用时 `search` 自动降级为关键词检索，`list_decisions` 和 `decision` 不依赖模型服务。

---

## Eval 模式 — 测试结果

支持通过 `--eval` 模式从本地文件模拟消息处理、验证系统稳定性。

### 一、多群聊测试（250 条 × 3 群聊）

测试配置：`--eval --delay 0 --group-num 3`

```
群聊分布:
  eval_0     84 msgs
  eval_1     83 msgs
  eval_2     83 msgs
  ─────────────────
  Episode:
    Suspend:  31 次
    Reopen:  120 次
    池大小:   20 / 20（触发2次LRU淘汰）
  ─────────────────
  新决策:     3 条 (含层级关系)
  层级关系:   容器化 → K8s → 容器网络/监控/安全
  LLM 调用:   3 次 (2,784 tokens)
  总耗时:     289.7s
```

### 二、层级关系测试（hierarchy_test.txt）

51 条层级化消息测试决策树父子关系提取能力：

| 指标 | 数值 |
|------|------|
| 群聊数 | 3 |
| 种子决策 | 11 条（4 根 + 7 子） |
| 消息数 | 51 |
| Suspend | 2 次 |
| Reopen | 28 次 |
| 决策提取 | 6 条 |
| 层级关系 | 微服务→gRPC/Kong/Consul, 容器化→监控/网络 |

### 三、启动 Eval 测试

```bash
# 基础运行（单群聊，默认1秒延迟）
uv run python main.py --eval

# 多群聊测试（3个群聊 round-robin）
uv run python main.py --eval --delay 0 --group-num 3

# 层级关系测试
uv run python scripts/test_decision_hierarchy.py

# 展示决策树
uv run python scripts/show_decision_tree.py
```

---

## 相关文档

- [系统架构](docs/wiki/project_overiew/System%20Architecture%20%26%20Data%20Flow.md)
- [MCP 工具参考](docs/wiki/mcp_server/MCP%20Tool%20Reference.md)
- [MCP 服务部署](docs/wiki/mcp_server/MCP%20Server%20Deployment.md)
- [快速开始](docs/wiki/project_overiew/Getting%20Started%20%26%20Configuration.md)
- [项目展示 PPT](docs/ppt/index.html)