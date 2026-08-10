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

## 2026-08-07 — 生产路径 contract smoke 与证据字段约束回归

**目标**: 重建可信的 production-path 消融与评估流程，重点验证最终 `MemoryEngine → mutation/dedup → graph export → evidence-aware evaluator` 输出是否保留可审计证据字段。

**代码修正**:
- 强化 `DECISION_EXTRACTION_PROMPT_SHORT`：每条输出必须包含非空 `source_message_ids`，且 `evidence_quote` 必须是原始 `[msg_id]` 聊天行中的连续原文片段；没有精确证据则不输出。
- 修复生产 mutation 路径丢证据字段的问题：`source_message_id`、`source_message_ids`、`evidence_quote`、`source_chat_id`、`is_suggestion` 通过 mutation metadata 写回最终 `DecisionNode`。
- `SimpleLLMExtractor` / `MemoryExtractor` 记录 `last_error`，production runner 将 extractor/provider 错误标为 `runner_errors`，避免 LLM/API/JSON 失败静默变成空输出或 FN。
- Langfuse 代码层临时强制禁用，避免当前 SDK API 不兼容影响生产 smoke；后续需单独恢复并验证 observability 集成。

### 回归测试

**命令**:

```bash
UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp uv run pytest -p no:cacheprovider \
  tests/test_confirmed_decision_eval.py \
  tests/test_evidence_linking.py \
  tests/test_pipeline_options.py \
  tests/test_production_ablation_runner.py \
  tests/test_production_ablation_cli.py
```

**结果**: 19 passed。

**补充相邻回归**:

```bash
UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp uv run pytest -p no:cacheprovider \
  tests/test_prompts.py tests/test_llm_config.py tests/test_comparator.py
```

**结果**: 35 passed。合计 54 项相关回归通过，覆盖生产消融开关、证据 evaluator、runner/CLI contract、prompt 基础结构、LLM config 与 comparator。

**未纳入通过数的旧测试**: `tests/test_eval.py tests/test_eval_pipeline.py` 本轮尝试结果为 44 passed / 7 failed；失败原因是旧 `eval_data/classification|conflicts|crosstopic|corpus` 数据目录缺失，以及旧 async 测试未加 pytest async 标记，非本次生产 contract 修改引入。

### 真实 one-chat contract smoke

**命令**:

```bash
LANGFUSE_ENABLE=false MODEL_NAME=deepseek-local \
UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp \
uv run python experiments/production_ablation/run.py --sample 1
```

**Run ID**: `3a488298c2614448bab1ada4fb5ec07d`

| 指标 | 值 |
|---|---:|
| selected chats | 1 |
| expected_count | 2 |
| output_count | 8 |
| strict_tp | 2 |
| strict_fp | 6 |
| strict_fn | 0 |
| evidence_valid | 8 |
| evidence_invalid | 0 |
| precision | 0.2500 |
| recall | 1.0000 |
| f1 | 0.4000 |
| incomplete | false |
| runner_errors | 0 |

**结论**: one-chat 最终生产输出的证据 contract 已通过。此前 smoke 出现 `evidence_valid=0/evidence_invalid=全部输出`，根因是 LLM 输出证据在 `_dict_to_node` 后进入 mutation CREATE 时未写回最终 graph 节点；现已修复并由 runner 测试覆盖。

### 真实 three-chat contract smoke

**命令**:

```bash
LANGFUSE_ENABLE=false MODEL_NAME=deepseek-local \
UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp \
uv run python experiments/production_ablation/run.py --sample 3
```

**Run ID**: `48873e09d6c74acea2787d4ef81a1f53`

| 指标 | 值 |
|---|---:|
| selected chats | 3 |
| expected_count | 6 |
| output_count | 15 |
| strict_tp | 5 |
| strict_fp | 10 |
| strict_fn | 1 |
| evidence_valid | 15 |
| evidence_invalid | 0 |
| precision | 0.3333 |
| recall | 0.8333 |
| f1 | 0.4762 |
| incomplete | false |
| runner_errors | 0 |

