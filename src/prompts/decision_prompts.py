# Decision Extraction Prompt (replaces FACT_EXTRACTION_PROMPT)

# Decision status lifecycle description (aligned with src/types.py and ref/decision/node.go)
DECISION_STATUS_DESCRIPTIONS = {
    "pending": "Newly identified, awaiting review",
    "pending_confirmation": "Uncertain, needs confirmation",
    "in_discussion": "Being actively discussed",
    "decided": "Final decision made, awaiting execution",
    "executing": "Currently being implemented",
    "completed": "Fully implemented and completed",
    "shelved": "Postponed, may be revisited later",
    "rejected": "Explicitly rejected/refused",
    "superseded": "Replaced by a newer decision",
    "deprecated": "No longer relevant or valid",
}

DECISION_STATUS_LIFECYCLE = {
    "active": [
        "pending", "pending_confirmation", "in_discussion", "decided", "executing",
    ],
    "inactive": [
        "completed", "shelved", "rejected", "superseded", "deprecated",
    ],
}


DECISION_EXTRACTION_PROMPT = """
You are an expert in extracting decisions and action items from group chat discussions.

Your task: Analyze the following topic context and episodes to extract ALL decisions that were made.

## TOPIC CONTEXT

Topic ID: {topic_id}
Title: {topic_title}
Summary: {topic_summary}

## ASSOCIATED EPISODES

{episodes_content}

## REFERENCE TIME

{reference_time}

---

# WHAT IS A "DECISION"?

A decision is a **conclusive choice, plan, or action item** that was agreed upon. Not every statement is a decision.

## Must mark as decision (any of):
1. A clear choice/plan/conclusion was reached — not just listing options, but making a selection
2. An identifiable scope or context (which project/module/area this decision applies to)
3. An explicit or implied next action ("I'll handle this", "please configure X")
4. Technical settings with specific parameters (shard_count=256, deploy_canary=true)
5. Explicit agreements: "那就定 X", "确认用 Y", "同意 Z"
6. Assignments of responsibility ("张三负责配置", "李四来改")

## Must NOT mark as decision:
1. Pure status updates ("已完成XX", "正在处理XX")
2. Brainstorming without conclusion
3. Pure questions asking for suggestions
4. Casual chat, greetings, social pleasantries
5. Intent without commitment ("打算用", "准备尝试")

## Confidence scoring:
- >= 0.8: Multiple confirmations, clear conclusion, explicit context → status: decided
- 0.6 - 0.8: Decision tendency but not fully explicit → status: pending_confirmation
- 0.5 - 0.6: Decision tendency but incomplete info → skip (don't extract)
- < 0.5: Not a decision → skip

## Decision status lifecycle:
- **pending**: Newly identified, awaiting review
- **pending_confirmation**: Uncertain, needs confirmation (use for confidence 0.6-0.8)
- **in_discussion**: Being actively discussed
- **decided**: Final decision made, awaiting execution (use for confidence >= 0.8)
- **executing**: Currently being implemented
- **completed**: Fully implemented and completed
- **shelved**: Postponed, may be revisited later
- **rejected**: Explicitly rejected/refused
- **superseded**: Replaced by a newer decision
- **deprecated**: No longer relevant or valid

---

# EXTRACTION STRATEGY

**Analyze each episode for decision signals**:

1. **Proposal-Acceptance pattern**: Someone proposes X, another confirms → decision
2. **Problem-Solution pattern**: Problem raised → specific solution agreed → decision
3. **Parameter-specification pattern**: Specific values/configs locked in → decision
4. **Task-assignment pattern**: Someone takes ownership of a task → decision

---

# OUTPUT FORMAT

Return JSON:
```json
{{
    "has_decisions": true,
    "decisions": [
        {{
            "decision_id": "dec_1",
            "title": "Concise decision title (10-20 words)",
            "content": "Full description of what was decided, including context, parameters, rationale",
            "confidence": 0.85,
            "rationale": "Why this decision was made",
            "proposer": "Name of person who proposed (if identifiable)",
            "executor": "Name of person assigned to execute (if identifiable)",
            "impact_level": "major/minor/advisory",
            "related_episode_ids": ["episode_1"]
        }}
    ],
    "reasoning": "Brief explanation of extraction strategy"
}}
```

**Notes**:
- decision_id: Use simple IDs like "dec_1", "dec_2" (will be mapped to UUID internally)
- impact_level: "major" for significant/consequential decisions, "minor" for routine ones, "advisory" for suggestions
- related_episode_ids: Use episode simple IDs (episode_1, episode_2, ...)
- When in doubt about whether something is a decision, lean towards extracting it
- At least analyze all episodes thoroughly — don't skip content
"""


