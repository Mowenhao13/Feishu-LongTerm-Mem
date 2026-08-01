# 大规模跨群聊评估方案

## 1. 概述

在现有评估框架基础上，构建大规模、有真值标注的多群聊数据集，以及配套的自动化精度评估流水线，实现对系统端到端决策提取能力的量化度量。

### 目标

- 生成数千条有真值标注的模拟群聊消息流
- 同时覆盖单群聊（基线精度）和多群聊（跨群隔离）两种场景
- 量化衡量：决策检测精度/召回/F1、话题分类准确率、状态判断准确率
- 数据集可复用、可版本化管理

### 架构总览

```
Phase 1: 数据生成                              Phase 2: 评估
┌──────────────────────────────┐             ┌────────────────────────┐
│  generate_eval_data.py        │             │  run_eval.py (增强版)   │
│                              │             │                        │
│  配置 → LLM 生成 → 标注      │ ──── 数据集 ─→ │  Pipeline 处理         │
│                              │             │  Comparator 对比       │
│  输出: messages.jsonl         │             │  生成精度报告           │
│        expected.jsonl         │             │                        │
└──────────────────────────────┘             └────────────────────────┘
```

## 2. 数据生成器 (Phase 1)

### 2.1 配置模型

```yaml
# eval_dataset/config.yaml
generation:
  method: llm                          # 生成方式
  model: "deepseek-chat"
  temperature: 0.7                     # 适度随机性，保证句式多样

single_chat:
  topics:
    - name: "数据库选型"
      keywords: ["PostgreSQL", "MySQL", "Redis", "MongoDB"]
    - name: "前端框架"
      keywords: ["React", "Vue", "Next.js", "Vite"]
    - name: "容器化方案"
      keywords: ["K8s", "Docker", "Calico", "Prometheus"]
    - name: "监控告警"
      keywords: ["OpenTelemetry", "Grafana", "告警规则", "自愈"]
    - name: "消息队列"
      keywords: ["Kafka", "RabbitMQ", "Pulsar"]
  num_decisions_per_topic: 10
  noise_ratio: 0.3                     # 30% 的消息为噪声/干扰
  difficulty:
    easy: 0.3
    medium: 0.4
    hard: 0.3
  total_messages: ~1500

multi_chat:
  num_chats: 5
  topics_per_chat: 3
  num_decisions_per_chat: 8
  overlap_ratio: 0.2                   # 20% 跨群话题重叠（测试隔离）
  total_messages: ~2500

speaker_styles:
  - name: "直接型"
    traits: "话少、结论前置、常用'就'字"
  - name: "分析型"
    traits: "话多、喜欢列举优缺点、长句多"
  - name: "谨慎型"
    traits: "常用反问/疑问句、倾向说'再想想''确定吗'"
  - name: "协调型"
    traits: "善于总结、常用'大家觉得呢''那就这么定了'"
```

### 2.2 三层 Prompt 生成

#### 第一层：场景蓝图

```
你是一个群聊对话设计师。请根据以下配置生成一个群聊场景蓝图。

要求：
- {num_chats} 个群聊，每个群聊 {topics_per_chat} 个讨论话题
- 每个群聊 {num_participants} 个参与者，风格各异
- 每个话题嵌入 {num_decisions} 个决策点
- 决策点不要太明显，要自然融入讨论

输出 JSON 格式蓝图（仅输出 JSON，无额外文字）。
```

#### 第二层：消息流生成

```
根据以下场景蓝图生成完整的群聊对话。

群聊配置：{蓝图的 JSON}

消息生成要求：
- 每条消息长度 5-80 字不等
- 句式多变：陈述句、反问句、疑问句、分析句混合
- 不同说话人有不同语言风格：
  {speaker_styles 的 JSON}
- 决策点不能太直接（避免"好，定了用X"的机械句式），
  而是通过共识形成（"X大家都同意吧""行""那就X"）
- 每 {noise_interval} 条消息插入一条完全无关的干扰消息
- 部分议题只讨论不定论（无决策的训练负样本）

输出格式：每行一个 JSON 对象，如下所示。
{
  "chat_id": "chat_0",
  "msg_id": "m001",
  "speaker": "张三",
  "msg": "数据库选型的话，之前项目用的PG感觉还不错",
  "expected_decision": false,
  "is_distractor": false
}

当一条消息中包含或确认了决策时，expected_decision=true，
并附带该决策的完整信息：
{
  "chat_id": "chat_0",
  "msg_id": "m005",
  "speaker": "李四",
  "msg": "大家都同意用PG的话就这么定了",
  "expected_decision": true,
  "expected_topic": "数据库选型",
  "expected_summary": "采用PostgreSQL作为主数据库",
  "expected_status": "decided",
  "expected_impact": "major",
  "difficulty": "easy"
}

只输出 JSONL 格式，不要输出其他文字。
```

#### 第三层：真值提炼（后处理）

第一、二层生成后，由后处理脚本从 JSONL 中提取所有 `expected_decision=true` 的记录，格式化为标准 expected.jsonl。

### 2.3 难度分级

| 难度 | 消息特征 | 决策清晰度 | 干扰程度 |
|------|---------|-----------|---------|
| easy | 有明确结论句 + 确认词 | 高 | 低 |
| medium | 需要跨轮次推理 | 中 | 中 |
| hard | 多话题交织 + 隐式共识 | 低 | 高 |

### 2.4 输出目录结构