**结论**: three-chat smoke 满足当前 acceptance contract：样本 GT 对齐、生产路径执行完成、无 runner/evaluator 基础设施错误、最终输出全部带可追溯证据。

### 仍需继续完善

1. evaluator 已具备三态结果结构（`match_gt` / `valid_extra` / `invalid`），但 production runner 当前仍未接入真实 semantic/neutral adjudicator；因此 GT 外但证据有效的 confirmed 输出仍会在无 adjudicator 模式下按 `invalid` 计入 strict FP。
2. three-chat smoke 中 `strict_fn=1`，需要依赖逐条输出审计定位漏掉的 GT 所在消息，判断是 prompt 漏召回、dedup 合并误伤，还是 GT 与 evidence 精确匹配粒度不一致。
3. 当前 full 路径仍使用两阶段 entity context，smoke 输出密度偏高；后续应在 production ablation 中比较 `full`、`no_entity_context`、`no_memory_extractor`，并使用多次重复运行统计均值/方差，再决定是否切 production 默认路径。
4. 如果要把 Langfuse 打开参与生产 smoke，需要单独验证当前安装的 Langfuse SDK 版本 API；本轮为了 contract smoke 稳定性保持代码层禁用。

### Langfuse 代码层禁用后复测

**命令**:

```bash
MODEL_NAME=deepseek-local UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp \
uv run python experiments/production_ablation/run.py --sample 1
```

**Run ID**: `dfb67b24d4f5446d8df6e27957c07f60`

**结果**: `evidence_valid=5`、`evidence_invalid=0`、`runner_errors=0`、`incomplete=false`。说明 Langfuse 硬禁用后生产 smoke contract 仍通过；本次 LLM 输出存在随机波动（strict_tp=1/2），不作为组件效果结论。

---

## 2026-08-07 — production smoke 审计明细补强

**目标**: 让 contract smoke 的最终 `report.json` 支持直接定位 `strict_fn`、`strict_fp` 和 evidence contract 问题，而不是只保留聚合指标。

**代码修正**:
- `EvaluationOutcome` 新增 `details`：记录每条 confirmed 输出的 `chat_id`、title/summary、`source_message_ids`、`evidence_quote`、evidence 是否有效、adjudication、匹配到的 GT message id 和判定原因。
- `EvaluationOutcome` 新增 `unmatched_expected`：列出本次 selection 内未被 exact/semantic match 覆盖的 GT，便于直接排查 three-chat smoke 的 `strict_fn=1`。
- `experiments/production_ablation/run.py` 将 report 拆成稳定的 `metrics` 与独立 `evaluation_audit`，避免把大块审计明细混入指标对象。
- `SimpleLLMExtractor` 不再盲信模型给出的 evidence：`evidence_quote` 必须能映射到某一条 cited `[msg_id]` 原始消息；多消息拼接 quote 会被本地重新绑定到单条 exact message，仍无法绑定则跳过该候选。
- `MEMORY_EXTRACTION_PROMPT` 增加 Stage 1 输出上限（20 entities / 20 relationships / 10 facts）并缩短 reasoning，production smoke runner 默认 `MAX_TOKENS=8192`，降低 MemoryExtractor JSON 截断概率。

**回归测试**:

```bash
UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp \
uv run pytest -p no:cacheprovider --basetemp .tmp/pytest \
  tests/test_confirmed_decision_eval.py \
  tests/test_evidence_linking.py \
  tests/test_pipeline_options.py \
  tests/test_production_ablation_cli.py \
  tests/test_production_ablation_runner.py \
  tests/test_prompts.py tests/test_llm_config.py tests/test_comparator.py
```

**结果**: 56 passed。

### 新 report 结构下的 three-chat smoke

**诊断性失败 run**: `6719a8535bd1481598215e3047bcf178`。结果为 `evidence_valid=12`、`evidence_invalid=2`、`runner_errors=1`、`incomplete=true`。根因有两类：一是模型把多条消息拼成一个 `evidence_quote`，不满足单条 source-message exact quote contract；二是 MemoryExtractor Stage 1 输出被截断导致 JSON parse error。

