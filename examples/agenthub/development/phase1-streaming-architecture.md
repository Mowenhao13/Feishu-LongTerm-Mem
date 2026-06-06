# Phase 1: Claude CLI 流式输出架构设计

基于 Multica 的分析，完整的从 Claude CLI 进程到前端流式输出链路如下：

## 1. 后端数据流

### 1.1 核心类型定义 (`packages/core/src/types/claude.ts`)

```typescript
export type MessageType =
  | "text"      // 普通文本输出
  | "thinking"  // 思考过程
  | "tool_use"   // 工具调用
  | "tool_result" // 工具结果
  | "status"    // 状态变更
  | "error"     // 错误信息
  | "log";      // 日志

export interface ClaudeStreamMessage {
  type: MessageType;
  content?: string;
  tool?: string;
  input?: Record<string, unknown>;
  output?: string;
  seq: number; // 序列号，用于保证顺序
}

export interface Session {
  id: string;
  taskId: string;
  messages: ClaudeStreamMessage[];
  done: boolean;
  error?: Error;
}

export interface ExecutionResult {
  exitCode: number;
  durationMs: number;
  messages: ClaudeStreamMessage[];
  error?: string;
}

export interface Backend {
  execute(
    prompt: string,
    options: ExecOptions
  ): {
    session: Session;
    messageChan: AsyncIterable<ClaudeStreamMessage>;
    result: Promise<ExecutionResult>;
  };
}

export interface ExecOptions {
  taskId: string;
  workspaceId: string;
  worktreePath: string;
  agentId: string;
  timeout?: number;
  onMessage?: (msg: ClaudeStreamMessage) => void;
}
```

### 1.2 Claude Adapter 实现 (`server/src/adapter/claude.ts`)

```typescript
import { exec } from "child_process";
import type { Backend, ClaudeStreamMessage, Session, ExecutionResult, ExecOptions } from "@agenthub/core/types";

export class ClaudeAdapter implements Backend {
  private binaryPath: string;
  private argsFilter: (args: string[]) => string[];

  constructor(binaryPath: string = "claude") {
    this.binaryPath = binaryPath;
    this.argsFilter = this.filterCustomArgs.bind(this);
  }

  execute(prompt: string, options: ExecOptions): {
    session: Session;
    messageChan: AsyncIterable<ClaudeStreamMessage>;
    result: Promise<ExecutionResult>;
  } {
    const sessionId = crypto.randomUUID();
    const session: Session = {
      id: sessionId,
      taskId: options.taskId,
      messages: [],
      done: false,
    };

    const args = [
      "-p",
      "--output-format",
      "stream-json",
      ...this.argsFilter(process.argv.slice(2)),
      prompt,
    ];

    const cmd = this.binaryPath;
    const child = spawn(cmd, args, {
      cwd: options.worktreePath,
      stdio: ["ignore", "pipe", "inherit"],
    });

    const channel = new Queue<ClaudeStreamMessage>();
    let seq = 0;

    const scanner = new Scanner(child.stdout!);
    scanner.onLine = (line: string) => {
      line = line.trim();
      if (!line) return;

      try {
        const parsed = JSON.parse(line) as Partial<ClaudeStreamMessage>;
        if (!parsed.type) return;

        const msg: ClaudeStreamMessage = {
          ...parsed,
          seq: seq++,
          type: parsed.type as MessageType,
        } as ClaudeStreamMessage;

        session.messages.push(msg);
        channel.enqueue(msg);

        options.onMessage?.(msg);
      } catch (e) {
        // 非JSON行，可能是debug输出，忽略或作为log
        channel.enqueue({
          type: "log",
          content: line,
          seq: seq++,
        });
      }
    };

    scanner.onClose = () => {
      channel.close();
    };

    scanner.start();

    const result = new Promise<ExecutionResult>((resolve) => {
      child.on("close", (code) => {
        session.done = true;
        resolve({
          exitCode: code || 0,
          durationMs: 0, // 计算得出
          messages: session.messages,
          error: code !== 0 ? `Exit code ${code}` : undefined,
        });
      });
    });

    const asyncIterable: AsyncIterable<ClaudeStreamMessage> = {
      [Symbol.asyncIterator]: () => {
        return {
          async next() {
            const msg = await channel.dequeue();
            if (msg === null) {
              return { done: true, value: undefined };
            }
            return { done: false, value: msg };
          },
        };
      },
    };

    return {
      session,
      messageChan: asyncIterable,
      result,
    };
  }

  private filterCustomArgs(args: string[]): string[] {
    // 参考 Multica：过滤危险参数
    const filtered = args.filter(arg => {
      const dangerous = ["--allow-unsafe", "--danger"];
      return !dangerous.some(d => arg.includes(d));
    });
    return filtered;
  }
}

// Simple bounded queue for streaming
class Queue<T> {
  private buf: T[] = [];
  private resolvers: ((value: T | null) => void)[] = [];
  private closed = false;

  enqueue(item: T): void {
    if (this.resolvers.length > 0) {
      const resolve = this.resolvers.shift()!;
      resolve(item);
    } else {
      this.buf.push(item);
    }
  }

  async dequeue(): Promise<T | null> {
    if (this.buf.length > 0) {
      return this.buf.shift()!;
    }
    if (this.closed) {
      return null;
    }
    return new Promise(resolve => {
      this.resolvers.push(resolve);
    });
  }

  close(): void {
    this.closed = true;
    while (this.resolvers.length > 0) {
      const resolve = this.resolvers.shift()!;
      resolve(null);
    }
  }
}
```

