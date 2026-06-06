# Hermes agent Kanban

# Kanban机制解释



Kanban是Hermes Agent中的一个持久化任务协调系统，基于SQLite数据库实现，用于多个Hermes profile之间的协作 \[1\]\(\#0\-0\) 。



## 核心概念



### 与`delegate\_task`的区别

Kanban不同于`delegate\_task`，它是一个持久化的消息队列\+状态机，而不是RPC调用 \[2\]\(\#0\-1\) ：



|特性|delegate\_task|Kanban|
|---|---|---|
|形态|RPC调用\(fork→join\)|持久化消息队列\+状态机|
|父任务|阻塞直到子任务返回|创建后fire\-and\-forget|
|子任务身份|匿名子agent|具有持久化内存的命名profile|
|可恢复性|无\-失败即失败|block→unblock→重运行；crash→reclaim|
|人工介入|不支持|任意时刻可comment/unblock|



### 核心组件



**Board（看板）**：独立的任务队列，每个board有自己的SQLite数据库、workspaces目录和dispatcher循环 \[3\]\(\#0\-2\) 。单项目用户使用`default` board，多项目用户可以为每个项目创建独立的board。



**Task（任务）**：数据库中的一行，包含title、body、assignee（profile名称）、status（triage/todo/ready/running/blocked/done/archived）、tenant命名空间等 \[4\]\(\#0\-3\) 。



**Dispatcher（调度器）**：长生命周期循环，默认每60秒运行一次，负责回收过期声明、提升ready任务、原子性地声明任务并派生指定的profile \[5\]\(\#0\-4\) 。默认运行在gateway内部。



**Worker（工作进程）**：由dispatcher派生的完整OS进程，每个worker有自己的身份和持久化内存 \[1\]\(\#0\-0\) 。



## 工作机制



### 两个交互界面



系统提供两个前端界面，都通过相同的`kanban\_db`层路由 \[6\]\(\#0\-5\) ：



1. **Agent通过****`kanban\_\*`****工具集驱动**：包括`kanban\_show`、`kanban\_complete`、`kanban\_block`、`kanban\_heartbeat`、`kanban\_comment`、`kanban\_create`、`kanban\_link`等工具。Dispatcher在派生worker时将这些工具加入其schema。

    

2. **用户通过CLI驱动**：使用`hermes kanban \.\.\.`命令、`/kanban \.\.\.`斜杠命令或dashboard界面。

    

### 任务生命周期



任务通过以下状态流转 \[7\]\(\#0\-6\) ：



```Plain Text
triage → todo → ready → running → blocked/done/archived
```



- **triage**：原始想法，默认会自动运行decomposer进行任务分解

- **todo**：已创建但等待依赖或未分配

- **ready**：已分配，等待dispatcher声明

- **running**：worker正在执行

- **blocked**：worker请求人工输入或熔断器触发

- **done**：已完成

- **archived**：已归档

    

### Worker执行流程



典型的worker执行流程如下 \[8\]\(\#0\-7\) ：



```Python
kanban_show()  # 读取任务信息、父任务handoff、历史尝试
# (执行实际工作)
kanban_heartbeat(note="进度更新")
kanban_complete(
    summary="完成摘要",
    metadata={"changed_files": [...], "tests_run": N}
)
```



### 依赖管理



通过`task\_links`表记录parent→child依赖关系，dispatcher在所有父任务完成时将子任务从`todo`提升到`ready` \[9\]\(\#0\-8\) 。



## 关键特性



### 持久化和审计

所有任务、评论、链接都持久化在SQLite中，可以承受agent重启，支持人工审计 \[2\]\(\#0\-1\) 。



### 熔断器和崩溃恢复

Dispatcher有两个防线 \[10\]\(\#0\-9\) ：

- **熔断器**：连续N次失败后自动block任务，防止无限重试

- **崩溃检测**：检测worker PID消失但TTL未过期的情况，回收任务

    

### 结构化handoff

`kanban\_complete\(summary=\.\.\., metadata=\.\.\.\)`是主要的handoff通道，下游worker可以通过`kanban\_show`读取父任务的summary和metadata \[11\]\(\#0\-10\) 。



## Notes



Kanban系统设计用于处理`delegate\_task`无法覆盖的工作负载：研究triage、定时运维、数字孪生、工程管道、fleet工作等 \[12\]\(\#0\-11\) 。完整的设计规范参见`docs/hermes\-kanban\-v1\-spec\.pdf`。