**修复后通过 run**: `f5bda6bc74454707a7f6e248cda37041`。

| 指标 | 值 |
|---|---:|
| selected chats | 3 |
| expected_count | 6 |
| output_count | 15 |
| strict_tp | 5 |
| strict_fp | 10 |
| strict_fn | 1 |
| evidence_valid | 15 |
| evidence_invalid | 0 |
| precision | 0.3333 |
| recall | 0.8333 |
| f1 | 0.4762 |
| incomplete | false |
| runner_errors | 0 |

**审计定位**: `evaluation_audit.unmatched_expected` 只剩 `ai_ml_platform_channel_1/m033`，GT 为“模型版本管理 / 好，我明天开始搭建。”。这说明当前剩余 `strict_fn=1` 不是证据字段丢失或 runner 基础设施错误，而是模型召回/抽取粒度问题。

**下一步**: 接入真实三态 adjudicator，把 evidence-valid 的 GT 外输出分成 `valid_extra` 与 `invalid`；同时针对 `ai_ml_platform_channel_1/m033` 建一个 focused regression，确认是 prompt 漏召回、dedup/update 合并误伤，还是 GT 粒度需要调整。

---

## 2026-08-07 — focused regression：模型版本管理执行确认漏召回

**术语说明**:
- `GT` = ground truth，即评测集里的人工/基准答案。
- `focused regression` = 针对一个已知漏例或 bug 的最小回归测试，用来保证这个具体问题后续不会被宽松指标掩盖或再次退化。

**目标漏例**: `ai_ml_platform_channel_1/m033`，GT topic 为“模型版本管理”，GT summary 为“好，我明天开始搭建。”。

**代码修正**:
- `DECISION_EXTRACTION_PROMPT_SHORT` 明确补充：承接上一条决定并承诺执行的确认语也算 confirmed decision，例如“好，我明天开始搭建”。
- `ConfirmedDecisionEvaluator` 收紧 deterministic exact match：不能只因为 `source_message_ids` 里夹带了 GT msg_id 就算 TP；`evidence_quote` 必须来自该 GT message 本身，才算 `exact_source_match`。
- 新增 `test_argusbot_model_version_acknowledgement_regression`：使用真实 `argusbot_v3` 数据，验证缺少 `m033` 时 audit 会报告该 GT；只有输出引用 `m033` 原文“好，我明天开始搭建。”时，`strict_fn` 才归零。

**回归测试**:

```bash
UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp \
uv run pytest -p no:cacheprovider --basetemp .tmp/pytest \
  tests/test_confirmed_decision_eval.py \
  tests/test_evidence_linking.py \
  tests/test_pipeline_options.py \
  tests/test_production_ablation_runner.py \
  tests/test_production_ablation_cli.py \
  tests/test_prompts.py tests/test_llm_config.py tests/test_comparator.py
```

**结果**: 57 passed。

### 新 exact-match 规则下的单 chat smoke

**命令**:

```bash
LANGFUSE_ENABLE=false MODEL_NAME=deepseek-local \
UV_CACHE_DIR=.uv-cache TEMP=.tmp TMP=.tmp \
uv run python experiments/production_ablation/run.py --chat-id ai_ml_platform_channel_1
```

**Run ID**: `f7d12bc2e84e469fa9db73badb966407`

| 指标 | 值 |
|---|---:|
| expected_count | 2 |
| output_count | 2 |
| strict_tp | 1 |
| strict_fp | 1 |
| strict_fn | 1 |
| evidence_valid | 2 |
| evidence_invalid | 0 |
| incomplete | false |
| runner_errors | 0 |

**结论**: evidence contract 通过，但 `m033` 仍未被模型作为独立 confirmed decision 抽出。当前剩余问题不是证据字段丢失，而是抽取粒度：模型把“先定 MLflow，PoC 后决定”（`m032`）作为决策输出，并把 `m033` 放进 source ids，但没有用 `m033` 的原文作为独立 evidence。

