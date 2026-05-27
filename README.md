# feishu-mem — 飞书协作记忆系统

通过飞书 WebSocket 监听群聊消息，自动提取团队决策并持久化存储，支持 MCP 协议接入 AI 客户端进行语义检索。

---

## 核心架构

```
飞书群聊消息 → WebSocket → 检测器(EnhancedDetector) → Snapshot → LLM提取(DeepSeek) → Git存储
                                                                                        ↓
                                                                              MCP Server ← ─ ─ 语义检索(Embedding + Reranker)
```

## MCP Server

MCP (Model Context Protocol) 服务器通过 stdio 传输协议暴露决策查询工具，供 Claude Desktop、OpenClaw 等 MCP 客户端使用。

### 注册的工具 (tools)

34 个工具全部注册在 [scripts/mcp_server.py](scripts/mcp_server.py)，分 6 类：

#### 查询类 (12)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `list_decisions` | **列出所有决策**（推荐，无需参数） | `top_k` (默认50) |
| `topic` | 按议题查询决策（省略 `topic_id` 则返回全部） | `topic_id`, `top_k` |
| `search` | 语义搜索决策（Embedding+Reranker，降级关键词） | `query`, `topic`, `top_k` |
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

#### Git 类 (3)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `git_history` | Git 提交历史 | `limit` |
| `git_search` | Git 内容搜索 | `query` |
| `git_blame` | Git 追溯（每行最后修改人） | `sid`, `topic_id` |

#### 冲突与异议类 (4)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `conflict_list` | 列出所有已记录的决策冲突 | `top_k` |
| `objection_list` | 列出异议 | `topic_id` |
| `decision_card` | 获取决策的飞书卡片格式 JSON | `sid` |
| `decision_history` | 决策版本变更历史 | `sid`, `topic_id` |

#### 写入类 (8)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `create_decision` | 创建新决策 | `summary`, `content`, `topic_id`, `impact_level` |
| `update_decision` | 更新已有决策 | `sid`, `summary`, `content`, `status` |
| `confirm_decision` | 确认（批准）决策 | `sid` |
| `reject_decision` | 拒绝决策 | `sid`, `reason` |
| `revert_decision` | 回滚到指定 Git 版本 | `sid`, `commit_hash` |
| `resolve_conflict` | 标记冲突已解决 | `decision_a`, `decision_b`, `resolution` |
| `classify_topic` | 重新归类到指定议题 | `sid`, `topic_id` |
| `detect_crosstopic` | 检测跨议题影响 | `sid` |

#### LLM 辅助类 (5)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `extract_decision` | 从文本提取决策信息 | `text` |
| `extract_and_create` | 提取决策并自动创建 | `text`, `topic_id` |
| `check_conflict` | 检查与现有决策的冲突 | `summary`, `content`, `topic_id` |
| `evaluate_dedup` | 评估决策重复或冲突 | `sid_a`, `sid_b` |
| `resolve_conflict_action` | 获取冲突解决建议 | `sid_a`, `sid_b` |

#### 系统类 (1)

| 工具 | 功能 | 关键参数 |
|---|---|---|
| `refresh` | 从 Git 存储重新加载所有决策 | — |

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

模型不可用时 `search_decisions` 自动降级为关键词检索，`list_decisions` 和 `get_decision` 不依赖模型服务。

---

## Eval 模式 — 测试结果

支持通过命令行 `--eval` 模式从本地文件模拟消息处理、验证系统稳定性。

### 一、单群聊测试（150 条 + 6 话题）

测试配置：`--eval --delay 0 --max-messages 150`

**阈值迭代：**

| 轮次 | SEMANTIC | REOPEN | Suspend | Reopen | 决策 | 说明 |
|------|----------|--------|---------|--------|------|------|
| ① | 0.45 (均) | 0.65 (均) | 13 | 0 | 26 | Mean聚合，reopen阈值太高 |
| ② | 0.50 (均) | 0.55 (均) | 13 | 0 | 22 | 降阈值仍不够 |
| ③ | 0.50 (均) | 0.55 (**Max**) | 12 | **84** | 13 | Max-similarity 方案A生效 |

**发现**：Max-similarity（新消息与episode内每条消息逐一比相似度取最高分）替代 Mean-aggregation（取平均）后，reopen 从 0 升至 84 次，话题回切时能正确匹配。

### 二、多群聊测试（250 条 × 3 群聊）

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
  新决策:     65 个
  总操作:     88 次（CREATE + UPDATE）
  失败:       0
  总耗时:     618.5s
```

**验证结论：**

| 特性 | 状态 | 说明 |
|------|------|------|
| 群聊隔离 | ✅ | 每群独立 `ChatEpisodeBuffer`，`find_reopen` 按 `chat_id` 过滤 |
| SuspendPool 持久化 | ✅ | 重启后从 JSON 恢复，支持 LRU 淘汰 |
| Plan A 去重 | ✅ | 250条提取65个决策，避免重复 |
| 语义边界检测 | ✅ | embedding + keyword 双通道触发 suspend |
| 系统稳定性 | ✅ | 全量通过 0 崩溃 |

### 三、启动 Eval 测试

```bash
# 单群聊快速测试
uv run python main.py --eval --max-messages 20

# 单群聊全量
uv run python main.py --eval --delay 0

# 多群聊测试（3个群聊 round-robin）
uv run python main.py --eval --delay 0 --group-num 3

# 限制消息数
uv run python main.py --eval --max-messages 50 --group-num 3
```

完整设计方案见 [`ref/design/eval_mode_design.md`](ref/design/eval_mode_design.md)。