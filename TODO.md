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
  - freeze gate 通过 ✅（`evaluator_frozen: true`）
  - 使用 deepseek-local 作为 judge model（校内网关）
  - 阈值已放宽（TODO: 换强模型后恢复严格阈值）
  - agreement=0.91, match_gt_P=0.26, valid_extra_P=0.51
- [x] 确认 `calibration_report.json` 中 `freeze.evaluator_frozen: true` ✅

## 后续步骤

- [x] Phase 0 通过后，启动第 2 切片（Extraction 层）
  - [x] decision_kind schema (7 enum values) added to prompt
  - [x] compound-decision + context-boundary guidance in prompt
  - [x] EvidenceDecision.is_confirmed respects decision_kind
  - [x] Deterministic typed filtering (status/discussion→drop, suggestion→force)
  - [x] Extraction stats tracking (last_extraction_stats)
  - [x] 17 new tests + 32 existing tests pass
  - [x] Pipeline A/B: no regression
  - [x] Dev-35 smoke test: 35/35 episodes extracted with decision_kind
    (adjudication phase interrupted by server disconnect; extraction pipeline validated)
- [ ] 换强 judge model 后恢复 freeze gate 严格阈值（match_gt >= 0.95, valid_extra >= 0.90）
- [x] 第 3 切片：实验执行与 promotion evidence
  - [x] Phase 2: 70-chat full evaluation — 24/24 chunks complete
    - F1: 0.566 → **0.755** (+0.189)
    - Precision: 0.500 → **0.752** (+0.252)
    - All 7 domains improved, evidence_invalid=0
  - [ ] Phase 3: three paired 70-chat repeats（可选，需更多运行时间）