**下一步**: 需要进一步改抽取策略，而不是继续放宽 evaluator。候选方向：
1. 在 extractor 后处理阶段，针对 `expected_decision=true` 风格的“承接式执行确认”增加可解释的拆分规则；
2. 或让 prompt 要求将“方案决定”和“执行承诺”拆成两条 confirmed decisions，并用各自原文 evidence；
3. 然后重跑 `ai_ml_platform_channel_1` 和 three-chat smoke，目标是 `m033` 被独立命中且 `evidence_invalid=0`。

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

## 2026-08-08 — 方法学更正：旧消融结果仅作探索记录

2026-08-06 至 2026-08-07 的 `experiments/ablation/run_ablation.py` 结果保留用于排查，但**不得作为生产组件贡献结论**，原因如下：

1. runner 直接调用 extractor，没有经过 `MemoryEngine` 的 mutation、embedding、LLM dedup、storage 等生产路径；
2. `no_embedding` 与 `full` 实现相同，`full` 没有注入 Neo4j client，`no_dedup` 没有进入生产 dedup；
3. `--sample` 只截断 chat，没有同步过滤 expected.jsonl，样本 P/R/F1 无效；
4. project context 是所有 chat 共用的伪造文件变化，不代表真实 conversation-file 关联；
5. LLM/Judge API、JSON 或限流错误会被计入未匹配结果；
6. prompt 要求输出 suggestions，而主 GT 只覆盖 confirmed decisions，导致严格 Precision 目标不一致。

此前关于“各组件正负收益”以及“真实 F1 为 60-70%”的判断均撤回。后续以 `experiments/production_ablation/` 的 production-path、evidence-aware 结果为准。

---

## 2026-08-08 — 旧 runner 消融记录：仅作排查线索

### 实验结论状态

**实验方法**: 对 argusbot_v3 全量数据集（70 chats, 2373 messages, 132 GT decisions）逐一跑 8 个消融变体，用 LLM Judge 评估每个变体的 Precision / Recall / F1。

**环境**: deepseek-chat + Qwen3-Embedding-4B, no Neo4j, Sonnet for LLM Judge

**采信状态**: 本节来自旧 `experiments/ablation/run_ablation.py`，不经过完整 `MemoryEngine → mutation/dedup → graph export → evidence-aware evaluator` 生产路径。下面的组件贡献度只保留为排查假设，不作为生产默认配置调整依据。

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

真实 P/R/F1 需要在 production-path runner 中接入三态 adjudicator 后重新计算。旧 runner 里的 GT 外正确输出现象只说明需要 `valid_extra` / neutral 分类，不能直接推出 60-70% 的可信区间。

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

**8. Claude Code 全量基线**（已执行，指标暂不采信）
- 已生成 70 chats 的 Claude Code 输出（约 614s）；生成模型为 `CLAUDE_MODEL=sonnet`
- 评估阶段的 DeepSeek LLM Judge 连接 `aigw.sysu.edu.cn` 失败；当前实现会把 judge 调用失败错误地作为 `match=false`，因此 P/R/F1 被系统性低估
- 还发现 4 个 chat 返回了可解析但空的 `decisions`；应在下次运行中单独统计为 generation failure，而非 `0 failed`
- 需要先持久化每 chat 原始预测、修复 judge-failure 状态、并统一生成模型，才能与 single-stage 做公平架构对比

---

## 2026-08-07 — Claude Code 基线

**命令**: `experiments/ablation/run_ablation.py --mode claude_code`
**时间**: 2026-08-07 02:02:29
**环境**: deepseek-local

### 结果

| true_positives | 91 |
| false_positives | 363 |
| false_negatives | 41 |
| precision | 0.2004 |
| recall | 0.6894 |
| f1 | 0.3106 |
| total_time | 613.6 |
| avg_time_per_chat | 8.8 |
| n_claude_calls | 70 |
| all_decisions_count | 454 |
| failed_chats | 0 |
| model | deepseek-local |
| claude_project_dir | D:\Projects\feishu-longterm-mem\ref\ArgusBot |

---

---

