# Frontend Required APIs

> These APIs are required by the dashboard SPA (`/dashboard`) views. Each page's data requirements are listed below with the expected request/response format.

**Base URL:** `http://localhost:3000/api`

**Auth:** `Authorization: Bearer <token>` (required for all endpoints)

---

## Table of Contents

| Page | Route | Description |
|------|-------|-------------|
| Inbox | `/dashboard/#inbox` | Notifications and task assignments |
| My Issues | `/dashboard/#my-issues` | Current user's assigned issues |
| Issues | `/dashboard/#issues` | Workspace-wide issue board |
| Projects | `/dashboard/#projects` | Project list |
| Sessions | `/dashboard/#sessions/:projectId` | Chat sessions within a project |
| Chat | `/dashboard/#chat/:projectId/:sessionId` | Single/Group chat |
| Autopilots | `/dashboard/#autopilots` | Autopilot automation profiles |
| Agents | `/dashboard/#agents` | Agent registry |
| Squads | `/dashboard/#squads` | Squad/team configurations |
| Usage | `/dashboard/#usage` | Token usage statistics |
| Runtimes | `/dashboard/#runtimes` | Runtime environments |
| Skills | `/dashboard/#skills` | Available skills |
| Settings | `/dashboard/#settings` | Workspace settings |

---

## 1. Inbox

### `GET /api/inbox`

Returns notifications grouped by type: task_assign, system_event, handoff, etc.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `limit` | int | No | Max items to return (default: 20) |
| `types` | string | No | Comma-separated notification types to filter |

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "notif_1",
      "type": "task_assign",
      "icon": "task",
      "title": "AHB-14 Implement token refresh",
      "body": "Assigned to you by architect",
      "project": "AgentHub Core",
      "timestamp": "2026-06-03T10:30:00Z",
      "read": false
    }
  ]
}
```

---

## 2. My Issues

### `GET /api/my-issues`

Returns the current user's assigned issues, grouped by status.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | No | Filter by status: `todo`, `in_progress`, `review`, `done` |
| `project_id` | string | No | Filter by project |

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "AHB-12",
      "title": "Implement auth flow",
      "status": "in_progress",
      "assignee": "Hall",
      "reporter": "architect",
      "project": "AgentHub Core",
      "progress": 70,
      "priority": "high"
    }
  ],
  "stats": {
    "todo": 2,
    "in_progress": 3,
    "review": 1,
    "done": 0
  }
}
```

---

## 3. Issues

### `GET /api/issues`

Returns all workspace issues with pagination and filtering.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `page` | int | No | Page number (default: 1) |
| `page_size` | int | No | Items per page (default: 50) |
| `project_id` | string | No | Filter by project |
| `status` | string | No | Filter by status |
| `assignee` | string | No | Filter by assignee |
| `search` | string | No | Full-text search on issue title/body |

**Response:**
```json
{
  "ok": true,
  "data": {
    "issues": [
      {
        "id": "AHB-12",
        "title": "Implement auth flow",
        "status": "in_progress",
        "assignee": "Hall",
        "reporter": "architect",
        "project": "AgentHub Core",
        "progress": 70
      }
    ],
    "total": 17,
    "page": 1,
    "page_size": 50
  }
}
```

---

## 4. Projects

### `GET /api/projects`

