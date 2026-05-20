# 超图记忆 - 飞书决策分析系统

## 评估结果

### 决策提取评估（2026-05-20）

| 场景 | 基准准确率 | 优化后准确率 | 变化 | 状态 |
|------|-----------|------------|-----|------|
| 01-technical-selection | 66.7% | 88.3% | ▲ +21.7pp | ✅ 达标 |
| 02-task-assignment | 78.9% | 94.4% | ▲ +15.5pp | ✅ 达标 |
| 03-parameter-lock | 60.0% | 88.3% | ▲ +28.3pp | ✅ 达标 |
| 05-conflict-decisions | 78.6% | 97.1% | ▲ +18.5pp | ✅ 达标 |
| **整体（优化场景）** | **71.1%** | **92.1%** | **▲ +21.0pp** | 🎉 |

### 按维度准确率（优化后）

| 维度 | 准确率 | 说明 |
|------|-------|------|
| detection | 100% | 是否做出了决策判断 |
| content | 95.0% | 决策内容提取 |
| status | 93.3% | 决策状态判断（decided/in_progress/completed） |
| conflict | 97.1% | 是否存在冲突决策判断 |
| impact_level | 86.7% | 影响级别判断（major/minor/advisory） |
| proposer | 78.6% | 决策提议者识别 |
| executor | 93.3% | 任务执行者识别 |

### 系统架构

#### 存储方式

**当前存储：GitStorage**

超图记忆系统目前使用 GitStorage（文件系统 + Git 版本控制），代码位于：
- [src/storage/git_storage.py](file:///Users/halllo/projects/local/feishu-mem/src/storage/git_storage.py) - GitStorage 主类
- [src/storage/git_format.py](file:///Users/halllo/projects/local/feishu-mem/src/storage/git_format.py) - Markdown + YAML frontmatter 格式

数据存储结构：
```
data/
└── decisions/
    └── <project>/
        └── <topic_id>/
            └── <sid>.md  # 每个决策一个 Markdown 文件（含 YAML frontmatter）
```

#### 核心模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 决策提取评估 | [src/eval/evaluator.py](file:///Users/halllo/projects/local/feishu-mem/src/eval/evaluator.py) | 端到端评估，支持 GitStorage 集成 |
| LLM 客户端 | [src/llm/client.py](file:///Users/halllo/projects/local/feishu-mem/src/llm/client.py) | LLM API 调用，带 Token 追踪 |
| 信号检测 | [src/signal/detector.py](file:///Users/halllo/projects/local/feishu-mem/src/signal/detector.py) | 对话决策识别（强化检测） |
| MCP 服务器 | [src/mcp_server/server.py](file:///Users/halllo/projects/local/feishu-mem/src/mcp_server/server.py) | MCP 协议服务器 |

### 存储集成

- GitStorage 已集成到评估流程
- 支持写入决策到 Git 存储 + 读取验证
- 02-task-assignment 验证：存储 15/15 对话，验证 15/15 成功（100%）

### 优化策略

1. 强化系统提示词，明确"对话决策分析专家"角色和"只输出选项字母"约束
2. 为每个维度添加具体判断规则和反例提示
3. 规范化答案提取：`_normalize_answer()` 清洗模型输出
4. 修复 02-task-assignment QA 数据中的重复选项 bug（B/D 和 C/D 重复）

### 使用方法

#### 运行完整评估

```bash
cd /Users/halllo/projects/local/feishu-mem
# 不带存储
PYTHONPATH=/Users/halllo/projects/local/feishu-mem .venv/bin/python3 -c "
from src.llm.client import LLMClient
from src.eval.evaluator import run_extraction_eval
client = LLMClient()
report = run_extraction_eval(client, scenarios=['02-task-assignment'])
print(report.to_dict())
"

# 带存储
PYTHONPATH=/Users/halllo/projects/local/feishu-mem .venv/bin/python3 -c "
from src.llm.client import LLMClient
from src.eval.evaluator import run_extraction_eval
client = LLMClient()
report = run_extraction_eval(client, enable_storage=True)
print(report.to_dict())
"
```

#### 运行测试

```bash
# 所有测试
PYTHONPATH=/Users/halllo/projects/local/feishu-mem .venv/bin/python3 -m pytest

# 特定测试
PYTHONPATH=/Users/halllo/projects/local/feishu-mem .venv/bin/python3 -m pytest tests/test_eval_extraction.py -v
```