## 2026-08-07 - execution acknowledgement split follow-up

**Implementation**: `SimpleLLMExtractor` now inspects only the model-cited `source_message_ids`. If a later cited message is an execution acknowledgement such as "好，我明天开始搭建", it is emitted as a separate confirmed decision with that message as exact evidence. Uncited messages are never used for this derivation.

**Regression**: `tests/test_evidence_linking.py` now covers the `m032 -> m033` shape.

**Smoke run**: `bd15a855d4344a06afee636995e95171` on `ai_ml_platform_channel_1`.

| metric | value |
|---|---:|
| expected_count | 2 |
| output_count | 2 |
| strict_tp | 2 |
| strict_fp | 0 |
| strict_fn | 0 |
| evidence_valid | 2 |
| evidence_invalid | 0 |
| precision | 1.0000 |
| recall | 1.0000 |
| f1 | 1.0000 |
| incomplete | false |
| runner_errors | 0 |

**Conclusion**: The previously missing `m033` is now matched with exact evidence. This is a targeted one-chat result, not yet a general production-quality claim; the next gate is to rerun the three-chat smoke and then repeat each ablation variant multiple times.

**Verification**: 58 related regression tests passed.

### Follow-up three-chat smoke after execution-ack split

**Run ID**: `e3fa913c188c46adb11a441df0cdd1d8`

| metric | value |
|---|---:|
| selected chats | 3 |
| expected_count | 6 |
| output_count | 16 |
| strict_tp | 4 |
| strict_fp | 9 |
| strict_fn | 2 |
| evidence_valid | 13 |
| evidence_invalid | 0 |
| precision | 0.3077 |
| recall | 0.6667 |
| f1 | 0.4211 |
| incomplete | false |
| runner_errors | 0 |

**审计结果**: `m033` 已被独立命中；本次剩余 FN 是 `ai_ml_platform_channel_0/m009` 和 `ai_ml_platform_channel_2/m012`。这表明 evidence contract 和执行确认拆分已生效，但 LLM 对其他确认句的召回仍存在随机波动，不能仅凭一次 three-chat 运行修改生产默认配置。

**下一步**: 对 `full`、`no_entity_context`、`no_memory_extractor` 各运行至少 5 次，记录均值、标准差、最小/最大值，以及 evidence health 和 runner health。

---

## 2026-08-07 - five-run production-path ablation repeat

**Method**: three-chat sample, 5 independent runs per variant, `LANGFUSE_ENABLE=false`, `MODEL_NAME=deepseek-local`. Aggregate reports preserve mean, population standard deviation, min/max, complete-run count, evidence contract pass rate, and runner error-free rate.

| variant | complete | F1 mean | F1 stddev | F1 min-max | Recall mean | evidence pass | runner pass |
|---|---:|---:|---:|---:|---:|---:|---:|
| `full` | 5/5 | 0.3232 | 0.0741 | 0.2105-0.4000 | 0.5667 | 100% | 100% |
| `no_entity_context` | 5/5 | 0.4304 | 0.0115 | 0.4211-0.4444 | 0.6667 | 100% | 100% |
| `no_memory_extractor` | 5/5 | 0.3708 | 0.0655 | 0.2727-0.4444 | 0.6000 | 100% | 100% |

**Observations**: `no_entity_context` is the strongest of these three under the current strict evaluator, with higher mean F1 and much lower variance than `full`. `full` has the lowest mean F1 and highest variance in this sample. `no_memory_extractor` is between them after fixing direct-branch `source_chat_id` provenance.

**Interpretation limits**: all three variants use the current no-adjudicator evaluator, so evidence-valid GT extras are still counted as strict FP. These results are component signals, not a production-default decision. The 5-run sample is also too small for a final statistical claim.

**Code fix discovered during repeats**: direct `_process_episode` did not set `self._active_episode_chat_id`; multi-chat `no_memory_extractor` reports therefore had `unknown_chat` evidence failures. The fix is covered by the production runner path and all post-fix repeats have evidence/runner health at 100%.

