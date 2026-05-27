# MCP 工具 CLI 测试脚本

本目录包含 MCP Server 注册的每个工具的独立 CLI 脚本，用户可直接调用进行测试。

## 使用方式

```bash
# 用项目虚拟环境的 Python 运行
.venv/bin/python scripts/mcp/<script_name>.py [参数]
```

所有脚本会自动加载项目配置（`.env`）、初始化 Git 数据仓库。

## 脚本列表

### 查询类

| 脚本 | 说明 | 参数 |
|------|------|------|
| `list_decisions.py` | 列出决策 | `--top-k N`（默认 20）, `--topic TOPIC` |
| `decision.py` | 查询单条决策 | `sid`（位置参数） |
| `search.py` | 语义搜索决策 | `--query TEXT`, `--top-k N`（默认 5） |
| `topic.py` | 按主题查询决策 | `--topic TEXT` |
| `timeline.py` | 时间线查询 | `--start DATE`, `--end DATE`, `--topic TOPIC` |
| `list_topics.py` | 列出所有主题 | 无参数 |
| `get_relations.py` | 查询决策关联关系 | `--sid TEXT` |
| `stats.py` | 系统统计信息 | 无参数 |
| `hot_decisions.py` | 热门决策 | `--top-k N`（默认 10） |
| `forgotten_decisions.py` | 被遗忘的决策 | `--threshold N`（默认 30，单位天） |
| `related_decisions.py` | 关联决策 | `--sid TEXT`, `--top-k N`（默认 5） |
| `recent_decisions.py` | 最近决策 | `--days N`（默认 7）, `--top-k N`（默认 10） |
| `fulltext_search.py` | 全文搜索 | `--query TEXT`, `--top-k N`（默认 10） |

### Git 类

| 脚本 | 说明 | 参数 |
|------|------|------|
| `git_history.py` | Git 提交历史 | `--limit N`（默认 20） |
| `git_search.py` | Git 日志搜索 | `--query TEXT`, `--limit N`（默认 20） |
| `git_blame.py` | Git Blame 查询 | `--sid TEXT` |

### 冲突/异议类

| 脚本 | 说明 | 参数 |
|------|------|------|
| `conflict_list.py` | 列出冲突 | `--status TEXT`（可选） |
| `objection_list.py` | 列出异议 | `--sid TEXT`（可选） |
| `decision_card.py` | 决策卡片信息 | `--sid TEXT` |
| `decision_history.py` | 决策历史版本 | `sid`（位置参数）, `--topic-id TEXT` |

### 写入类

| 脚本 | 说明 | 参数 |
|------|------|------|
| `create_decision.py` | 创建决策 | `--summary TEXT`, `--full-text TEXT`, `--topic TEXT` |
| `update_decision.py` | 更新决策 | `--sid TEXT`, `--summary TEXT`, `--full-text TEXT` |
| `confirm_decision.py` | 确认决策 | `--sid TEXT` |
| `reject_decision.py` | 驳回决策 | `--sid TEXT`, `--reason TEXT` |
| `revert_decision.py` | 回退决策 | `--sid TEXT` |
| `resolve_conflict.py` | 解决冲突 | `--sid TEXT`, `--resolution TEXT` |

### LLM 类

| 脚本 | 说明 | 参数 |
|------|------|------|
| `extract_decision.py` | 从文本提取决策 | `--text TEXT` |
| `classify_topic.py` | 主题分类 | `--text TEXT` |
| `detect_crosstopic.py` | 跨主题检测 | `--text TEXT` |
| `check_conflict.py` | 冲突检测 | `--text TEXT` |
| `evaluate_dedup.py` | 重复判断 | `--text1 TEXT`, `--text2 TEXT` |
| `resolve_conflict_action.py` | 冲突解决建议 | `--sid TEXT` |
| `extract_and_create.py` | 提取并创建决策 | `--text TEXT` |

### 工具类

| 脚本 | 说明 | 参数 |
|------|------|------|
| `refresh.py` | 刷新数据加载 | 无参数 |

## 示例

```bash
# 列出最近 10 条决策
.venv/bin/python scripts/mcp/list_decisions.py --top-k 10

# 按主题查询
.venv/bin/python scripts/mcp/list_decisions.py --topic 技术选型

# 查询单条决策详情
.venv/bin/python scripts/mcp/decision.py 7eb7728d7ee8

# 语义搜索
.venv/bin/python scripts/mcp/search.py --query "数据库选型" --top-k 3

# 系统统计
.venv/bin/python scripts/mcp/stats.py

# 查看 Git 提交历史
.venv/bin/python scripts/mcp/git_history.py --limit 10
```