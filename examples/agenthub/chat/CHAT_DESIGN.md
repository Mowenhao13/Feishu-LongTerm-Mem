# 群聊/单聊设计文档

> **分析来源**: Repo2 (ref/repo2), Multica (ref/multica), Repo3 (ref/repo3)
> **推荐方案**: Repo2 WS Hub (主) + Multica Chat Store (前端参考)

---

## 1. 分析范围

| 仓库 | 实现 | 关键文件 |
|------|------|---------|
| **repo2** | Go — WebSocket Hub + Room 管理 | pkg/ws/{hub.go, room.go} |
| **multica** | TypeScript — Chat Store + Query/Mutation | packages/core/chat/{store,index,queries,mutations}.ts |
| **repo3** | TypeScript — WebSocket 协议 + 领域模型 + Mention Router | packages/shared-types/src/ws-protocol.ts, apps/server/src/conversation/mention-router.ts |
| repo2 还有多用户在线检测、群聊分组等功能 |

---

## 2. 方案对比

### 2.1 Repo2 WS Hub (推荐主方案)

**设计定位**: 基于消息总线的 WebSocket 中心，统一管理房间、私聊、广播、在线状态。

**核心架构**:

```
┌───────────────┐   消息总线    ┌───────────────┐
│  写通道        │──────bus─────→│ 事件循环       │
│  (Register/    │              │ (dispatch)    │
│   SendToRoom)  │              │               │
└───────────────┘              └───────┬───────┘
                                       │
              ┌────────────────────────┼────────────────────┐
              ▼                        ▼                    ▼
       ┌─────────────┐        ┌──────────────┐     ┌──────────────┐
       │ 房间消息     │        │ 私聊消息      │     │ 全局广播      │
       │ (RoomMsg)   │        │ (DirectMsg)  │     │ (Broadcast)  │
       └─────────────┘        └──────────────┘     └──────────────┘
```

**消息类型**:

```go
const (
    TypeMessageStreaming = "message.streaming" // Agent 流式输出
    TypeMessageComplete  = "message.complete"  // 消息完成
    TypeAgentStatus      = "agent.status"      // Agent 状态变更
    TypeError            = "error"
    TypeUserOnline       = "user.online"       // 用户上线
    TypeUserOffline      = "user.offline"      // 用户下线
    TypeMessageRecall    = "message.recall"    // 消息撤回
)
```

**Client 设计**:

```go
type Client struct {
    Conn          *websocket.Conn
    UserID        string
    Username      string
    ConnectedAt   time.Time
    lastPong      atomic.Int64     // 原子操作避免数据竞争
    lastActive    atomic.Int64     // 原子操作避免数据竞争

    sendCh        chan []byte      // 独立写缓冲通道
    mu            sync.Mutex       // 保护 Conn 的写操作
    closeOnce     sync.Once        // 保证 sendCh 只关闭一次
}
```

**Hub 消息总线**:

```go
type Hub struct {
    clients sync.Map     // string -> *[]*Client（同一用户多设备支持）
    bus      chan BusMessage
    rooms    map[string]map[*Client]bool  // roomID -> client set
    roomMu   sync.RWMutex
}

// 8 种总线消息类型
const (
    BusRegister      BusMessageType = iota  // 注册连接
    BusUnregister                            // 注销连接
    BusBroadcast                             // 全局广播
    BusRoomMsg                               // 房间消息
    BusDirectMsg                             // 私聊消息
    BusJoinRoom                              // 加入房间
    BusLeaveRoom                             // 离开房间
    BusPersistedMsg                          // 持久化消息推送
    BusCustomEvent                           // 自定义事件推送
)
```

**关键设计决策**:

| 特征 | Repo2 方案 | 理由 |
|------|-----------|------|
| **消息总线** | 单 goroutine 事件循环 | 无锁设计，所有状态操作在单 goroutine 中完成，无需额外同步 |
| **Client 存储** | sync.Map → `*[]*Client` | 支持同用户多设备同时在线 |
| **写缓冲** | channel 256 缓存 + 背压丢弃 | 防止慢消费者阻塞整个系统 |
| **心跳** | 30s Ping + 60s Pong 超时 | 可配置超时 + 原子操作避免竞态 |
| **房间模型** | map[string]map[*Client]bool | 支持 join/leave/SendToRoom/SendToRoomExcept |
| **持久化消息** | BusPersistedMsg → 按成员列表推送 | DB 写入完成后推送，房间+用户列表双重覆盖 |
| **用户在线** | 首次连接广播 online，最后一断广播 offline | 跨设备感知 |
| **最大连接** | maxConnsPerUser = 5 | 防止单用户耗尽资源 |
| **连接清理** | 15s 间隔巡检 pong 超时连接 | 自动清理僵尸连接 |
| **优雅关闭** | sync.Once + draining flag + 2s drain | 幂等关闭，排空待发消息 |

