# Hermes handoff 机制

# Handoff机制解释



Handoff是Kanban系统中worker完成任务时向下游worker或人类传递工作结果的核心机制，通过`kanban\_complete\(summary=\.\.\., metadata=\.\.\.\)`实现 \[1\]\(\#1\-0\) 。



## 核心组成



### Summary

人类可读的1\-3句话描述，说明具体完成了什么 \[2\]\(\#1\-1\) 。例如：

```Plain Text
"shipped rate limiter — token bucket, keys on user_id with IP fallback, 14 tests pass"
```



### Metadata

机器可读的结构化JSON字典，包含具体的事实数据 \[3\]\(\#1\-2\) ：

- `changed\_files`: 修改的文件列表

- `tests\_run`: 运行的测试数量

- `decisions`: 做出的技术决策

- `findings`: 研究发现

- `verification`: 验证步骤

    

## 工作流程



下游worker通过`kanban\_show\(\)`读取handoff信息 \[4\]\(\#1\-3\) ：



1. **Prior attempts**: 当前任务的历史尝试（outcome、summary、error、metadata），避免重复失败路径

2. **Parent task results**: 每个父任务最近一次完成运行的summary和metadata，了解上游工作如何完成

    

## 典型示例



### 编码任务

```Python
kanban_complete(
    summary="shipped rate limiter — token bucket, keys on user_id with IP fallback, 14 tests pass",
    metadata={
        "changed_files": ["rate_limiter.py", "tests/test_rate_limiter.py"],
        "tests_run": 14,
        "tests_passed": 14,
        "decisions": ["user_id primary, IP fallback for unauthenticated requests"],
    },
)
``` [5](#1-4) 

### 研究任务
```python
kanban_complete(
    summary="3 competing libraries reviewed; vLLM wins on throughput, SGLang on latency, Tensorrt-LLM on memory efficiency",
    metadata={
        "sources_read": 12,
        "recommendation": "vLLM",
        "benchmarks": {"vllm": 1.0, "sglang": 0.87, "trtllm": 0.72},
    },
)
``` [6](#1-5) 

## Review-required模式

对于需要人工审查的代码变更，使用block而非complete [7](#1-6) ：

```python
kanban_comment(
    body="review-required handoff:\n" + json.dumps({
        "changed_files": ["rate_limiter.py", "tests/test_rate_limiter.py"],
        "tests_run": 14,
        "tests_passed": 14,
        "diff_path": "/path/to/worktree",
        "decisions": ["user_id primary, IP fallback for unauthenticated requests"],
    }, indent=2),
)
kanban_block(
    reason="review-required: rate limiter shipped, 14/14 tests pass — needs eyes on the user_id/IP fallback choice before merging",
)
```



## 数据持久化



Handoff数据存储在`task\_runs`表中，每次任务尝试都会创建新的run行 \[8\]\(\#1\-7\) 。这确保了完整的尝试历史，便于postmortem分析。



## Gateway通知



当任务完成时，gateway notifier会发送包含summary的通知到订阅的chat \[9\]\(\#1\-8\) 。



## Notes



Handoff是Kanban区别于传统TODO系统的关键特性，它使下游worker能够结构化地获取上游工作结果，而不需要翻阅评论和工作输出 \[1\]\(\#1\-0\) 。推荐在metadata中包含changed\_files、verification、dependencies、blocked\_reason、retry\_notes、residual\_risk等字段。