DECISION_ROLE_ASSIGNMENT_PROMPT = """
You are an expert in prioritizing and categorizing extracted decisions.

Your task: Assign a priority and category to each decision.

## TOPIC CONTEXT

Topic ID: {topic_id}
Title: {topic_title}
Summary: {topic_summary}

## EXTRACTED DECISIONS

{decisions_text}

---

# CATEGORY TYPES

1. **technical**: Technical architecture, configuration, parameter choices
2. **process**: Workflow, timeline, process-related decisions
3. **product**: Feature, UI/UX, product direction decisions
4. **resource**: Human resources, budget, tooling decisions
5. **strategy**: High-level strategic direction
6. **other**: Anything that doesn't fit above

# PRIORITY LEVELS

- **critical**: Blocking, urgent, high-impact
- **high**: Important but not blocking
- **medium**: Standard priority
- **low**: Nice-to-have, minor

---

# OUTPUT FORMAT

Return JSON:
```json
{{
    "decision_roles": [
        {{
            "decision_id": "dec_1",
            "category": "technical",
            "priority": "high",
            "rationale": "Brief explanation"
        }}
    ],
    "extraction_confidence": 0.9,
    "reasoning": "Overall explanation"
}}
```
"""

DECISION_EXTRACTION_PROMPT_SHORT = """
You are an expert in extracting decisions and suggestions from group chat messages.

Analyze the following conversation and extract ALL decisions and suggestions made.

## CONVERSATION

{conversation_text}

---

# WHAT COUNTS AS A DECISION (is_suggestion=false)?

1. A clear choice/plan/conclusion was reached
2. Technical parameters were specified (e.g. shard_count=256)
3. Responsibility was assigned ("张三负责", "李四来改")
4. Explicit agreement ("那就定", "确认用", "同意")

# WHAT COUNTS AS A SUGGESTION (is_suggestion=true)?

1. Someone proposes a specific technical approach or configuration, but it hasn't been confirmed yet
2. A concrete recommendation with reasoning ("建议用X，因为...")
3. A proposed action plan or process improvement that's being considered

# WHAT DOES NOT COUNT?

1. Pure status updates
2. Brainstorming without any concrete proposal
3. Casual chat and greetings
4. Vague intent without any commitment

---

# OUTPUT FORMAT

Return JSON:
```json
{{
    "has_decisions": true,
    "decisions": [
        {{
            "decision_id": "dec_1",
            "title": "Concise decision/suggestion title",
            "content": "Full description including context and parameters",
            "confidence": 0.85,
            "rationale": "Why this decision/suggestion was made",
            "proposer": "Name or null",
            "executor": "Name or null",
            "impact_level": "major/minor/advisory",
            "is_suggestion": false
        }}
    ],
    "reasoning": "Brief explanation"
}}
```

If no decisions found, return {{"has_decisions": false, "decisions": []}}

**IMPORTANT**: Set `is_suggestion: true` for items that are proposed but not yet confirmed. Set `is_suggestion: false` for items that have been agreed upon or decided.
"""


# ========== Conflict Assessment ==========

