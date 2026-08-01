# 飞书云文档插件（Docs Add-on）设计方案

## 1. 概述

本项目（feishu-mem）是一个飞书群聊决策记忆系统，能够从群聊消息中自动提取决策、事实和议题，构建结构化的超图记忆库。通过飞书云文档插件（Docs Add-on）能力，可以将这些记忆直接嵌入到云文档中，实现 **「群聊 → 记忆 → 文档」** 的无缝工作流。

### 1.1 可提供服务总览

| 服务 | 描述 | 数据来源 |
|------|------|---------|
| **决策检索** | 按关键字/议题/时间范围搜索已记录的决策 | MemoryGraph + Retrieval |
| **决策详情** | 获取单个决策的完整信息（内容、状态、执行人、版本历史） | GitStorage |
| **决策创建/确认** | 在文档中直接创建新决策、确认或拒绝已有决策 | MemoryEngine |
| **议题关联** | 将文档内容与已有议题/决策建立关联 | MemoryGraph |
| **决策时间线** | 按时间线展示项目决策演变 | GitHistory |
| **冲突检测** | 检测新内容与已有决策的冲突 | ConflictDetector |
| **关系网络** | 展示决策之间的关联关系图谱 | MemoryGraph |
| **每日/每周摘要** | 聚合最近决策动态的摘要报告 | PushEngine |
| **全文搜索** | 在记忆库中全文搜索相关内容 | FulltextSearch |
| **决策热点排行** | 展示热点决策排名 | HotScore |

### 1.2 交互形式

用户在云文档中可通过以下形式与 feishu-mem 交互：

| 交互形式 | 组件类型 | 说明 |
|---------|---------|------|
| **正文嵌入式块** | Body Add-on | 直接在文档内容中插入决策卡片、列表、时间线等 |
| **浮动面板** | Floating Add-on | 拖拽式悬浮助手面板，随时查询记忆 |
| **全文弹窗** | Attached View (Fullscreen) | 全屏展示决策关系网络图 |
| **浮卡片预览** | Attached View (FloatCard) | 鼠标悬停/选中时弹出决策详情浮卡片 |
| **模态编辑** | Attached View (Modal) | 新建/编辑决策的模态表单 |
| **弹出菜单** | Attached View (Popup) | 快速操作菜单 |

---

## 2. 组件设计方案

### 2.1 正文组件（Body Add-on）

#### 2.1.1 决策卡片组件（Decision Card）

**用途**：在文档中嵌入单个决策的完整展示卡片。

**UI 结构**：

```
┌─────────────────────────────────────────┐
│  [状态] 决策标题                           │
│  ─────────────────────────────────────  │
│  决策内容摘要文本...                        │
│                                          │
│  影响等级: 🔴 高  |  执行人: @张三         │
│  来源群聊: 项目A群  |  时间: 2025-06-01    │
│                                          │
│  [查看详情]  [编辑]  [确认]  [关联文档]     │
└─────────────────────────────────────────┘
```

**数据流**：

```
[文档加载] → Widget 通过 props 获取 decision_id
    → fetch `/api/decisions/{id}` (通过 MCP Server)
    → 渲染决策卡片
    → 用户操作 → 调用 MCP API 更新决策
    → 文档内实时刷新
```

**Props / 配置参数**：

```typescript
interface DecisionCardProps {
  decisionId: string;           // 决策 SDRID
  showActions?: boolean;        // 显示操作按钮
  compact?: boolean;            // 紧凑模式
  highlight?: string;           // 高亮关键词
}
```

**app.json 配置**：

```json
{
  "contributes": {
    "addPanel": {
      "view": "decision-card/index.html",
      "initialHeight": 260
    }
  }
}
```

---

#### 2.1.2 决策列表组件（Decision List）

**用途**：在文档中嵌入查询结果列表，支持搜索和筛选。

**UI 结构**：