Returns all projects in the workspace.

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "p1",
      "title": "AgentHub Core",
      "description": "Platform infrastructure and core features",
      "issues": 8,
      "active_agents": 3,
      "active_sessions": 3,
      "gradient": "#8b5cf6",
      "initial": "A"
    }
  ]
}
```

### `POST /api/projects`

Create a new project.

**Request body:**
```json
{
  "title": "New Project",
  "description": "Description"
}
```

**Response:** `201 Created`
```json
{
  "ok": true,
  "data": {
    "id": "p4",
    "title": "New Project",
    "description": "Description",
    "issues": 0,
    "active_agents": 0,
    "active_sessions": 0,
    "gradient": "#8b5cf6",
    "initial": "N"
  }
}
```

---

## 5. Sessions

### `GET /api/projects/:projectId/sessions`

Returns all chat sessions (direct + group) for a given project.

**Response:**
```json
{
  "ok": true,
  "data": {
    "project": {
      "id": "p1",
      "name": "AgentHub Core",
      "gradient": "#8b5cf6",
      "initial": "A"
    },
    "sessions": [
      {
        "id": "s1",
        "type": "single",
        "agent_id": "a1",
        "name": "architect",
        "preview": "The API contract looks good...",
        "time": "2m",
        "unread": 1,
        "status": "active",
        "message_count": 5
      },
      {
        "id": "g1",
        "type": "group",
        "name": "Core Platform Team",
        "members": ["a1", "a2", "u1", "u2"],
        "preview": "architect: Let's align on the API...",
        "time": "5m",
        "unread": 3,
        "status": "active",
        "message_count": 6
      }
    ],
    "stats": {
      "active_sessions": 3,
      "unread_messages": 4,
      "agents_involved": 3
    }
  }
}
```

---

## 6. Chat

### `GET /api/sessions/:sessionId`

Returns a single chat session with full message history.

**Response:**
```json
{
  "ok": true,
  "data": {
    "session": {
      "id": "s1",
      "type": "single",
      "project_id": "p1",
      "name": "architect",
      "agent_id": "a1",
      "status": "active",
      "members": ["a1"],
      "message_count": 5
    },
    "messages": [
      {
        "id": "m1",
        "sender_id": "u1",
        "sender_type": "user",
        "text": "Can you review the auth flow design?",
        "timestamp": "2026-06-03T10:30:00Z",
        "time_display": "10:30 AM"
      }
    ]
  }
}
```

**Field `sender_type` values:** `user`, `agent`, `system`

### `POST /api/sessions/:sessionId/messages`

Send a message to a chat session.

**Request body:**
```json
{
  "text": "That makes sense. Should we also add device fingerprinting?",
  "sender_type": "user"
}
```

**Response:** `201 Created`
```json
{
  "ok": true,
  "data": {
    "id": "m6",
    "sender_id": "u1",
    "sender_type": "user",
    "text": "That makes sense. Should we also add device fingerprinting?",
    "timestamp": "2026-06-03T10:37:00Z",
    "time_display": "10:37 AM"
  }
}
```

### `GET /api/sessions/:sessionId/members`

Returns all members of a group chat session.

**Response:**
```json
{
  "ok": true,
  "data": {
    "session_id": "g1",
    "members": [
      {
        "id": "a1",
        "type": "agent",
        "name": "architect",
        "initials": "A1",
        "color": "#8b5cf6",
        "online": true
      },
      {
        "id": "u1",
        "type": "user",
        "name": "Hall",
        "initials": "H",
        "color": "#60a5fa",
        "online": true
      }
    ]
  }
}
```

---

## 7. Autopilots

### `GET /api/autopilots`

Returns all autopilot automation profiles.

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "ap1",
      "name": "Code Review Pipeline",
      "description": "Automated code review and lint",
      "trigger": "on_push",
      "agents": ["a1", "a3"],
      "status": "active",
      "runs_today": 12,
      "last_run": "2026-06-03T14:00:00Z",
      "success_rate": 95
    }
  ]
}
```

### `POST /api/autopilots`

Create a new autopilot.

**Request body:**
```json
{
  "name": "New Autopilot",
  "description": "Description",
  "trigger": "on_push"
}
```

**Response:** `201 Created`

### `PATCH /api/autopilots/:autopilotId`

Update an autopilot's status.

**Request body:**
```json
{
  "status": "paused"
}
```

---

## 8. Agents

### `GET /api/agents`

