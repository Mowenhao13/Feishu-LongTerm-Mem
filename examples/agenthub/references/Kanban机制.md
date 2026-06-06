# Kanban机制

# Vibe Kanban 看板机制 vs 传统多 Agent 协作



Vibe Kanban 的看板机制与传统多 agent 协作的核心区别在于：**Vibe Kanban 将项目管理（看板）与代理执行（Workspace）分离，通过结构化的工作流实现人工监督下的 AI 协作**。 



## 核心区别对比



|维度|Vibe Kanban 看板机制|传统多 Agent 协作|
|---|---|---|
|**工作组织**|基于 Issue 的看板规划，支持状态、优先级、标签、父子关系 \[2\]\(\#3\-1\)|通常基于对话或任务列表，缺乏结构化项目管理|
|**执行隔离**|每个 Workspace 使用独立的 Git worktree，提供分支、终端和开发服务器 \[3\]\(\#3\-2\)|通常共享执行环境，可能相互干扰|
|**人工监督**|内置差异审查、内联评论、预览测试，人工在每个环节介入 \[4\]\(\#3\-3\)|代理间直接协作，人工介入点较少|
|**多代理协作**|单个 Workspace 内支持多会话，可并行运行不同代理或审查代理 \[5\]\(\#3\-4\)|代理间直接通信，缺乏会话隔离|
|**工作流**|规划（Issue）→ 执行（Workspace）→ 审查（Diff）→ 合并（PR） \[6\]\(\#3\-5\)|通常线性执行，缺乏明确的阶段划分|



## Vibe Kanban 的看板机制



### Issue\-Workspace 分离架构

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=Y2Y1ZGY3ODE3NzlkOTc5N2Q2ZGNmNDdkNDliMGM0MzBfODNlODdlMzUzMDE4MzQxZjlkMDk3OGYzZjYxZGRmOWFfSUQ6NzY0MzI4OTI0MDgyMTk3NjI1M18xNzgwMzAzMjE3OjE3ODAzODk2MTdfVjM)



**关键设计：**

- **Issue 描述工作**：Issue 代表要完成的功能或问题，包含标题、描述、优先级、标签等元数据 \[7\]\(\#3\-6\) 

- **Workspace 执行工作**：Workspace 是隔离的执行环境，每个 Workspace 关联特定的 Git 分支和代理配置 \[3\]\(\#3\-2\) 

- **一对多关系**：单个 Issue 可以关联多个 Workspace，支持并行执行和审查 \[8\]\(\#3\-7\) 

    

### 多会话机制



Vibe Kanban 支持在单个 Workspace 内创建多个代理对话会话，这是与传统多 agent 协作的重要区别： \[5\]\(\#3\-4\) 

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MzM0ZmVhY2E0Yzc1NmYwYmM0MWRlMGVkODgzN2M5YjZfNWFmZjczNzQ0YWEwODBlZTY5MzAwZjhiOGY1NDQwY2VfSUQ6NzY0MzI4OTM3Mjg4MTUwNTI0MV8xNzgwMzAzMjE3OjE3ODAzODk2MTdfVjM)



**优势：**

- 绕过对话限制：不同会话独立管理上下文

- 并行工作：同时运行不同代理处理不同方面

- 隔离审查：在单独线程中启动审查代理，不影响主执行

    

### 审查和反馈循环



Vibe Kanban 强调人工审查，与传统多 agent 协作的\&\#34;自动协作\&\#34;形成对比： \[4\]\(\#3\-3\) 



**审查机制：**

- 差异面板：显示文件树和代码变更

- 内联评论：直接在差异上添加评论，反馈给代理

- GitHub 集成：Workspace 链接到 PR 时可查看 GitHub 评论

    

## 传统多 Agent 协作模式



传统多 agent 协作通常采用以下模式：



### 直接协作模式

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=N2FjZTY0NzY1NDNhNjVmMzU5OTlmNGM5MzdmMWI0M2RfM2QyYTBiY2UxMDgwNzlmYzlmZGZiZjRlNDJiMmI3YTVfSUQ6NzY0MzI4OTQ5NjEyOTM0MjQwNl8xNzgwMzAzMjE3OjE3ODAzODk2MTdfVjM)



**特点：**

- 代理间直接通信，缺乏人工监督

- 通常共享执行环境

- 缺乏结构化的项目管理层

- 工作流线性，难以并行和审查

    

### Vibe Kanban 的改进



Vibe Kanban 通过看板机制解决了传统模式的痛点：



|痛点|Vibe Kanban 解决方案|
|---|---|
|缺乏项目管理|Kanban board 提供结构化 Issue 管理 \[9\]\(\#3\-8\)|
|执行环境冲突|Git worktree 隔离确保安全 \[3\]\(\#3\-2\)|
|难以审查变更|集成差异查看器和内联评论 \[4\]\(\#3\-3\)|
|测试需要切换上下文|内置浏览器预览 \[10\]\(\#3\-9\)|
|代理接口不统一|统一的执行器抽象支持 10\+ 代理 \[11\]\(\#3\-10\)|



## Notes



- Vibe Kanban 的看板机制本质上是一个**人机协作框架**，而非纯粹的自动化多 agent 系统

- 系统支持通过 MCP 服务器让代理创建和管理 Issue，实现半自动化的规划流程 

- 多仓库支持允许在单个 Workspace 中处理多个代码库，这是传统多 agent 系统通常不具备的能力 