```
┌─────────────────────────────────────────┐
│  🔍 搜索记忆库...     [筛选] [排序]      │
│  ─────────────────────────────────────  │
│  ├─ [已确认] 采用微服务架构方案           │
│  │   @张三 · 2025-06-01 · 🔴高影响      │
│  ├─ [待确认] 数据库选型PostgreSQL         │
│  │   @李四 · 2025-05-28 · 🟡中影响      │
│  ├─ [已实施] CI/CD 流水线搭建             │
│  │   @王五 · 2025-05-25 · 🟢低影响      │
│  └─ ...                                  │
│                                          │
│  共 12 条决策  [加载更多 →]               │
└─────────────────────────────────────────┘
```

**数据流**：

```
[用户输入搜索关键词] → Widget 调用 search API
    → MCP Server 执行 HierarchicalRetriever.retrieve()
    → 返回匹配决策列表
    → 渲染列表
    → 点击某条 → 展开详情 或 跳转到 Decision Card
```

**Props**：

```typescript
interface DecisionListProps {
  defaultQuery?: string;         // 默认搜索词
  topicId?: string;              // 限定议题
  filters?: {
    status?: DecisionStatus[];
    impactLevel?: ImpactLevel[];
    dateFrom?: string;
    dateTo?: string;
    assignee?: string;
  };
  pageSize?: number;
}
```

---

#### 2.1.3 决策时间线组件（Decision Timeline）

**用途**：沿时间轴展示项目决策演变过程，适合在项目总结、周报中使用。

**UI 结构**：

```
┌─────────────────────────────────────────┐
│  项目里程碑决策时间线  2025年6月          │
│                                          │
│  ─── 6月第1周 ───                        │
│  ● [已确认] 采用微服务架构               │
│  │  @张三 决定拆分订单服务               │
│  ● [已实施] 数据库从MySQL迁移至PG         │
│  │  @李四 完成迁移方案                   │
│                                          │
│  ─── 5月第4周 ───                        │
│  ● [已确认] 前端框架选型React             │
│  │  @王五 确定技术栈                     │
│  ...                                     │
└─────────────────────────────────────────┘
```

**数据流**：

```
Widget 加载 → 调用 timeline API
    → MCP Server 聚合按时间分组的决策
    → 渲染时间线视图
    → 支持点击展开详情
```

**Props**：

```typescript
interface DecisionTimelineProps {
  project?: string;              // 项目筛选
  dateFrom?: string;
  dateTo?: string;
  groupBy?: 'day' | 'week' | 'month';
  maxItems?: number;
}
```

---

#### 2.1.4 议题看板组件（Topic Board）

**用途**：展示所有活跃议题及其关联决策的看板视图。

**UI 结构**：

```
┌──────────┬──────────┬──────────┬──────────┐
│ 技术架构   │ 项目管理   │ 人员组织   │ 运营策略   │
├──────────┼──────────┼──────────┼──────────┤
│ 微服务    │ 迭代计划  │ 招聘HC   │ 定价方案  │
│ 方案 ✅   │ ✅       │ 🟡讨论中  │ ✅       │
│          │          │          │          │
│ 数据库    │ 周会规范  │ 分工     │ 市场推广  │
│ 选型 ✅   │ ✅       │ ✅       │ 🟡讨论中  │
│          │          │          │          │
│ CI/CD    │ 风险登记  │          │          │
│ 🟡讨论中  │ 🟡讨论中  │          │          │
└──────────┴──────────┴──────────┴──────────┘
```

---

### 2.2 浮动组件（Floating Add-on）

#### 2.2.1 记忆助手浮动面板（Memory Assistant）

**用途**：文档右侧/任意位置悬浮的 AI 助手面板，用户可随时查询记忆或执行操作。

**UI 结构**：

```
┌──────────────────┐
│  🤖 记忆助手      │  ← 拖拽标题栏
│  ──────────────  │
│                   │
│  [输入查询内容...] │
│  [搜索]           │
│                   │
│  相关决策:         │
│  ├─ 采用微服务架构 │
│  ├─ 数据库选型PG   │
│  └─ 前端React     │
│                   │
│  [快速操作]        │
│  ├─ 新建决策       │
│  ├─ 查看时间线     │
│  ├─ 今日摘要       │
│  └─ 冲突检测       │
│                   │
│  ──────────────  │
│  数据来源: 群聊记忆  │
└──────────────────┘
```