CONFLICT_ASSESSMENT_PROMPT = """# 系统提示词：决策冲突评估器

## 角色
你是一个技术决策一致性检查专家。评估两个决策是否存在语义矛盾。

## 任务
给定两个决策的内容，判断它们是否矛盾，给出矛盾分数。

## 矛盾类型
1. 直接矛盾：两个决策的结论直接矛盾
   例: A 说"用 PostgreSQL"，B 说"用 MySQL" → 分数 0.9-1.0
2. 参数矛盾：两个决策对同一参数规定不同值
   例: A 说"token 长度 256"，B 说"token 长度 512" → 分数 0.7-0.9
3. 时序矛盾：两个决策的执行顺序不可调和
   例: A 说"先迁数据库再改 API"，B 说"先改 API 再迁数据库" → 分数 0.5-0.7
4. 范围矛盾：一个决策的范围与另一个决策重叠但有冲突
   分数 0.3-0.5
5. 无矛盾：两个决策互不影响
   分数 < 0.3

## 输出格式
{
  "contradiction_score": 0.0-1.0,
  "contradiction_type": "direct/param/timing/scope/none",
  "description": "一句话描述矛盾点",
  "suggestion": "如果需要调整某个决策才能共存，给出建议"
}

## 规则
- score < 0.3: 无冲突，正常插入
- score 0.3-0.6: 标记 RELATED_TO 关系
- score > 0.6: 需要进一步处理（SUPERSEDES 或 CONFLICTS_WITH）
- 只评估技术事实的矛盾，不评估"谁对谁错"
- 如果两个决策在不同阶段生效（phase 不同），矛盾应降级
"""


# ========== Decision Dedup + Conflict Combined Judgment ==========

DEDUP_DECISION_PROMPT = """# 系统提示词：决策去重与冲突联合判断

## 角色
你是项目决策一致性检查专家。比较新旧两个决策，同时判断是否存在重复（需要去重）以及是否存在冲突。

## 判断标准

你需要输出一个动作（action），三选一：

### skip — 跳过，不创建新决策
- 新旧决策说的是同一件事，仅有措辞、标点、空格差异
- 例："后端语言：Python" → "后端开发语言为 Python"（只是表述方式不同，事实不变）
- 例："使用 PostgreSQL" → "使用 PostgreSQL 数据库"（补充了"数据库"三个字，无实质变化）

### update — 更新现有决策
- 同一议题下的信息补充或细化，不矛盾
- 例："后端语言：Python" → "后端语言：Python，框架：Django"（补充了框架信息）
- 例："使用缓存" → "使用 Redis 作为缓存方案"（从模糊到具体）

### conflict — 标记冲突
- 新旧决策对同一事项给出了不同甚至矛盾的结论
- 例："后端语言：Python" → "后端语言：Golang"（语言变了）
- 例："使用 MySQL" → "使用 PostgreSQL"（数据库变了）
- 例："token 长度 256" → "token 长度 512"（参数变了）
- 即使只是细微差异，只要是**不同的事实陈述**就是冲突

## 输出格式（严格遵守）
{
  "action": "skip|update|conflict",
  "reason": "一句话说明判断理由"
}

## 规则
- 只看事实是否一致，不评价"哪个更好"
- 值变更（即使是同义词）≠ skip，而是 conflict
- 补充新信息但不动原有内容 = update
- 如果不确定，倾向 create_new（宁保留勿误删）
- 只输出 JSON，不要任何额外文字
"""


# ========== Tree Structure Building ==========

DECISION_TREE_BUILD_PROMPT = """# 系统提示词：决策树构建

## 角色
你是决策关系专家。根据已有的决策列表，判断它们之间的父子关系（层级关系）。

## 输入

以下是一个扁平决策列表（每条都是系统已确认的独立决策事项）：

{decision_list}

## 判断规则

请为每条决策判断它是否"从属于/细化"另一条决策——即是否存在父-子关系。

### PARENT_OF — 决策A 是 决策B 的父
判断条件：
1. 决策B 是实现 决策A 的**具体手段或实施选择**
2. 决策B 是 决策A 的**更具体的细化/拆分**
3. 决策B 可以独立存在，但它的前提是 决策A 已被做出

例子：
- 父="后端架构升级" → 子="数据库选型为PostgreSQL" ✅
  (选PG是后端升级的具体实施选择)
- 父="K8s容器化部署" → 子="采用Helm Chart管理K8s部署" ✅
  (Helm是K8s的具体实现方式)

### 不是父子的情况
1. 两个决策是**同级备选方案**（都是实现同一目标的不同路径）
   - 如："云托管K8s" 和 "混合架构" — 都是部署方案的不同选择，同级
2. 两个决策**完全独立**（涉及不同方面）
   - 如："数据库选PG" 和 "缓存击穿防御" — 无关
3. 两个决策存在**时间先后关系**但不是父子
   - 如："架构升级" 和 "三期推进" — 一个是做什么，一个是时间计划

### 树的规则
- 每个决策最多只能有一个父决策
- 树的深度不超过 3 层（根 → 子 → 孙）
- 不做深度嵌套的判断
- 如果不确定，倾向不建立关系（根节点更安全）

## 输出格式
{{
  "relations": [
    {{
      "parent_sid": "父决策 SDRID",
      "child_sid": "子决策 SDRID",
      "reason": "一句话说明为什么是父子关系"
    }}
  ],
  "no_relation_sids": ["没有建立关系的决策SDRID列表"]
}}

## 规则
- 只输出 JSON，不要任何额外文字
- 如果没有需要建立的父子关系，返回空 relations 列表
- 不要创建超过 3 层的深度
"""


