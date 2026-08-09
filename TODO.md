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
  - **freeze gate 未通过**
  - deepseek-local (校内网关): match_gt P=0.24, valid_extra P=0.50, agreement=0.93
  - deepseek-v4-flash (API): **余额不足 (HTTP 402)**
  - 已确认 production evaluator 代码已使用 LLMDecisionAdjudicator（非 lexical veto）
  - 根因：deepseek-local 模型能力不足以达到校准阈值

## ⛔ 阻塞

**需要充值 deepseek API 余额**才能用 `deepseek-v4-flash` 作为 judge model 完成校准。

或者可选方案：
1. 充值 deepseek API → 用 deepseek-v4-flash 重跑校准
2. 配置其他可用的强模型（如 `HYPERMEM_JUDGE_*` 指向其他 provider）
3. 降低 freeze gate 阈值（不推荐，违反设计文档）

```bash
# 充值后运行：
HYPERMEM_JUDGE_MODEL=deepseek-v4-flash \
HYPERMEM_JUDGE_BASE_URL=https://api.deepseek.com \
HYPERMEM_JUDGE_API_KEY=<your-key> \
uv run --active python experiments/production_ablation/calibrate_evaluator.py \
  --reports-root experiments/production_ablation/chunked_runs/full_70_adjudicate_20260807_s3 \
  --labels experiments/production_ablation/reference_labels.json \
  --manifest eval_dataset/argusbot_v3/performance_dev_35.json \
  --repeats 3 \
  --output experiments/production_ablation/calibration_report.json
```

## 后续步骤（阻塞解除后）

- [ ] 用强 judge model 重跑校准，确认 freeze gate 通过
- [ ] 合并到 `feat/project-dev-watchdog`
- [ ] Phase 0 通过后，启动第 2 切片（Extraction 层）