**数据流**：

```
面板常驻 → 用户输入查询
    → Widget 调用多个 MCP API
    → 聚合结果展示在面板
    → 用户点击某项 → 可展开为正文组件/弹窗查看详情
```

---

### 2.3 附属视图（Attached Views）

#### 2.3.1 决策关系网络图（Fullscreen View）

**用途**：全屏展示决策之间的关联关系图谱，支持交互式探索。

**触发方式**：从正文组件或浮动面板点击 "关系图谱" 按钮。

**技术选型**：使用 D3.js 或 vis-network 渲染力导向图。

**UI 结构**：

```
┌─────────────────────────────────────────┐
│  决策关系网络                  [关闭]    │
│                                          │
│        ┌─────┐                           │
│        │微服务│                           │
│        │架构  │─── 关联 ─→ ┌─────┐       │
│        └─────┘            │数据库│       │
│          │                │选型  │       │
│          │ 冲突           └─────┘       │
│          ▼                  │            │
│        ┌─────┐              │ 依赖      │
│        │容器化│←── 关联 ────┘            │
│        │方案  │                          │
│        └─────┘                          │
│                                          │
│  悬停节点查看详情  拖拽调整布局            │
└─────────────────────────────────────────┘
```

---

#### 2.3.2 决策编辑弹窗（Modal View）

**用途**：模态弹窗中创建或编辑决策。

**UI 结构**：

```
┌─────────────────────────────────────────┐
│  创建决策                     [关闭] ×   │
│  ─────────────────────────────────────  │
│                                          │
│  标题: [________________________________]│
│                                          │
│  内容:                                   │
│  [______________________________________]│
│  [______________________________________]│
│                                          │
│  影响等级: [🔴 高] [🟡 中] [🟢 低]      │
│  执行人:   [________________] @选择成员   │
│  所属议题: [▼ 技术架构]                   │
│                                          │
│  关联文档: [当前文档] [选择其他文档]       │
│                                          │
│         [取消]     [创建决策]             │
└─────────────────────────────────────────┘
```

---

#### 2.3.3 决策详情浮卡片（FloatCard View）

**用途**：在正文组件中悬停某条决策时，弹出浮卡片展示完整详情。

**触发方式**：鼠标悬停在决策卡片或列表条目上。

**UI 结构**：

```
┌────────────────────────────────────┐
│  📋 决策详情                       │
│  标题: 采用微服务架构方案           │
│  状态: ✅ 已确认 (v3)              │
│  ──────────────────────────────── │
│  内容: 团队决定采用微服务架构，      │
│  将订单服务独立拆分部署...           │
│                                    │
│  影响等级: 🔴 高                    │
│  决策人: 张三  执行人: 李四          │
│  来源: 项目A群 · 2025-06-01 14:30  │
│  关联议题: 技术架构                  │
│                                    │
│  版本历史:                          │
│  v1 创建 → v2 补充执行人 → v3 确认  │
│                                    │
│  [编辑] [关联文档] [查看图谱]        │
└────────────────────────────────────┘
```

---

## 3. 技术实现方案

### 3.1 整体架构

