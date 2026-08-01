# Web View 设计文档

## 1. 分析范围

本文档参考 Multica 前端架构进行设计。Multica 是一个多平台协作工具，其前端代码组织为 pnpm monorepo，核心源码位于以下包中：

- **apps/web** — Next.js Web 应用，包含页面路由、布局、平台适配层
- **apps/desktop** — Electron 桌面应用，共享 core/ui/views 包
- **apps/mobile** — Expo React Native 移动应用
- **packages/core** — 无 UI 依赖的业务逻辑层：API 客户端、WebSocket 客户端、认证、状态管理、实时同步、查询定义
- **packages/ui** — 原子 UI 组件库（基于 Radix UI + Tailwind）
- **packages/views** — 跨平台共享页面视图（看板、收件箱、聊天等）

## 2. 架构概览

### 2.1 整体架构

Multica 采用 Go 后端（Chi router + gorilla/websocket）提供 REST API 和 WebSocket 实时推送。前端采用五层架构：

- **Store 层（状态管理）**: TanStack Query 管理服务端缓存，Zustand 管理客户端本地状态，两者严格分离
- **API 层（网络通信）**: ApiClient（HTTP REST）+ WSClient（WebSocket 长连接）
- **WS 层（实时事件）**: WSProvider 通过 React Context 分发事件，useRealtimeSync 将事件映射为 Query 缓存失效
- **Views 层（页面视图）**: 跨平台共享页面组件（packages/views），根据平台注入不同的导航适配器
- **UI 层（原子组件）**: 无业务逻辑的基础组件库（packages/ui）

**AgentHub 的选择**: 与 Multica 不同，AgentHub 后端采用 TypeScript（Bun 运行时），与前端共享同一语言。后端使用 Hono 处理 HTTP/WS，Drizzle/Prisma 管理数据库。`packages/core/` 中的类型定义（Handoff DAG、Event Store、Actor 等）由前后端共同引用，实现零重复的类型定义共享。

状态管理的核心原则：

- TanStack Query 是服务端状态的唯一信源，所有 API 返回的数据都通过 Query 缓存管理
- Zustand 仅管理客户端本地状态（如导航记录、聊天活跃会话、Modal 开关）
- 两者之间不存在数据镜像——避免缓存不一致

### 2.2 实时通信

Multica 的实时通信架构围绕 WebSocket 长连接构建，核心组件包括：

- **WSClient** (`packages/core/api/ws-client.ts`): 轻量级 WebSocket 客户端，支持 auth/workspace 隔离、自动重连、事件订阅。连接建立后先发送 auth 消息完成身份认证，再订阅当前 workspace。断开后 3 秒自动重连，重连后重新执行完整订阅流程

- **WSProvider** (`packages/core/realtime/provider.tsx`): React Context Provider，监听认证状态和当前 workspace slug 变化。当 workspace 切换时，自动销毁旧 WSClient 实例并创建新实例绑定到新的 workspace。通过 React 的 `useSyncExternalStore` 响应式读取 workspace slug（URL 驱动的单例）

- **useRealtimeSync** (`packages/core/realtime/use-realtime-sync.ts`): 核心实时同步 Hook。将 WebSocket 事件分为两类处理：
  - 通用事件（如 `issue:updated`、`inbox:new` 等）→ 触发对应 Query 缓存失效，驱动自动重新获取
  - 副作用事件（如 `workspace:deleted`、`member:removed`）→ 触发导航跳转、Toast 通知等 UI 行为
  - 通过 100ms 防抖避免高频事件（如批量更新）导致过多请求

- **useWSEvent / useWSReconnect** (`packages/core/realtime/hooks.ts`): 面向组件的轻量 Hook，用于订阅特定事件或在重连后执行回调

### 2.3 平台适配

Multica 通过 **CoreProvider + NavigationAdapter** 模式实现跨平台桥接：

- **NavigationAdapter** (`packages/views/navigation/types.ts`): 定义 `push`、`replace`、`back`、`pathname`、`searchParams`、`getShareableUrl`、`prefetch`、`openInNewTab` 等接口。Web 平台对接 Next.js Router，Desktop 对接 react-router，Mobile 对接 Expo Router

- **NavigationProvider** (`packages/views/navigation/context.tsx`): React Context 包装器，将 NavigationAdapter 注入组件树，并通过 `useTransition` 提供导航加载状态（`useIsNavigating`）

- **CoreProvider** (`packages/core/platform/types.ts`): 聚合 API 基础 URL、WS URL、存储适配器、认证配置、国际化配置等平台差异点，作为根组件一次性注入

## 3. AgentHub Web View 设计

### 3.1 页面结构

从用户视角出发的页面导航结构如下：

```
Landing Page → 登录 → Dashboard
                          ├── 看板 (Kanban View)
                          ├── Agent 状态 (Agent Status)
                          ├── 会话视图 (Session View)
                          ├── 消息 (Inbox)
                          └── 设置 (Settings)
```

