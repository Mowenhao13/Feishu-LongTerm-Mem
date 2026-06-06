# context隔离机制

## 核心隔离机制

### 1\. Agent vs Session 所有权模型

Agent拥有provider实例，所有session共享这些实例；Session拥有状态数据，每个session的状态完全隔离 \[1\]\(\#0\-0\) 。Provider实例在session间共享，但通过`state`参数传递provider\-scoped的mutable state dict，确保每个session的状态独立 \[2\]\(\#0\-1\) 。



### 2\. source\_id 归属机制

每个`ContextProvider`必须提供唯一的`source\_id`，用于消息和工具的归属标记 \[3\]\(\#0\-2\) 。`SessionContext\.context\_messages`使用`dict\[str, list\[ChatMessage\]\]`结构，以`source\_id`为键存储各provider添加的消息 \[4\]\(\#0\-3\) 。



### 3\. SessionContext 隔离

每次`agent\.run\(\)`调用都会创建新的`SessionContext`实例，provider通过`before\_run`和`after\_run`方法修改这个context对象 \[5\]\(\#0\-4\) 。context包含：

- `input\_messages`: 只读的输入消息

- `context\_messages`: 按source\_id键入的消息字典

- `instructions`和`tools`: provider可追加的列表

    

### 4\. 消息过滤能力

框架支持按source\_id过滤消息，provider可以：

- 使用`context\.get\_messages\(sources=\[\.\.\.\]\)`获取特定来源的消息

- 使用`context\.get\_messages\(exclude\_sources=\[\.\.\.\]\)`排除特定来源的消息 \[6\]\(\#0\-5\) 

    

### 5\. 状态管理隔离

每个`AgentSession`维护一个`state: dict\[str, Any\]`，provider写入的值必须是JSON可序列化的 \[7\]\(\#0\-6\) 。Provider通过`state`参数访问provider\-scoped状态，通过`session\.state`访问跨provider状态 \[8\]\(\#0\-7\) 。



Jido框架在多agent协作中实现了多层context隔离机制，主要包括以下几个方面：

## Plugin State Isolation（插件状态隔离）

每个插件通过`state_key`选项在agent的状态中获得独立的命名空间，防止插件之间互相干扰状态 [1](#0-0) 。

```elixir
# ChatPlugin with state_key: :chat
agent.state = %{
  chat: %{messages: [], model: "gpt-4"},  # ChatPlugin state
  database: %{pool_size: 5}               # DatabasePlugin state
}
```

这种设计确保了插件只能访问和修改自己命名空间下的状态 [2](#0-1) 。

## Instance-Scoped Architecture（实例作用域架构）

Jido 2.0引入了实例作用域架构，不再使用全局单例，而是要求用户显式定义Jido实例模块并添加到监督树中 [3](#0-2) 。

```elixir
defmodule MyApp.Jido do
  use Jido, otp_app: :my_app
end

children = [
  MyApp.Jido
]
```

每个Jido实例拥有独立的Registry、TaskSupervisor和AgentSupervisor，实现了：
- 多个隔离的Jido实例可以在同一应用中运行
- 清晰的所有权和监督边界
- 更容易的测试隔离 [4](#0-3) 。

## InstanceManager（实例管理器）

`Jido.Agent.InstanceManager`提供键控单例注册表，用于管理每个逻辑上下文（用户会话、游戏房间、连接、对话）的一个agent实例 [5](#0-4) 。

关键特性：
- **键控单例**：每个键对应一个agent实例，按需查找或启动
- **自动生命周期**：空闲超时和附件跟踪
- **可选存储**：支持可插拔存储后端的休眠/恢复
- **多个注册表**：不同的agent类型可以使用不同的配置 [6](#0-5) 。

持久化键是管理器作用域的（`{manager_name, pool_key}`），因此多个管理器可以安全地共享同一个存储后端而不会发生检查点冲突 [7](#0-6) 。

## Signal Context（信号上下文）

在信号处理过程中，插件的`handle_signal/2`回调接收一个context参数，包含`:plugin_instance`等信息，提供了插件实例级别的上下文隔离 [8](#0-7) 。

```elixir
@impl Jido.Plugin
def handle_signal(signal, context) do
  if signal.type == "check.context" do
    has_instance = Map.has_key?(context, :plugin_instance)
    # 可以访问 context.plugin_instance.module 和 context.plugin_instance.state_key
  end
end
```