```
┌─────────────────────────────────────────────────┐
│                飞书云文档 (Feishu Docs)            │
│  ┌───────────────┐  ┌─────────────────────────┐  │
│  │ 正文组件区域    │  │ 浮动组件区域             │  │
│  │ ┌───────────┐ │  │ ┌─────────────────────┐ │  │
│  │ │ Decision  │ │  │ │ Memory Assistant    │ │  │
│  │ │ Card      │ │  │ │ (iframe)            │ │  │
│  │ └───────────┘ │  │ └─────────────────────┘ │  │
│  │ ┌───────────┐ │  └─────────────────────────┘  │
│  │ │ Decision  │ │                                │
│  │ │ List      │ │  ┌─────────────────────────┐  │
│  │ └───────────┘ │  │ 附属视图 (Modal/Full)    │  │
│  │ ┌───────────┐ │  │ ┌─────────────────────┐ │  │
│  │ │ Timeline  │ │  │ │ 决策编辑 / 关系图谱  │ │  │
│  │ └───────────┘ │  │ └─────────────────────┘ │  │
│  └───────────────┘  └─────────────────────────┘  │
└──────────────────────┬──────────────────────────┘
                       │  Widget API (BlockitClient)
                       │  + HTTP 请求
                       ▼
┌─────────────────────────────────────────────────┐
│              feishu-mem 后端服务                   │
│                                                   │
│  ┌───────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ MCP Server│  │ HTTP API │  │ WebSocket Hub │  │
│  │ (stdio)   │  │ (FastAPI)│  │ (可选)        │  │
│  └─────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│        │              │               │           │
│        ▼              ▼               ▼           │
│  ┌─────────────────────────────────────────────┐  │
│  │          Memory Engine + Pipeline            │  │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────────┐ │  │
│  │  │ Retrieval│ │Extractors│ │ConflictDetect│ │  │
│  │  └─────────┘ └──────────┘ └──────────────┘ │  │
│  └─────────────────────┬───────────────────────┘  │
│                        │                           │
│  ┌─────────────────────▼───────────────────────┐  │
│  │      MemoryGraph + GitStorage                │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 3.2 通信方式

Widget 与 feishu-mem 后端之间的通信：

| 方式 | 适用场景 | 实现 |
|------|---------|------|
| **HTTP REST API** | 查询、列表、详情等同步操作 | Widget 通过 fetch 调用后端 HTTP API |
| **MCP over HTTP** | 复用已有 MCP 工具 | 将 MCP Server 包装为 HTTP 网关 |
| **WebSocket** | 实时推送（如新决策通知） | 可选，用于实时更新 |

**推荐方案**：将现有的 MCP Server 工具集通过 HTTP 网关暴露，Widget 通过 HTTP 调用。

### 3.3 HTTP API 网关设计

在现有 feishu-mem 基础上新增一个轻量 HTTP 接口层，将 MCP 工具包装为 RESTful API：

```
POST  /api/decisions/search      # 搜索决策
GET   /api/decisions/:id         # 获取决策详情
POST  /api/decisions             # 创建决策
PATCH /api/decisions/:id         # 更新决策
POST  /api/decisions/:id/confirm # 确认决策
POST  /api/decisions/:id/reject  # 拒绝决策
GET   /api/topics                # 议题列表
GET   /api/timeline              # 时间线
GET   /api/stats                 # 统计信息
POST  /api/check-conflict        # 冲突检测
GET   /api/hot-decisions         # 热点排名
GET   /api/relations/:id         # 关联关系
```

### 3.4 Widget 端代码结构

```
feishu-mem-docs-addon/
├── app.json                          # 插件全局配置
├── package.json
├── tsconfig.json
├── webpack.config.js
├── src/
│   ├── index.ts                      # 入口
│   ├── api/
│   │   ├── client.ts                 # HTTP API 客户端
│   │   └── types.ts                  # API 类型定义
│   │
│   ├── components/
│   │   ├── DecisionCard/
│   │   │   ├── index.tsx
│   │   │   ├── Card.tsx
│   │   │   └── styles.css
│   │   ├── DecisionList/
│   │   │   ├── index.tsx
│   │   │   ├── List.tsx
│   │   │   └── styles.css
│   │   ├── DecisionTimeline/
│   │   │   ├── index.tsx
│   │   │   └── styles.css
│   │   ├── TopicBoard/
│   │   │   ├── index.tsx
│   │   │   └── styles.css
│   │   ├── MemoryAssistant/
│   │   │   ├── index.tsx
│   │   │   └── styles.css
│   │   ├── RelationGraph/
│   │   │   ├── index.tsx
│   │   │   └── styles.css
│   │   └── DecisionEditor/
│   │       ├── index.tsx
│   │       └── styles.css
│   │
│   ├── views/
│   │   ├── decision-card.html          # 正文组件入口
│   │   ├── decision-list.html
│   │   ├── decision-timeline.html
│   │   ├── topic-board.html
│   │   ├── memory-assistant.html       # 浮动组件入口
│   │   ├── relation-graph.html         # 全屏视图入口
│   │   └── decision-editor.html        # 模态视图入口
│   │
│   └── utils/
│       ├── blockit.ts                  # BlockitClient 封装
│       ├── auth.ts                     # 认证逻辑
│       └── format.ts                   # 格式化工具
│
└── docs/
    └── configuration.md