```
eval_dataset/
├── config.yaml
├── generation.log
├── single_chat/
│   ├── messages.jsonl     # Pipeline 输入（一行一个消息对象）
│   └── expected.jsonl     # 真值（一行一个决策对象）
└── multi_chat/
    ├── messages.jsonl
    └── expected.jsonl
```

### 2.5 生成器 CLI

```bash
# 生成单群聊数据集
python -m scripts.generate_eval_data --mode single_chat --output eval_dataset/single_chat

# 生成多群聊数据集
python -m scripts.generate_eval_data --mode multi_chat --output eval_dataset/multi_chat

# 覆盖默认配置
python -m scripts.generate_eval_data --mode multi_chat --num-chats 3 --num-decisions 5
```

## 3. 评估器 (Phase 2)

### 3.1 EvalRunner 增强

现有的 EvalRunner 从纯文本文件加载消息。增强后支持从 JSONL 加载完整消息对象（含 chat_id、speaker 等字段）。

关键变更点：

```
eval_runner.py 的 _load_messages() 方法：
  - 检测文件后缀 .jsonl → 按 JSONL 格式加载
  - 返回 List[Dict] 而非 List[str]
  - 每条消息包含 chat_id 用于群聊分配
```

### 3.2 EvalComparator（新增）

负责 Pipeline 运行后对比实际决策与预期真值。

```
EvalComparator
├── __init__(expected_path, actual_decisions)
├── match() → (tp, fp, fn)          # 匹配决策
├── compute_metrics() → Dict        # 计算精度/召回/F1
├── report_by_topic() → Dict        # 按话题拆解
├── report_by_difficulty() → Dict   # 按难度拆解
└── report_by_chat() → Dict         # 按群聊拆解（多群模式下）
```

**匹配逻辑**：

```
for each expected_decisions:
  在同话题的 actual_decisions 中找 summary 相似度 > 0.3 的
  → 找到 → TP（记录匹配对）
  → 未找到 → FN

for each actual_decisions（未匹配的）:
  → FP
```

匹配时也记录 `topic` 和 `status` 是否匹配，用于计算维度准确率。

### 3.3 评估指标

| 指标 | 计算方式 | 用途 |
|------|---------|------|
| Precision | TP / (TP + FP) | 系统提取的决策中，正确的比例 |
| Recall | TP / (TP + FN) | 真实决策中，系统找出的比例 |
| F1 | 2×P×R/(P+R) | 综合评分 |
| Topic Accuracy | 正确分类数 / TP | 主题分类准确率 |
| Status Accuracy | 状态正确数 / TP | 状态判断准确率 |
| Isolation Score | 跨群正确归位数 / 总决策（多群模式） | 群聊隔离效果 |

### 3.4 评估 CLI

```bash
# 单群聊评估
python -m scripts.run_eval \
  --input eval_dataset/single_chat/messages.jsonl \
  --expected eval_dataset/single_chat/expected.jsonl \
  --mode single

# 多群聊评估（自动按 chat_id 分配群聊）
python -m scripts.run_eval \
  --input eval_dataset/multi_chat/messages.jsonl \
  --expected eval_dataset/multi_chat/expected.jsonl \
  --mode multi

# 指定模型和延迟
python -m scripts.run_eval \
  --input eval_dataset/multi_chat/messages.jsonl \
  --expected eval_dataset/multi_chat/expected.jsonl \
  --mode multi \
  --delay 0.5 \
  --model deepseek-chat
```

### 3.5 报告输出格式

终端带颜色的摘要 + JSON 文件：

```json
{
  "mode": "single_chat",
  "dataset": "eval_dataset/single_chat/",
  "config": { ... },
  "total_messages": 1500,
  "expected_decisions": 50,
  "detected_decisions": 43,
  "true_positives": 38,
  "false_positives": 5,
  "false_negatives": 12,
  "precision": 0.88,
  "recall": 0.76,
  "f1": 0.82,
  "by_topic": {
    "数据库选型": { "precision": 0.9, "recall": 0.8, "f1": 0.85 },
    ...
  },
  "by_difficulty": {
    "easy": { "precision": 0.95, "recall": 0.9, "f1": 0.92 },
    "medium": { "precision": 0.85, "recall": 0.75, "f1": 0.80 },
    "hard": { "precision": 0.7, "recall": 0.5, "f1": 0.58 }
  },
  "cross_chat": {
    "isolation_score": 0.92,
    "migration_count": 2
  },
  "dimension_accuracy": {
    "topic": 0.85,
    "status": 0.72,
    "impact": 0.68
  },
  "token_cost": { ... }
}
```

## 4. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/eval/generator.py` | 新增 | LLM 数据生成器（三层 Prompt 架构） |
| `src/eval/comparator.py` | 新增 | 决策比对器（TP/FP/FN 匹配、指标计算） |
| `src/eval/__init__.py` | 修改 | 导出新模块 |
| `src/eval_runner.py` | 修改 | 支持 JSONL 输入、集成 Comparator |
| `scripts/generate_eval_data.py` | 新增 | 数据生成 CLI |
| `scripts/run_eval.py` | 新增 | 评估执行 CLI |
| `eval_dataset/config.yaml` | 新增 | 默认生成配置 |

## 5. 注意事项

- **LLM 生成成本**：约 2000-4000 条消息需要 20-40 次 LLM 调用，每次生成一批（约 100 条消息）
- **评估耗时**：2500 条消息 × 0.5s 延迟 ≈ 20 分钟跑完多群模式
- **真值校验**：生成后建议抽样人工检查 expected.jsonl 的标注质量
- **数据集复用**：生成的 eval_dataset 可 git 跟踪，每次改进后跑同一数据集对比回归效果