# ========== Conflict Resolution ==========

CONFLICT_RESOLVE_PROMPT = """# 系统提示词：冲突自动解决判断器

## 角色
你是项目决策冲突解决专家。判断新旧决策之间的冲突能否自动合并。

## 判断标准

### merge — 可自动合并
- 两个决策说的是同一件事，但措辞不同 → 合并为更清晰的版本
- 新决策是对旧决策的合理更新/细化 → 用新决策覆盖
- 例: "后端语言: Python" vs "后端开发语言为 Python" → 可合并
- 例: "使用缓存" vs "使用 Redis 缓存" → 可合并为 "使用 Redis 缓存"

### keep_both — 无法自动合并，需人工介入
- 两个决策对同一事项给出矛盾结论
- 例: "后端语言: Python" vs "后端语言: Golang" → 需人工
- 例: "使用 MySQL" vs "使用 PostgreSQL" → 需人工
- 无法判断哪个版本更正确

## 规则
- 只看事实是否一致，不评价"哪个更好"
- 如果难以判断是否矛盾，优先 keep_both
- 结构化输出由 JSON Schema 强制约束
"""


# ========== Deep Sleep (Batch) Dedup ==========

DEEP_SLEEP_DEDUP_PROMPT = """# 系统提示词：记忆整理 — 批量决策去重判定

## 角色
你是记忆整理专家。在一次批量扫描中，判断多条候选决策与主决策是否重复。

## 任务
主决策（需判断它与其他决策的关系）：
主决策 ID: {main_sid}
主决策标题: {main_title}
主决策摘要: {main_summary}
主决策内容: {main_content}
主决策主题: {main_topic}
主决策置信度: {main_confidence}
主决策版本: {main_version}
主决策状态: {main_status}

候选决策列表（每条是一个潜在的重复）：
{decision_list}

## 判断标准

对每条候选决策，输出以下操作之一：

### skip — 跳过，不做任何操作
- 与主决策说的是同一事实，仅措辞/表述方式不同
- 候选决策是等同的，不需要保留
- 例：主="使用 PostgreSQL" → 候="采用PG数据库" → skip
- 例：主="K8s容器化部署" → 候="K8s容器化" → skip

### merge — 合并到主决策
- 候选决策提供了额外的有用信息，但不矛盾
- 例：主="后端语言Python" → 候="框架用Django" → merge
- 合并后候选标记为被取代，其信息补充到主决策

### conflict — 标记冲突
- 候选决策与主决策对同一事项给出不同事实
- 例：主="用MySQL" → 候="用PostgreSQL" → conflict
- 例：主="token 长度 256" → 候="token 长度 512" → conflict

### keep — 保留，不是重复
- 候选决策讨论的是不同主题/不同方面，不是同一决策事项

## 输出格式
{{
  "judgments": [
    {{
      "candidate_sid": "...",
      "action": "skip|merge|conflict|keep",
      "similarity_score": 0.0~1.0,
      "reason": "一句话说明判断理由",
      "info_to_merge": "如果有 merge，提取候选决策中额外的有用信息"
    }}
  ]
}}

## 规则
- 只看事实是否一致，不评价"哪个更好"
- 值变更（即使是同义词）≠ skip，而是 conflict
- 补充新信息但不动原有内容 = merge
- 如果不确定，倾向 keep（宁保留勿误删）
- 只输出 JSON，不要任何额外文字
"""


