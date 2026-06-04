# Enhanced Sleep — 全局记忆整理与跨群决策关联

## 动机

当前 Sleep 机制只做同 topic 内部的去重和冲突检测，不跨 chat_id，不做全局记忆整理。对于 multi_chat 场景（多个群聊讨论同一技术选型），不同群聊中相似/重复的决策无法被关联和压缩，导致 FP 增多。

本分支的目标是增强 SleepManager 的跨群决策关联能力，并验证其对 eval 指标的影响。

## 设计

### 1. SleepManager 支持外部决策加载

**现状**：SleepManager 只从 `self._graph.get_all_decisions()` 获取决策。

**改动**：增加 `source_path` 参数，允许从指定路径加载决策到 graph：

```python
class SleepManager:
    def __init__(self, ..., source_path: Optional[str] = None):
        ...
        self._source_path = source_path
```

当 `source_path` 被指定时：
- 从该路径读取决策 JSON 文件
- 用 `_graph.upsert_decision()` 加载到 graph
- 后续 sleep 流程不变（light_sleep → deep_sleep → promote → wave）

### 2. 跨群 topic 匹配

**现状**：`_fast_prefilter` 要求 `a.topic_id == b.topic_id`。

**改动**：对跨 chat_id 的决策对放宽条件：

```python
def _fast_prefilter(self, a, b):
    if a.topic_id == b.topic_id:
        return True
    # 跨群：不同 chat_id 但 topic 语义相近
    if a.chat_id != b.chat_id:
        sim = self._summary_similarity(a.topic_id, b.topic_id)
        if sim >= 0.5:
            return True
    return False
```

### 3. 备份 & 测试脚本

`scripts/run_sleep_test.py`:

1. 运行 eval（不清除 mem-data）
2. 备份 mem-data → `mem-data_backup/{dataset}_{timestamp}/`
3. 加载备份到 SleepManager
4. 运行完整的 sleep 周期
5. 输出整理报告（去重数量、冲突数量、噪音修剪数量）
6. 用整理后的决策重新计算 F1

### 4. 对比基准

| 数据集 | v3 最佳 F1 | sleep 后 F1 | 变化 |
|---|---|---|---|
| single_chat | 83.08% | ? | ? |
| multi_chat | 71.26% | ? | ? |

### 5. 不修改的部分

- 不修改 eval_runner.py 的测试流程
- 不修改 episode 拆分逻辑
- 不修改 extractor prompt
- 不修改 comparator 匹配逻辑

## 改动文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/memory/sleep.py` | 修改 | 支持 source_path 参数、跨群 topic 匹配 |
| `scripts/run_sleep_test.py` | 新增 | 备份 + sleep + 对比测试脚本 |

## 测试方法

1. 在 feat/enhanced-sleep 分支上
2. 先运行 baseline eval（single_chat 和 multi_chat）确认 F1 与 v3 一致
3. 运行 run_sleep_test.py 对每个数据集做 sleep 整理
4. 比较 sleep 前后的 F1 差异