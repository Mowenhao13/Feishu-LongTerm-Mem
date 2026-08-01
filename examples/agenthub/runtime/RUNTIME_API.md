使用到 Runtime 的 API 主要分为用户管理 API、Daemon 注册 API、云 Runtime API 和 CLI 命令四类。 [1](#11-0) [2](#11-1) 

---

## 用户管理 Runtime API

### 基础 CRUD
| API 端点 | 方法 | 处理器 | 前端方法 |
|----------|------|--------|----------|
| `/api/runtimes` | GET | `ListAgentRuntimes` | `listRuntimes()` [3](#11-2)  |
| `/api/runtimes/{runtimeId}` | PATCH | `UpdateAgentRuntime` | `updateRuntime()` [4](#11-3)  |
| `/api/runtimes/{runtimeId}` | DELETE | `DeleteAgentRuntime` | - |
| `/api/runtimes/{runtimeId}/archive-agents-and-delete` | POST | `ArchiveAgentsAndDeleteRuntime` | `archiveAgentsAndDeleteRuntime()` [5](#11-4)  |

### 用量统计
| API 端点 | 方法 | 处理器 | 前端方法 |
|----------|------|--------|----------|
| `/api/runtimes/{runtimeId}/usage` | GET | `GetRuntimeUsage` | `getRuntimeUsage()` [6](#11-5)  |
| `/api/runtimes/{runtimeId}/usage/by-agent` | GET | `GetRuntimeUsageByAgent` | - |
| `/api/runtimes/{runtimeId}/usage/by-hour` | GET | - | - |
| `/api/runtimes/{runtimeId}/activity` | GET | `GetRuntimeTaskActivity` | - |

### CLI 管理
| API 端点 | 方法 | 处理器 | 前端方法 |
|----------|------|--------|----------|
| `/api/runtimes/{runtimeId}/update` | POST | `InitiateUpdate` | - |
| `/api/runtimes/{runtimeId}/update/{updateId}` | GET | `GetUpdate` | - |
| `/api/runtimes/{runtimeId}/models` | POST | `InitiateListModels` | `initiateListModels()` [7](#11-6)  |
| `/api/runtimes/{runtimeId}/models/{requestId}` | GET | `GetModelListRequest` | `getListModelsResult()` [8](#11-7)  |

### 本地技能管理
| API 端点 | 方法 | 处理器 | 前端方法 |
|----------|------|--------|----------|
| `/api/runtimes/{runtimeId}/local-skills` | POST | `InitiateListLocalSkills` | `initiateListLocalSkills()` [9](#11-8)  |
| `/api/runtimes/{runtimeId}/local-skills/{requestId}` | GET | `GetLocalSkillListRequest` | `getListLocalSkillsResult()` [10](#11-9)  |
| `/api/runtimes/{runtimeId}/local-skills/import` | POST | `InitiateImportLocalSkill` | `initiateImportLocalSkill()` [11](#11-10)  |
| `/api/runtimes/{runtimeId}/local-skills/import/{requestId}` | GET | `GetLocalSkillImportRequest` | - |

## Daemon 注册 API

| API 端点 | 方法 | 处理器 | 说明 |
|----------|------|--------|------|
| `/api/daemon/register` | POST | `DaemonRegister` | Daemon 启动时注册 Runtime [12](#11-11)  |
| `/api/daemon/deregister` | POST | `DaemonDeregister` | Daemon 关闭时注销 Runtime [13](#11-12)  |

## 云 Runtime API

| API 端点 | 方法 | 处理器 | 前端方法 |
|----------|------|--------|----------|
| `/api/cloud-runtime` | GET | `GetCloudRuntimeService` | - |
| `/api/cloud-runtime/healthz` | GET | `GetCloudRuntimeHealth` | - |
| `/api/cloud-runtime/readyz` | GET | `GetCloudRuntimeReady` | - |
| `/api/cloud-runtime/nodes` | GET | `ListCloudRuntimeNodes` | `listCloudRuntimeNodes()` [14](#11-13)  |
| `/api/cloud-runtime/nodes` | POST | `CreateCloudRuntimeNode` | - |
| `/api/cloud-runtime/nodes` | DELETE | `DeleteCloudRuntimeNode` | - |
| `/api/cloud-runtime/nodes/start` | POST | `StartCloudRuntimeNode` | - |
| `/api/cloud-runtime/nodes/stop` | POST | `StopCloudRuntimeNode` | - |
| `/api/cloud-runtime/nodes/reboot` | POST | `RebootCloudRuntimeNode` | - |
| `/api/cloud-runtime/nodes/status` | POST | `GetCloudRuntimeNodeStatus` | - |
| `/api/cloud-runtime/nodes/exec` | POST | `ExecCloudRuntimeNode` | - |

## CLI 命令

| 命令 | 处理函数 | 调用的 API |
|------|----------|-----------|
| `multica runtime list` | `runRuntimeList` | `GET /api/runtimes` [15](#11-14)  |
| `multica runtime usage <id>` | `runRuntimeUsage` | `GET /api/runtimes/{id}/usage` |
| `multica runtime activity <id>` | `runRuntimeActivity` | `GET /api/runtimes/{id}/activity` [16](#11-15)  |

## Notes

所有 Runtime API 都在 `server/cmd/server/router.go` 中定义路由 [1](#11-0) ，处理器实现在 `server/internal/handler/runtime.go` 中 [17](#11-16) 。前端通过 `packages/core/api/client.ts` 封装这些 API 调用 [18](#11-17) 。云 Runtime API 仅在 SaaS 环境中可用，自托管部署返回 503。

Wiki pages you might want to explore:
- [Runtimes and Agent Providers (multica-ai/multica)](/wiki/multica-ai/multica#10)
- [Glossary (multica-ai/multica)](/wiki/multica-ai/multica#15)

Wiki pages you might want to explore:
- [Glossary (multica-ai/multica)](/wiki/multica-ai/multica#15)

### Citations

**File:** server/cmd/server/router.go (L596-638)
```go
			// Runtimes
			r.Route("/api/runtimes", func(r chi.Router) {
				r.Get("/", h.ListAgentRuntimes)
				r.Route("/{runtimeId}", func(r chi.Router) {
					r.Patch("/", h.UpdateAgentRuntime)
					r.Get("/usage", h.GetRuntimeUsage)
					r.Get("/usage/by-agent", h.GetRuntimeUsageByAgent)
					r.Get("/usage/by-hour", h.GetRuntimeUsageByHour)
					r.Get("/activity", h.GetRuntimeTaskActivity)
					r.Post("/update", h.InitiateUpdate)
					r.Get("/update/{updateId}", h.GetUpdate)
					r.Post("/models", h.InitiateListModels)
					r.Get("/models/{requestId}", h.GetModelListRequest)
					r.Post("/local-skills", h.InitiateListLocalSkills)
					r.Get("/local-skills/{requestId}", h.GetLocalSkillListRequest)
					r.Post("/local-skills/import", h.InitiateImportLocalSkill)
					r.Get("/local-skills/import/{requestId}", h.GetLocalSkillImportRequest)
					r.Delete("/", h.DeleteAgentRuntime)
					// Cascade variant of DELETE: archive every active agent
					// bound to this runtime, cancel their tasks, then delete
					// the runtime — all in one transaction. Used by the
					// DeleteRuntimeDialog when the strict DELETE refused with
					// `runtime_has_active_agents` and the user confirmed the
					// cascade plan.
					r.Post("/archive-agents-and-delete", h.ArchiveAgentsAndDeleteRuntime)
				})
			})

			// Cloud Runtime fleet proxy. The remote service URL is configured
			// on SaaS API nodes only; self-hosted deployments return 503.
			r.Route("/api/cloud-runtime", func(r chi.Router) {
				r.Get("/", h.GetCloudRuntimeService)
				r.Get("/healthz", h.GetCloudRuntimeHealth)
				r.Get("/readyz", h.GetCloudRuntimeReady)
				r.Get("/nodes", h.ListCloudRuntimeNodes)
				r.Post("/nodes", h.CreateCloudRuntimeNode)
				r.Delete("/nodes", h.DeleteCloudRuntimeNode)
				r.Post("/nodes/start", h.StartCloudRuntimeNode)
				r.Post("/nodes/stop", h.StopCloudRuntimeNode)
				r.Post("/nodes/reboot", h.RebootCloudRuntimeNode)
				r.Post("/nodes/status", h.GetCloudRuntimeNodeStatus)
				r.Post("/nodes/exec", h.ExecCloudRuntimeNode)
			})
```

**File:** packages/core/api/client.ts (L817-1098)
```typescript
  async listRuntimes(params?: { workspace_id?: string; owner?: "me" }): Promise<AgentRuntime[]> {
    const search = new URLSearchParams();
    if (params?.workspace_id) search.set("workspace_id", params.workspace_id);
    if (params?.owner) search.set("owner", params.owner);
    return this.fetch(`/api/runtimes?${search}`);
  }

  async listCloudRuntimeNodes(
    params?: ListCloudRuntimeNodesParams,
  ): Promise<CloudRuntimeNode[]> {
    const search = new URLSearchParams();
    if (params?.limit !== undefined) search.set("limit", String(params.limit));
    if (params?.offset !== undefined) search.set("offset", String(params.offset));
    const query = search.toString();
    const raw = await this.fetch<unknown>(
      `/api/cloud-runtime/nodes${query ? `?${query}` : ""}`,
    );
    return parseWithFallback(
      raw,
      CloudRuntimeNodeListSchema,
      EMPTY_CLOUD_RUNTIME_NODE_LIST,
      { endpoint: "GET /api/cloud-runtime/nodes" },
    );
  }

  async createCloudRuntimeNode(
    data: CreateCloudRuntimeNodeRequest,
  ): Promise<CloudRuntimeNode> {
    const res = await this.fetchRaw("/api/cloud-runtime/nodes", {
      method: "POST",
      body: JSON.stringify(data),
      extraHeaders: { "Content-Type": "application/json" },
    });
    const raw = await res.json() as unknown;
    return parseWithFallback(
      raw,
      CloudRuntimeNodeSchema,
      EMPTY_CLOUD_RUNTIME_NODE,
      { endpoint: "POST /api/cloud-runtime/nodes" },
    );
  }

  async deleteCloudRuntimeNode(instanceId: string): Promise<void> {
    await this.fetchRaw("/api/cloud-runtime/nodes", {
      method: "DELETE",
      body: JSON.stringify({ instance_id: instanceId }),
      extraHeaders: { "Content-Type": "application/json" },
    });
  }

  async deleteRuntime(runtimeId: string): Promise<void> {
    await this.fetch(`/api/runtimes/${runtimeId}`, { method: "DELETE" });
  }

  // Cascade variant of deleteRuntime. The strict DELETE refuses with
  // structured 409 (`code: "runtime_has_active_agents"`, body carries the
  // blocking agents) when active agents are bound; the front-end then opens
  // the cascade-mode confirmation dialog and submits the user-confirmed
  // active agent set here. Server compares the snapshot to the live set
  // inside the transaction and refuses with `code: "runtime_delete_plan_changed"`
  // (same shape, fresh `active_agents`) if they don't match — caller should
  // re-render the agent list and force the user to re-confirm.
  async archiveAgentsAndDeleteRuntime(
    runtimeId: string,
    expectedActiveAgentIds: string[],
  ): Promise<{ status: string; agents_archived: number; tasks_cancelled: number }> {
    return this.fetch(`/api/runtimes/${runtimeId}/archive-agents-and-delete`, {
      method: "POST",
      body: JSON.stringify({ expected_active_agent_ids: expectedActiveAgentIds }),
    });
  }

  async updateRuntime(
    runtimeId: string,
    patch: { visibility?: "private" | "public" },
  ): Promise<AgentRuntime> {
    return this.fetch(`/api/runtimes/${runtimeId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  }

  async getRuntimeUsage(
    runtimeId: string,
    params?: { days?: number; tz?: string },
  ): Promise<RuntimeUsage[]> {
    const search = new URLSearchParams();
    if (params?.days) search.set("days", String(params.days));
    // `tz` drives the calendar-day boundary for the trend chart (Viewing
    // layer). Caller-supplied; the backend falls back to user.timezone /
    // UTC if omitted.
    if (params?.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(
      `/api/runtimes/${runtimeId}/usage?${search}`,
    );
    return parseWithFallback<RuntimeUsage[]>(raw, RuntimeUsageListSchema, [], {
      endpoint: "GET /api/runtimes/:id/usage",
    });
  }

  async getRuntimeTaskActivity(
    runtimeId: string,
    params?: { tz?: string },
  ): Promise<RuntimeHourlyActivity[]> {
    // Hour-of-day heatmap follows the viewer's tz, like the other reports on
    // this page. Pass the viewer's IANA zone so the server buckets correctly.
    const search = new URLSearchParams();
    if (params?.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(
      `/api/runtimes/${runtimeId}/activity?${search}`,
    );
    return parseWithFallback<RuntimeHourlyActivity[]>(
      raw,
      RuntimeHourlyActivityListSchema,
      [],
      { endpoint: "GET /api/runtimes/:id/activity" },
    );
  }

  async getRuntimeUsageByAgent(
    runtimeId: string,
    params?: { days?: number; tz?: string },
  ): Promise<RuntimeUsageByAgent[]> {
    const search = new URLSearchParams();
    if (params?.days) search.set("days", String(params.days));
    if (params?.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(
      `/api/runtimes/${runtimeId}/usage/by-agent?${search}`,
    );
    return parseWithFallback<RuntimeUsageByAgent[]>(
      raw,
      RuntimeUsageByAgentListSchema,
      [],
      { endpoint: "GET /api/runtimes/:id/usage/by-agent" },
    );
  }

  async getRuntimeUsageByHour(
    runtimeId: string,
    params?: { days?: number; tz?: string },
  ): Promise<RuntimeUsageByHour[]> {
    const search = new URLSearchParams();
    if (params?.days) search.set("days", String(params.days));
    if (params?.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(
      `/api/runtimes/${runtimeId}/usage/by-hour?${search}`,
    );
    return parseWithFallback<RuntimeUsageByHour[]>(
      raw,
      RuntimeUsageByHourListSchema,
      [],
      { endpoint: "GET /api/runtimes/:id/usage/by-hour" },
    );
  }

  // ---------------------------------------------------------------------------
  // Workspace dashboard — three independent rollups for `/{slug}/dashboard`.
  // Each accepts an optional `project_id` to narrow the scope to one project.
  // Cost is computed client-side from the model pricing table (same contract
  // as the per-runtime endpoints above).
  // ---------------------------------------------------------------------------

  async getDashboardUsageDaily(
    params: { days?: number; project_id?: string | null; tz?: string },
  ): Promise<DashboardUsageDaily[]> {
    const search = new URLSearchParams();
    if (params.days) search.set("days", String(params.days));
    if (params.project_id) search.set("project_id", params.project_id);
    if (params.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(`/api/dashboard/usage/daily?${search}`);
    return parseWithFallback<DashboardUsageDaily[]>(
      raw,
      DashboardUsageDailyListSchema,
      [],
      { endpoint: "GET /api/dashboard/usage/daily" },
    );
  }

  async getDashboardUsageByAgent(
    params: { days?: number; project_id?: string | null; tz?: string },
  ): Promise<DashboardUsageByAgent[]> {
    const search = new URLSearchParams();
    if (params.days) search.set("days", String(params.days));
    if (params.project_id) search.set("project_id", params.project_id);
    if (params.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(`/api/dashboard/usage/by-agent?${search}`);
    return parseWithFallback<DashboardUsageByAgent[]>(
      raw,
      DashboardUsageByAgentListSchema,
      [],
      { endpoint: "GET /api/dashboard/usage/by-agent" },
    );
  }

  async getDashboardAgentRunTime(
    params: { days?: number; project_id?: string | null; tz?: string },
  ): Promise<DashboardAgentRunTime[]> {
    const search = new URLSearchParams();
    if (params.days) search.set("days", String(params.days));
    if (params.project_id) search.set("project_id", params.project_id);
    // `tz` aligns the "last N days" cutoff with the viewer's calendar,
    // matching the per-agent token card.
    if (params.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(`/api/dashboard/agent-runtime?${search}`);
    return parseWithFallback<DashboardAgentRunTime[]>(
      raw,
      DashboardAgentRunTimeListSchema,
      [],
      { endpoint: "GET /api/dashboard/agent-runtime" },
    );
  }

  async getDashboardRunTimeDaily(
    params: { days?: number; project_id?: string | null; tz?: string },
  ): Promise<DashboardRunTimeDaily[]> {
    const search = new URLSearchParams();
    if (params.days) search.set("days", String(params.days));
    if (params.project_id) search.set("project_id", params.project_id);
    // `tz` cuts the day buckets in the viewer's calendar so Time / Tasks
    // align with the Cost / Tokens charts.
    if (params.tz) search.set("tz", params.tz);
    const raw = await this.fetch<unknown>(`/api/dashboard/runtime/daily?${search}`);
    return parseWithFallback<DashboardRunTimeDaily[]>(
      raw,
      DashboardRunTimeDailyListSchema,
      [],
      { endpoint: "GET /api/dashboard/runtime/daily" },
    );
  }

  async initiateUpdate(
    runtimeId: string,
    targetVersion: string,
  ): Promise<RuntimeUpdate> {
    return this.fetch(`/api/runtimes/${runtimeId}/update`, {
      method: "POST",
      body: JSON.stringify({ target_version: targetVersion }),
    });
  }

  async getUpdateResult(
    runtimeId: string,
    updateId: string,
  ): Promise<RuntimeUpdate> {
    return this.fetch(`/api/runtimes/${runtimeId}/update/${updateId}`);
  }

  async initiateListModels(runtimeId: string): Promise<RuntimeModelListRequest> {
    return this.fetch(`/api/runtimes/${runtimeId}/models`, { method: "POST" });
  }

  async getListModelsResult(
    runtimeId: string,
    requestId: string,
  ): Promise<RuntimeModelListRequest> {
    return this.fetch(`/api/runtimes/${runtimeId}/models/${requestId}`);
  }

  async initiateListLocalSkills(
    runtimeId: string,
  ): Promise<RuntimeLocalSkillListRequest> {
    return this.fetch(`/api/runtimes/${runtimeId}/local-skills`, {
      method: "POST",
    });
  }

  async getListLocalSkillsResult(
    runtimeId: string,
    requestId: string,
  ): Promise<RuntimeLocalSkillListRequest> {
    return this.fetch(`/api/runtimes/${runtimeId}/local-skills/${requestId}`);
  }

  async initiateImportLocalSkill(
    runtimeId: string,
    data: CreateRuntimeLocalSkillImportRequest,
  ): Promise<RuntimeLocalSkillImportRequest> {
    return this.fetch(`/api/runtimes/${runtimeId}/local-skills/import`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }
```

**File:** server/internal/handler/daemon.go (L322-362)
```go
		row, err := h.Queries.UpsertAgentRuntime(r.Context(), db.UpsertAgentRuntimeParams{
			WorkspaceID: wsUUID,
			DaemonID:    strToText(req.DaemonID),
			Name:        name,
			RuntimeMode: "local",
			Provider:    provider,
			Status:      status,
			DeviceInfo:  deviceInfo,
			Metadata:    metadata,
			OwnerID:     ownerID,
		})
		if err != nil {
			h.Analytics.Capture(analytics.RuntimeFailed(
				uuidToString(ownerID),
				req.WorkspaceID,
				req.DaemonID,
				provider,
				"registration_failed",
				"db_error",
				true,
			))
			writeError(w, http.StatusInternalServerError, "failed to register runtime: "+err.Error())
			return
		}

		registered := db.AgentRuntime{
			ID:             row.ID,
			WorkspaceID:    row.WorkspaceID,
			DaemonID:       row.DaemonID,
			Name:           row.Name,
			RuntimeMode:    row.RuntimeMode,
			Provider:       row.Provider,
			Status:         row.Status,
			DeviceInfo:     row.DeviceInfo,
			Metadata:       row.Metadata,
			LastSeenAt:     row.LastSeenAt,
			CreatedAt:      row.CreatedAt,
			UpdatedAt:      row.UpdatedAt,
			OwnerID:        row.OwnerID,
			LegacyDaemonID: row.LegacyDaemonID,
		}
```

**File:** server/internal/handler/daemon.go (L511-571)
```go
// DaemonDeregister marks runtimes as offline when the daemon shuts down.
func (h *Handler) DaemonDeregister(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RuntimeIDs []string `json:"runtime_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if len(req.RuntimeIDs) == 0 {
		writeError(w, http.StatusBadRequest, "runtime_ids is required")
		return
	}
	runtimeUUIDs, ok := parseUUIDSliceOrBadRequest(w, req.RuntimeIDs, "runtime_ids")
	if !ok {
		return
	}

	// Track affected workspaces for WS notifications.
	affectedWorkspaces := make(map[string]bool)

	for i, rid := range req.RuntimeIDs {
		// Look up the runtime and verify ownership.
		rt, err := h.Queries.GetAgentRuntime(r.Context(), runtimeUUIDs[i])
		if err != nil {
			slog.Warn("deregister: runtime not found", "runtime_id", rid, "error", err)
			continue
		}

		wsID := uuidToString(rt.WorkspaceID)
		if !h.verifyDaemonWorkspaceAccess(r, wsID) {
			slog.Warn("deregister: workspace mismatch", "runtime_id", rid)
			continue
		}

		if err := h.Queries.SetAgentRuntimeOffline(r.Context(), rt.ID); err != nil {
			slog.Warn("deregister: failed to set offline", "runtime_id", rid, "error", err)
			continue
		}
		h.Analytics.Capture(analytics.RuntimeOffline(
			uuidToString(rt.OwnerID),
			wsID,
			uuidToString(rt.ID),
			rt.DaemonID.String,
			rt.Provider,
		))

		affectedWorkspaces[wsID] = true
	}

	// Notify frontend clients so they re-fetch runtime list.
	for wsID := range affectedWorkspaces {
		h.publish(protocol.EventDaemonRegister, wsID, "system", "", map[string]any{
			"action": "deregister",
		})
	}

	slog.Info("daemon deregistered", "runtime_ids", req.RuntimeIDs)
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
```

**File:** server/cmd/multica/cmd_runtime.go (L72-105)
```go
func runRuntimeList(cmd *cobra.Command, _ []string) error {
	client, err := newAPIClient(cmd)
	if err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	var runtimes []map[string]any
	if err := client.GetJSON(ctx, "/api/runtimes", &runtimes); err != nil {
		return fmt.Errorf("list runtimes: %w", err)
	}

	output, _ := cmd.Flags().GetString("output")
	if output == "json" {
		return cli.PrintJSON(os.Stdout, runtimes)
	}

	headers := []string{"ID", "NAME", "MODE", "PROVIDER", "STATUS", "LAST_SEEN"}
	rows := make([][]string, 0, len(runtimes))
	for _, rt := range runtimes {
		rows = append(rows, []string{
			strVal(rt, "id"),
			strVal(rt, "name"),
			strVal(rt, "runtime_mode"),
			strVal(rt, "provider"),
			strVal(rt, "status"),
			strVal(rt, "last_seen_at"),
		})
	}
	cli.PrintTable(os.Stdout, headers, rows)
	return nil
}
```

**File:** server/cmd/multica/cmd_runtime.go (L149-178)
```go
func runRuntimeActivity(cmd *cobra.Command, args []string) error {
	client, err := newAPIClient(cmd)
	if err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	var activity []map[string]any
	if err := client.GetJSON(ctx, "/api/runtimes/"+args[0]+"/activity", &activity); err != nil {
		return fmt.Errorf("get runtime activity: %w", err)
	}

	output, _ := cmd.Flags().GetString("output")
	if output == "json" {
		return cli.PrintJSON(os.Stdout, activity)
	}

	headers := []string{"HOUR", "COUNT"}
	rows := make([][]string, 0, len(activity))
	for _, a := range activity {
		rows = append(rows, []string{
			strVal(a, "hour"),
			strVal(a, "count"),
		})
	}
	cli.PrintTable(os.Stdout, headers, rows)
	return nil
}
```

**File:** server/internal/handler/runtime.go (L498-616)
```go
func (h *Handler) ListAgentRuntimes(w http.ResponseWriter, r *http.Request) {
	workspaceID := h.resolveWorkspaceID(r)

	var runtimes []db.AgentRuntime
	var err error

	if ownerFilter := r.URL.Query().Get("owner"); ownerFilter == "me" {
		userID, ok := requireUserID(w, r)
		if !ok {
			return
		}
		runtimes, err = h.Queries.ListAgentRuntimesByOwner(r.Context(), db.ListAgentRuntimesByOwnerParams{
			WorkspaceID: parseUUID(workspaceID),
			OwnerID:     parseUUID(userID),
		})
	} else {
		runtimes, err = h.Queries.ListAgentRuntimes(r.Context(), parseUUID(workspaceID))
	}

	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to list runtimes")
		return
	}

	resp := make([]AgentRuntimeResponse, len(runtimes))
	for i, rt := range runtimes {
		resp[i] = runtimeToResponse(rt)
	}

	writeJSON(w, http.StatusOK, resp)
}

// DeleteAgentRuntime deletes a runtime after permission and dependency checks.
//
// The strict variant: refuses with 409 + structured `runtime_has_active_agents`
// when any non-archived agent is still bound to the runtime, and returns the
// blocking agent list in the response body so the front-end can pivot to the
// cascade dialog without an extra round-trip. The cascade itself lives at
// POST /api/runtimes/:id/archive-agents-and-delete (ArchiveAgentsAndDeleteRuntime
// below) and runs the multi-write teardown inside a single transaction.
func (h *Handler) DeleteAgentRuntime(w http.ResponseWriter, r *http.Request) {
	runtimeID := chi.URLParam(r, "runtimeId")
	runtimeUUID, ok := parseUUIDOrBadRequest(w, runtimeID, "runtime_id")
	if !ok {
		return
	}

	rt, err := h.Queries.GetAgentRuntime(r.Context(), runtimeUUID)
	if err != nil {
		writeError(w, http.StatusNotFound, "runtime not found")
		return
	}

	wsID := uuidToString(rt.WorkspaceID)
	member, ok := h.requireWorkspaceMember(w, r, wsID, "runtime not found")
	if !ok {
		return
	}

	// Permission: owner/admin can delete any runtime; members can only delete their own.
	if !canEditRuntime(member, rt) {
		writeError(w, http.StatusForbidden, "you can only delete your own runtimes")
		return
	}
	userID := uuidToString(member.UserID)

	// Check if any active (non-archived) agents are bound to this runtime.
	// Surface them on the 409 so the dialog can render the cascade plan
	// directly from this response — saves a second round-trip when the
	// user clicked Delete from a stale list page.
	activeAgents, err := h.Queries.ListActiveAgentsByRuntime(r.Context(), rt.ID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to check runtime dependencies")
		return
	}
	if len(activeAgents) > 0 {
		writeJSON(w, http.StatusConflict, runtimeHasActiveAgentsResponse(activeAgents))
		return
	}

	// Pause autopilots pointing at the archived agents BEFORE we delete
	// them. Migration 096 dropped the autopilot.assignee_id agent FK, so a
	// hard-delete here would otherwise leave dangling rows that subsequent
	// scheduler ticks would skip with "assignee agent no longer exists" —
	// quiet, but burning a run record every tick until an operator notices.
	// Pausing makes the breakage visible in the autopilot list so the owner
	// can re-point or delete the row instead.
	archivedAgentIDs, err := h.Queries.ListArchivedAgentIDsByRuntime(r.Context(), rt.ID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to enumerate archived agents")
		return
	}
	if len(archivedAgentIDs) > 0 {
		if err := h.Queries.PauseAutopilotsByAgentAssignees(r.Context(), archivedAgentIDs); err != nil {
			slog.Warn("pause autopilots for archived agents failed",
				"runtime_id", uuidToString(rt.ID), "error", err)
		}
	}

	// Remove archived agents so the FK constraint (ON DELETE RESTRICT) won't block deletion.
	if err := h.Queries.DeleteArchivedAgentsByRuntime(r.Context(), rt.ID); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to clean up archived agents")
		return
	}

	if err := h.Queries.DeleteAgentRuntime(r.Context(), rt.ID); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete runtime")
		return
	}

	slog.Info("runtime deleted", "runtime_id", uuidToString(rt.ID), "deleted_by", userID)

	// Notify frontend to refresh runtime list.
	h.publish(protocol.EventDaemonRegister, wsID, "member", userID, map[string]any{
		"action": "delete",
	})

	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
```