### 1.3 任务执行与 WS 广播 (`server/src/daemon/runner.ts`)

```typescript
import { ClaudeAdapter } from "../adapter/claude";
import { wsHub } from "../realtime/hub";
import type { Task } from "@agenthub/core/types";

export async function runTask(
  task: Task,
  worktreePath: string
): Promise<void> {
  const adapter = new ClaudeAdapter();
  const { session, messageChan, result } = adapter.execute(
    task.prompt,
    {
      taskId: task.id,
      workspaceId: task.workspaceId,
      worktreePath,
      agentId: task.agentId,
      onMessage: (msg) => {
        // 每收到一条消息，立即通过 WS 广播给所有连接的前端
        wsHub.broadcastToWorkspace(task.workspaceId, {
          type: "task:message",
          payload: {
            task_id: task.id,
            ...msg,
          },
        });
      },
    }
  );

  for await (const msg of messageChan) {
    // 已经通过 onMessage 广播，这里不需要重复处理
  }

  const finalResult = await result;

  // 任务完成，广播最终状态
  if (finalResult.exitCode === 0) {
    wsHub.broadcastToWorkspace(task.workspaceId, {
      type: "task:completed",
      payload: {
        task_id: task.id,
        chat_session_id: task.chatSessionId,
        elapsed_ms: finalResult.durationMs,
      },
    });
  } else {
    wsHub.broadcastToWorkspace(task.workspaceId, {
      type: "task:failed",
      payload: {
        task_id: task.id,
        chat_session_id: task.chatSessionId,
        error: finalResult.error,
      },
    });
  }
}
```

### 1.4 WebSocket Hub (`server/src/realtime/hub.ts`)

```typescript
import type { WebSocket } from "ws";
import type { WSMessage } from "@agenthub/core/types";

export class WSHub {
  private connections: Map<string, Set<WebSocket>> = new Map();

  addConnection(workspaceId: string, ws: WebSocket): void {
    if (!this.connections.has(workspaceId)) {
      this.connections.set(workspaceId, new Set());
    }
    this.connections.get(workspaceId)!.add(ws);

    ws.on("close", () => {
      this.removeConnection(workspaceId, ws);
    });
  }

  removeConnection(workspaceId: string, ws: WebSocket): void {
    const conns = this.connections.get(workspaceId);
    if (conns) {
      conns.delete(ws);
      if (conns.size === 0) {
        this.connections.delete(workspaceId);
      }
    }
  }

  broadcastToWorkspace(workspaceId: string, message: WSMessage): void {
    const conns = this.connections.get(workspaceId);
    if (!conns) return;

    const data = JSON.stringify(message);
    for (const ws of conns) {
      if (ws.readyState === ws.OPEN) {
        ws.send(data);
      }
    }
  }

  broadcastAll(message: WSMessage): void {
    const data = JSON.stringify(message);
    for (const [_, conns] of this.connections) {
      for (const ws of conns) {
        if (ws.readyState === ws.OPEN) {
          ws.send(data);
        }
      }
    }
  }
}

export const wsHub = new WSHub();
```