# ========== Realtime Dedup ==========

REALTIME_DEDUP_PROMPT = """# 系统提示词：决策去重判断

## 角色
你是一个决策去重专家。判断新提取的决策是否与已有的决策重复、冲突或可补充。

## 输入

### 新提取的决策（刚被 LLM 提取出来）
新标题: {new_title}
新摘要: {new_summary}
新内容: {new_content}
新主题: {new_topic}
新置信度: {new_confidence}
新来源: {new_source}

### 已有决策（系统中存储的）
已有标题: {existing_title}
已有摘要: {existing_summary}
已有内容: {existing_content}
已有主题: {existing_topic}
已有版本: {existing_version}
已有状态: {existing_status}

## 判断标准

输出动作，四选一：

### skip — 跳过，不创建、不更新
- 两条决策说的是同一件事实，仅有措辞/标点/空格差异
- 新决策没有提供比已有决策更多的信息
- 例："后端语言Python" → "后端开发语言为Python" → skip

### update — 更新已有决策
- 同一决策事项，新决策提供了更多/更新的信息
- 例："后端语言Python" → "后端语言Python，框架Django" → update
- 例："使用缓存" → "用Redis缓存" → update（模糊→具体）

### conflict — 标记冲突
- 新决策与旧决策对同一事项给出不同甚至矛盾的事实
- 例："用MySQL" → "用PostgreSQL" → conflict
- 即使只是细微的差异，只要是不同的事实陈述就是冲突

### create_new — 创建新决策（不是重复）
- 讨论的是不同主题/不同方面
- 与已有决策无关

## 输出格式
{{
  "action": "skip|update|conflict|create_new",
  "should_overwrite": true/false,
  "reason": "一句话说明判断理由",
  "info_to_merge": "如果 action=update，建议合并的额外信息"
}}

## 规则
- 只看事实是否一致，不评价"哪个更好"
- 值变更 ≠ skip，而是 conflict
- 如果不确定，倾向 create_new（宁保留勿误删）
- 只输出 JSON，不要任何额外文字
"""


# ========== Sleep FP Assessment ==========

SLEEP_FP_ASSESS_PROMPT = """# 系统提示词：记忆整理 — 决策质量评估

## 角色
你是记忆整理专家。评估一批决策的质量，判断哪些是真实有价值的决策/建议，哪些是噪声/误提取（FP）。

## 输入
以下是从群聊中提取的决策列表。请对每条决策判断其质量。

{decisions_json}

## 判断标准

对每条决策，判断它是"keep"（保留）还是"shelve"（搁置/FP）：

### keep — 保留为有效决策
- 是清晰的技术决策、方案选型、任务分配（已达成共识）
- 是具体的建议——包含明确的技术方案、参数配置、改进方向
- 有人明确认领了执行任务
- 有明确的执行意图和上下文

### shelve — 搁置（可能是噪声/误提取/FP）
- 纯状态更新："已完成XX"、"正在处理XX"、"准备做XX"
- 无结论的头脑风暴——只是列出了选项但没有选择
- 闲聊和日常问候
- 模糊意图无承诺："打算用"、"准备尝试"、"可以考虑"
- 纯信息分享，没有决策意图："XX发布了新版本"、"XX有这么一个功能"
- 讨论中的中间过程语句："需要验证一下"、"我看看文档"、"确认一下"
- 重复表达——上下文中的同一意思被反复提取

## 置信度参考
- confidence >= 0.8: 高置信度，倾向 keep
- confidence < 0.6: 低置信度，仔细判断是否为 FP
- is_suggestion=true 的建议：如果是具体技术方案，保留；如果只是模糊想法，搁置

## 输出格式
{{
  "judgments": [
    {{
      "sid": "...",
      "action": "keep|shelve",
      "reason": "一句话说明判断理由"
    }}
  ]
}}

只输出 JSON，不要额外文字。
"""