```

### 3.5 app.json 配置

```json
{
  "manifestVersion": 1,
  "appID": "cli_xxxxxxxxxxxxx",
  "blockTypeID": "blk_xxxxxxxxxxxxx",
  "projectName": "feishu-mem-docs-addon",
  "contributes": {
    "addPanel": {
      "initialHeight": 320,
      "view": "src/views/decision-card.html"
    },
    "fullscreen": {
      "view": "src/views/relation-graph.html"
    },
    "floatCard": {
      "view": "src/views/decision-detail-float.html"
    },
    "modal": {
      "view": "src/views/decision-editor.html"
    },
    "popup": {
      "view": "src/views/quick-actions.html"
    }
  }
}
```

### 3.6 关键技术点

#### 3.6.1 用户认证

Widget 通过 `Service.User.login()` 获取 User Access Token，用于调用后端 API：

```typescript
const { code } = await DocMiniApp.Service.User.login();
// 将 code 发送到后端换取 user access token
const token = await fetch('/api/auth/exchange', { 
  method: 'POST', 
  body: JSON.stringify({ code }) 
});
```

#### 3.6.2 文档上下文获取

Widget 可以获取当前文档的上下文信息，用于关联决策与文档：

```typescript
const docToken = await DocMiniApp.Document.getDocToken();
const docTitle = await DocMiniApp.Document.getTitle();
const selection = await DocMiniApp.Document.getSelection();
```

#### 3.6.3 与后端通信

```typescript
// API 客户端示例
class MemoryApiClient {
  private baseUrl: string;
  private token: string;