### 1.5 HTTP 入口 (`server/src/index.ts`)

```typescript
import { Hono } from "hono";
import { WebSocket } from "ws";
import { wsHub } from "./realtime/hub";

const app = new Hono();

// WebSocket upgrade endpoint
app.get("/ws", (c) => {
  const workspaceSlug = c.req.query("workspace_slug");
  if (!workspaceSlug) {
    return c.text("Bad Request", 400);
  }

  const ws = new WebSocket(c.req.raw);
  // 这里需要解析 workspaceId 从 slug...
  const workspaceId = "TODO";

  wsHub.addConnection(workspaceId, ws);

  ws.on("message", (data) => {
    // 客户端 -> 服务器消息暂不处理（测试阶段）
  });

  return new Response(null, { status: 101, webSocket: ws as any });
});

// Model 测试接口（用户要求：用/model命令测试获取输出）
app.post("/api/model", async (c) => {
  const { prompt } = await c.req.json();

  // SSE 流式响应
  c.header("Content-Type", "text/event-stream");
  c.header("Cache-Control", "no-cache");
  c.header("Connection", "keep-alive");

  const adapter = new ClaudeAdapter();
  const { messageChan } = adapter.execute(prompt, {
    taskId: "test-model",
    workspaceId: "test",
    worktreePath: process.cwd(),
    agentId: "test",
  });

  let id = 0;
  for await (const msg of messageChan) {
    const data = `data: ${JSON.stringify(msg)}\n\n`;
    c.write(data);
  }

  return c.body(null);
});

const port = parseInt(process.env.PORT || "3000", 10);
console.log(`Server starting on port ${port}`);
Bun.serve({
  fetch: app.fetch,
  port,
});
```

## 2. 前端数据流

### 2.1 核心类型 (`packages/core/src/types/events.ts`)

```typescript
export type WSEventType =
  | "task:queued"
  | "task:dispatch"
  | "task:running"
  | "task:waiting_local_directory"
  | "task:progress"
  | "task:completed"
  | "task:failed"
  | "task:message"
  | "task:cancelled";

export interface WSMessage {
  type: WSEventType;
  payload: unknown;
  actor_id?: string;
  actor_type?: string;
}

export interface TaskMessagePayload {
  task_id: string;
  seq: number;
  type: "tool_use" | "tool_result" | "thinking" | "text" | "error";
  tool?: string;
  content?: string;
  input?: Record<string, unknown>;
  output?: string;
}
```

### 2.2 时间线构建 (`packages/core/src/task/build-timeline.ts`)

```typescript
import type { TaskMessagePayload, TimelineItem } from "../types";

export function canMergeStreamingText(
  prev: TimelineItem,
  next: TimelineItem
): boolean {
  return (prev.type === "thinking" || prev.type === "text") &&
         prev.type === next.type;
}

export function coalesceTimelineItems(
  items: TimelineItem[]
): TimelineItem[] {
  const sorted = [...items].sort((a, b) => a.seq - b.seq);
  const out: TimelineItem[] = [];

  for (const item of sorted) {
    const prev = out[out.length - 1];
    if (prev && canMergeStreamingText(prev, item)) {
      out[out.length - 1] = {
        ...prev,
        content: `${prev.content ?? ""}${item.content ?? ""}`,
      };
      continue;
    }
    out.push(item);
  }

  return out;
}

export function appendTimelineItem(
  items: TimelineItem[],
  item: TimelineItem
): TimelineItem[] {
  return coalesceTimelineItems([...items, item]);
}

export function buildTimeline(
  msgs: TaskMessagePayload[]
): TimelineItem[] {
  const items: TimelineItem[] = msgs.map((msg) => ({
    seq: msg.seq,
    type: msg.type,
    tool: msg.tool,
    content: msg.content,
    input: msg.input,
    output: msg.output,
  }));
  return coalesceTimelineItems(items);
}
```

