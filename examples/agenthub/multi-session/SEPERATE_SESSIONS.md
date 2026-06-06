会话间数据通过数据库层、API 层、前端状态层和执行环境层四个维度实现隔离。 [1](#6-0) [2](#6-1) 

---

## 数据库层隔离

### 会话表隔离
`chat_session` 表通过 `workspace_id` 和 `creator_id` 实现多租户隔离 [3](#6-2) ：
- `ListChatSessionsByCreator` 查询同时过滤 `workspace_id` 和 `creator_id`
- `GetChatSessionInWorkspace` 要求同时匹配 `id` 和 `workspace_id` [4](#6-3) 

### 消息表隔离
`chat_message` 通过 `chat_session_id` 外键关联，查询时必须先验证会话所有权 [5](#6-4) 。

## API 层隔离

### 所有权验证
`loadChatSessionForUser` 函数验证会话属于当前用户 [6](#6-5) ：
```go
if uuidToString(session.CreatorID) != userID {
    writeError(w, http.StatusForbidden, "not your chat session")
    return db.ChatSession{}, false
}
```

### 私有 Agent 访问控制
`gateChatSessionForUser` 在所有权检查基础上，额外验证用户对目标 agent 的访问权限 [7](#6-6) 。这防止用户在失去 agent 访问权限后继续查看历史会话。

### 会话列表过滤
`ListChatSessions` 计算用户可访问的 agent 集合，过滤掉用户无权访问的 agent 对应的会话 [8](#6-7) 。

## 前端状态层隔离

### Web 端 Zustand Store
使用 `wsKey` 函数为每个工作区创建独立的存储键 [9](#6-8) ：
```typescript
const wsKey = (base: string) => {
  const slug = getCurrentSlug();
  return slug ? `${base}:${slug}` : base;
};
```
- `activeSessionId` 按 workspace 隔离
- `inputDrafts` 按 workspace 隔离
- `selectedAgentId` 按 workspace 隔离

### Mobile 端路由隔离
Mobile 端通过 Expo Router 的 `[workspace]` 动态段实现路由级隔离，每个工作区有独立的导航栈 [10](#6-9) 。

## 执行环境层隔离

### Daemon 工作目录隔离
每个任务在 `execenv.Prepare` 中创建独立的 `workdir/` 目录 [11](#6-10) 。会话通过 `session_id` 和 `work_dir` 维护执行上下文。

### 会话状态恢复
`GetLastChatTaskSession` 查询特定会话的最后有效任务状态，用于恢复会话上下文 [12](#6-11) 。查询条件包含 `chat_session_id`，确保只恢复当前会话的状态。

### 垃圾回收检查
`GetChatSessionGCCheck` 供 Daemon GC 使用，返回会话状态以判断是否清理工作目录 [13](#6-12) 。跨工作区的 daemon token 会返回 404，防止跨租户探测 [14](#6-13) 。

## 附件隔离

文件上传时通过 `chat_session_id` 关联，`UploadFile` 拒绝绑定到其他工作区或用户的会话 [15](#6-14) 。

## Notes

会话隔离是多层防御的：数据库层提供基础隔离，API 层验证业务权限，前端状态层防止跨工作区状态泄漏，执行环境层确保文件系统隔离。私有 agent 的访问控制是额外的安全层，即使会话创建者失去 agent 访问权限，也无法继续查看会话内容 [16](#6-15) 。

Wiki pages you might want to explore:
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)
- [Daemon and Task Execution (multica-ai/multica)](/wiki/multica-ai/multica#5.2)

Wiki pages you might want to explore:
- [Daemon and Task Execution (multica-ai/multica)](/wiki/multica-ai/multica#5.2)
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)

### Citations

**File:** server/pkg/db/queries/chat.sql (L1-30)
```sql
-- name: CreateChatSession :one
INSERT INTO chat_session (workspace_id, agent_id, creator_id, title, runtime_id)
VALUES ($1, $2, $3, $4, (SELECT runtime_id FROM agent WHERE id = $2))
RETURNING *;

-- name: GetChatSession :one
SELECT * FROM chat_session
WHERE id = $1;

-- name: GetChatSessionInWorkspace :one
SELECT * FROM chat_session
WHERE id = $1 AND workspace_id = $2;

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

**File:** server/pkg/db/queries/chat.sql (L81-84)
```sql
-- name: ListChatMessages :many
SELECT * FROM chat_message
WHERE chat_session_id = $1
ORDER BY created_at ASC;
```

**File:** server/pkg/db/queries/chat.sql (L95-115)
```sql
-- name: GetLastChatTaskSession :one
-- Returns the most recent task in this chat session that managed to record a
-- session_id. Includes both completed and failed tasks: even a failed task
-- may have established a real agent session before failing, and we'd rather
-- resume there than start over and lose conversation memory. Used as a
-- fallback when chat_session.session_id is NULL. Resume-unsafe failures are
-- excluded because replaying those sessions deterministically reproduces the
-- same terminal state.
SELECT session_id, work_dir, runtime_id FROM agent_task_queue
WHERE chat_session_id = $1
  AND (
    status = 'completed'
    OR (
      status = 'failed'
      AND COALESCE(failure_reason, '') NOT IN ('iteration_limit', 'agent_fallback_message', 'api_invalid_request', 'codex_semantic_inactivity')
      AND NOT (COALESCE(error, '') ILIKE '%400%' AND COALESCE(error, '') ILIKE '%invalid_request_error%')
    )
  )
  AND session_id IS NOT NULL
ORDER BY completed_at DESC
LIMIT 1;
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

**File:** server/internal/handler/chat.go (L177-199)
```go
func (h *Handler) loadChatSessionForUser(w http.ResponseWriter, r *http.Request, userID, workspaceID, sessionID string) (db.ChatSession, bool) {
	sessionUUID, ok := parseUUIDOrBadRequest(w, sessionID, "chat session id")
	if !ok {
		return db.ChatSession{}, false
	}
	workspaceUUID, ok := parseUUIDOrBadRequest(w, workspaceID, "workspace id")
	if !ok {
		return db.ChatSession{}, false
	}
	session, err := h.Queries.GetChatSessionInWorkspace(r.Context(), db.GetChatSessionInWorkspaceParams{
		ID:          sessionUUID,
		WorkspaceID: workspaceUUID,
	})
	if err != nil {
		writeError(w, http.StatusNotFound, "chat session not found")
		return db.ChatSession{}, false
	}
	if uuidToString(session.CreatorID) != userID {
		writeError(w, http.StatusForbidden, "not your chat session")
		return db.ChatSession{}, false
	}
	return session, true
}
```

**File:** server/internal/handler/chat.go (L201-222)
```go
// gateChatSessionForUser combines the session ownership check with the
// private-agent access gate so a member who has lost access to the target
// agent (role downgrade, ownership transfer, agent flipped to private)
// cannot continue reading the chat transcript even though they remain the
// session creator. Returns ok=false after writing the error response.
func (h *Handler) gateChatSessionForUser(w http.ResponseWriter, r *http.Request, userID, workspaceID, sessionID string) (db.ChatSession, bool) {
	session, ok := h.loadChatSessionForUser(w, r, userID, workspaceID, sessionID)
	if !ok {
		return db.ChatSession{}, false
	}
	agent, err := h.Queries.GetAgent(r.Context(), session.AgentID)
	if err != nil {
		writeError(w, http.StatusNotFound, "agent not found")
		return db.ChatSession{}, false
	}
	actorType, actorID := h.resolveActor(r, userID, workspaceID)
	if !h.canAccessPrivateAgent(r.Context(), agent, actorType, actorID, workspaceID) {
		writeError(w, http.StatusForbidden, "you do not have access to this agent")
		return db.ChatSession{}, false
	}
	return session, true
}
```

**File:** server/pkg/db/generated/chat.sql.go (L210-238)
```go
const getChatSessionInWorkspace = `-- name: GetChatSessionInWorkspace :one
SELECT id, workspace_id, agent_id, creator_id, title, session_id, work_dir, status, created_at, updated_at, unread_since, runtime_id FROM chat_session
WHERE id = $1 AND workspace_id = $2
`

type GetChatSessionInWorkspaceParams struct {
	ID          pgtype.UUID `json:"id"`
	WorkspaceID pgtype.UUID `json:"workspace_id"`
}

func (q *Queries) GetChatSessionInWorkspace(ctx context.Context, arg GetChatSessionInWorkspaceParams) (ChatSession, error) {
	row := q.db.QueryRow(ctx, getChatSessionInWorkspace, arg.ID, arg.WorkspaceID)
	var i ChatSession
	err := row.Scan(
		&i.ID,
		&i.WorkspaceID,
		&i.AgentID,
		&i.CreatorID,
		&i.Title,
		&i.SessionID,
		&i.WorkDir,
		&i.Status,
		&i.CreatedAt,
		&i.UpdatedAt,
		&i.UnreadSince,
		&i.RuntimeID,
	)
	return i, err
}
```

**File:** server/internal/handler/daemon.go (L2232-2258)
```go
// GetChatSessionGCCheck returns the status and updated_at of a chat session
// for the daemon GC loop. A 404 here means the session was hard-deleted
// (DeleteChatSession in chat.go runs a real DELETE), which the daemon treats
// as an immediate-clean signal — the user's explicit delete is the strongest
// reclaim authorization we can get.
//
// Same anti-enumeration shape as GetIssueGCCheck: workspace mismatch returns
// the same 404 so a scoped daemon token can't probe other workspaces.
func (h *Handler) GetChatSessionGCCheck(w http.ResponseWriter, r *http.Request) {
	sessionID := chi.URLParam(r, "sessionId")
	sessionUUID, ok := parseUUIDOrBadRequest(w, sessionID, "session_id")
	if !ok {
		return
	}
	session, err := h.Queries.GetChatSession(r.Context(), sessionUUID)
	if err != nil {
		writeError(w, http.StatusNotFound, "chat session not found")
		return
	}
	if !h.requireDaemonWorkspaceAccess(w, r, uuidToString(session.WorkspaceID)) {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status":     session.Status,
		"updated_at": session.UpdatedAt.Time,
	})
}
```

**File:** server/internal/handler/daemon_test.go (L2969-3040)
```go
// TestGetChatSessionGCCheck verifies the chat session gc-check endpoint
// matches the same anti-enumeration shape as GetIssueGCCheck: cross-workspace
// daemon tokens get 404, same-workspace tokens get the live status.
func TestGetChatSessionGCCheck(t *testing.T) {
	if testHandler == nil {
		t.Skip("database not available")
	}

	ctx := context.Background()

	var agentID string
	if err := testPool.QueryRow(ctx, `SELECT id FROM agent WHERE workspace_id = $1 LIMIT 1`, testWorkspaceID).Scan(&agentID); err != nil {
		t.Fatalf("setup: get agent: %v", err)
	}

	var sessionID string
	if err := testPool.QueryRow(ctx, `
		INSERT INTO chat_session (workspace_id, agent_id, creator_id, title, status)
		VALUES ($1, $2, $3, 'gc-check fixture', 'active')
		RETURNING id
	`, testWorkspaceID, agentID, testUserID).Scan(&sessionID); err != nil {
		t.Fatalf("setup: create chat session: %v", err)
	}
	defer testPool.Exec(ctx, `DELETE FROM chat_session WHERE id = $1`, sessionID)

	// Cross-workspace daemon token must 404 with no oracle.
	w := httptest.NewRecorder()
	req := newDaemonTokenRequest("GET", "/api/daemon/chat-sessions/"+sessionID+"/gc-check", nil,
		"00000000-0000-0000-0000-000000000000", "attacker-daemon")
	req = withURLParam(req, "sessionId", sessionID)
	testHandler.GetChatSessionGCCheck(w, req)
	if w.Code != http.StatusNotFound {
		t.Fatalf("cross-workspace token: expected 404, got %d: %s", w.Code, w.Body.String())
	}

	// Same-workspace daemon token sees the live row.
	w = httptest.NewRecorder()
	req = newDaemonTokenRequest("GET", "/api/daemon/chat-sessions/"+sessionID+"/gc-check", nil,
		testWorkspaceID, "legit-daemon")
	req = withURLParam(req, "sessionId", sessionID)
	testHandler.GetChatSessionGCCheck(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("same-workspace token: expected 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp struct {
		Status    string `json:"status"`
		UpdatedAt string `json:"updated_at"`
	}
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Status != "active" {
		t.Fatalf("expected status %q, got %q", "active", resp.Status)
	}
	if resp.UpdatedAt == "" {
		t.Fatal("expected updated_at to be set")
	}

	// Hard-deleted session: 404 — exactly what the daemon needs to reclaim
	// the workdir on the next GC pass after a user runs DeleteChatSession.
	if _, err := testPool.Exec(ctx, `DELETE FROM chat_session WHERE id = $1`, sessionID); err != nil {
		t.Fatalf("delete chat session: %v", err)
	}
	w = httptest.NewRecorder()
	req = newDaemonTokenRequest("GET", "/api/daemon/chat-sessions/"+sessionID+"/gc-check", nil,
		testWorkspaceID, "legit-daemon")
	req = withURLParam(req, "sessionId", sessionID)
	testHandler.GetChatSessionGCCheck(w, req)
	if w.Code != http.StatusNotFound {
		t.Fatalf("hard-deleted session: expected 404, got %d: %s", w.Code, w.Body.String())
	}
}
```

**File:** server/internal/handler/file_test.go (L293-319)
```go
// TestUploadFile_RejectsForeignChatSession verifies a chat_session in another
// workspace (or owned by another user) is rejected with 403/404, preventing
// cross-tenant attachment binding.
func TestUploadFile_RejectsForeignChatSession(t *testing.T) {
	origStorage := testHandler.Storage
	testHandler.Storage = &mockStorage{}
	defer func() { testHandler.Storage = origStorage }()

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, _ := writer.CreateFormFile("file", "evil.txt")
	part.Write([]byte("payload"))
	// Random non-existent UUID.
	writer.WriteField("chat_session_id", "00000000-0000-0000-0000-0000deadbeef")
	writer.Close()

	req := httptest.NewRequest("POST", "/api/upload-file", &body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("X-User-ID", testUserID)
	req.Header.Set("X-Workspace-ID", testWorkspaceID)

	w := httptest.NewRecorder()
	testHandler.UploadFile(w, req)
	if w.Code != http.StatusNotFound && w.Code != http.StatusForbidden && w.Code != http.StatusBadRequest {
		t.Fatalf("UploadFile with unknown chat_session_id: expected 4xx, got %d: %s", w.Code, w.Body.String())
	}
}
```

**File:** server/internal/handler/agent_access_test.go (L334-379)
```go
// A member who created a chat session is later denied access to the agent
// (here simulated by the member never being on the allowlist for a private
// agent owned by someone else; the equivalent of an after-the-fact ownership
// transfer). The session row still names them as creator, but the read
// endpoints must refuse to surface the transcript.
func TestListChatMessages_PrivateAgentForbidsAfterAccessRevoked(t *testing.T) {
	if testHandler == nil {
		t.Skip("database not available")
	}

	ctx := context.Background()
	agentID, _, memberID := privateAgentTestFixture(t)

	// Insert a chat session row directly with the plain member as creator,
	// bypassing CreateChatSession's own gate. This represents a session
	// that existed before the member lost access (or before the gate
	// landed).
	var sessionID string
	if err := testPool.QueryRow(ctx, `
		INSERT INTO chat_session (workspace_id, agent_id, creator_id, title, status)
		VALUES ($1, $2, $3, 'pre-revocation session', 'active')
		RETURNING id
	`, testWorkspaceID, agentID, memberID).Scan(&sessionID); err != nil {
		t.Fatalf("seed chat session: %v", err)
	}
	t.Cleanup(func() {
		testPool.Exec(context.Background(), `DELETE FROM chat_session WHERE id = $1`, sessionID)
	})

	memberRow, err := testHandler.Queries.GetMemberByUserAndWorkspace(ctx, db.GetMemberByUserAndWorkspaceParams{
		UserID:      util.MustParseUUID(memberID),
		WorkspaceID: util.MustParseUUID(testWorkspaceID),
	})
	if err != nil {
		t.Fatalf("load plain member row: %v", err)
	}

	w := httptest.NewRecorder()
	req := newRequestAs(memberID, "GET", "/api/chat/sessions/"+sessionID+"/messages", nil)
	req = req.WithContext(middleware.SetMemberContext(req.Context(), testWorkspaceID, memberRow))
	req = withURLParam(req, "sessionId", sessionID)
	testHandler.ListChatMessages(w, req)
	if w.Code != http.StatusForbidden {
		t.Fatalf("ListChatMessages on stale session: expected 403, got %d: %s", w.Code, w.Body.String())
	}
}
```
