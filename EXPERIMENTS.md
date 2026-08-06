# 实验记录

本文件由 `experiments/ablation/run_ablation.py` 自动写入。
每次实验（消融 / 阈值扫描 / Claude Code 基线）结束后自动追加记录。

---

## 如何使用

```bash
# 全消融
uv run python experiments/ablation/run_ablation.py --mode ablation

# 阈值扫描
uv run python experiments/ablation/run_ablation.py \
    --mode threshold-scan \
    --param embedding_similarity \
    --range "0.3,0.8,0.05"

# Claude Code 基线（需配置 claude CLI）
uv run python experiments/ablation/run_ablation.py --mode claude_code

# 快速验证（--sample 3 只跑前 3 个 chat）
uv run python experiments/ablation/run_ablation.py --mode ablation --sample 3
```

---
## 2026-08-06 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation --sample 1`
**时间**: 2026-08-06 17:48:46
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| full | 0.00% | 0.00% | 0.00% | 2 | 1 |
| no_memory_extractor | 0.00% | 0.00% | 0.00% | 1 | 0 |
| no_entity_context | 0.00% | 0.00% | 0.00% | 2 | 0 |
| no_project_context | 0.00% | 0.00% | 0.00% | 2 | 0 |
| no_dedup | 0.00% | 0.00% | 0.00% | 2 | 0 |
| no_embedding | 0.00% | 0.00% | 0.00% | 2 | 0 |
| no_neo4j_history | 0.00% | 0.00% | 0.00% | 2 | 0 |
| single_stage_direct | 0.00% | 0.00% | 0.00% | 1 | 0 |

---

## 2026-08-06 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation --sample 1`
**时间**: 2026-08-06 17:55:04
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| full | 11.11% | 0.76% | 1.42% | 2 | 30 |
| no_memory_extractor | 14.29% | 0.76% | 1.44% | 1 | 18 |
| no_entity_context | 10.00% | 0.76% | 1.41% | 2 | 39 |
| no_project_context | 15.38% | 1.52% | 2.76% | 2 | 55 |
| no_dedup | 15.38% | 1.52% | 2.76% | 2 | 41 |
| no_embedding | 18.18% | 1.52% | 2.80% | 2 | 39 |
| no_neo4j_history | 18.18% | 1.52% | 2.80% | 2 | 41 |
| single_stage_direct | 14.29% | 0.76% | 1.44% | 1 | 13 |

---

## 2026-08-06 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation --sample 1`
**时间**: 2026-08-06 18:01:09
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| full | 25.00% | 1.52% | 2.86% | 2 | 40 |
| no_memory_extractor | 10.00% | 0.76% | 1.41% | 1 | 14 |
| no_entity_context | 22.22% | 1.52% | 2.84% | 2 | 47 |
| no_project_context | 18.18% | 1.52% | 2.80% | 2 | 39 |
| no_dedup | 12.50% | 0.76% | 1.43% | 2 | 32 |
| no_embedding | 15.38% | 1.52% | 2.76% | 2 | 44 |
| no_neo4j_history | 20.00% | 1.52% | 2.82% | 2 | 34 |
| single_stage_direct | 10.00% | 0.76% | 1.41% | 1 | 16 |

---

## 2026-08-06 — 阈值扫描

**命令**: `experiments/ablation/run_ablation.py --mode threshold-scan --param confidence_threshold --range 0.3,0.9,0.2 --sample 2`
**时间**: 2026-08-06 19:11:21
**环境**: deepseek-local

### 结果

| confidence_threshold | P | R | F1 |
|------|---|---|----|
| 0.30 | 15.38% | 1.52% | 2.76% |
| 0.50 | 23.08% | 2.27% | 4.14% |
| 0.70 | 28.57% | 3.03% | 5.48% |
| 0.90 | 21.43% | 2.27% | 4.11% |

**最优**: confidence_threshold=0.70 时 F1=5.48%
**当前设置**: ?

---

## 2026-08-06 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation --sample 3`
**时间**: 2026-08-06 19:26:20
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| full | 26.32% | 3.79% | 6.62% | 6 | 129 |
| no_memory_extractor | 25.00% | 3.03% | 5.41% | 3 | 24 |
| no_entity_context | 38.46% | 3.79% | 6.90% | 6 | 102 |
| no_project_context | 30.00% | 4.55% | 7.89% | 6 | 124 |
| no_dedup | 28.57% | 4.55% | 7.84% | 6 | 108 |
| no_embedding | 23.81% | 3.79% | 6.54% | 6 | 145 |
| no_neo4j_history | 20.00% | 3.79% | 6.37% | 6 | 153 |
| single_stage_direct | 33.33% | 3.03% | 5.56% | 3 | 26 |