### 2.3 WSClient (`packages/core/src/api/ws-client.ts`)

```typescript
import type { WSMessage, WSEventType, WSClientIdentity } from "../types";

type EventHandler = (payload: unknown, actorId?: string, actorType?: string) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private baseUrl: string;
  private token: string | null = null;
  private workspaceSlug: string | null = null;
  private handlers = new Map<WSEventType, Set<EventHandler>>();
  private anyHandlers = new Set<(msg: WSMessage) => void>();
  private onReconnectCallbacks = new Set<() => void>();

  constructor(
    url: string,
    options?: {
      identity?: WSClientIdentity;
    }
  ) {
    this.baseUrl = url;
  }

  setAuth(token: string | null, workspaceSlug: string): void {
    this.token = token;
    this.workspaceSlug = workspaceSlug;
  }

  connect(): void {
    const url = new URL(this.baseUrl);
    if (this.workspaceSlug) {
      url.searchParams.set("workspace_slug", this.workspaceSlug);
    }

    this.ws = new WebSocket(url.toString());

    this.ws.onopen = () => {
      if (!this.token) return;
      this.ws!.send(JSON.stringify({
        type: "auth",
        payload: { token: this.token },
      }));
    };

    this.ws.onmessage = (event) => {
      let msg: WSMessage;
      try {
        msg = JSON.parse(event.data as string) as WSMessage;
      } catch (e) {
        console.warn("ws: unparseable message", event.data);
        return;
      }

      const handlers = this.handlers.get(msg.type);
      if (handlers) {
        for (const handler of handlers) {
          handler(msg.payload, msg.actor_id, msg.actor_type);
        }
      }
      for (const handler of this.anyHandlers) {
        handler(msg);
      }
    };

    this.ws.onclose = () => {
      setTimeout(() => this.connect(), 3000);
    };
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.handlers.clear();
    this.anyHandlers.clear();
  }

  on(event: WSEventType, handler: EventHandler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);
    return () => {
      this.handlers.get(event)?.delete(handler);
    };
  }

  onAny(handler: (msg: WSMessage) => void): () => void {
    this.anyHandlers.add(handler);
    return () => {
      this.anyHandlers.delete(handler);
    };
  }

  onReconnect(callback: () => void): () => void {
    this.onReconnectCallbacks.add(callback);
    return () => {
      this.onReconnectCallbacks.delete(callback);
    };
  }

  send(message: WSMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }
}
```

### 2.4 WS Provider (`packages/core/src/realtime/provider.tsx`)

```typescript
"use client";

import {
  createContext,
  use,
  useEffect,
  useState,
  useCallback,
} from "react";
import { WSClient } from "../api/ws-client";
import type { AuthState } from "../auth/store";
import type { UseBoundStore, StoreApi } from "zustand";

type EventHandler = (payload: unknown, actorId?: string, actorType?: string) => void;

interface WSContextValue {
  subscribe: (event: WSEventType, handler: EventHandler) => () => void;
}

const WSContext = createContext<WSContextValue | null>(null);

export interface WSProviderProps {
  children: React.ReactNode;
  wsUrl: string;
  authStore: UseBoundStore<StoreApi<AuthState>>;
}

export function WSProvider({
  children,
  wsUrl,
  authStore,
}: WSProviderProps) {
  const user = authStore((s) => s.user);
  const [wsClient, setWsClient] = useState<WSClient | null>(null);

  useEffect(() => {
    if (!user?.token) return;

    const ws = new WSClient(wsUrl);
    ws.setAuth(user.token, "current-slug");
    ws.connect();
    setWsClient(ws);

    return () => {
      ws.disconnect();
      setWsClient(null);
    };
  }, [user, wsUrl, authStore]);

  const subscribe = useCallback(
    (event: WSEventType, handler: EventHandler) => {
      if (!wsClient) return () => {};
      return wsClient.on(event, handler);
    },
    [wsClient]
  );

  return (
    <WSContext.Provider value={{ subscribe }}>
      {children}
    </WSContext.Provider>
  );
}

export function useWS() {
  const ctx = use(WSContext);
  if (!ctx) throw new Error("useWS must be used within WSProvider");
  return ctx;
}
```