### 2.2 Multica Chat Store (前端参考)

**设计定位**: Zustand 驱动的聊天状态管理，Proxy 模式实现模块级单例。

```typescript
// store.ts — Zustand 聊天 store
// createChatStore(options): ChatStore — 创建含全量聊天状态的 store
//   - sessions: 会话列表
//   - messages: 消息列表
//   - drafts: 未发送草稿
//   - 选择器: useChatStore(state => state.sessions)

// index.ts — Proxy 单例模式
// 1. registerChatStore(store) — 应用启动时注册
// 2. useChatStore(selector) — 全局单例访问
```

**状态管理规则**: 前端遵循 Zustand + React Query 分离。

### 2.3 Repo3 Mention Router (参考)

```typescript
// mention-router.ts
// 职责: 解析用户消息中的 @mention → 路由到指定 Agent
// 过滤规则: 排除系统消息 / 排除自身 / 排除已删除 Agent
// 路由: @agentName → 对应 Agent 的 Chat 会话
```

---

## 3. 推荐方案: Repo2 WS Hub (主) + Multica Chat Store (前端)

### 3.1 AgentHub 聊天体系

```
Chat 系统
│
├── WS Hub (采纳 Repo2)
│   ├── 单 goroutine 消息总线 — 无锁设计
│   ├── Room 模型 — 群聊/单聊统一抽象
│   ├── Client 管理 — 多设备支持 + 连接数限制
│   ├── 8 种消息类型 — 覆盖全场景
│   ├── 心跳检测 — 30s Ping + 60s Pong
│   └── 优雅关闭 — draining + 排空
│
├── Room 类型 (AgentHub 设计)
│   ├── direct_chat    — 1 人 ↔ Agent (单聊)
│   ├── session_room   — 多人 + 多 Agent (围绕任务)
│   └── topic_room     — 多人 + 多 Agent (围绕主题)
│
├── Chat Store (采纳 Multica)
│   ├── Zustand: sessions/messages/drafts
│   ├── React Query: message list/mutations
│   └── Proxy 单例: registerChatStore + useChatStore
│
├── Mention Router (采纳 Repo3)
│   ├── @agentName → 路由到目标 Agent
│   ├── @squadName → Squad Leader 接收
│   └── @humanName → 路由到用户
│
└── 消息类型 (整合 Repo2 + AgentHub)
    ├── message.streaming — Agent 流式输出
    ├── message.complete  — 消息完成
    ├── agent.status      — Agent 状态变更
    ├── handoff.status    — Handoff 状态变更
    └── inbox.new         — 新通知
```

### 3.2 房间模型设计

```go
// 单聊和群聊统一用一个 Room 抽象

type RoomType string
const (
    RoomDirectChat  RoomType = "direct_chat"  // 1 人 1 Agent
    RoomSession     RoomType = "session"      // 多人 + 多 Agent
    RoomTopic       RoomType = "topic"        // 持续主题
)

type Room struct {
    ID           string           // 唯一标识
    Type         RoomType         // 房间类型
    WorkspaceID  string           // 所属工作区
    IssueID      *string          // 锚定的 Issue (session 类型)
    Members      []ActorRef       // {type: member|agent, id}
    Agents       []RuntimeAgent   // 加入房间的 Agent
    CreatedAt    time.Time
}

// Client 加入 Room 时:
// 1. Hub.JoinRoom(roomID, client) — WS 连接加入房间
// 2. 所有在 Room 中的成员收到 member_joined 事件
// 3. Agent 被 @mention 时 → Mention Router → Hub.SendToRoom(roomID, msg)
```

### 3.3 群聊 vs 单聊差异

| 维度 | 单聊 (direct_chat) | 群聊 (session_room) |
|------|-------------------|-------------------|
| **成员** | 1 人 + N Agent | M 人 + N Agent |
| **房间数量** | 每个组合一个 | 每次 Session 一个 |
| **发言规则** | 用户自由发言 | 用户自由发言，Agent 被 @ 才响应 |
| **Orchestrator** | 隐式存在 | 显式 @Orchestrator |
| **通知** | 所有消息 | 只有 @ 我 的消息 |
| **消息持久化** | 永久 | Session 结束后可选归档 |