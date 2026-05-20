在微服务和大模型（LLM/Agent）开发中，Guardrails（护栏检查）**和**Circuit Breaker（超时熔断器）是确保系统安全、稳定和高可用的两大利器。

Python 生态中这两个方向都有非常成熟、开箱即用的现成开源库。

---

## 一、 Guardrails（大模型护栏/输入输出检查）

在 Agent 开发中，Guardrails 主要用于：防止用户恶意注入（Prompt Injection）、检查 LLM 输出是否包含敏感词/幻觉、确保输出符合特定 JSON 格式。

### 1. `guardrails-ai` (最流行的 LLM 专属护栏库)

这是目前大模型生态中最火的护栏框架。它允许你通过 Python 代码或 XML 结构（称为 `.rail`）来定义针对大模型输入和输出的**强校验规则**。

* **特性**：如果 LLM 的输出没有通过检查，它可以自动触发“重新生成（Re-ask）”，或者直接拦截并返回修正后的默认值。
* **安装**：`uv add guardrails-ai`
* **代码示例**：

```python
from pydantic import BaseModel, Field
from guardrails import Guard
from guardrails.hub import ProfanityFree, SqlParse

# 1. 定义期望的结构，并直接注入现成的护栏组件（从 Guardrails Hub 动态加载）
class MedicalBotOutput(BaseModel):
    # 护栏1：确保输出绝对不包含脏话/敏感词
    response: str = Field(validators=[ProfanityFree(on_fail="fix")]) 
    # 护栏2：如果是生成的 SQL，确保其语法完全正确
    generated_query: str = Field(validators=[SqlParse(on_fail="reask")])

# 2. 创建护栏对象
guard = Guard.from_pydantic(output_class=MedicalBotOutput)

# 3. 包裹你的 LLM 调用（它会自动在底层拦截、校验、甚至在失败时自动重新调 LLM）
raw_llm_output, validated_output, *args = guard(
    llm_api=your_llm_call_function,
    prompt="请为用户生成一份医疗建议并附带查询数据库的 SQL..."
)

```

### 2. `NeMo Guardrails` (NVIDIA 出品，适合复杂对话流控制)

由英伟达开源，它不仅能检查单次输入输出，还能通过一种名为 Colang 的声明式语言，控制 Agent 的**对话轨迹**。例如：如果用户问到政治问题，强行将对话流路由到“委婉拒绝”的节点，不允许 Agent 自行发挥。

---

## 二、 Circuit Breaker（超时熔断器与重试机制）

在 Agent 调用外部 Tool（如第三方 API、网络爬虫、向量数据库）或调用 LLM 供应商时，由于网络波动，经常会出现超时或卡死。**熔断器**的作用是：当上游服务连续失败达到阈值时，自动“跳闸”断开连接，直接返回降级数据，避免整个 Agent 线程因等待而雪崩。

### 3. `pybreaker` (Python 最经典的通用熔断器库)

这是一个遵从标准经典设计模式的熔断器库。支持三种状态：**Closed（闭合，正常通行）**、**Open（断开，直接拦截并抛出异常/执行降级）**、**Half-Open（半断开，尝试放行少量请求看是否恢复）**。

* **安装**：`uv add pybreaker`
* **代码示例**：

```python
import pybreaker
import requests

# 1. 创建一个熔断器：如果连续失败 3 次，则熔断 60 秒
db_breaker = pybreaker.CircuitBreaker(
    fail_max=3, 
    reset_timeout=60
)

# 2. 使用装饰器或上下文管理器包裹不稳定的工具调用
@db_breaker
def call_unstable_tool_api():
    # 假设这是一个经常超时或报错的外部大模型 API
    response = requests.get("https://api.unstable-provider.com/v1", timeout=5)
    return response.json()

# 3. 业务调用
try:
    result = call_unstable_tool_api()
except pybreaker.CircuitBreakerError:
    # 熔断器已经跳闸时，会直接抛出这个异常，不再请求网络
    print("上游服务已熔断，启动本地备用降级方案（Fallback）")
    result = {"status": "success", "data": "本地缓存数据"}

```

### 4. `tenacity` (大模型生态标配的重试与超时控制库)

严格来说它不是熔断器，它是重试（Retry）领域的王者（LangChain 底层重试全部基于它）。在 Agent 开发中，它经常和 `pybreaker` 配合使用——**先重试几次，实在不行再熔断**。

* **安装**：`uv add tenacity`
* **代码示例**：

```python
from tenacity import retry, stop_after_attempt, wait_exponential

# 如果调用 LLM 失败，以指数退避的方式（等 2s, 4s, 8s...）最多重试 5 次
@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
def call_llm_with_retry():
    print("尝试调用 LLM...")
    raise RemoteDisconnected("网络断开")

```

---

## 总结建议

如果你在组装一个高可用的 Agent 系统：

1. **输入输出的业务合规与格式检查**：直接用 `guardrails-ai`，配合它的 Pydantic 验证极其丝滑。
2. **外部不可靠工具（Tools/API）的防雪崩保护**：用 `pybreaker` 设立熔断防线，并在外层包裹 `tenacity` 做网络抗震荡重试。