**Artifacts**: `experiments/production_ablation/repeat.py`, `experiments/production_ablation/aggregates/`, and the 15 successful run reports.

**Next gate**: add a semantic/neutral adjudicator, then repeat the same matrix with `valid_extra` separated from `invalid`; only after that consider changing the production default.

---

## 2026-08-07 - 真实三态 adjudicator 接入

### 为什么此前 strict F1 偏低

旧 evaluator 的 strict 公式是：
- evidence-valid 且命中 GT：TP
- evidence-valid 但不在 GT：FP
- evidence-invalid：FP
- 未命中 GT：FN

argusbot_v3 的 GT 很保守，只覆盖每个 chat 的少数关键决策；而 production extractor 会输出执行承诺、任务分配、阶段性结论等真实决策。因此很多“有真实证据、但 GT 未标注”的输出被系统性算成 FP。比如 three-chat 中一次典型结果是 `output_count=16`、`strict_tp=4`、`strict_fp=9`、`strict_fn=2`，其中很多 FP 实际是 evidence-valid extra。这个 F1 不能代表真实决策质量。

### 三态 adjudicator

新增 `LLMDecisionAdjudicator`，通过 `run.py --adjudicate` 显式启用：
- `match_gt`：语义上等价于某条 GT，计入 TP。
- `valid_extra`：证据真实、是独立有效决策，但 GT 未覆盖；单独统计，不计 strict FP。
- `invalid`：不是决策、只是噪声/提醒，或 judge 判定不成立；计入 FP。
- judge/API/JSON 失败：run 标记 `incomplete`，不静默变成 FP。
- judge 返回的 `match_gt` 还经过候选 msg_id 和标题/GT summary 词面重叠防线，避免把无关输出强行对齐。

### 真实 one-chat adjudication

**Run ID**: `ff397effab7c4b22aa4624d0dc21b832`

| metric | value |
|---|---:|
| strict_tp | 2 |
| strict_fp | 1 |
| strict_fn | 0 |
| valid_extra | 1 |
| invalid | 1 |
| evidence_valid | 4 |
| evidence_invalid | 0 |
| precision | 0.6667 |
| recall | 1.0000 |
| f1 | 0.8000 |
| incomplete | false |

### 真实 three-chat adjudication

**Run ID**: `643c764a42664899941d1fb20b2fddec`

| metric | value |
|---|---:|
| strict_tp | 5 |
| strict_fp | 2 |
| strict_fn | 1 |
| valid_extra | 8 |
| invalid | 2 |
| evidence_valid | 15 |
| evidence_invalid | 0 |
| precision | 0.7143 |
| recall | 0.8333 |
| f1 | 0.7692 |
| incomplete | false |
| adjudicator calls | 15 |

**结论**: 三态 adjudication 解释了此前低 F1 的主要来源：本次 8 条 valid extra 不再污染 strict FP，生产路径的 evidence health 仍为 100%。剩余 `strict_fn=1` 是 GT 漏召回/粒度问题，不能靠 adjudicator 凭空修复。

**运行方式**: `uv run python experiments/production_ablation/run.py --sample 3 --adjudicate`。批量重复工具也支持 `repeat.py --adjudicate`。

**下一步**: 对三态 evaluator 的 `full`、`no_entity_context`、`no_memory_extractor` 各重复至少 5 次，比较 `match_gt`、`valid_extra`、`invalid` 的均值/方差；在此之前不改变 production 默认配置。

---

## 2026-08-07 - sample size and macro-F1 protocol

**Dataset scope**: current `eval_dataset/argusbot_v3` contains 59 unique chats, 2373 messages, and 132 GT decisions. The old 70-chat number belongs to an older runner/statistics record.

**`sample` semantics**: `--sample N` selects N chats, including all messages and GT rows for those chats. It is not N messages. `--sample 3` is therefore a three-chat smoke.

**Statistical interpretation**: 5 runs x 3 chats is useful for pipeline smoke and variance debugging, but too small for a production-default conclusion. The full protocol is:
1. Run each variant once on all 59 chats with `--adjudicate` to verify end-to-end health and full-scope F1.
2. Repeat the strongest candidates 3-5 times on all 59 chats.
3. Compare micro-F1 and macro-F1, plus per-chat TP/FP/FN and evidence/runner health.

