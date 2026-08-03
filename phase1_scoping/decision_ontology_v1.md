# Feishu-Mem 决策领域本体设计（v1.0）

> 参考 [nano-ontoprompt](https://github.com/jingw2/nano-ontoprompt) 的 Entity/Relation/Rule/Action 四层本体模型，
> 为 Feishu-Mem 的"对话 + 文档"双通道场景设计初步决策领域本体。
>
> 设计原则：
> 1. Schema-driven extraction — 先定义本体，再约束提取
> 2. 覆盖比赛要求：决策 + 理由 + 反对意见 + 结论 + 项目阶段 + 时间点 + 主动推送
> 3. 与现有 Hypergraph（L0-L3）兼容，不是替代而是增量

---

## 1. 本体概览（TBox）

### 1.1 Entity 层次

```
Thing
├── Agentive Entity
│   ├── Person          — 参与者（proposer, executor, objector）
│   ├── Team            — 团队/部门（影响范围的载体）
│   └── Role            — 角色（architect, developer, PM — 可作为 Person 的标注）
│
├── Information Entity
│   ├── Decision        — 决策（核心，propositional knowledge）
│   ├── Objection       — 反对意见（反对/替代/质疑）
│   ├── Requirement     — 需求或约束（trigger 决策的外部条件）
│   ├── Conclusion      — 结论（对决策的正式确认）
│   │
│   ├── Document        — 飞书文档（长文本 source）
│   ├── Episode         — 对话轮次（短消息 source）
│   └── Message         — 单条消息（文档/对话的原子单位）
│
├── Process Entity
│   ├── ProjectStage    — 项目阶段（Phase 1 / Phase 2 / 里程碑）
│   ├── Milestone       — 里程碑（具体的时间点目标）
│   └── Timeline        — 时间线（决策的绝对/相对时间参考）
│
└── Abstraction Entity
    └── Topic           — 主题（已有的 L3 TopicNode）
```

### 1.2 属性约束

| Entity | Required | Optional | Derivation Rules |
|--------|---------|---------|-----------------|
| `Decision` | `summary`, `status`, `timestamp` | `rationale`, `alternatives`, `scope`, `priority`, `impact_level`, `proposer` | scope defaults to "project" if unset |
| `Objection` | `content`, `status` | `proposer`, `resolution`, `superseded_by` | status defaults to "open" |
| `Requirement` | `content` | `source_doc`, `priority`, `deadline`, `status` | priority defaults to "medium" |
| `Conclusion` | `decision_id`, `outcome` | `agreed_by`, `timestamp`, `document_ref` | outcome must be enum(approved|rejected|deferred) |
| `Document` | `token`, `title` | `type`, `url`, `author`, `project_stage`, `created_at` | type defaults to "docx" |
| `ProjectStage` | `name`, `order` | `start_date`, `end_date`, `milestones` | order must be integer ≥ 1 |
| `Topic` | `title` | `summary`, `keywords`, `participants` | |

---

## 2. Entity 详细定义（ABox Level）

### 2.1 Decision（核心实体）

```python
DECISION_SCHEMA = {
    "name": "Decision",
    "description": "团队在对话或文档中达成的决策性结论",
    "source": "IM 消息 / 文档段落",
    
    "required_fields": {
        "summary": {"type": "string", "description": "决策摘要，一句话", "max_length": 200},
        "status": {"type": "enum", "values": [
            "proposed",     # 刚提出，未讨论
            "in_discussion", # 正在讨论中
            "decided",      # 已决定
            "rejected",     # 被拒绝
            "superseded",   # 被后续决策替代
            "executing",    # 执行中
            "completed",    # 已完成
            "deprecated"    # 已废弃
        ]},
        "timestamp": {"type": "datetime", "description": "决策时间（绝对时间或从对话时间推导）"},
    },

    "optional_fields": {
        "rationale": {
            "type": "string",
            "description": "决策理由/依据",
            "extraction_hint": "注意原文中'因为''由于''考虑到'等因果标记词后的内容"
        },
        "alternatives": {
            "type": "list[string]",
            "description": "讨论中提到的替代方案",
            "extraction_hint": "不仅提取最终决定，还要记录被否决的选项"
        },
        "scope": {
            "type": "enum",
            "values": ["individual", "team", "project", "org", "cross_org"],
            "default": "project"
        },
        "priority": {
            "type": "enum",
            "values": ["p0_critical", "p1_high", "p2_normal", "p3_low"],
            "default": "p2_normal"
        },
        "impact_level": {
            "type": "enum",
            "values": ["advisory", "minor", "major", "critical"],
            "default": "minor"
        },
        "proposer": {"type": "string", "description": "提出者 ID"},
        "deadline": {"type": "datetime", "description": "决策的截止日期"},
        "references": {
            "type": "list[object]",
            "description": "引用的文档/消息/外部链接",
            "items": {
                "source_type": {"type": "enum", "values": ["doc", "message", "url"]},
                "source_id": {"type": "string"},
                "snippet": {"type": "string", "description": "引用片段"}
            }
        }
    },
    
    "extraction_prompt_template": """
从以下内容中提取决策信息：
- summary（必填）：决策摘要
- status（必填）：决策状态
- rationale：决策依据。注意原文中的“因为、由于、考虑到、基于”等词
- alternatives：讨论中被提到但未选择的替代方案
- references：如果引用了其他文档/对话内容，记录引用
"""
}
```

### 2.2 Objection（反对意见）

```python
OBJECTION_SCHEMA = {
    "name": "Objection",
    "description": "对某个提案或决策的反对意见、质疑或替代建议",
    "source": "IM 消息 / 文档评审意见",
    "note": "比赛原文明确要求跟踪反对意见",
    
    "required_fields": {
        "content": {"type": "string", "description": "反对内容"},
        "status": {"type": "enum", "values": [
            "open",         # 待处理
            "discussing",   # 讨论中
            "accepted",     # 被接受（原决策被修改）
            "rejected",     # 被驳回（原决策维持）
            "withdrawn"     # 提出者自行撤回
        ], "default": "open"},
    },
    
    "optional_fields": {
        "proposer": {"type": "string", "description": "反对意见提出者"},
        "reason": {"type": "string", "description": "反对的理由"},
        "resolution": {"type": "string", "description": "如何解决的"},
        "superseded_by": {"type": "string", "description": "如果被新 Objection 覆盖，引用新 ID"},
        "target_decision_id": {"type": "string", "description": "反对的对象决策 ID（若已提取）"},
    },
    
    "extraction_hint": "注意'但是''不过''我不同意''不太好吧''我觉得应该...而不是...'等反对语气标记"
}
```

### 2.3 Requirement（需求与约束）

```python
REQUIREMENT_SCHEMA = {
    "name": "Requirement",
    "description": "产生决策的项目需求、外部约束或假设条件",
    
    "required_fields": {
        "content": {"type": "string", "description": "需求描述"},
    },

    "optional_fields": {
        "source_doc": {"type": "string", "description": "来源文档"},
        "priority": {"type": "enum", "values": ["must", "should", "could", "wont"], "default": "must"},
        "deadline": {"type": "datetime", "description": "截止日期"},
        "status": {"type": "enum", "values": ["active", "fulfilled", "cancelled", "deferred"], "default": "active"},
        "proposed_by": {"type": "string"},
    },
    
    "extraction_hint": "注意'要求''需要''必须''截止''时间点''deadline'等标记。从文档中提取时特别注意'需求分析''非功能需求''约束条件'等章节标题。"
}
```

### 2.4 Document（文档）

```python
DOCUMENT_SCHEMA = {
    "name": "Document",
    "description": "飞书文档——长篇决策信息的主要来源",
    "source": "飞书 Docx / Wiki",
    
    "required_fields": {
        "token": {"type": "string", "description": "飞书文档 token"},
        "title": {"type": "string", "description": "文档标题"},
    },
    
    "optional_fields": {
        "type": {"type": "enum", "values": ["doc", "docx", "wiki", "sheet", "slides", "mindnote"],
                 "default": "docx"},
        "url": {"type": "string"},
        "author": {"type": "string"},
        "project_stage": {"type": "string", "description": "关联的项目阶段"},
        "created_at": {"type": "datetime"},
        "updated_at": {"type": "datetime"},
        "summary": {"type": "string", "description": "LLM 生成的文档摘要"},
    },
    
    "extraction_strategy": """
    文档处理策略（参考 nano-ontoprompt 的半结构化数据管道）：
    1. 按章节分块（Heading 1/2/3 作为分割点）
    2. 每块独立提取 Decision / Objection / Requirement
    3. 跨块引用需要显式标注（章节 A 引用章节 B 的结论）
    4. 文档级别元数据（title/author/stage）一次性提取
    """
}
```

### 2.5 ProjectStage（项目阶段）

```python
PROJECT_STAGE_SCHEMA = {
    "name": "ProjectStage",
    "description": "项目阶段/里程碑——决策的时间上下文",
    "note": "比赛要求'建立与项目阶段的关联'",
    
    "required_fields": {
        "name": {"type": "string", "description": "阶段名称"},
        "order": {"type": "integer", "description": "阶段序号，1-based"},
    },
    
    "optional_fields": {
        "start_date": {"type": "datetime"},
        "end_date": {"type": "datetime"},
        "milestones": {"type": "list[string]", "description": "本阶段的里程碑"},
        "description": {"type": "string"},
    },
}
```

---

## 3. Relation 类型定义

### 3.1 完整关系矩阵

| 关系 | Domain | Range | 基数 | 说明 | 示例 |
|------|--------|-------|------|------|------|
| `decides` | Decision | Requirement | N:1 | 决策确定了一个需求/约束的实施方案 | Decision("用PG") → decides → Requirement("数据库选型") |
| `overrules` | Decision | Decision | 1:1 | 新决策替代了旧决策 | Decision("改MongoDB") → overrules → Decision("用PG") |
| `raises_objection` | Person | Objection | 1:N | 某人提出了反对意见 | Person("张三") → raises_objection → Objection("PG不支持GIS") |
| `resolves` | Decision | Objection | N:1 | 决策解决了某个反对意见 | Decision("PG+PostGIS插件") → resolves → Objection("不支持GIS") |
| `constrained_by` | Decision | Requirement | N:M | 决策受到需求/约束的限制 | Decision("用PG RDS") → constrained_by → Requirement("预算50万") |
| `references` | Decision,Objection | Document,Episode,Message | N:M | 引用了来源文档或对话内容 | Decision("用PG") → references → Document("技术方案v2.docx") |
| `depends_on` | Decision | Decision | N:1 | 决策 A 等待决策 B 的决定 | Decision("DB迁移工具") → depends_on → Decision("数据库选型") |
| `belongs_to` | Decision,Objection | Topic | N:M | 属于某个讨论主题 | Decision("用PG") → belongs_to → Topic("数据库选型讨论") |
| `occurs_at` | Decision,Objection | ProjectStage | N:1 | 发生在某个项目阶段 | Decision("用PG") → occurs_at → ProjectStage("Phase 1") |
| `mentioned_by` | Decision,Objection,Requirement | Message | N:1 | 由哪条消息触发 | Decision("用PG") → mentioned_by → Message("好了，数据库PG方案定稿") |
| `agreed_by` | Conclusion | Person | N:M | 结论被哪些人同意 | Conclusion("PG方案通过") → agreed_by → Person("李四") |

### 3.2 与现有 Hypergraph 关系的映射

| 现有 RelationType | 对应新关系 | 区别 |
|------------------|-----------|------|
| `CONFLICTS_WITH` | → 被 `overrules` + `resolves(objection)` 取代 | 更加语义化：冲突的原因要么是替代（overrules），要么是反对意见被解决（resolves） |
| `SUPERSEDES` | → `overrules` | 改名以消除歧义 |
| `DEPENDS_ON` | → 保留 `depends_on` | 不变 |
| `REFINES` | → 删除 | 语义模糊，可由 `decides` + `constrained_by` 的组合表达 |
| `RELATES_TO` | → 删除 | 语义模糊，应使用具体关系 |
| `PARENT_OF` / `CHILD_OF` | → 删除 | 可由 `depends_on` + `overrules` 的组合表达 |

---

## 4. Logic Rule 定义

### 4.1 验证规则（Validation Rules）

```python
VALIDATION_RULES = [
    {
        "id": "R001",
        "name": "timeline_consistency",
        "description": "如果 Decision A overrules Decision B，则 A.timestamp > B.timestamp",
        "severity": "error",
        "condition": """
            MATCH (a:Decision)-[:OVERRULES]->(b:Decision)
            WHERE a.timestamp <= b.timestamp
            RETURN a.id, b.id
        """,
        "fix_hint": "检查决策的时间戳是否准确。如果 A 确定晚于 B，时间戳应该反映这一点。"
    },
    {
        "id": "R002",
        "name": "objection_resolution_chain",
        "description": "每个 resolved Objection 必须有至少一个关联的 Decision",
        "severity": "warning",
        "condition": """
            MATCH (o:Objection {status: "resolved"})
            WHERE NOT EXISTS { MATCH (d:Decision)-[:RESOLVES]->(o) }
            RETURN o.id
        """,
        "fix_hint": "已解决的反对意见应链接到解决它的决策，否则 'resolved' 状态无法追溯原因。"
    },
    {
        "id": "R003",
        "name": "document_reference_integrity",
        "description": "引用 Document 的 Decision 必须有有效的 token",
        "severity": "error",
        "condition": """
            MATCH (d:Decision)-[:REFERENCES]->(doc:Document)
            WHERE doc.token IS NULL OR doc.token = ''
            RETURN d.id, doc.title
        """,
        "fix_hint": "引用的文档必须有有效的 token。如果 token 不可用，考虑使用 URL 替代。"
    },
]
```

### 4.2 推理规则（Inference Rules）

```python
INFERENCE_RULES = [
    {
        "id": "I001",
        "name": "auto_status_on_overrule",
        "description": "被 overruled 的 Decision 自动标记为 superseded",
        "trigger": "on_relation_created(OVERRULES)",
        "action": "target.status = 'superseded'",
    },
    {
        "id": "I002",
        "name": "scope_propagation",
        "description": "如果 Decision 的 proposer 属于某 Team，则 Decision.scope 自动包含该 Team",
        "trigger": "on_node_created_or_updated(Decision.proposer)",
        "condition": "Decision.proposer IN Person ⟶ Team.members",
        "action": "Decision.scope = Union(Decision.scope, Team.name)",
    },
    {
        "id": "I003",
        "name": "objection_supersession",
        "description": "如果 Decision 被标记为 rejected 且有活跃的 Objection，Objection 自动标记为 accepted",
        "trigger": "on_status_change(Decision.status → rejected)",
        "condition": "EXISTS( (Decision)-[:DECIDES]->() ) AND EXISTS( Objection ) WHERE Objection.target = Decision",
        "action": "Objection.status = 'accepted'",
    },
    {
        "id": "I004",
        "name": "temporal_annotation",
        "description": "从对话中提取相对时间（'上周五'）时，解析为绝对时间并记录原始表达",
        "trigger": "on_extraction(Decision.timestamp)",
        "condition": "timestamp IS datetime AND contains_relative_reference(raw_text)",
        "action": "Decision.timestamp_original = raw_text; Decision.timestamp = resolve_relative(raw_text, conversation_context)",
    },
]
```

### 4.3 覆盖率规则（Coverage Rules）

```python
COVERAGE_RULES = [
    {
        "id": "C001",
        "name": "orphan_detection",
        "description": "检测未被任何关系链接的孤立节点",
        "severity": "warning",
        "condition": "MATCH (n) WHERE NOT (n)--() RETURN n.id, labels(n)",
    },
    {
        "id": "C002",
        "name": "decision_must_have_source",
        "description": "每个 Decision 必须至少有一条 REFERENCES 或 mentioned_by 关系",
        "severity": "warning",
        "condition": """
            MATCH (d:Decision)
            WHERE NOT EXISTS { MATCH (d)-[:REFERENCES|MENTIONED_BY]->() }
            RETURN d.id
        """,
    },
]
```

---

## 5. 与现有代码结构的映射

### 5.1 Entity → 现有 Model 映射

| 新实体 | 现有 Model / 文件 | 变更 |
|--------|-----------------|------|
| Decision | `src/node/node.py:DecisionNode` | 新增 `alternatives`, `deadline`, `references` 字段 |
| Objection | `src/node/types.py:Objection`（已定义） | 增强使用，当前只定义未充分使用 |
| Requirement | **新建** | 当前无对应实体 |
| Document | **新建**（参考 `src/adapter/lark_doc.py` 空文件） | 需要适配器 |
| Person | `src/node/types.py` 中的 string 引用 | 建议独立为 Person 节点 |
| ProjectStage | **新建** | 当前无对应实体 |
| Episode | `src/structure.py:EpisodeNode` | 已有，保留 |
| Topic | `src/structure.py:TopicNode` | 已有，保留 |
| Conclusion | 决策 Decision.status == 'decided' | 建议独立为 Conclusion 节点 |

### 5.2 本体 → Hypergraph 的跨层映射

```
TBox Level（新）:
  Decision Ontology / Objection Ontology / Requirement Ontology 等 Schema 定义
       │
       │   schema-driven extraction (LLM 按 schema 提取)
       ▼
ABox Level（现有 Hypergraph 扩展）:
  L0: DecisionNode + DecisionHyperedge ← 扩展字段
    新增:  ObjectionNode + ObjectionHyperedge  (当前已定义但未充分使用)
  L1: FactNode + FactHyperedge ← 保留
    新增:  RequirementNode + RequirementHyperedge
  L2: EpisodeNode + EpisodeHyperedge ← 保留
    新增:  DocumentNode + DocumentHyperedge （文档维度的 Episode 等价物）
  L3: TopicNode ← 保留
    新增:  ProjectStageNode + MilestoneNode + TimelineNode
```

### 5.3 提取 Pipeline 的变化

```
当前：
  IM/Doc → LLM("提取决策") → DecisionNode → Hypergraph → validate_bidirectional_links()

引入本体后：
  IM/Doc → Load Ontology Schema(TBox)
         → LLM("按以下 schema 提取: {Decision Schema} {Objection Schema} ...")
         → 结构化输出（JSON 格式，对齐 schema）
         → Python 端 parse & validate（Logic Rule 检查）
         → 构建 ABox（Hypergraph 扩展）
         → 覆盖率检查（orphan detection）
         → 推理规则触发（auto_status, scope_propagation 等）
```

---

## 6. 存储策略建议

| 组件 | 推荐存储 | 理由 |
|------|---------|------|
| TBox（本体定义） | `src/ontology/` 目录下的 Python 字典 | 纯元数据，变更频率极低，不依赖持久化 |
| ABox（实体实例） | **SQLite** 关系表（Phase A）；Neo4j（Phase B 可选） | 当前 ~44 节点，SQLite 足够。预留 GraphBackend 抽象 |
| Logic Rules | `src/ontology/rules.py` 的 Python 函数 | 规则执行在内存中完成，不依赖 DB 实现 |
| Extraction Cache | SQLite（已提取的段落去重） | 避免同一文档反复提取 |
| Validation Results | SQLite / JSON 日志 | 用于审计追踪，不是查询热点 |

### 6.1 SQLite 表结构（Phase A）

```sql
-- Entity 表（基础实体注册表）
CREATE TABLE entities (
    id TEXT PRIMARY KEY,           -- 全局唯一 ID
    type TEXT NOT NULL,             -- Decision | Objection | Requirement | ...
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 属性表（EAV 模式——Entity-Attribute-Value）
-- 参考 nano-ontoprompt 的半结构化处理方式
CREATE TABLE attributes (
    entity_id TEXT NOT NULL REFERENCES entities(id),
    attr_name TEXT NOT NULL,
    attr_value TEXT,                -- JSON 序列化（list/object 类型）
    attr_type TEXT NOT NULL,        -- string | enum | datetime | list
    PRIMARY KEY (entity_id, attr_name)
);

-- 关系表
CREATE TABLE relations (
    source_id TEXT NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL,    -- decides | overrules | ...
    target_id TEXT NOT NULL REFERENCES entities(id),
    metadata TEXT,                  -- JSON，用于存储 weight、confidence 等
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_id, relation_type, target_id)
);

-- 索引
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_relations_source ON relations(source_id);
CREATE INDEX idx_relations_target ON relations(target_id);
CREATE INDEX idx_relations_type ON relations(relation_type);
CREATE INDEX idx_attributes ON attributes(entity_id, attr_name);
```

---

## 7. 命名规范与扩展性

### 7.1 命名规则

- Entity: `PascalCase`（Decision, Objection, ProjectStage）
- Relation: `snake_case`（decides, raises_objection）
- Attribute: `snake_case`（extraction_confidence, project_stage_id）
- Rule ID: `R` 验证规则 / `I` 推理规则 / `C` 覆盖率规则 + 三位数字编号

### 7.2 扩展方式

```python
# Phase B 需要新 Entity 时：
# step 1: 在 ontology/entities.py 中定义 schema
# step 2: 在 ontology/relations.py 中定义关系
# step 3: 在 LLM extraction prompt 中追加
# step 4: 在 Hypergraph 容器中注册（如需要）

Event = {
    "name": "Event",
    "description": "项目事件或里程碑事件",
    "required_fields": {
        "name": {"type": "string"},
        "event_type": {"type": "enum", "values": ["release", "meeting", "decision", "milestone"]},
        "timestamp": {"type": "datetime"},
    }
}
```

### 7.3 与 GraphBackend 接口的配合

```python
# Phase A（SQLite 实现）
class SQLiteBackend(GraphBackend):
    def execute_query(self, cypher_like_query: str) -> List[Entity]:
        # 将 Cypher 风格的图查询翻译为 SQL + CTE
        pass

# Phase B（Neo4j 实现，可选）
class Neo4jBackend(GraphBackend):
    def execute_query(self, cypher_like_query: str) -> List[Entity]:
        # 直接在 Neo4j 上执行 Cypher
        pass
```

---

## 8. 与实验结论的关联

本体的引入直接解决了实验暴露的两个问题：

| 实验问题 | 暴露的问题 | 本体的解决方案 |
|---------|-----------|---------------|
| Q5 索引规则遗漏 | LLM 在提取时未将"避免过多索引"识别为决策 | 本体定义了 `extraction_hint`，LLM 按照 hint 中的因果标记词搜索，提高召回率 |
| Q8 死锁检测遗漏 | 对话中"提到但未决定"的内容被完全跳过 | 本体区分了 `Decision`（已决定）和 `Objection`（有反对/质疑），"提到但未决定"的内容可以作为 `Objection(status=open)` 或 `Requirement` 而非直接丢弃 |
| Q10 跨消息推理弱 | 单一 Decision 缺少对比分析的上下文 | 本体的 `alternatives` 字段显式要求提取"被否决的选项"，而不是只记录最终结论 |
| 预处理模式 14/20 | 提取覆盖率不足 | 规则 I004（时间标注自动解析）可以提高时间相关决策的精确性 |

---

## 9. 实施路线

| 步骤 | 工作量 | 产出 | Phase |
|------|--------|------|-------|
| 1. 实体定义文件 | 0.5 天 | `src/ontology/entities.py` — 所有 Entity Schema | Phase A |
| 2. 关系定义文件 | 0.5 天 | `src/ontology/relations.py` — 所有 Relation 类型 | Phase A |
| 3. 规则引擎 | 1-2 天 | `src/ontology/rules.py` — Validation + Inference + Coverage | Phase A |
| 4. LLM prompt 整合 | 1 天 | 修改 extraction prompt 为 schema-driven | Phase A |
| 5. SQLite 存储 | 1-2 天 | `src/storage/ontology_storage.py` | Phase A |
| 6. GraphBackend 接口 | 0.5 天 | `src/graph/backend.py` | Phase A |
| 7. 文档适配器整合 | 待定 | 与 lark_doc.py 配合 | Phase A 后半程 |

**合计**：~5-7 天工作量（参考 Phase A 的 4-6 周计划，本体层是其中的一个子模块）。

---

*本文档是 Phase 1（Scoping）的产物。参考的 nano-ontoprompt 设计模式：Entity Type / Relation Type / Logic Rule / Action 四层模型。*