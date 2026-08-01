# 决策提取评估方案

## 评估目标

评估 LLM（DeepSeek Chat）从对话中提取决策信息的能力，包括：决策检测、内容识别、提议者识别、执行者识别、影响级别判断、状态判断。

## 评估数据集

使用 `eval_data/decision_extraction/` 下的 12 个场景：

| # | 场景 | 说明 | 对话数 |
|---|------|------|--------|
| 01 | technical-selection | 技术选型决策 | 20 |
| 02 | task-assignment | 任务分配决策 | - |
| 03 | parameter-lock | 参数锁定决策 | - |
| 04 | implicit-consensus | 隐式共识 | - |
| 05 | conflict-decisions | 冲突决策 | - |
| 06 | rejection-override | 否决与推翻 | - |
| 07 | pure-discussion | 纯讨论（无决策） | - |
| 08 | status-update | 状态更新 | - |
| 09 | suggestion-only | 仅建议 | - |
| 10 | small-talk | 闲聊 | - |
| 11 | mixed-scenario | 混合场景 | - |
| 12 | boundary-case | 边界情况 | - |

## 评估维度

| 维度 | 说明 | 示例问题 |
|------|------|----------|
| detection | 是否做出决策 | "以上对话中是否做出了决策？" |
| content | 决策内容 | "决策内容是什么？" |
| proposer | 提议者 | "这个决策是谁提出的？" |
| executor | 执行者 | "这个决策由谁执行？" |
| impact_level | 影响级别 | "这个决策的影响级别是？major/minor/advisory" |
| status | 状态 | "这个决策的当前状态是？decided/in_progress/completed" |

## 评估方法

### 方法一：多选 QA 评估（主要方法）

每个对话对应一组 QA 问题（选择题），逐题向 LLM 提问，比较 LLM 的答案与真值。

- **LLM 配置**: 使用 DeepSeek Chat（deepseek-chat）
- **温度**: 0.0（确定性输出）
- **max_tokens**: 10（答案极短，仅需输出选项字母）
- **系统提示**: "你是一个决策提取评估助手。根据对话内容回答问题，只输出选项字母（A/B/C/D），不要输出其他内容。"
- **评估指标**: 按维度计算准确率、整体准确率、token 消耗

### 方法二：自由格式提取评估（扩展方法）

直接让 LLM 从对话中提取结构化决策信息（JSON 格式），再与真值对比。

- **LLM 配置**: temperature=0.0
- **max_tokens**: 256
- **评估指标**: 决策检测召回率、内容精确匹配率、提议者/执行者准确率

## 评估流程

1. 加载所有场景的 dialogue.json 和 qa.json
2. 对每个场景：
   a. 提取对话列表
   b. 对每个对话的每个 QA 问题，向 LLM 提问
   c. 记录 LLM 答案与预期答案
   d. 记录 token 消耗
3. 汇总结果：按维度计算准确率
4. 输出评估报告（JSON）

## 评估工具

- `src/eval/evaluator.py`: ExtractionEvaluator，封装评估逻辑
- `tests/test_eval_extraction.py`: 评估测试脚本，运行完整评估并输出报告

## Token 追踪

使用 `tiktoken` 库进行 token 计数，支持：
- 按 prompt/completion/total 分类统计
- 每次调用的 token 消耗
- 累计 token 消耗

## 预期输出

```json
{
  "overall_accuracy": 0.85,
  "overall_dim_accuracies": {
    "detection": 0.92,
    "content": 0.88,
    "proposer": 0.75,
    "executor": 0.80,
    "impact_level": 0.85,
    "status": 0.90
  },
  "total_calls": 120,
  "total_tokens": 50000,
  "scenarios": [
    {
      "scenario": "01-technical-selection",
      "dim_accuracies": { ... },
      "total": 20,
      "correct": 18,
      "accuracy": 0.90
    }
  ]
}
```