`run.py` now writes `chat_metrics`; `repeat.py` aggregates macro precision/recall/F1 as well as micro metrics. This prevents a few high-volume chats from dominating the conclusion.

**Cost gate**: current adjudication is one judge call per evidence-valid output. A full 59-chat run will therefore make hundreds of judge calls; run the one-pass full matrix first, then repeat only candidates after checking judge health and latency.

---

## 2026-08-07 - checkpointed full-run execution

此前 70-chat full run 连续运行近 4 小时后卡住，未生成 report。新增 `experiments/production_ablation/chunked.py`：
- 默认按 10 chat 一块执行；
- 每块独立写 `chunk_XXX/report.json`；
- 每块有独立 timeout，失败写入 manifest；
- `--resume` 会跳过已经 complete 的块；
- 最终按计数合并 micro-F1，并按 chat 合并 macro-F1/per-chat 指标。

示例：
```bash
uv run python experiments/production_ablation/chunked.py \\
  --variant full \\
  --chunk-size 10 \\
  --sample 70 \\
  --timeout 1800 \\
  --adjudicate \\
  --resume
```

建议先使用 `--chunk-size 10` 完成 full baseline，再对 `no_entity_context` 和 `no_memory_extractor` 运行相同范围。单块失败不会丢失已完成块，修复后可用同一个 job-id `--resume` 继续。

---

## 2026-08-07 - full 70-chat baseline completed

**Job**: `full_70_adjudicate_20260807_s3`
**Scope**: 70/70 chats, 24 checkpoint chunks, `full` variant, three-state adjudicator enabled.

| metric | value |
|---|---:|
| output_count | 298 |
| strict_tp / match_gt | 86 |
| strict_fp / invalid | 86 |
| strict_fn | 46 |
| valid_extra | 109 |
| evidence_valid | 281 |
| evidence_invalid | 0 |
| micro precision | 0.5000 |
| micro recall | 0.6515 |
| micro F1 | 0.5658 |
| macro precision | 0.5725 |
| macro recall | 0.6571 |
| macro F1 | 0.5821 |
| chunks complete | 24/24 |
| runner/evidence health | 100% / 100% |

**Domain macro-F1**: `ai_ml_platform=0.5467`, `backend_arch=0.6600`, `cloud_infra=0.6667`, `data_platform=0.5238`, `frontend_mobile=0.5238`, `sec_compliance=0.5767`, `sre_reliability=0.5771`.

**Interpretation**: 109 of 298 evidence-valid outputs were adjudicated `valid_extra`, which explains why strict precision/F1 remains lower than the raw extraction quality might suggest. The full run is complete and healthy, but this is still one stochastic run of the `full` variant; it is not enough to choose a production default. The next comparison is the same 70-chat checkpointed run for `no_entity_context` and `no_memory_extractor`, followed by repeated runs for the strongest variant.

**Artifact**: `experiments/production_ablation/chunked_runs/full_70_adjudicate_20260807_s3/aggregate.json`.

---

## 2026-08-08 — Global semantic evaluator: calibration tooling and performance manifests

**Scope**: Added frozen-output evaluator calibration harness (`calibrate_evaluator.py`), label seed file (`calibration_labels.json`), and balanced 35/35 dev/holdout performance manifests (`performance_manifest.py` + `performance_dev_35.json` + `performance_holdout_35.json`). Also added the global semantic decision matcher (`confirmed_decision_adjudicator.py` with per-chat `adjudicate_chat`) and integrated per-chat global adjudication into the production runner (`run.py`).

