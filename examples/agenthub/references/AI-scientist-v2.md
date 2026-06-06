# AI\-scientist\-v2

AI Scientist\-v2 系统通过分层架构实现多agent协作，使用 `AgentManager` 作为高层协调器，`ParallelAgent` 管理并行执行，`MinimalAgent` 在工作进程中执行具体任务 \[1\]\(\#2\-0\) 。



---



## 多Agent协作



系统采用主从架构，通过进程池实现并行执行：



```Plain Text
graph TD
    AM["AgentManager<br/>阶段协调器"] --> PA["ParallelAgent<br/>并行执行管理器"]
    PA --> PPE["ProcessPoolExecutor<br/>进程池"]
    PPE --> W1["Worker 1: MinimalAgent"]
    PPE --> W2["Worker 2: MinimalAgent"]
    PPE --> W3["Worker 3: MinimalAgent"]
    PA --> GPU["GPUManager<br/>资源分配"]
    GPU --> W1
    GPU --> W2
    GPU --> W3
```



`ParallelAgent` 初始化时创建 `ProcessPoolExecutor` 和 `GPUManager`，根据GPU数量自动调整worker数量 \[2\]\(\#2\-1\) 。每个worker进程通过 `\_process\_node\_wrapper` 静态方法创建独立的 `MinimalAgent` 实例 \[3\]\(\#2\-2\) 。



## 上下文管理



上下文通过三个层次管理：



### 1\. Journal和Node

`Journal` 跟踪所有实验节点，维护树结构和父子关系 \[4\]\(\#2\-3\) 。每个 `Node` 包含代码、执行结果、指标和VLM分析。



### 2\. 阶段状态

`AgentManager` 维护阶段历史和当前状态 \[1\]\(\#2\-0\) ：

```Python
self.stages: List[Stage] = []
self.journals: Dict[str, Journal] = {}
self.stage_history: List[StageTransition] = []
```



### 3\. 检查点机制

每个阶段完成后保存完整状态到pickle文件，支持中断恢复 \[5\]\(\#2\-4\) 。



## 消息传递



### 1\. LLM交互

通过 `query\(\)` 函数与LLM通信，使用 `FunctionSpec` 强制结构化输出 \[6\]\(\#2\-5\) 。



### 2\. 进程间通信

节点数据通过序列化/反序列化在进程间传递 \[7\]\(\#2\-6\) ：

```Python
node_data = node.to_dict()  # 主进程序列化
parent_node = Node.from_dict(node_data, journal=None)  # 工作进程反序列化
```



### 3\. GPU资源协调

`GPUManager` 通过进程ID分配GPU，通过环境变量 `CUDA\_VISIBLE\_DEVICES` 传递给工作进程 \[8\]\(\#2\-7\) 。



## 任务分解



### 1\. 阶段分解

研究过程分解为四个主要阶段 \[9\]\(\#2\-8\) ：



|阶段|目标|
|---|---|
|`initial\_implementation`|基础实现|
|`baseline\_tuning`|超参数调优|
|`creative\_research`|创造性研究|
|`ablation\_studies`|消融研究|



### 2\. 子阶段分解

每个主阶段可包含多个子阶段，通过 `\_create\_next\_substage` 动态生成 \[10\]\(\#2\-9\) 。



### 3\. 节点处理分解

根据父节点状态和当前阶段，节点处理分为不同类型 \[11\]\(\#2\-10\) ：



```Plain Text
graph TD
    A["parent_node"] --> B{is_buggy?}
    B -->|Yes| C["_debug"]
    B -->|No| D{stage 2?}
    D -->|Yes| E["_generate_hyperparam_tuning_node"]
    D -->|No| F{stage 4?}
    F -->|Yes| G["_generate_ablation_node"]
    F -->|No| H["_improve"]
    A --> I{parent_node is None?}
    I -->|Yes| J["_draft"]
```



### 4\. 并行任务选择

`\_select\_parallel\_nodes` 实现探索与利用的平衡，根据阶段特性选择不同策略 \[12\]\(\#2\-11\) 。



