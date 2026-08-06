# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## 5. A/B 测试验证

每次加入新功能后，必须运行全量 A/B 测试来验证对最终结果的影响：

### 超图架构对比（已有）
对比 4 层超图和 2 层超图的架构差异：
```bash
python experiments/two_layer_vs_four_layer/run_experiments.py --all
```

### 提取管道对比（新增）
对比单阶段（direct）和两阶段（two_stage）提取管道的差异：
```bash
python experiments/pipeline_ab_test/run.py --all
```

测试内容包括：
1. **实体/关系提取质量**：对比两阶段 vs 单阶段的实体/关系/事实提取准确率
2. **决策提取质量**：对比两阶段 vs 单阶段的决策 Precision / Recall / F1
3. **LLM 调用成本**：两阶段模式下总 LLM 调用次数 vs 单阶段
4. **端到端延迟**：从消息到决策入库的完整耗时

两阶段模式（two_stage）：
- Stage 1: MemoryExtractor — 提取实体/关系/事实（1次 LLM 调用）
- Stage 2: 基于实体上下文的决策提取（1次 LLM 调用）
- 总调用：2次 LLM / episode

单阶段模式（direct，baseline）：
- SimpleLLMExtractor.extract_decision — 直接提取决策（1次 LLM 调用）
- 总调用：1次 LLM / episode

### 提交要求

必须在测试报告中确认：
1. **Precision / Recall / F1 不能下降**（或下降原因有合理解释）
2. **LLM 调用次数不能显著增加**（避免成本膨胀）
3. 确认改动没有破坏已有功能

如果改动后测试结果有变化，在 commit message 中注明影响。

---

## 6. 实验框架

### 消融实验
对比 8 个管道变体，量化每个组件的贡献度：
```bash
uv run python experiments/ablation/run_ablation.py --mode ablation

# 快速验证（只跑前 3 个 chat）
uv run python experiments/ablation/run_ablation.py --mode ablation --sample 3
```

### 阈值扫描
对关键超参数做步进扫描，找最优值：
```bash
# embedding 相似度阈值 (0.3~0.8)
uv run python experiments/ablation/run_ablation.py \
    --mode threshold-scan \
    --param embedding_similarity \
    --range "0.3,0.8,0.05"

# MemoryExtractor 置信度阈值 (0.3~0.9)
uv run python experiments/ablation/run_ablation.py \
    --mode threshold-scan \
    --param confidence_threshold \
    --range "0.3,0.9,0.1"
```

### Claude Code 基线
对比纯 Agent 输出与分阶段管道的差距：
```bash
uv run python experiments/ablation/run_ablation.py --mode claude_code
```

### 实验结果记录
所有实验结果自动写入 `EXPERIMENTS.md`（项目根目录）。
每次 commit 前检查 `EXPERIMENTS.md` 是否有新记录，与代码改动一起提。

### 提交要求
1. **消融实验 Precision / Recall / F1 不能下降**（或下降原因有合理解释）
2. **阈值扫描结果确认当前参数在最优区间**
3. 实验记录（EXPERIMENTS.md）与代码改动一起提交

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
