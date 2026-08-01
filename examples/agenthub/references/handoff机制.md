# 多Agent协作的Handoff机制解释

Handoff机制是AutoGen中实现多Agent协作的核心设计模式，允许Agent将任务动态委托给其他Agent。 [1](#0-0) 

## 核心概念

### Handoff设计模式
Handoff是OpenAI在Swarm项目中引入的多Agent设计模式，其核心思想是让Agent通过特殊的工具调用来将任务委托给其他Agent。 [2](#0-1) 

### HandoffMessage
`HandoffMessage`是用于信号交接的特殊消息类型，包含以下关键字段：
- `target`: 目标Agent的名称
- `content`: 交接消息内容
- `source`: 源Agent名称
- `context`: 上下文信息（可选） [3](#0-2) 

## Handoff配置

### Handoff类
`Handoff`类用于配置交接行为，主要属性包括：
- `target`: 目标Agent名称
- `description`: 交接条件描述
- `name`: 交接配置名称（默认生成格式：`transfer_to_{target}`）
- `message`: 传递给目标Agent的消息 [4](#0-3) 

### 工具转换
Handoff配置可以转换为工具函数，供Agent调用：
```python
@property
def handoff_tool(self) -> BaseTool[BaseModel, BaseModel]:
    def _handoff_tool() -> str:
        return self.message
    return FunctionTool(_handoff_tool, name=self.name, description=self.description, strict=True)
```  

## AssistantAgent中的Handoff处理

### 配置Handoffs
AssistantAgent通过`handoffs`参数配置可交接的目标Agent：
```python
agent = AssistantAgent(
    name="travel_agent",
    model_client=model_client,
    handoffs=["flights_refunder", "user"],
    system_message="..."
)
``` 

### Handoff检测与处理
AssistantAgent在`_check_and_handle_handoff`方法中检测和处理handoff请求：
1. 检查模型结果中的函数调用是否包含handoff工具
2. 如果检测到handoff，收集相关的工具调用和执行结果
3. 构建handoff上下文（包含工具调用和执行结果）
4. 返回包含HandoffMessage的响应

### 上下文传递
当接收到HandoffMessage时，Agent会将上下文信息添加到模型上下文中：
```python
async def _add_messages_to_context(
    model_context: ChatCompletionContext,
    messages: Sequence[BaseChatMessage],
) -> None:
    for msg in messages:
        if isinstance(msg, HandoffMessage):
            for llm_msg in msg.context:
                await model_context.add_message(llm_msg)
        await model_context.add_message(msg.to_model_message())
```

## Swarm团队中的Handoff机制

### Speaker选择
在Swarm团队中，speaker Agent的选择基于最近的HandoffMessage，这与SelectorGroupChat和RoundRobinGroupChat的轮询机制不同。

### 工作流程
1. 每个Agent可以生成HandoffMessage来信号交接
2. 当Agent生成HandoffMessage时，接收Agent接管任务并共享相同的消息上下文
3. 过程持续直到满足终止条件 

### 终止条件
使用`HandoffTermination`来检测特定的handoff消息并终止团队运行：
```python
termination = HandoffTermination(target="user") | TextMentionTermination("TERMINATE")
team = Swarm([travel_agent, flights_refunder], termination_condition=termination)
``` 

## 实际示例

### 客户支持场景
在客户支持场景中，Travel Agent可以将任务交接给Flights Refunder：
```python
travel_agent = AssistantAgent(
    "travel_agent",
    model_client=model_client,
    handoffs=["flights_refunder", "user"],
    system_message="The flights_refunder is in charge of refunding flights..."
)
``` 

### 执行流程
当Travel Agent调用`transfer_to_flights_refunder`工具时：
1. 生成HandoffMessage
2. Flights Refunder接管任务
3. 共享相同的消息上下文
4. Flights Refunder处理退款请求 [13](#0-12) 

## 注意事项

1. **模型要求**: 使用handoff功能需要模型支持工具调用
2. **并行工具调用**: 如果模型支持并行工具调用，可能会同时生成多个handoff，建议禁用并行工具调用
3. **Handoff名称唯一性**: Handoff名称必须与工具名称唯一 [14](#0-13) 

