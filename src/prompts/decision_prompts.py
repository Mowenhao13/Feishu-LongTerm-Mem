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
You are an expert in extracting decisions from group chat messages.

Analyze the following conversation and extract ALL decisions made.

## CONVERSATION

{conversation_text}

---

# WHAT COUNTS AS A DECISION?

1. A clear choice/plan/conclusion was reached
2. Technical parameters were specified (e.g. shard_count=256)
3. Responsibility was assigned ("张三负责", "李四来改")
4. Explicit agreement ("那就定", "确认用", "同意")

# WHAT DOES NOT COUNT?

1. Pure status updates
2. Brainstorming without conclusion
3. Casual chat and greetings
4. Vague intent without commitment

---

# OUTPUT FORMAT

Return JSON:
```json
{{
    "has_decisions": true,
    "decisions": [
        {{
            "decision_id": "dec_1",
            "title": "Concise decision title",
            "content": "Full description including context and parameters",
            "confidence": 0.85,
            "rationale": "Why this decision was made",
            "proposer": "Name or null",
            "executor": "Name or null",
            "impact_level": "major/minor/advisory"
        }}
    ],
    "reasoning": "Brief explanation"
}}
```

If no decisions found, return {"has_decisions": false, "decisions": []}
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
- 只输出 JSON，不要任何额外文字
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