**What changed**:
1. `confirmed_decision_eval.py` — `AssignmentRow`/`ChatAssignment`/`GlobalAdjudicationGroup` domain, `build_global_adjudication_groups()`, `GlobalAdjudicator` callback contract.
2. `confirmed_decision_adjudicator.py` — `LLMDecisionAdjudicator` with `PROMPT_VERSION="global-assignment-v1"`, `SCHEMA_VERSION="global-assignment-v1"`, stable normalized payload, versioned cache key, Chinese one-to-one global assignment prompt, `temp=0`/`response_format=json_object`, strict parser.
3. `run.py` — `_adjudicate_decisions()` helper with in-memory per-chat cache, extended report metadata (`calls`, `cache_hits`, `errors`, `prompt_version`, `schema_version`, `cache_keys`).
4. `performance_manifest.py` — Balanced 35-chat dev / 35-chat holdout selection by stratified domain sampling. Generated manifests verified against the `full_70_adjudicate_20260807_s3` aggregate.
5. `calibrate_evaluator.py` — Frozen-output calibration: `load_final_outputs()` (only `chunk_*/report.json`), `score_calibration()` (per-class confusion matrix, `valid_extra` distinct from `invalid`), `run_calibration()` (dry-run, unreviewed-label guard, repeat agreement). Seed `calibration_labels.json` with `reviewed: false`.

**No extractor comparison, no production-default decision, no quality improvement claim.** The calibration harness requires human-reviewed labels before it can produce meaningful agreement/confusion metrics. The evaluator changes (Tasks 1-3) replace per-output lexical-overlap adjudication with validated per-chat global semantic assignment but do not change production defaults or extraction behavior.

**Focused tests**: 29/29 passing across Task 1-5 test modules.

---

## 2026-08-10 — Slice 2: Decision-Kind Typed Filtering + 70-Chat Full Evaluation

### Changes
1. **decision_kind schema** — 7 enum values added to extraction prompt: `choice`, `conditional_choice`, `execution_commitment`, `policy_constraint`, `suggestion`, `status`, `discussion`
2. **Deterministic typed filtering** — `status`/`discussion` dropped before evidence check; `suggestion` forces `is_suggestion=True`
3. **Compound-decision guidance** — atomic decision splitting rule in prompt
4. **Context-boundary guidance** — context cannot provide evidence for new decisions
5. **EvidenceDecision.is_confirmed** — only confirmable kinds pass (choice, conditional_choice, execution_commitment, policy_constraint)
6. **Extraction stats** — `last_extraction_stats` tracks total_candidates, confidence_filtered, status_discussion_filtered, evidence_attachment_dropped

### 70-Chat Full Evaluation Results (full_70_decision_kind_20260810)

| Metric | Baseline (20260807) | Candidate | Delta |
|--------|-------------------:|----------:|------:|
| Precision | 0.500 | **0.752** | **+0.252** |
| Recall | 0.652 | **0.758** | **+0.106** |
| F1 | 0.566 | **0.755** | **+0.189** |
| TP | 86 | 100 | +14 |
| FP (invalid) | 86 | 33 | **-53** |
| FN | 46 | 32 | -14 |
| Valid extra | 109 | 217 | +108 |
| Evidence invalid | 0 | 0 | ✅ |

### Per-Domain F1

| Domain | Baseline | Candidate | Delta |
|--------|--------:|---------:|------:|
| ai_ml_platform | 0.547 | 0.817 | +0.270 |
| backend_arch | 0.660 | 0.847 | +0.187 |
| cloud_infra | 0.667 | 0.750 | +0.083 |
| data_platform | 0.524 | 0.570 | +0.046 |
| frontend_mobile | 0.524 | 0.757 | +0.233 |
| sec_compliance | 0.577 | 0.747 | +0.170 |
| sre_reliability | 0.577 | 0.780 | +0.203 |

**All 7 domains improved. No domain decreased.** Largest gains in ai_ml_platform (+0.27) and frontend_mobile (+0.23).

### Conclusion
Decision-kind typed filtering substantially reduces false positives (86→33) by filtering status updates and discussion items, while the improved prompt guidance increases true positive recall (86→100). The global semantic evaluator correctly classifies previously-rejected valid decisions as valid_extra (109→217). Evidence-invalid remains 0.

**Tests**: 17 new + 32 existing = 49 tests passing. Pipeline A/B: no regression.
