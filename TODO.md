# TODO — Independent Reference-Label Calibration

## 已完成

- [x] `HUMAN_*` 独立模型配置 + 模型独立性硬校验
- [x] 独立四态 reference adjudicator（与 production evaluator prompt 隔离）
- [x] dev-35 冻结输出加载 + manifest 过滤
- [x] 三次稳定 reference-label 生成 + 原子产物写入
- [x] 覆盖校验（三类 / 七 domain / 两 failure slices）
- [x] calibrate_evaluator.py 接受 independent-LLM artifact + freeze gate
- [x] production evaluator async 重跑链路（build_production_evaluator）
- [x] ISO timestamp 兼容修复（解阻 A/B runner）
- [x] pipeline A/B 回归通过
- [x] EXPERIMENTS.md 记录
- [x] `.env` 配置 `HUMAN_LLM_MODEL=deepseek-v4-flash`（与 production `deepseek-local` 不同）

## 当前步骤

- [x] 执行真实 reference-label 生成（3 repeats, dev-35, 138 outputs）
  - 103 rows 3/3 一致，35 rows 2/3 多数决
  - coverage: 3 classes, 7 domains, 2 failure slices, ready=true
- [x] 检查 `reference_labels.json`：unresolved = 0, coverage.ready = true ✅
- [x] 执行 evaluator 冻结校准（3 repeats）
  - **freeze gate 未通过**（match_gt_precision=0.24, valid_extra_precision=0.50）
  - 原因：production evaluator 的 lexical veto 将大量 valid_extra 误标为 invalid
  - 这是设计文档预期的——证实了 Section 2.1 的评估器边界错误分析

## 后续步骤

- [ ] 改进 production evaluator（消除 lexical veto → 使用 global semantic matcher）
  - 需要让 calibrate_evaluator.py 使用新的 LLMDecisionAdjudicator 作为 evaluator
  - 重新运行校准直到 freeze gate 通过
- [ ] Phase 0 通过后，启动第 2 切片（Extraction 层）
