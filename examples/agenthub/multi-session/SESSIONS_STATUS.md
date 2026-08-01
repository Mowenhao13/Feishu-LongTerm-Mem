会话状态相关的 API 分布在后端路由、处理器、数据库查询和前端客户端中。 [1](#17-0) [2](#17-1) 

---

## 后端 API 路由

会话状态相关的路由定义在 `server/cmd/server/router.go` [1](#17-0) ：

| API 端点 | 方法 | 处理器 | 说明 |
|----------|------|--------|------|
| `/api/chat/sessions` | GET | `ListChatSessions` | 列出会话，支持 `?status=all` 参数过滤 [3](#17-2)  |
| `/api/chat/sessions/{sessionId}` | GET | `GetChatSession` | 获取单个会话详情 |
| `/api/chat/sessions/{sessionId}` | PATCH | `UpdateChatSession` | 更新会话（目前仅支持标题） [4](#17-3)  |
| `/api/chat/sessions/{sessionId}` | DELETE | `DeleteChatSession` | 删除会话 |
| `/api/chat/sessions/{sessionId}/read` | POST | `MarkChatSessionRead` | 标记会话为已读（清除 `unread_since`） [5](#17-4)  |

## 后端处理器实现

### ListChatSessions
支持通过 `status` 查询参数过滤会话 [3](#17-2) ：
- `status=all`：返回所有会话（包括 archived）
- 默认：仅返回 `status='active'` 的会话

### UpdateChatSession
目前仅支持更新 `title` 字段，`status` 字段是只读的（legacy + read-only） [6](#17-5) 。

### MarkChatSessionRead
清除会话的 `unread_since` 字段，将 `has_unread` 设为 false [7](#17-6) 。

## 数据库查询

SQL 查询定义在 `server/pkg/db/queries/chat.sql` [8](#17-7) ：

- `ListChatSessionsByCreator`：查询 `status='active'` 的会话
- `ListAllChatSessionsByCreator`：查询所有会话（包括 archived）
- `MarkChatSessionRead`：清除 `unread_since` [9](#17-8) 
- `SetUnreadSinceIfNull`：原子性地设置 `unread_since` [10](#17-9) 

## 前端 API 客户端

前端 API 封装在 `packages/core/api/client.ts` [11](#17-10) ：

```typescript
async listChatSessions(params?: { status?: string }): Promise<ChatSession[]>
async getChatSession(id: string): Promise<ChatSession>
async updateChatSession(id: string, data: { title: string }): Promise<ChatSession>
async deleteChatSession(id: string): Promise<void>
async markChatSessionRead(sessionId: string): Promise<void>
```

## 前端查询和变更

React Query hooks 定义在 `packages/core/chat/queries.ts` 和 `packages/core/chat/mutations.ts` [12](#17-11) [13](#17-12) ：

- `chatSessionsOptions(wsId)`：查询会话列表
- `useMarkChatSessionRead()`：标记已读的 mutation
- `useDeleteChatSession()`：删除会话的 mutation

## 会话状态值

数据库中 `chat_session.status` 字段的可能值：
- `active`：活跃会话
- `archived`：已归档会话（legacy 功能，新会话不再使用）

## Notes

会话状态主要通过 `status` 字段区分，但前端更多使用 `has_unread`（从 `unread_since` 计算得出）来显示未读状态。`status='archived'` 是遗留功能，新创建的会话都是 `active` 状态，删除会话使用硬删除而非软删除 [14](#17-13) 。

Wiki pages you might want to explore:
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)

Wiki pages you might want to explore:
- [API Client and Real-time Sync (multica-ai/multica)](/wiki/multica-ai/multica#3.3)
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)

### Citations

**File:** server/cmd/server/router.go (L655-668)
```go
			r.Route("/api/chat/sessions", func(r chi.Router) {
				r.Post("/", h.CreateChatSession)
				r.Get("/", h.ListChatSessions)
				r.Route("/{sessionId}", func(r chi.Router) {
					r.Get("/", h.GetChatSession)
					r.Patch("/", h.UpdateChatSession)
					r.Delete("/", h.DeleteChatSession)
					r.Post("/messages", h.SendChatMessage)
					r.Get("/messages", h.ListChatMessages)
					r.Get("/pending-task", h.GetPendingChatTask)
					r.Post("/read", h.MarkChatSessionRead)
				})
			})
			r.Get("/api/chat/pending-tasks", h.ListPendingChatTasks)
```

**File:** server/internal/handler/chat.go (L92-175)
```go
func (h *Handler) ListChatSessions(w http.ResponseWriter, r *http.Request) {
	userID, ok := requireUserID(w, r)
	if !ok {
		return
	}
	workspaceID := ctxWorkspaceID(r.Context())

	// Compute the accessible-agents set once and use it to drop sessions
	// whose target agent the caller no longer has access to — without this,
	// a member whose role was downgraded would still see the session list
	// (and transcripts via ListChatMessages) for any private agent they
	// previously had access to. Falls back to the user's role from the
	// workspace member context.
	member, ok := h.workspaceMember(w, r, workspaceID)
	if !ok {
		return
	}
	actorType, actorID := h.resolveActor(r, userID, workspaceID)
	allowed, ok := h.accessibleAgentIDs(r.Context(), workspaceID, actorType, actorID, member.Role)
	if !ok {
		writeError(w, http.StatusInternalServerError, "failed to resolve agent access")
		return
	}

	status := r.URL.Query().Get("status")

	// Two call sites → two row types with identical shape. Collect into a
	// common response slice via small per-branch loops.
	var resp []ChatSessionResponse
	if status == "all" {
		rows, err := h.Queries.ListAllChatSessionsByCreator(r.Context(), db.ListAllChatSessionsByCreatorParams{
			WorkspaceID: parseUUID(workspaceID),
			CreatorID:   parseUUID(userID),
		})
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to list chat sessions")
			return
		}
		resp = make([]ChatSessionResponse, 0, len(rows))
		for _, s := range rows {
			if _, ok := allowed[uuidToString(s.AgentID)]; !ok {
				continue
			}
			resp = append(resp, ChatSessionResponse{
				ID:          uuidToString(s.ID),
				WorkspaceID: uuidToString(s.WorkspaceID),
				AgentID:     uuidToString(s.AgentID),
				CreatorID:   uuidToString(s.CreatorID),
				Title:       s.Title,
				Status:      s.Status,
				HasUnread:   s.HasUnread,
				CreatedAt:   timestampToString(s.CreatedAt),
				UpdatedAt:   timestampToString(s.UpdatedAt),
			})
		}
	} else {
		rows, err := h.Queries.ListChatSessionsByCreator(r.Context(), db.ListChatSessionsByCreatorParams{
			WorkspaceID: parseUUID(workspaceID),
			CreatorID:   parseUUID(userID),
		})
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to list chat sessions")
			return
		}
		resp = make([]ChatSessionResponse, 0, len(rows))
		for _, s := range rows {
			if _, ok := allowed[uuidToString(s.AgentID)]; !ok {
				continue
			}
			resp = append(resp, ChatSessionResponse{
				ID:          uuidToString(s.ID),
				WorkspaceID: uuidToString(s.WorkspaceID),
				AgentID:     uuidToString(s.AgentID),
				CreatorID:   uuidToString(s.CreatorID),
				Title:       s.Title,
				Status:      s.Status,
				HasUnread:   s.HasUnread,
				CreatedAt:   timestampToString(s.CreatedAt),
				UpdatedAt:   timestampToString(s.UpdatedAt),
			})
		}
	}
	writeJSON(w, http.StatusOK, resp)
}
```

**File:** server/internal/handler/chat.go (L244-248)
```go
// UpdateChatSession updates user-editable fields on a chat session — today
// just `title`, surfaced by the inline rename affordance in the session
// dropdown. Title is the only field accepted: `status` is legacy + read-only,
// agent/creator/workspace are immutable, the resume pointers
// (session_id / work_dir / runtime_id) are daemon-owned.
```

**File:** server/internal/handler/chat.go (L249-298)
```go
func (h *Handler) UpdateChatSession(w http.ResponseWriter, r *http.Request) {
	userID, ok := requireUserID(w, r)
	if !ok {
		return
	}
	workspaceID := ctxWorkspaceID(r.Context())
	sessionID := chi.URLParam(r, "sessionId")

	var req UpdateChatSessionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Title == nil {
		writeError(w, http.StatusBadRequest, "title is required")
		return
	}
	title := strings.TrimSpace(*req.Title)
	if title == "" {
		writeError(w, http.StatusBadRequest, "title is required")
		return
	}
	if len([]rune(title)) > chatSessionTitleMaxLen {
		writeError(w, http.StatusBadRequest, "title is too long")
		return
	}

	session, ok := h.gateChatSessionForUser(w, r, userID, workspaceID, sessionID)
	if !ok {
		return
	}

	updated, err := h.Queries.UpdateChatSessionTitle(r.Context(), db.UpdateChatSessionTitleParams{
		ID:    session.ID,
		Title: title,
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to update chat session")
		return
	}

	resolvedSessionID := uuidToString(updated.ID)
	h.publishChat(protocol.EventChatSessionUpdated, workspaceID, "member", userID, resolvedSessionID, protocol.ChatSessionUpdatedPayload{
		ChatSessionID: resolvedSessionID,
		Title:         updated.Title,
		UpdatedAt:     timestampToString(updated.UpdatedAt),
	})

	writeJSON(w, http.StatusOK, chatSessionToResponse(updated))
}
```

**File:** server/internal/handler/chat.go (L547-574)
```go
// MarkChatSessionRead clears the session's unread_since (→ has_unread=false)
// and broadcasts chat:session_read so other devices of the same user drop
// their badges.
func (h *Handler) MarkChatSessionRead(w http.ResponseWriter, r *http.Request) {
	userID, ok := requireUserID(w, r)
	if !ok {
		return
	}
	workspaceID := ctxWorkspaceID(r.Context())
	sessionID := chi.URLParam(r, "sessionId")

	session, ok := h.gateChatSessionForUser(w, r, userID, workspaceID, sessionID)
	if !ok {
		return
	}

	if err := h.Queries.MarkChatSessionRead(r.Context(), session.ID); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to mark session read")
		return
	}

	resolvedSessionID := uuidToString(session.ID)
	h.publishChat(protocol.EventChatSessionRead, workspaceID, "member", userID, resolvedSessionID, protocol.ChatSessionReadPayload{
		ChatSessionID: resolvedSessionID,
	})

	w.WriteHeader(http.StatusNoContent)
}
```

**File:** server/pkg/db/queries/chat.sql (L14-30)
```sql
-- name: ListChatSessionsByCreator :many
-- Returns active sessions with a boolean unread flag. Unread is strictly
-- per-session: either the user has uncleared assistant replies in this
-- session or they don't. Counting messages would be misleading.
SELECT cs.*,
       (cs.unread_since IS NOT NULL)::bool AS has_unread
FROM chat_session cs
WHERE cs.workspace_id = $1 AND cs.creator_id = $2 AND cs.status = 'active'
ORDER BY cs.updated_at DESC;

-- name: ListAllChatSessionsByCreator :many
SELECT cs.*,
       (cs.unread_since IS NOT NULL)::bool AS has_unread
FROM chat_session cs
WHERE cs.workspace_id = $1 AND cs.creator_id = $2
ORDER BY cs.updated_at DESC;

```

**File:** server/pkg/db/queries/chat.sql (L61-70)
```sql
-- name: DeleteChatSession :exec
-- Hard delete. chat_message rows cascade via FK ON DELETE CASCADE; the
-- chat_session_id on agent_task_queue is set NULL by FK so completed/failed
-- task history survives the session being removed. Callers MUST run inside
-- the same transaction that holds LockChatSessionForDelete and that has
-- already cancelled any in-flight tasks (see CancelAgentTasksByChatSession)
-- so the daemon does not keep running work whose result has nowhere to
-- land. workspace_id in the WHERE clause is a SQL-layer tenant guard; see
-- DeleteIssue.
DELETE FROM chat_session WHERE id = $1 AND workspace_id = $2;
```

**File:** server/pkg/db/queries/chat.sql (L140-143)
```sql
-- name: MarkChatSessionRead :exec
-- Clears unread_since, dropping the session's unread count to 0.
UPDATE chat_session SET unread_since = NULL
WHERE id = $1;
```

**File:** server/pkg/db/queries/chat.sql (L145-150)
```sql
-- name: SetUnreadSinceIfNull :exec
-- Atomically stamps the first unread assistant message's arrival time.
-- No-op if the session is already in "has unread" state — keeps the earliest
-- unread boundary stable across multiple incoming replies.
UPDATE chat_session SET unread_since = now()
WHERE id = $1 AND unread_since IS NULL;
```

**File:** packages/core/api/client.ts (L1407-1469)
```typescript
  // Chat Sessions
  async listChatSessions(params?: { status?: string }): Promise<ChatSession[]> {
    const query = params?.status ? `?status=${params.status}` : "";
    return this.fetch(`/api/chat/sessions${query}`);
  }

  async getChatSession(id: string): Promise<ChatSession> {
    return this.fetch(`/api/chat/sessions/${id}`);
  }

  async createChatSession(data: { agent_id: string; title?: string }): Promise<ChatSession> {
    return this.fetch("/api/chat/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteChatSession(id: string): Promise<void> {
    await this.fetch(`/api/chat/sessions/${id}`, { method: "DELETE" });
  }

  async updateChatSession(id: string, data: { title: string }): Promise<ChatSession> {
    return this.fetch(`/api/chat/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async listChatMessages(sessionId: string): Promise<ChatMessage[]> {
    return this.fetch(`/api/chat/sessions/${sessionId}/messages`);
  }

  async sendChatMessage(
    sessionId: string,
    content: string,
    attachmentIds?: string[],
  ): Promise<SendChatMessageResponse> {
    const body: { content: string; attachment_ids?: string[] } = { content };
    if (attachmentIds && attachmentIds.length > 0) {
      body.attachment_ids = attachmentIds;
    }
    return this.fetch(`/api/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async getPendingChatTask(sessionId: string): Promise<ChatPendingTask> {
    return this.fetch(`/api/chat/sessions/${sessionId}/pending-task`);
  }

  async listPendingChatTasks(): Promise<PendingChatTasksResponse> {
    return this.fetch(`/api/chat/pending-tasks`);
  }

  async markChatSessionRead(sessionId: string): Promise<void> {
    await this.fetch(`/api/chat/sessions/${sessionId}/read`, { method: "POST" });
  }

  async cancelTaskById(taskId: string): Promise<void> {
    await this.fetch(`/api/tasks/${taskId}/cancel`, { method: "POST" });
  }

```

**File:** packages/core/chat/queries.ts (L30-36)
```typescript
export function chatSessionsOptions(wsId: string) {
  return queryOptions({
    queryKey: chatKeys.sessions(wsId),
    queryFn: () => api.listChatSessions({ status: "all" }),
    staleTime: Infinity,
  });
}
```

**File:** packages/core/chat/mutations.ts (L37-65)
```typescript
export function useMarkChatSessionRead() {
  const qc = useQueryClient();
  const wsId = useWorkspaceId();

  return useMutation({
    mutationFn: (sessionId: string) => {
      logger.info("markChatSessionRead.start", { sessionId });
      return api.markChatSessionRead(sessionId);
    },
    onMutate: async (sessionId) => {
      await qc.cancelQueries({ queryKey: chatKeys.sessions(wsId) });

      const prevSessions = qc.getQueryData<ChatSession[]>(chatKeys.sessions(wsId));

      const clear = (old?: ChatSession[]) =>
        old?.map((s) => (s.id === sessionId ? { ...s, has_unread: false } : s));
      qc.setQueryData<ChatSession[]>(chatKeys.sessions(wsId), clear);

      return { prevSessions };
    },
    onError: (err, sessionId, ctx) => {
      logger.error("markChatSessionRead.error.rollback", { sessionId, err });
      if (ctx?.prevSessions) qc.setQueryData(chatKeys.sessions(wsId), ctx.prevSessions);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: chatKeys.sessions(wsId) });
    },
  });
}
```