### 2.5 实时同步到 Query Cache (`packages/core/src/realtime/use-realtime-sync.ts`)

```typescript
"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { WSClient } from "../api/ws-client";
import { taskMessageKeys } from "../task/queries";

export function useRealtimeSync(ws: WSClient | null) {
  const qc = useQueryClient();

  useEffect(() => {
    if (!ws) return;

    const unsub = ws.on("task:message", (payload) => {
      const p = payload as { task_id: string } & Record<string, unknown>;
      // 增量更新：直接追加到 QueryCache
      qc.setQueryData(
        taskMessageKeys.list(p.task_id),
        (old: unknown[] = []) => {
          return [...old, p];
        }
      );
    });

    return unsub;
  }, [ws, qc]);
}
```

### 2.6 查询键 (`packages/core/src/task/queries.ts`)

```typescript
export const taskKeys = {
  all: ["tasks"] as const,
  list: (workspaceId: string) => [...taskKeys.all, "list", workspaceId] as const,
  detail: (taskId: string) => [...taskKeys.all, "detail", taskId] as const,
};

export const taskMessageKeys = {
  all: ["task-messages"] as const,
  list: (taskId: string) => [...taskMessageKeys.all, "list", taskId] as const,
};
```

### 2.7 流式输出组件 (`apps/web/features/task/components/task-transcript.tsx`)

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { useWS } from "@agenthub/core/realtime/provider";
import { buildTimeline } from "@agenthub/core/task/build-timeline";
import { taskMessageKeys } from "@agenthub/core/task/queries";
import type { TaskMessagePayload, TimelineItem } from "@agenthub/core/types";

interface TaskTranscriptProps {
  taskId: string;
  isLive: boolean;
}

export function TaskTranscript({ taskId, isLive }: TaskTranscriptProps) {
  const { data: messages = [] } = useQuery({
    queryKey: taskMessageKeys.list(taskId),
    queryFn: () => api.getTaskMessages(taskId),
    // 因为 WS 已经在实时增量更新，所以设置较长的 staleTime
    staleTime: Infinity,
  });

  const timeline = buildTimeline(messages as TaskMessagePayload[]);

  useWS().subscribe("task:message", () => {
    // 不需要做任何事情 — queryCache 已经被 incremental setQueryData 更新
    // React Query 自动触发组件重渲染
  });

  return (
    <div className="space-y-2">
      {timeline.map((item) => (
        <TimelineEntry key={item.seq} item={item} />
      ))}
      {isLive && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
          <span className="w-2 h-2 rounded-full bg-blue-500"></span>
          Generating...
        </div>
      )}
    </div>
  );
}

function TimelineEntry({ item }: { item: TimelineItem }) {
  switch (item.type) {
    case "text":
      return (
        <div className="p-3 rounded bg-muted">
          <pre className="whitespace-pre-wrap text-sm">{item.content}</pre>
        </div>
      );
    case "thinking":
      return (
        <div className="p-2 rounded bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 text-sm italic">
          <span className="font-semibold">Thinking:</span> {item.content}
        </div>
      );
    case "tool_use":
      return (
        <div className="p-2 rounded border border-purple-500/30 bg-purple-500/10">
          <div className="text-xs font-semibold text-purple-600 dark:text-purple-400 mb-1">
            Using tool: {item.tool}
          </div>
          <pre className="text-xs">{JSON.stringify(item.input, null, 2)}</pre>
        </div>
      );
    case "tool_result":
      return (
        <div className="p-2 rounded border border-green-500/30 bg-green-500/10">
          <div className="text-xs font-semibold text-green-600 dark:text-green-400 mb-1">
            Tool result: {item.tool}
          </div>
          <pre className="text-xs whitespace-pre-wrap">{item.output}</pre>
        </div>
      );
    case "error":
      return (
        <div className="p-2 rounded border border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400">
          <span className="font-semibold text-xs">Error:</span> {item.content}
        </div>
      );
    default:
      return null;
  }
}
```

### 2.8 测试页面 (`apps/web/app/(dashboard)/test/model/page.tsx`)

```typescript
"use client";

