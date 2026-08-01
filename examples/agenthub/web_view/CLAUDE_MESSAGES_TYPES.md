前端通过消息类型字段区分模型回复的不同部分，后端将 CLI 输出解析为结构化的消息类型，前端根据类型渲染不同的 UI 组件。 [1](#3-0) [2](#3-1) 

---

## 后端消息类型解析

后端在 `server/pkg/agent/` 包中统一处理不同 provider 的输出，将其转换为标准的 `Message` 类型：

### Claude Provider
Claude CLI 输出 NDJSON，`handleAssistant` 函数解析 content block 并根据类型发送不同消息 [1](#3-0) 
- **Copilot**：处理 `assistant.message` 中的 `ReasoningText` 作为思考内容 [3](#3-2) 
- **Hermes**：通过 `handleAgentThought` 发送思考内容 [4](#3-3) 

## 前端消息类型定义

前端使用 `ChatTimelineItem` 类型统一表示时间线中的不同条目 [2](#3-1) 
- **ToolCallRow**：渲染工具调用
- **ToolResultRow**：渲染工具结果
- **ErrorRow**：渲染错误信息

### 时间线布局
`TimelineView` 使用 `splitTimeline` 将内容分为三部分 [5](#3-4) 

## 数据流

```
CLI 输出 (NDJSON/JSON-RPC)
  ↓
Provider 解析 (claude.go, cursor.go, etc.)
  ↓
统一 Message 类型 (MessageText, MessageThinking, MessageToolUse)
  ↓
WebSocket 实时推送到前端
  ↓
前端转换为 ChatTimelineItem
  ↓
根据 type 渲染不同 UI 组件
```

## Notes

所有 provider 都遵循相同的消息类型抽象，前端无需关心底层 CLI 的具体协议差异。思考内容默认折叠以保持界面整洁，用户可点击展开查看详细推理过程。Web 和 Mobile 端的渲染逻辑保持一致，仅 UI 组件实现不同。

Wiki pages you might want to explore:
- [Agent Provider Implementations (multica-ai/multica)](/wiki/multica-ai/multica#10.2)
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)

### Citations

**File:** server/pkg/agent/claude.go (L239-279)
```go
func (b *claudeBackend) handleAssistant(msg claudeSDKMessage, ch chan<- Message, output *strings.Builder, usage map[string]TokenUsage) {
	var content claudeMessageContent
	if err := json.Unmarshal(msg.Message, &content); err != nil {
		return
	}

	// Accumulate token usage per model.
	if content.Usage != nil && content.Model != "" {
		u := usage[content.Model]
		u.InputTokens += content.Usage.InputTokens
		u.OutputTokens += content.Usage.OutputTokens
		u.CacheReadTokens += content.Usage.CacheReadInputTokens
		u.CacheWriteTokens += content.Usage.CacheCreationInputTokens
		usage[content.Model] = u
	}

	for _, block := range content.Content {
		switch block.Type {
		case "text":
			if block.Text != "" {
				output.WriteString(block.Text)
				trySend(ch, Message{Type: MessageText, Content: block.Text})
			}
		case "thinking":
			if block.Text != "" {
				trySend(ch, Message{Type: MessageThinking, Content: block.Text})
			}
		case "tool_use":
			var input map[string]any
			if block.Input != nil {
				_ = json.Unmarshal(block.Input, &input)
			}
			trySend(ch, Message{
				Type:   MessageToolUse,
				Tool:   block.Name,
				CallID: block.ID,
				Input:  input,
			})
		}
	}
}
```

**File:** packages/core/chat/store.ts (L62-69)
```typescript
export interface ChatTimelineItem {
  seq: number;
  type: "tool_use" | "tool_result" | "thinking" | "text" | "error";
  tool?: string;
  content?: string;
  input?: Record<string, unknown>;
  output?: string;
}
```

**File:** server/pkg/agent/copilot.go (L95-97)
```go
		if msg.ReasoningText != "" {
			msgs = append(msgs, Message{Type: MessageThinking, Content: msg.ReasoningText})
		}
```

**File:** server/pkg/agent/hermes.go (L778-791)
```go
func (c *hermesClient) handleAgentThought(data json.RawMessage) {
	var msg struct {
		Content struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
	}
	if err := json.Unmarshal(data, &msg); err != nil || msg.Content.Text == "" {
		return
	}
	if c.onMessage != nil {
		c.onMessage(Message{Type: MessageThinking, Content: msg.Content.Text})
	}
}
```

**File:** packages/views/chat/components/chat-message-list.tsx (L385-435)
```typescript
// ─── Timeline: outer process fold + final text (Conductor-style) ─────────
//
// splitTimeline (lib/copy-text.ts) carves the items into:
//   preface — text before the first thinking/tool item
//   middle  — first → last non-text item (inclusive, may sandwich text)
//   final   — text after the last non-text item
//
// We render preface + final outside an outer Collapsible ("X steps") that
// wraps middle. The inner row Collapsibles (ThinkingRow / ToolCallRow /
// ToolResultRow) are unchanged — clicking them toggles independently of
// the outer fold. Copy mirrors what's visible when the outer fold is
// closed: preface + final, never middle. See extractCopyText for the
// authoritative copy logic.

function TimelineView({
  items,
  isStreaming,
  attachments,
}: {
  items: ChatTimelineItem[];
  isStreaming?: boolean;
  attachments?: import("@multica/core/types").Attachment[];
}) {
  const { preface, middle, final } = splitTimeline(items);

  return (
    <>
      {preface.length > 0 && (
        <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none">
          <Markdown attachments={attachments}>
            {preface.map((t) => t.content ?? "").join("")}
          </Markdown>
        </div>
      )}
      {middle.length > 0 && (
        <OuterProcessFold
          items={middle}
          defaultOpen={!!isStreaming}
          attachments={attachments}
        />
      )}
      {final.length > 0 && (
        <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none">
          <Markdown attachments={attachments}>
            {final.map((t) => t.content ?? "").join("")}
          </Markdown>
        </div>
      )}
    </>
  );
}
```