  async searchDecisions(query: string, filters?: Filters): Promise<Decision[]> {
    const res = await fetch(`${this.baseUrl}/api/decisions/search`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query, filters }),
    });
    return res.json();
  }

  async createDecision(data: CreateDecisionInput): Promise<Decision> {
    const res = await fetch(`${this.baseUrl}/api/decisions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    return res.json();
  }
}
```

#### 3.6.4 文档内容交互

Widget 可以将选中的文档内容作为决策上下文：

```typescript
// 选区文本作为决策内容
const selection = await DocMiniApp.Document.getSelection();
const selectedText = selection.getText();

// 关联当前文档到决策
const docId = await DocMiniApp.Document.getDocToken();
```

---

## 4. 开发计划

### 阶段一：基础设施搭建（1-2天）

| 任务 | 产出 |
|------|------|
| 搭建 Docs Add-on 项目骨架 | `opdev create` 生成项目 |
| 实现 HTTP API 网关层 | FastAPI 路由 + MCP 工具封装 |
| 配置 app.json 和开发环境 | 飞书开放平台 App 注册 + 配置 |
| 实现基础认证流程 | User Token 获取 + 后端验证 |

### 阶段二：核心组件开发（3-5天）

| 任务 | 产出 |
|------|------|
| Decision Card 组件 | 正文组件 - 展示单个决策详情 |
| Decision List 组件 | 正文组件 - 搜索/筛选决策列表 |
| Decision Editor 模态视图 | 模态视图 - 创建/编辑决策 |
| Memory Assistant 浮动组件 | 浮动组件 - 常驻助手面板 |

### 阶段三：高级组件开发（2-3天）

| 任务 | 产出 |
|------|------|
| Decision Timeline 组件 | 正文组件 - 时间线视图 |
| Topic Board 组件 | 正文组件 - 议题看板 |
| Relation Graph 全屏视图 | 全屏视图 - 关系网络图可视化 |
| Decision Detail FloatCard | 浮卡片 - 决策详情预览 |

### 阶段四：集成与优化（1-2天）

| 任务 | 产出 |
|------|------|
| 文档上下文关联 | 决策与当前文档自动关联 |
| 冲突检测集成 | 在编辑决策时自动检测冲突 |
| 样式打磨与国际化 | 支持多语言、暗黑模式适配 |
| 端到端测试 | 完整的测试流程 |

---

## 5. 典型使用场景

### 场景一：撰写项目周报时引用决策

1. 用户在文档中使用 `/Decision List` 插入决策列表组件
2. 搜索 "本周" 或筛选时间范围
3. 组件展示本周所有决策
4. 用户点击单条决策展开为详细卡片
5. 决策内容直接嵌入周报

### 场景二：文档评审时创建决策

1. 用户在某份设计文档中撰写评审意见
2. 选中关键文本 → 右键 "创建决策"
3. 弹出 Modal 编辑框，自动填入选中文本
4. 填写执行人、影响等级后提交
5. 决策自动写入记忆库，并关联当前文档

### 场景三：项目复盘时查看决策时间线

1. 用户在文档中插入 `/Decision Timeline` 组件
2. 选择项目和时间范围
3. 展示可视化时间线，按周/月分组
4. 每个节点可展开查看决策详情和版本历史
5. 可直接在时间线视图中标注里程碑

### 场景四：协作编写技术方案时查询历史决策

1. 用户在文档中调出 Memory Assistant 浮动面板
2. 输入 "数据库选型"
3. 面板展示相关决策列表
4. 点击某条决策 → 浮卡片展示详情
5. 用户确认后可直接引用到文档正文

### 场景五：文档内容与已有决策冲突检查

1. 用户在文档中完成某个章节
2. 点击 "冲突检测" 按钮
3. 系统将文档内容与记忆库中的决策进行语义比对
4. 发现冲突时弹出提示，列出冲突决策
5. 用户可选择修改文档内容或重新审视历史决策

---

## 6. 安全与权限

| 安全项 | 措施 |
|--------|------|
| **用户认证** | 通过飞书 User Token 认证，后端验证 token 有效性 |
| **数据隔离** | 每个用户/群组只能访问自己有权限的决策数据 |
| **API 鉴权** | 后端 API 使用 Bearer Token 鉴权 |
| **内容安全** | Widget 内容遵循 CSP（内容安全策略）配置 |
| **HTTPS** | 所有 API 通信使用 HTTPS |

---

## 7. 现有资源复用

以下 feishu-mem 的现有能力可直接复用：

| 现有模块 | 复用方式 | 对应组件 |
|---------|---------|---------|
| `src/graph/retrieval.py` - HierarchicalRetriever | HTTP API 包装 | Decision List |
| `src/node/node.py` - DecisionNode | 数据模型 | 所有组件 |
| `src/storage/git_storage.py` - GitStorage | 版本历史查询 | Timeline, 决策历史 |
| `src/mcp_server/server.py` - 39个MCP工具 | HTTP API 映射 | 所有组件 |
| `src/card/renderer.py` - 卡片渲染 | 样式参考 | Decision Card |
| `src/engine/mutations.py` - 决策变更 | 创建/更新 API | Decision Editor |
| `src/detect/detector.py` - 冲突检测 | 冲突判断 API | 冲突检测功能 |
| `src/graph/memory_graph.py` - MemoryGraph | 关系查询 | Relation Graph |

---

## 8. 后续扩展

- **双向同步**：文档中的决策变更可同步回群聊，群聊中的新决策可自动同步到文档
- **富文本编辑**：决策内容支持 Markdown/富文本编辑
- **评论互动**：在决策卡片上直接发起文档评论
- **批量操作**：支持批量确认/拒绝/归档决策
- **模板化**：支持预设周报模板，自动填充本周决策
- **权限集成**：与飞书文档的权限体系集成，控制决策的可见范围