import { useState, FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@agenthub/core/api/client";
import type { ClaudeStreamMessage } from "@agenthub/core/types";

export default function ModelTestPage() {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<ClaudeStreamMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const { mutate } = useMutation({
    mutationFn: async (prompt: string) => {
      setMessages([]);
      setIsStreaming(true);

      const response = await fetch("/api/model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      if (!response.body) {
        throw new Error("No response body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        // SSE 格式: "data: {...}\n\n"
        const lines = chunk.split("\n\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6)) as ClaudeStreamMessage;
              setMessages((prev) => [...prev, data]);
            } catch (e) {
              console.warn("Failed to parse SSE", e);
            }
          }
        }
      }

      setIsStreaming(false);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    mutate(prompt);
  };

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <h1 className="text-2xl font-bold mb-4">Test Claude CLI /model</h1>

      <form onSubmit={handleSubmit} className="mb-6">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter your prompt..."
          className="w-full h-32 p-3 rounded border bg-card"
        />
        <div className="mt-2 flex justify-end">
          <button
            type="submit"
            disabled={isStreaming || !prompt.trim()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded disabled:opacity-50"
          >
            {isStreaming ? "Streaming..." : "Send"}
          </button>
        </div>
      </form>

      <div className="space-y-3">
        <h2 className="text-lg font-semibold">
          Output {isStreaming && <span className="text-sm text-muted-foreground animate-pulse">(streaming...)</span>}
        </h2>
        {messages.map((msg, i) => (
          <div key={i} className="p-3 border rounded bg-card">
            <div className="text-xs text-muted-foreground mb-1">
              [{msg.type}] #{msg.seq}
            </div>
            {msg.content && (
              <pre className="whitespace-pre-wrap text-sm">{msg.content}</pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

## 3. 页面刷新恢复

遵循 Multica 的设计模式：

1. **后端**: 所有 `task:message` 持久化到数据库
2. **前端**: 组件挂载时调用 `GET /api/tasks/:id/messages` 获取全部历史
3. **Query Cache**: 缓存全量消息列表
4. **WS**: 实时增量追加到缓存，无需全量刷新
5. **构建时间线**: `buildTimeline(rawMessages)` → 合并相邻 text/thinking 片段，按 seq 排序

页面刷新后流程：
```
组件挂载 → useQuery 从缓存/HTTP 获取全量消息 → 构建时间线 → 渲染
↓
WS 连接 → 订阅 task:message → 增量追加到 QueryCache → React 自动更新
↓
新消息到达 → setQueryData 增量更新 → 组件重渲染 → 时间线重新构建
```

## 4. 项目结构

```
packages/
  core/                    # 共享核心类型和工具
    src/
      types/
        claude.ts         # Claude 流消息类型
        events.ts         # WS 事件类型
        task.ts           # 任务类型
      api/
        client.ts         # HTTP API 客户端
        ws-client.ts      # WebSocket 客户端
      realtime/
        provider.tsx      # React WS Context Provider
        use-realtime-sync.ts  # 实时同步到 QueryCache
      task/
        build-timeline.ts  # 时间线构建（合并相邻片段）
        queries.ts        # React Query 查询键
  ui/                     # 基础 UI 组件
  views/                  # 共享视图组件
apps/
  web/                    # Next.js 前端
    app/
      (dashboard)/
        layout.tsx
        issues/
          [id]/
            page.tsx
        test/
          model/
            page.tsx      # 测试页面（用户要求）
    features/
      task/
        components/
          task-transcript.tsx
server/                   # Bun/TypeScript 后端
  src/
    adapter/
      claude.ts           # Claude CLI 适配器（流式读取）
      codex.ts            # Codex CLI 适配器（JSON-RPC）
    daemon/
      runner.ts          # 任务运行器
    realtime/
      hub.ts              # WS Hub 广播
    index.ts              # 入口（Hono 服务器）
```

## 5. 启动测试

用户要求第一步：**用 /model 测试获取输出**

1. 启动后端服务器: `bun run server/src/index.ts`
2. 打开浏览器: `http://localhost:3000/test/model`
3. 输入 prompt，点击 Send
4. 观看 SSE 流式输出逐步显示在页面上

完成这个之后，再把 WS 实时广播集成到 Issue 详情页面。