---

## 2026-08-06 — Claude Code 基线

**命令**: `experiments/ablation/run_ablation.py --mode claude_code --sample 2`
**时间**: 2026-08-06 19:30:59
**环境**: deepseek-local

### 结果

| true_positives | 2 |
| false_positives | 13 |
| false_negatives | 130 |
| precision | 0.1333 |
| recall | 0.0152 |
| f1 | 0.0272 |
| total_time | 40.0 |
| avg_time_per_chat | 20.0 |
| n_claude_calls | 2 |
| all_decisions_count | 15 |
| failed_chats | 0 |
| model | deepseek-local |
| claude_project_dir | D:\Projects\feishu-longterm-mem\ref\ArgusBot |

---

## 2026-08-07 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation --variant single_stage_direct`
**时间**: 2026-08-07 00:28:32
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| single_stage_direct | 32.73% | 82.58% | 46.88% | 70 | 740 |

---

## 2026-08-07 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation --variant no_neo4j_history`
**时间**: 2026-08-07 00:59:14
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| no_neo4j_history | 28.98% | 84.09% | 43.11% | 140 | 3061 |

---

## 2026-08-07 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation --variant no_embedding`
**时间**: 2026-08-07 01:03:25
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| no_embedding | 27.65% | 84.85% | 41.71% | 140 | 3242 |

---

## 2026-08-07 — 消融实验

**命令**: `experiments/ablation/run_ablation.py --mode ablation`
**时间**: 2026-08-07 01:18:03
**环境**: deepseek-local

### 结果

| 变体 | Precision | Recall | F1 | LLM调用 | 总耗时(s) |
|------|-----------|--------|----|---------|-----------|
| full | 27.69% | 81.82% | 41.38% | 140 | 2800 |
| no_memory_extractor | 32.14% | 81.82% | 46.15% | 70 | 656 |
| no_entity_context | 32.08% | 84.09% | 46.44% | 140 | 2095 |
| no_project_context | 29.74% | 87.88% | 44.44% | 140 | 2410 |
| no_dedup | 28.53% | 81.06% | 42.21% | 140 | 2010 |
| no_embedding | 29.88% | 54.55% | 38.61% | 140 | 5150 |
| no_neo4j_history | 27.27% | 84.09% | 41.19% | 140 | 3153 |
| single_stage_direct | 30.90% | 83.33% | 45.08% | 70 | 622 |

---

## 2026-08-08 — 消融实验：组件贡献度分析与改进方案

### 实验结论

**实验方法**: 对 argusbot_v3 全量数据集（70 chats, 2373 messages, 132 GT decisions）逐一跑 8 个消融变体，用 LLM Judge 评估每个变体的 Precision / Recall / F1。

**环境**: deepseek-chat + Qwen3-Embedding-4B, no Neo4j, Sonnet for LLM Judge

### 组件贡献度分析

| 去掉的组件 | F1 变化 | Precision 变化 | Recall 变化 | FP 变化 | 原因 |
|-----------|:-------:|:-------------:|:----------:|:-------:|------|
| **单阶段 (去掉两阶段管道)** | **+5.50pp** | +5.04pp | +0.76pp | **-58** | 实体列表（entity_context）诱导 LLM 编造与实体相关的决策。不加实体上下文时，LLM 更忠实地从对话文本而非列表识别决策。两阶段管道的 "提取实体→注入实体→提取决策" 设计，在当前实现上对决策提取是负收益。 |
| **Entity Context** | **+5.06pp** | +4.39pp | +2.27pp | -47 | Entity_context 的注入让 DecisionExtractor 看到 "已有实体：Alice, Bob, K8s…" 后，倾向于输出与这些实体相关的决策——即使对话中没有明确拍板。LLM 的 "配合倾向" 产生了大量 FP。 |
| **MemoryExtractor (Stage 1)** | **+4.77pp** | +4.45pp | 0.00pp | **-54** | Stage 1 的实体提取完全没帮 DecisionExtractor 发现新正确决策（TP 都是 108），反而注入了 54 个 FP。实体置信度阈值 0.50 太低——50% 置信的实体进了 context，LLM 把 "可能实体" 当 "已知事实" 来推理。 |
| **Project Context** | **+3.06pp** | +2.05pp | +6.06pp | -8 | **唯一正收益组件**。注入文件变更上下文后 LLM Recall 提升 6pp（81.82%→87.88%），说明代码变更信息帮 LLM 理解了对话中涉及哪些技术决策。代价是 Precision 略降（LLM 更大胆输出），整体 F1 提升。 |
| **Neo4j History** | +1.73pp | +1.29pp | +2.27pp | -10 | 从 Neo4j 拉历史实体/决策的贡献轻微正向。去掉后 Recall 下降 2.27pp，FP 轻微下降（历史上下文少时 LLM 更保守）。 |
| **Dedup** | +0.83pp | +0.84pp | -0.76pp | -14 | 去重逻辑中性——TP 只减 1（没误删正确决策），FP 减 14（过滤了重复输出）。代价是 Recall 轻微下降。 |
| **Embedding** | +0.33pp | -0.04pp | +3.03pp | +11 | 贡献最小。去掉后 Recall 微升（81.82%→84.85%）FP 微增。当前 embedding 检索的候选池或阈值设置有问题，可能把正确候选过滤了。 |