- **Landing Page**: 产品介绍页，未登录用户的入口
- **登录**: 认证流程，支持多种登录方式
- **Dashboard**: 登录后的主界面，包含以下子视图
- **看板视图**: AgentHub 的核心视图，可视化展示 Handoff DAG 的状态
- **Agent 状态视图**: 各 Agent 的实时运行状态
- **会话视图**: Worker Agent 在 Worktree 内的执行过程展示
- **消息**: 系统通知和 Agent 推送的消息
- **设置**: 用户偏好和系统配置

### 3.2 核心视图

**看板视图**: 可视化 Handoff DAG 的执行状态。每个 Issue 卡片展示 handoff 的标题、状态（待处理/运行中/已完成/失败）、分配的 Agent 以及执行摘要。看板列按 Handoff 状态划分，支持拖拽操作改变状态

**Agent 状态视图**: 实时显示各 Agent 的当前状态（空闲/忙碌/故障），所在 Worktree，以及正在执行的 Handoff 信息。支持按状态、Worktree 过滤

**会话视图**: 展示 Worker Agent 在 Worktree 内的执行过程。支持可选的流式输出，实时展示 Agent 的思考过程和执行步骤

**时序图视图**: Handoff DAG 执行过程的时间线可视化。展示并行分支的执行时间线、依赖链的阻塞关系、各 Agent 的执行耗时

### 3.3 状态投射

看板状态不是直接读取数据库的产物，而是 Event Store 的投影：

- **事件日志是唯一真相源**: 所有 Handoff 状态变化（创建、分配、开始、完成、失败）都以事件形式写入 Event Store
- **看板状态 = 投影**: 看板显示的 Issue 卡片列表、状态分布、分配关系，都是从 Event Store 的事件流经过投影计算得到
- **支持时间旅行**: 可以通过回放 Event Store 的事件流，重建任意时间点的看板状态快照，用于审计和问题排查

### 3.4 实时推送

AgentHub 的实时更新完全基于事件驱动：

- Worker Agent 在执行过程中产生的 `handoff_complete`、`handoff_block`（阻塞等待）、`handoff_show`（输出中间结果）等事件，通过 Event Store 广播
- 前端 WebSocket 连接接收这些事件推送，自动更新看板卡片状态、Agent 状态面板和会话视图
- 无需前端轮询，无需用户手动刷新页面
- 事件驱动缓存失效机制确保多窗口/多用户间视图状态一致

## 4. 关键设计决策

### 4.1 状态管理策略

AgentHub 采用以 Event Store 为中心的架构：

- **事件日志（Event Store）** 是系统的唯一真相源。所有状态变化都以不可变事件的形式追加存储
- **看板状态是投影**：从 Event Store 事件流通过投影计算得出，随时可以重建
- **前端不直接缓存服务端投影结果**：前端 Query 缓存（如 TanStack Query）仅缓存最近一次投影结果，通过 WebSocket 事件驱动自动失效
- **客户端本地状态**（如当前选中看板列、筛选条件等）使用轻量级状态管理工具（如 Zustand）管理

### 4.2 与 Multica 的差异

| 维度 | Multica | AgentHub |
|------|---------|----------|
| 服务端状态源 | PostgreSQL 数据库 | Event Store（事件日志） |
| 前端缓存策略 | TanStack Query 管理 API 缓存，WS 事件驱动缓存失效 | Event Store 投影取代 Query 缓存，WS 事件驱动前端直接更新 |
| 状态可回溯性 | 有限（基于数据库快照） | 原生支持（Event Store 时间旅行） |
| 实时更新范围 | REST API + WebSocket 双向 | WebSocket 单向事件推送为主 |
| 页面复杂度 | 多实体 CRUD（Issue、Inbox、Chat、Project） | 聚焦看板 DAG 可视化和 Agent 状态监控 |
| 跨平台需求 | Web / Desktop / Mobile 三端 | 初期以 Web 为主 |

## 5. 推荐方案

基于 Multica 的五层前端架构（Store → API → WS → Views → UI），针对 AgentHub 的业务特点进行调整：

- **保留五层架构**: 保持 Store / API / WS / Views / UI 的分层结构，确保关注点分离
- **替换状态管理层**: 将 Multica 的 TanStack Query + REST API 缓存模式，替换为 Event Store 投影模式。Query 层不再直接读取 API，而是从投影服务获取数据
- **强化 WebSocket 层**: 采用 Multica 的 WSClient + WSProvider + useRealtimeSync 模式，但事件处理逻辑从"失效 Query 缓存"调整为"直接更新投影状态"
- **精简视图范围**: 以看板视图和 DAG 可视化作为核心交互界面，Agent 状态和 Session 执行过程作为辅助面板

前端页面渲染以看板和 DAG 可视化为主，Agent 的运行状态和执行日志流为辅。整体设计强调事件的实时性、状态的可追溯性，以及架构的简洁性。