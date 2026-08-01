前端输入文本发送给本地 Claude CLI 的流程如下：

## 数据流概览

前端文本通过以下路径传递给本地 Claude CLI：

```
前端输入 → HTTP API → 任务队列 → Daemon 轮询认领 → 启动 Claude CLI 子进程 → 写入 stdin
```

## 详细流程

### 1. 前端输入处理

前端使用 `ChatInput` 组件接收用户输入，通过 `onSend` 回调发送文本和附件 ID [1](#0-0) 。

### 2. 后端任务入队

后端接收请求后，通过 `EnqueueTaskForIssue` 将任务加入 `agent_task_queue` 表 [2](#0-1) 。

### 3. Daemon 认领任务

本地 Daemon 每 3 秒轮询服务器，通过 `ClaimTask` 使用 `FOR UPDATE SKIP LOCKED` 策略认领任务 [3](#0-2) 。

### 4. Daemon 执行 Agent

Daemon 调用 `agent.Backend.Execute()` 接口执行任务，传入 prompt 和执行选项 [4](#0-3) 。

### 5. Claude CLI 启动与输入写入

对于 Claude provider，`claudeBackend.Execute` 执行以下步骤：

- 使用 `exec.CommandContext` 启动 `claude` 进程，参数由 `buildClaudeArgs` 构建（包括 `--output-format stream-json` 等） [5](#0-4) 
- 通过 `writeClaudeInput` 将 prompt 写入进程的 stdin [6](#0-5) 
- `buildClaudeInput` 将 prompt 格式化为 JSON 格式：`{"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}` [7](#0-6) 

### 6. 输出流式返回

Claude CLI 的 stdout 通过 scanner 逐行读取，解析 NDJSON 消息并通过 WebSocket 实时推回前端 [8](#0-7) 。

## 关键代码位置

| 阶段 | 文件 | 函数/组件 |
|------|------|----------|
| 前端输入 | `packages/views/chat/components/chat-input.tsx` | `ChatInput.onSend` |
| 任务入队 | `server/internal/service/task.go` | `EnqueueTaskForIssue` |
| 任务认领 | `server/internal/service/task.go` | `ClaimTask` |
| Claude 执行 | `server/pkg/agent/claude.go` | `claudeBackend.Execute` |
| 输入写入 | `server/pkg/agent/claude.go` | `writeClaudeInput` |
| 参数构建 | `server/pkg/agent/claude.go` | `buildClaudeArgs` |

## Notes

整个流程的核心是 Daemon 作为本地代理，它不直接处理业务逻辑，只负责将 server 下达的任务转换为本地 CLI 进程的执行，并将输出流式传回。文本通过 stdin 以 JSON 格式传递给 Claude CLI，这是 `stream-json` 协议的要求。

Wiki pages you might want to explore:
- [Quick Start and Self-Hosting (multica-ai/multica)](/wiki/multica-ai/multica#1.1)
- [Agent Provider Implementations (multica-ai/multica)](/wiki/multica-ai/multica#10.2)
- [Glossary (multica-ai/multica)](/wiki/multica-ai/multica#15)

### Citations

**File:** packages/views/chat/components/chat-input.tsx (L22-30)
```typescript
interface ChatInputProps {
  onSend: (content: string, attachmentIds?: string[]) => void;
  /** Receives a File and returns the attachment row (with id + CDN link).
   *  The wrapper owner (ChatWindow) lazy-creates a chat_session if needed
   *  and forwards `chatSessionId` to the upload — chat-input only cares
   *  about the upload result so it can map URL → id for back-fill on send.
   *  When unset, paste/drag/button still type into the editor but no upload
   *  fires (the editor's file-upload extension is a no-op without a handler). */
  onUploadFile?: (file: File) => Promise<UploadResult | null>;
```

**File:** server/pkg/agent/claude.go (L62-69)
```go
	cmd := exec.CommandContext(runCtx, execPath, args...)
	hideAgentWindow(cmd)
	b.cfg.Logger.Info("agent command", "exec", execPath, "args", args)
	cmd.WaitDelay = 10 * time.Second
	if opts.Cwd != "" {
		cmd.Dir = opts.Cwd
	}
	cmd.Env = buildEnv(b.cfg.Env)
```

**File:** server/pkg/agent/claude.go (L100-112)
```go
	if err := writeClaudeInput(stdin, prompt); err != nil {
		// claude almost certainly died during startup (broken pipe). The
		// real reason is sitting in stderrBuf — surface it the same way the
		// post-handshake error path does, otherwise the daemon log is the
		// only place that knows whether it was a V8 abort, a missing native
		// module, or anything else. cmd.Wait() flushes os/exec's stderr
		// copy goroutine, so stderrBuf.Tail() is safe to read.
		closeStdin()
		cancel()
		_ = cmd.Wait()
		return nil, errors.New(withAgentStderr(fmt.Sprintf("write claude input: %v", err), "claude", stderrBuf.Tail()))
	}
	closeStdin()
```

**File:** server/pkg/agent/claude.go (L143-190)
```go
		scanner := bufio.NewScanner(stdout)
		scanner.Buffer(make([]byte, 0, 1024*1024), 10*1024*1024)

		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line == "" {
				continue
			}

			var msg claudeSDKMessage
			if err := json.Unmarshal([]byte(line), &msg); err != nil {
				continue
			}

			switch msg.Type {
			case "assistant":
				b.handleAssistant(msg, msgCh, &output, usage)
			case "user":
				b.handleUser(msg, msgCh)
			case "system":
				if msg.SessionID != "" {
					sessionID = msg.SessionID
				}
				trySend(msgCh, Message{Type: MessageStatus, Status: "running", SessionID: sessionID})
			case "result":
				closeStdin()
				sessionID = msg.SessionID
				if msg.ResultText != "" {
					output.Reset()
					output.WriteString(msg.ResultText)
				}
				if resultUsage := claudeResultUsage(msg, opts.Model); len(resultUsage) > 0 {
					usage = resultUsage
				}
				if msg.IsError {
					finalStatus = "failed"
					finalError = msg.ResultText
				}
			case "log":
				if msg.Log != nil {
					trySend(msgCh, Message{
						Type:    MessageLog,
						Level:   msg.Log.Level,
						Content: msg.Log.Message,
					})
				}
			}
		}
```

**File:** server/pkg/agent/claude.go (L532-550)
```go
func buildClaudeInput(prompt string) ([]byte, error) {
	payload := map[string]any{
		"type": "user",
		"message": map[string]any{
			"role": "user",
			"content": []map[string]string{
				{
					"type": "text",
					"text": prompt,
				},
			},
		},
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal claude input: %w", err)
	}
	return append(data, '\n'), nil
}
```