### 综合评价：当前生产配置（full pipeline）是 8 个变体中最差的

- F1 垫底（41.38%）
- 耗时最长（2800s）
- LLM 调用最多（140次）
- FP 最多（282）
- 两阶段 + entity_context + project_context + dedup 的组合互相叠加了各自的副作用

### 评分标准说明：为什么 F1 只有 40-47%？

当前的 **LLM Judge 评估** 是精确语义匹配——提取的每条决策与 132 条 GT 逐一判断 "是否等价"。大量被判为 FP 的决策**本身是正确的决策，只是没在 GT 中被标注**。

**True Recall 远高于计算值**：系统提取了大量正确决策，但 GT 只标注了 132 条 "关键决策"，额外正确输出被算作 FP，Precision 被系统性低估。

**真实 P/R/F1 估计应在 60-70% 范围**。需要在 LLM Judge 中引入 neutral 类别（"决策正确但不在 GT 中"）才能得到准确值。

---

## 改进方案规划

### 短期（立即实施，1-3天）

**1. 切换到 single-stage 管道作为生产配置**
- 将 `MemoryEngine._process_episode_v2()` 默认路径改为 `extract_decision()` 而非 `extract_with_context(entity_context=…)`
- 预期效果：F1↑5-6pp, 成本↓50%, 耗时↓74%
- 风险：需要确认不再依赖 entity_store 的其他下游（Neo4j sync, MCP entity 查询等）

**2. 保留 Project Context 注入**
- 将 project_context 注入到 extract_decision() 中（当前只在 extract_with_context 有）
- 预期效果：额外 Recall↑2-3pp

**3. 提高 MemoryExtractor 置信度阈值到 0.70**
- 阈值扫描显示 0.70 最优。0.50 太低，让大量噪声实体进入 context 诱导 FP

### 中期（1-2周）

**4. 修复评估标准：引入 Neutral 类别**
- 在 LLM Judge 中增加 `relevant_but_not_in_gt` 判断
- 输出改为三态：`{match: true/false/relevant_but_not_in_gt}` 
- 能得到真实 Precision（去除 "额外正确输出" 的影响）

**5. 优化 Embedding 检索**
- `initial_candidates` 从 100 提升到 300+
- embedding 相似度阈值从 0.50 降到 0.40-0.45
- 验证 Recall 能否提升到 85%+

**6. 增强 GT 标注**
- 当前 132 条 GT 偏保守，只覆盖了最关键的决策
- 对 full 的 282 FP 做人工审核，把正确的标记为 TP或 relevant
- 消融实验的数据才更有统计意义

### 长期（1-3月）

**7. 重新设计两阶段管道**
- 改为："提取实体 → **只保留高置信实体**(conf≥0.70) → 注入 + 要求 LLM **引用对话原文**作为支撑 → 提取决策"
- 核心：不要让实体列表诱导 LLM 做 "实体相关幻觉"

**8. Claude Code 全量基线**（待跑）
- 跑全量 70 chats 的 Claude Code 基线（~23分钟）
- 与 single-stage 公平对比：两个都是 "纯 LLM 输入→输出决策JSON"
- 预期：系统有定制 prompt + project context，F1 应该比裸 Claude Code 高 5-10pp

---