Returns all registered agents.

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "a1",
      "name": "architect",
      "initials": "A1",
      "color": "#8b5cf6",
      "online": true,
      "skills": ["code-review", "architecture"],
      "current_session_id": "s1",
      "session_name": "auth flow review"
    }
  ]
}
```

---

## 9. Squads

### `GET /api/squads`

Returns all squads (teams with multiple agents).

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "sq1",
      "name": "Backend Agents",
      "description": "API development team",
      "gradient": "#8b5cf6",
      "initial": "B",
      "members": [
        {
          "id": "a1",
          "name": "architect",
          "initials": "A1",
          "color": "#8b5cf6",
          "online": true,
          "role": "lead"
        },
        {
          "id": "a2",
          "name": "frontend",
          "initials": "A2",
          "color": "#34d399",
          "online": true,
          "role": "member"
        }
      ],
      "active_sessions": 2
    }
  ]
}
```

### `POST /api/squads`

Create a new squad.

**Request body:**
```json
{
  "name": "New Squad",
  "description": "Description",
  "member_ids": ["a1", "a2"]
}
```

---

## 10. Usage

### `GET /api/usage`

Returns current billing period usage stats.

**Response:**
```json
{
  "ok": true,
  "data": {
    "billing_cycle_start": "2026-06-01",
    "billing_cycle_end": "2026-06-30",
    "tokens_used": 3420000,
    "tokens_limit": 5000000,
    "token_input": 2100000,
    "token_output": 1320000,
    "estimated_cost": 34.20,
    "cost_limit": 50.00,
    "api_calls_used": 12850,
    "api_calls_limit": 20000,
    "sessions_used": 48,
    "sessions_limit": 100,
    "daily_breakdown": [
      { "date": "2026-06-01", "tokens": 150000, "cost": 1.50 },
      { "date": "2026-06-02", "tokens": 200000, "cost": 2.00 }
    ]
  }
}
```

---

## 11. Runtimes

### `GET /api/runtimes`

Returns available runtime environments.

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "rt1",
      "name": "Node.js 20",
      "status": "available",
      "version": "20.11.0",
      "description": "Default runtime for JavaScript/TypeScript agents"
    },
    {
      "id": "rt2",
      "name": "Python 3.12",
      "status": "available",
      "version": "3.12.1",
      "description": "Runtime for Python-based agents"
    }
  ]
}
```

---

## 12. Skills

### `GET /api/skills`

Returns all available skills.

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "sk1",
      "name": "web-design-guidelines",
      "description": "Applies web design best practices to UI code",
      "category": "Design",
      "enabled": true
    },
    {
      "id": "sk2",
      "name": "api-doc-builder",
      "description": "Generates API documentation from code",
      "category": "Documentation",
      "enabled": true
    }
  ]
}
```

### `PATCH /api/skills/:skillId`

Enable/disable a skill.

**Request body:**
```json
{
  "enabled": false
}
```

---

## 13. Settings

### `GET /api/settings/workspace`

Returns workspace settings.

**Response:**
```json
{
  "ok": true,
  "data": {
    "id": "ws1",
    "name": "AgentHub",
    "member_count": 1,
    "created_at": "2026-01-15T00:00:00Z"
  }
}
```

### `PATCH /api/settings/workspace`

Update workspace settings.

**Request body:**
```json
{
  "name": "New Workspace Name"
}
```

### `GET /api/settings/workspace/members`

Returns workspace members.

**Response:**
```json
{
  "ok": true,
  "data": [
    {
      "id": "u1",
      "name": "Hall",
      "email": "hall@example.com",
      "role": "owner",
      "joined_at": "2026-01-15T00:00:00Z"
    }
  ]
}
```

### `DELETE /api/settings/workspace`

Delete the workspace.

**Response:** `204 No Content`

---

## Common Response Envelope

All API responses follow this format:

```json
{
  "ok": true,
  "data": <payload>,
  "error": null
}
```

On error:
```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "NOT_FOUND",
    "message": "Session not found"
  }
}
```
