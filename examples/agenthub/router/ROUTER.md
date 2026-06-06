Multica 的前端页面切换采用**跨平台导航适配器模式**，不同平台使用不同的路由实现，但通过共享的 `NavigationAdapter` 提供统一的导航接口。 [1](#11-0) 

---

## 平台特定的路由实现

### Web 端（Next.js App Router）

Web 端使用 Next.js 16 的 App Router，通过文件系统路由和 `next/navigation` 进行页面切换： [2](#11-1) 

- 路由文件位于 `apps/web/app/` 目录
- 使用 `next/navigation` 的 `useRouter()` 进行导航
- URL 变化触发页面切换
- 支持服务端渲染（SSR）

### Desktop 端（React Router + Memory Router）

Desktop 端使用 `react-router-dom` 的 `createMemoryRouter`，每个标签页有独立的内存路由： [3](#11-2) 

```typescript
export function createTabRouter(initialPath: string) {
  return createMemoryRouter(appRoutes, {
    initialEntries: [initialPath],
  });
}
```

- 路由定义在 `apps/desktop/src/renderer/src/routes.tsx` [4](#11-3) 
- 每个工作区标签页有独立的 router 实例
- 使用 `useNavigation()` hook 进行导航（来自共享层）
- 不依赖 URL，完全基于内存状态

### Mobile 端（React Navigation）

Mobile 端使用 Expo 的 React Navigation，通过 Stack Navigation 进行页面切换： [5](#11-4) 

- 路由定义在 `apps/mobile/app/(app)/[workspace]/_layout.tsx`
- 使用 `<Stack.Screen>` 定义各个页面
- 支持模态页面和 sheet 组件

## 共享导航层

### NavigationAdapter

`packages/views/navigation` 提供了跨平台的导航适配器，让共享代码可以使用统一的导航 API： [1](#11-0) 

- Web 端适配器：包装 `next/navigation`
- Desktop 端适配器：包装 `react-router-dom`
- Mobile 端：独立实现（不共享）

### useNavigation() Hook

共享代码使用 `useNavigation()` hook 进行导航，而不是直接使用框架特定的路由 API： [6](#11-5) 

```typescript
const { push } = useNavigation();
push('/issues/123');
```

## 路由结构

### 工作区内路由

所有平台共享相同的工作区内路由结构： [7](#11-6) 

- `/{slug}/issues` — Issue 列表
- `/{slug}/issues/[id]` — Issue 详情
- `/{slug}/projects` — 项目列表
- `/{slug}/agents` — Agent 列表
- `/{slug}/settings` — 设置
- 等等...

### 搜索命令面板

搜索命令面板（Cmd+K）提供快速页面切换功能，支持跳转到各个页面： [8](#11-7) 

```typescript
const navPages: NavPage[] = [
  { key: "inbox", label: t(($) => $.pages.inbox), icon: Inbox, keywords: ["inbox", "notifications"] },
  { key: "myIssues", label: t(($) => $.pages.my_issues), icon: CircleUser, keywords: ["my", "issues"] },
  { key: "issues", label: t(($) => $.pages.issues), icon: ListTodo, keywords: ["issues", "tasks"] },
  // ...
];
```

## 跨工作区切换

### Web 端

Web 端通过 URL 变化切换工作区，例如从 `/workspace-a/issues` 到 `/workspace-b/issues`。

### Desktop 端

Desktop 端的跨工作区切换通过 `switchWorkspace()` 实现，导航适配器会检测跨工作区的 `push()` 并自动切换： [9](#11-8) 

```typescript
// Cross-workspace push is detected by the navigation adapter
// and translated into switchWorkspace(slug, targetPath)
```

## Notes

Multica 的导航架构遵循"共享业务逻辑，平台特定路由"的原则。所有业务页面组件都在 `packages/views/` 中，不依赖特定框架的路由 API。每个平台在 `platform/` 层提供自己的 `NavigationAdapter` 实现，让共享代码可以通过 `useNavigation()` 进行统一的页面切换。 [10](#11-9) 

Wiki pages you might want to explore:
- [Cross-Platform Development Rules (multica-ai/multica)](/wiki/multica-ai/multica#1)
- [Desktop-specific Rules (multica-ai/multica)](/wiki/multica-ai/multica#1)

Wiki pages you might want to explore:
- [Overview (multica-ai/multica)](/wiki/multica-ai/multica#1)

### Citations

**File:** CLAUDE.md (L32-34)
```markdown
- `server/` — Go backend (Chi router, sqlc for DB, gorilla/websocket for real-time)
- `apps/web/` — Next.js frontend (App Router)
- `apps/desktop/` — Electron desktop app (electron-vite)
```

**File:** CLAUDE.md (L49-50)
```markdown
**Platform bridge:** `packages/core/platform/` provides `CoreProvider` — initializes API client, auth/workspace stores, WS connection, and QueryClient. Each app wraps its root with `<CoreProvider>` and provides its own `NavigationAdapter` for routing.

```

**File:** CLAUDE.md (L214-246)
```markdown
### Package Boundary Rules

These are hard constraints. Violating them breaks the cross-platform architecture:

- `packages/core/` — zero react-dom, zero localStorage (use StorageAdapter), zero process.env, zero UI libraries. **Shared Zustand stores live here**, even view-related ones (filters, view modes) — stores are pure state, not UI.
- `packages/ui/` — zero `@multica/core` imports (pure UI, no business logic).
- `packages/views/` — zero `next/*` imports, zero `react-router-dom` imports, zero stores. Use `NavigationAdapter` for all routing.
- `apps/web/platform/` — the only place for Next.js APIs (`next/navigation`).
- `apps/desktop/src/renderer/src/platform/` — the only place for react-router-dom navigation wiring.

### The No-Duplication Rule (web + desktop)

**If the same logic exists in both web and desktop, it must be extracted to a shared package.**

This applies to everything between web and desktop: components, hooks, guards, providers, utility functions. The decision process:

1. Does this code depend on Next.js or Electron APIs? → Keep in the respective app.
2. Does it depend on `react-router-dom` or `next/navigation`? → Keep in app's `platform/` layer.
3. Everything else → belongs in `packages/core/` (headless logic) or `packages/views/` (UI components).

When the two apps need different behavior for the same concept (e.g., different loading UI), extract the shared logic into a component with props/slots for the differences. Don't duplicate the logic.

### Cross-Platform Development Rules (web + desktop)

When adding a new page or feature for web/desktop:

1. **New page component** → add to `packages/views/<domain>/`. Never import from `next/*` or `react-router-dom`.
2. **Wire it in both apps** → add a route in `apps/web/app/` (Next.js page file) AND in the desktop router. **Exception**: pre-workspace transition flows (create workspace, accept invite) are NOT routes on desktop — they're `WindowOverlay` state. See *Desktop-specific Rules → Route categories*.
3. **Navigation** → use `useNavigation().push()` or `<AppLink>`. Never use framework-specific link/router APIs in shared code.
4. **Shared guards/providers** → use `DashboardGuard` from `packages/views/layout/`. Don't create separate guard logic per app.
5. **Platform-specific UI** → if a feature is web-only or desktop-only, keep it in the respective app. Use props slots (`extra`, `topSlot`) on shared layout components to inject platform-specific UI.
6. **New hooks that need workspace context** → accept `wsId` as parameter instead of reading from `useWorkspaceId()` Context, so they work both inside and outside `WorkspaceIdProvider`.

```

**File:** CLAUDE.md (L290-291)
```markdown
Cross-workspace `push(path)` is detected by the navigation adapter (`platform/navigation.tsx`) and translated into `switchWorkspace(slug, targetPath)` — NOT a navigation within the current tab's router. Don't bypass the adapter; always go through `useNavigation()` from shared code.

```

**File:** apps/desktop/src/renderer/src/routes.tsx (L109-211)
```typescript
export const appRoutes: RouteObject[] = [
  {
    element: <PageShell />,
    children: [
      { index: true, element: null },
      {
        path: ":workspaceSlug",
        element: <WorkspaceRouteLayout />,
        children: [
          { index: true, element: <Navigate to="issues" replace /> },
          {
            path: "issues",
            element: (
              <ErrorBoundary>
                <IssuesPage />
              </ErrorBoundary>
            ),
            handle: { title: "Issues" },
          },
          {
            path: "issues/:id",
            element: <IssueDetailPage />,
            handle: { title: "Issue" },
          },
          {
            path: "projects",
            element: <ProjectsPage />,
            handle: { title: "Projects" },
          },
          {
            path: "projects/:id",
            element: <ProjectDetailPage />,
            handle: { title: "Project" },
          },
          {
            path: "autopilots",
            element: <AutopilotsPage />,
            handle: { title: "Autopilot" },
          },
          {
            path: "autopilots/:id",
            element: <AutopilotDetailPage />,
            handle: { title: "Autopilot" },
          },
          {
            path: "my-issues",
            element: <MyIssuesPage />,
            handle: { title: "My Issues" },
          },
          {
            path: "runtimes",
            element: <DesktopRuntimesPage />,
            handle: { title: "Runtimes" },
          },
          {
            path: "runtimes/:id",
            element: <RuntimeDetailPage />,
            handle: { title: "Runtime" },
          },
          { path: "skills", element: <SkillsPage />, handle: { title: "Skills" } },
          {
            path: "skills/:id",
            element: <SkillDetailPage />,
            handle: { title: "Skill" },
          },
          { path: "agents", element: <AgentsPage />, handle: { title: "Agents" } },
          {
            path: "agents/:id",
            element: <AgentDetailPage />,
            handle: { title: "Agent" },
          },
          {
            path: "members/:id",
            element: <MemberDetailPage />,
            handle: { title: "Member" },
          },
          { path: "squads", element: <SquadsPage />, handle: { title: "Squads" } },
          {
            path: "squads/:id",
            element: <SquadDetailPageView />,
            handle: { title: "Squad" },
          },
          { path: "inbox", element: <InboxPage />, handle: { title: "Inbox" } },
          {
            path: "attachments/:id/preview",
            element: <AttachmentPreviewRoute />,
            handle: { title: "Attachment" },
          },
          {
            path: "usage",
            element: <DashboardPage />,
            handle: { title: "Usage" },
          },
          {
            path: "settings",
            element: <DesktopSettingsRoute />,
            handle: { title: "Settings" },
          },
        ],
      },
    ],
  },
];
```

**File:** apps/desktop/src/renderer/src/routes.tsx (L213-218)
```typescript
/** Create an independent memory router for a tab. */
export function createTabRouter(initialPath: string) {
  return createMemoryRouter(appRoutes, {
    initialEntries: [initialPath],
  });
}
```

**File:** apps/mobile/app/(app)/[workspace]/_layout.tsx (L253-337)
```typescript
        />
        <Stack.Screen
          name="new-issue-picker/priority"
          options={SHEET_OPTIONS}
        />
        <Stack.Screen
          name="new-issue-picker/assignee"
          options={{
            ...SHEET_OPTIONS,
            headerShown: true,
            title: "Assignee",
          }}
        />
        <Stack.Screen
          name="new-issue-picker/project"
          options={SHEET_OPTIONS}
        />
        <Stack.Screen
          name="new-issue-picker/due-date"
          options={SHEET_OPTIONS}
        />
        {/* New-project draft formSheet pickers — same pattern as
            new-issue-picker/*. Stacked on top of `project/new` (a modal). */}
        <Stack.Screen
          name="new-project-picker/status"
          options={SHEET_OPTIONS}
        />
        <Stack.Screen
          name="new-project-picker/priority"
          options={SHEET_OPTIONS}
        />
        {/* Shared filter sheet for My Issues and the workspace Issues page —
            chooses the right view-store via `?scope=my|all` URL param. */}
        <Stack.Screen name="issues-filter" options={SHEET_OPTIONS} />
        {/* Chat session-switch sheet. */}
        <Stack.Screen name="chat-sessions" options={SHEET_OPTIONS} />
        {/* Workspace switcher — reached from the More popover's collapsed
            WorkspaceCard. Two-step (pick → iOS Alert confirm → switch). */}
        <Stack.Screen name="switch-workspace" options={SHEET_OPTIONS} />
        <Stack.Screen
          name="more/issues"
          options={{ title: "Issues", headerBackTitle: "Back" }}
        />
        <Stack.Screen
          name="more/projects"
          options={{ title: "Projects", headerBackTitle: "Back" }}
        />
        <Stack.Screen
          name="more/agents"
          options={{ title: "Agents", headerBackTitle: "Back" }}
        />
        <Stack.Screen
          name="more/pins"
          options={{ title: "Pinned", headerBackTitle: "Back" }}
        />
        <Stack.Screen
          name="more/settings"
          options={{ title: "Settings", headerBackTitle: "Back" }}
        />
        <Stack.Screen
          name="more/settings/profile"
          options={{ title: "Profile", headerBackTitle: "Settings" }}
        />
        <Stack.Screen
          name="more/settings/notifications"
          options={{ title: "Notifications", headerBackTitle: "Settings" }}
        />
        <Stack.Screen
          name="new-issue"
          options={{
            title: "New Issue",
            presentation: "modal",
            headerLeft: () => <ModalCloseButton />,
          }}
        />
        <Stack.Screen
          name="search"
          options={{
            title: "Search",
            presentation: "modal",
            headerLeft: () => <ModalCloseButton />,
          }}
        />
      </Stack>
    </RealtimeProvider>
```

**File:** docs/product-overview.md (L848-861)
```markdown
### 工作区内（`/{slug}/...`）

- `/issues` — Issue 列表（board / list 视图）
- `/issues/[id]` — Issue 详情
- `/my-issues` — 我的 issue（三 scope）
- `/projects` — 项目列表
- `/projects/[id]` — 项目详情
- `/autopilots` — Autopilot 列表
- `/autopilots/[id]` — Autopilot 详情
- `/agents` — Agent 列表
- `/runtimes` — Runtime 列表
- `/skills` — Skill 库
- `/inbox` — 收件箱
- `/settings` — 设置（包含多个 tab：profile / appearance / tokens / workspace / members / repos / daemon / updates）
```

**File:** packages/views/search/search-command.tsx (L167-176)
```typescript
  const navPages: NavPage[] = [
    { key: "inbox", label: t(($) => $.pages.inbox), icon: Inbox, keywords: ["inbox", "notifications", "收件箱"] },
    { key: "myIssues", label: t(($) => $.pages.my_issues), icon: CircleUser, keywords: ["my", "issues", "assigned", "我的"] },
    { key: "issues", label: t(($) => $.pages.issues), icon: ListTodo, keywords: ["issues", "tasks", "bugs"] },
    { key: "projects", label: t(($) => $.pages.projects), icon: FolderKanban, keywords: ["projects", "kanban", "项目"] },
    { key: "agents", label: t(($) => $.pages.agents), icon: Bot, keywords: ["agents", "bots", "ai"] },
    { key: "runtimes", label: t(($) => $.pages.runtimes), icon: Monitor, keywords: ["runtimes", "environments"] },
    { key: "skills", label: t(($) => $.pages.skills), icon: BookOpenText, keywords: ["skills", "library"] },
    { key: "settings", label: t(($) => $.pages.settings), icon: Settings, keywords: ["settings", "config", "preferences", "设置"] },
  ];
```

前端页面代码分布在 Web、Desktop 和 Mobile 三个应用中，通过不同的路由系统实现页面切换。 [1](#5-0) [2](#5-1) 

---

## Web 端页面结构

### 预工作区路由（`apps/web/app/(auth)/`）
- **登录页**：`apps/web/app/(auth)/login/page.tsx` - 处理 magic link 和 OAuth 登录 [3](#5-2) 
- **Onboarding**：`apps/web/app/(auth)/onboarding/page.tsx` - 首次引导流程 [4](#5-3) 
- **OAuth 回调**：`apps/web/app/auth/callback/page.tsx`

### 工作区内路由（`apps/web/app/[workspaceSlug]/(dashboard)/`）
所有工作区页面都使用 `[workspaceSlug]` 动态段，通过 `proxy.ts` 中间件处理旧 URL 重定向 [5](#5-4) 。

| 页面 | 路由 | 源文件位置 |
|------|------|-----------|
| Issues 列表 | `/{slug}/issues` | `packages/views/issues/components` |
| Issue 详情 | `/{slug}/issues/[id]` | `packages/views/issues/components` |
| Projects 列表 | `/{slug}/projects` | `packages/views/projects/components` |
| Project 详情 | `/{slug}/projects/[id]` | `packages/views/projects/components` |
| Autopilots | `/{slug}/autopilots` | `packages/views/autopilots/components` |
| My Issues | `/{slug}/my-issues` | `apps/web/app/[workspaceSlug]/(dashboard)/my-issues/page.tsx` [6](#5-5)  |
| Agents | `/{slug}/agents` | `packages/views/agents` |
| Agent 详情 | `/{slug}/agents/[id]` | `apps/web/app/[workspaceSlug]/(dashboard)/agents/[id]/page.tsx` [7](#5-6)  |
| Runtimes | `/{slug}/runtimes` | `packages/views/runtimes` |
| Skills | `/{slug}/skills` | `packages/views/skills` |
| Inbox | `/{slug}/inbox` | `packages/views/inbox` |
| Settings | `/{slug}/settings` | `packages/views/settings` |
| Usage | `/{slug}/usage` | `packages/views/dashboard` |

### 页面切换逻辑
Web 端使用 Next.js App Router，通过 `useNavigation()` 适配器统一处理导航 [8](#5-7) 。共享组件使用 `NavigationAdapter` 接口，避免直接依赖 `next/navigation` [9](#5-8) 。

## Desktop 端页面结构

### 路由定义（`apps/desktop/src/renderer/src/routes.tsx`）
Desktop 使用 `react-router-dom` 的 `createMemoryRouter`，每个标签页有独立的路由实例 [10](#5-9) 。

| 页面 | 路由 | 源文件 |
|------|------|--------|
| Issues | `:workspaceSlug/issues` | `@multica/views/issues/components` |
| Issue 详情 | `:workspaceSlug/issues/:id` | `./pages/issue-detail-page` |
| Projects | `:workspaceSlug/projects` | `@multica/views/projects/components` |
| Project 详情 | `:workspaceSlug/projects/:id` | `./pages/project-detail-page` |
| Autopilots | `:workspaceSlug/autopilots` | `@multica/views/autopilots/components` |
| My Issues | `:workspaceSlug/my-issues` | `@multica/views/my-issues` |
| Runtimes | `:workspaceSlug/runtimes` | `./components/desktop-runtimes-page` |
| Runtime 详情 | `:workspaceSlug/runtimes/:id` | `./pages/runtime-detail-page` |
| Skills | `:workspaceSlug/skills` | `@multica/views/skills` |
| Agents | `:workspaceSlug/agents` | `@multica/views/agents` |
| Agent 详情 | `:workspaceSlug/agents/:id` | `./pages/agent-detail-page` |
| Squads | `:workspaceSlug/squads` | `@multica/views/squads/components` |
| Inbox | `:workspaceSlug/inbox` | `@multica/views/inbox` |
| Settings | `:workspaceSlug/settings` | `./components/desktop-settings-route` |

### 页面切换逻辑
- **会话路由**：工作区页面通过 `WorkspaceRouteLayout` 渲染，支持多标签 [11](#5-10) 
- **过渡流程**：创建工作区、接受邀请等预工作区流程使用 `WindowOverlay`，不走路由 [12](#5-11) 
- **跨工作区导航**：通过导航适配器检测并调用 `switchWorkspace(slug, targetPath)` [13](#5-12) 

## Mobile 端页面结构

### 路由定义（`apps/mobile/app/(app)/[workspace]/_layout.tsx`）
Mobile 使用 Expo Router 的 Stack 导航 [14](#5-13) 。

| 页面 | 路由 | 源文件 |
|------|------|--------|
| Chat | `(tabs)/chat` | `apps/mobile/app/(app)/[workspace]/(tabs)/chat.tsx` |
| Issues | `(tabs)/issues` | `apps/mobile/app/(app)/[workspace]/(tabs)/issues.tsx` |
| Inbox | `(tabs)/inbox` | `apps/mobile/app/(app)/[workspace]/(tabs)/inbox.tsx` |
| More | `(tabs)/more` | `apps/mobile/app/(app)/[workspace]/(tabs)/more.tsx` |
| Issue 详情 | `issue/[id]` | `apps/mobile/app/(app)/[workspace]/issue/[id].tsx` |
| Project 详情 | `project/[id]` | `apps/mobile/app/(app)/[workspace]/project/[id].tsx` |
| 会话选择 | `chat-sessions` | `apps/mobile/app/(app)/[workspace]/chat-sessions.tsx` |
| 工作区切换 | `switch-workspace` | `apps/mobile/app/(app)/[workspace]/switch-workspace.tsx` [15](#5-14)  |

### 页面切换逻辑
- **Tab 导航**：底部 Tab 切换使用 `(tabs)` 组
- **Modal Sheet**：选择器（状态、优先级等）使用 `presentation: "formSheet"` 的独立路由 [16](#5-15) 
- **工作区切换**：通过 `switch-workspace` 页面展示工作区列表，确认后调用 `router.replace` [15](#5-14) 

## 共享页面组件

大部分业务页面组件位于 `packages/views/`，Web 和 Desktop 共享 [17](#5-16) ：

- `packages/views/issues/` - Issues 相关页面
- `packages/views/projects/` - Projects 相关页面
- `packages/views/agents/` - Agents 相关页面
- `packages/views/settings/` - Settings 页面
- `packages/views/dashboard/` - Dashboard 页面

## 路由规范

### 预工作区路由
必须使用单个单词或 `/{noun}/{verb}` 格式 [18](#5-17) ：
- ✅ `/login`, `/inbox`, `/workspaces/new`
- ❌ `/new-workspace`, `/create-team`

### 工作区路由
永远使用 `/{slug}/{section}` 格式 [19](#5-18) ：
- ✅ `/{slug}/issues`, `/{slug}/agents`, `/{slug}/settings`

## Notes

Web 和 Desktop 共享 `packages/views/` 中的业务组件，但使用不同的路由系统（Next.js vs react-router-dom）。Mobile 端完全独立，仅共享类型和纯函数。所有平台都通过 `NavigationAdapter` 接口统一导航逻辑，避免在共享代码中直接使用框架特定的路由 API [8](#5-7) 。

Wiki pages you might want to explore:
- [Authentication and Layout (multica-ai/multica)](/wiki/multica-ai/multica#3.1)
- [Conventions (multica-ai/multica)](/wiki/multica-ai/multica#14)

Wiki pages you might want to explore:
- [Overview (multica-ai/multica)](/wiki/multica-ai/multica#1)
- [Authentication and Layout (multica-ai/multica)](/wiki/multica-ai/multica#3.1)

### Citations

**File:** CLAUDE.md (L30-39)
```markdown
**Go backend + monorepo frontend (pnpm workspaces + Turborepo) with shared packages.**

- `server/` — Go backend (Chi router, sqlc for DB, gorilla/websocket for real-time)
- `apps/web/` — Next.js frontend (App Router)
- `apps/desktop/` — Electron desktop app (electron-vite)
- `apps/mobile/` — Expo / React Native iOS app. See `apps/mobile/CLAUDE.md`.
- `packages/core/` — Headless business logic (zero react-dom)
- `packages/ui/` — Atomic UI components (zero business logic)
- `packages/views/` — Shared business pages/components (zero next/* imports, zero react-router imports)
- `packages/tsconfig/` — Shared TypeScript configuration
```

**File:** CLAUDE.md (L75-80)
```markdown
## Sharing Principles

The monorepo splits into two share zones:

- **Web and desktop** share business logic, components, hooks, stores, and views through `packages/core/`, `packages/ui/`, and `packages/views/`. Existing model — keep using it.
- **Mobile (`apps/mobile/`) is independent.** It shares only **types and pure functions** from `@multica/core/`, with `import type` for types (zero runtime coupling). UI, state, hooks, providers, i18n, React version, build pipeline, release cadence — all mobile-owned.
```

**File:** CLAUDE.md (L263-271)
```markdown
### Route categories

Every path in the desktop app falls into exactly one category. Choosing the wrong one reproduces bugs we've already fixed.

- **Session routes** — workspace-scoped pages (`/:slug/issues`, `/:slug/settings`). Rendered by the per-tab memory router under `WorkspaceRouteLayout`. These are legitimate tab destinations.
- **Transition flows** — pre-workspace / one-shot actions (create workspace, accept invite). **NOT routes.** They live as `WindowOverlay` state, dispatched when the navigation adapter sees `push('/workspaces/new')` or `push('/invite/<id>')`. The shared view (`NewWorkspacePage`, `InvitePage`) is the content; the overlay wrapper supplies platform chrome.
- **Error / stale states** — "workspace not available", tabs pointing at a revoked workspace. **NOT pages.** `WorkspaceRouteLayout` auto-heals by dropping the stale tab group from the store; the user never lands on an explicit error screen. Web keeps `NoAccessPage` (shareable URL makes the error state meaningful); desktop has no URL bar so stale = heal silently.

**Adding a new pre-workspace flow on desktop**: register a new `WindowOverlay` type in `stores/window-overlay-store.ts`. Do NOT add it to `routes.tsx`. If a shared view needs the flow on both platforms, add the route on web (`apps/web/app/(auth)/...`) AND the overlay type on desktop — the shared view component is identical.
```

**File:** CLAUDE.md (L286-291)
```markdown
### Tab isolation

Tabs are grouped per workspace in `stores/tab-store.ts`. The TabBar shows only the active workspace's tabs; cross-workspace tab leakage is impossible by construction (no flat global tabs array).

Cross-workspace `push(path)` is detected by the navigation adapter (`platform/navigation.tsx`) and translated into `switchWorkspace(slug, targetPath)` — NOT a navigation within the current tab's router. Don't bypass the adapter; always go through `useNavigation()` from shared code.

```

**File:** apps/docs/content/docs/developers/conventions.mdx (L14-26)
```text
### Routes

Pre-workspace routes (the routes that exist before the user is in a workspace) MUST use either a single word or the `/{noun}/{verb}` pattern.

- ✅ `/login`, `/inbox`, `/workspaces/new`
- ❌ `/new-workspace`, `/create-team`, `/accept-invite`

Hyphenated word groups at the root collide with user-chosen workspace slugs and force endless reserved-slug audits. Reserving the noun (`workspaces`) automatically protects the entire `/workspaces/*` subtree.

### Workspace-scoped routes

Always live under `/{slug}/{section}` — `/{slug}/issues`, `/{slug}/agents`, `/{slug}/settings`. Never duplicate workspace routing logic; use `useNavigation().push()` from shared code, never framework-specific link APIs.

```

**File:** apps/docs/content/docs/developers/conventions.mdx (L30-38)
```text

| Package | May depend on | Must NOT depend on |
| --- | --- | --- |
| `packages/core` | nothing app-specific | `react-dom`, `localStorage`, `process.env`, `next/*`, UI libraries |
| `packages/ui` | nothing | `@multica/core`, business logic |
| `packages/views` | `core/`, `ui/` | `next/*`, `react-router-dom`, stores |
| `apps/web/platform/` | `next/*` | other apps |
| `apps/desktop/.../platform/` | `react-router-dom`, electron | other apps |

```

**File:** apps/web/app/(auth)/login/page.tsx (L57-113)
```typescript
function LoginPageContent() {
  const router = useRouter();
  const qc = useQueryClient();
  const { t } = useT("auth");
  const googleClientId = useConfigStore((state) => state.googleClientId);
  const user = useAuthStore((s) => s.user);
  const isLoading = useAuthStore((s) => s.isLoading);
  const searchParams = useSearchParams();

  const cliCallbackRaw = searchParams.get("cli_callback");
  const cliState = searchParams.get("cli_state") || "";
  const platform = searchParams.get("platform");
  const isDesktopHandoff = platform === "desktop" && !cliCallbackRaw;
  // `next` carries a protected URL the user was originally headed to
  // (e.g. /invite/{id}). With URL-driven workspaces there is no legacy
  // "/issues" default — if `next` is absent we decide after login based on
  // the user's workspace list. Sanitize first so a crafted `?next=https://evil`
  // cannot bounce the user off-origin after a successful login.
  const nextUrl = sanitizeNextUrl(searchParams.get("next"));

  const [desktopToken, setDesktopToken] = useState<string | null>(null);
  const [desktopError, setDesktopError] = useState("");
  const hasOnboarded = useHasOnboarded();

  // Already authenticated — honor ?next= or fall back to first workspace
  // (or /onboarding if the user has none). Skip this entire path when
  // the user arrived to authorize the CLI.
  useEffect(() => {
    if (isLoading || !user || cliCallbackRaw) return;
    if (isDesktopHandoff) {
      // Desktop opened the browser for login but the web session is already
      // authenticated — mint a bearer token from the cookie session and hand
      // it off via deep link instead of silently redirecting to the workspace.
      api
        .issueCliToken()
        .then(({ token }) => {
          setDesktopToken(token);
          window.location.href = `multica://auth/callback?token=${encodeURIComponent(token)}`;
        })
        .catch((err) => {
          setDesktopError(
            err instanceof Error
              ? err.message
              : t(($) => $.web.desktop_handoff.prepare_failed),
          );
        });
      return;
    }
    if (nextUrl) {
      router.replace(nextUrl);
      return;
    }
    const list = qc.getQueryData<Workspace[]>(workspaceKeys.list()) ?? [];
    void resolveLoggedInDestination(qc, hasOnboarded, list).then((dest) =>
      router.replace(dest),
    );
  }, [isLoading, user, router, nextUrl, cliCallbackRaw, isDesktopHandoff, hasOnboarded, qc]);
```

**File:** apps/web/app/(auth)/onboarding/page.tsx (L28-90)
```typescript
export default function OnboardingPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isLoading = useAuthStore((s) => s.isLoading);
  const hasOnboarded = useHasOnboarded();
  const { data: workspaces = [], isFetched: workspacesFetched } = useQuery({
    ...workspaceListOptions(),
    enabled: !!user,
  });
  // The bootstrap path calls refreshMe() before returning, which flips
  // hasOnboarded to true while the page is still mounted. Without this
  // flag the guard below races onComplete: the guard's router.replace
  // (issues list) can overtake onComplete's router.push (guide issue),
  // dropping the user on the wrong destination. Marking the page as
  // "completing" right before onComplete navigates keeps the guard
  // silent for the in-flight transition.
  const completingRef = useRef(false);

  useEffect(() => {
    if (isLoading || !user) {
      if (!isLoading && !user) router.replace(paths.login());
      return;
    }
    if (!workspacesFetched) return;
    if (completingRef.current) return;
    // Bounce out only when onboarding genuinely doesn't apply: the user is
    // already onboarded. We deliberately don't bounce on `workspaces.length`
    // here — Step 3 of the flow creates a workspace mid-onboarding, and a
    // hasWorkspaces bounce here would kick the user out before Steps 4–5
    // (runtime / agent / first issue) can run. The new entry-point
    // judgment in callback / login handles "where should this user go on
    // login" so OnboardingPage no longer needs to second-guess it.
    if (hasOnboarded) {
      router.replace(resolvePostAuthDestination(workspaces, hasOnboarded));
    }
  }, [isLoading, user, hasOnboarded, workspacesFetched, workspaces, router]);

  if (isLoading || !user || hasOnboarded) return null;

  // Layout: page owns its own scroll (root layout sets `body {
  // overflow: hidden }` for the app-shell convention). OnboardingFlow
  // owns the per-step width constraint internally — Welcome renders a
  // wide two-column hero, all other steps wrap themselves at max-w-xl.
  return (
    <div className="h-full overflow-y-auto bg-background">
      <OnboardingFlow
        onComplete={(ws, issueId) => {
          // Runtime-connected onboarding now creates one focused
          // onboarding issue. Skip/runtime-less exits still land on the
          // workspace issues list.
          completingRef.current = true;
          if (ws && issueId) {
            router.push(paths.workspace(ws.slug).issueDetail(issueId));
          } else if (ws) {
            router.push(paths.workspace(ws.slug).issues());
          } else {
            router.push(paths.root());
          }
        }}
        runtimeInstructions={<CliInstallInstructions />}
      />
    </div>
  );
```

**File:** apps/web/proxy.ts (L45-85)
```typescript
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession = req.cookies.has("multica_logged_in");
  const lastSlug = req.cookies.get("last_workspace_slug")?.value;

  // --- Legacy URL redirect: /issues/... → /{slug}/issues/... ---
  // Old bookmarks and clients that hit us before the slug migration would
  // otherwise 404 since the route moved under [workspaceSlug].
  const firstSegment = pathname.split("/")[1] ?? "";
  if (LEGACY_ROUTE_SEGMENTS.has(firstSegment)) {
    const url = req.nextUrl.clone();

    if (!hasSession) {
      url.pathname = "/login";
      return NextResponse.redirect(url);
    }

    if (lastSlug) {
      // Preserve deep-link path + query: /issues/abc → /{lastSlug}/issues/abc
      url.pathname = `/${lastSlug}${pathname}`;
      return NextResponse.redirect(url);
    }

    // Logged-in but no cookie yet (first login since slug migration, or
    // cookie cleared). Bounce to root; the root-path logic below picks a
    // workspace and writes the cookie, then future hits short-circuit here.
    url.pathname = "/";
    return NextResponse.redirect(url);
  }

  // --- Root path: redirect logged-in users to their last workspace ---
  if (pathname === "/" && hasSession && lastSlug) {
    const url = req.nextUrl.clone();
    url.pathname = `/${lastSlug}/issues`;
    return NextResponse.redirect(url);
  }

  // --- Default: forward locale header to RSC, no redirect/rewrite ---
  // Covers logged-out root path, /login, /:slug/*, and everything else.
  return nextWithLocale(req);
}
```

**File:** apps/web/app/[workspaceSlug]/(dashboard)/my-issues/page.tsx (L1-9)
```typescript
"use client";

import { MyIssuesPage } from "@multica/views/my-issues";

export default function Page() {
  return <MyIssuesPage />;
}


```

**File:** apps/web/app/[workspaceSlug]/(dashboard)/agents/[id]/page.tsx (L1-15)
```typescript
"use client";

import { use } from "react";
import { AgentDetailPage } from "@multica/views/agents";

export default function AgentDetailRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <AgentDetailPage agentId={id} />;
}


```

**File:** packages/views/navigation/types.ts (L1-29)
```typescript
export interface NavigationAdapter {
  push(path: string): void;
  replace(path: string): void;
  back(): void;
  pathname: string;
  searchParams: URLSearchParams;
  /**
   * Desktop only: open a path in a new tab. Optional `title` overrides the
   * default tab label. `opts.activate` controls focus:
   *   - `false` / omitted → background tab (browser cmd+click semantics; what
   *     modifier-click on links and mentions should use).
   *   - `true` → foreground tab (explicit "Open in new tab" toolbar buttons,
   *     where the user is asking to move into the new context).
   * Cross-workspace paths always switch workspace, regardless of `activate`.
   */
  openInNewTab?: (
    path: string,
    title?: string,
    opts?: { activate?: boolean },
  ) => void;
  /** Return a shareable URL for a path. Web: origin + path. Desktop: public web URL of the connected environment. */
  getShareableUrl: (path: string) => string;
  /**
   * Optional: warm up route assets / RSC payload for a path. Web wires this
   * to `router.prefetch`; desktop leaves it undefined because react-router
   * already loads the whole SPA. Callers must invoke via `prefetch?.(href)`.
   */
  prefetch?: (path: string) => void;
}
```

**File:** apps/desktop/src/renderer/src/routes.tsx (L92-108)
```typescript
/**
 * Route definitions shared by all tabs.
 *
 * Every tab path is workspace-scoped: `/{slug}/{route}/...`. Pre-workspace
 * flows (create workspace, accept invite) are NOT routes — they render as a
 * window-level overlay via `WindowOverlay`, dispatched by the navigation
 * adapter's transition-path interception. The `activeWorkspaceSlug` in the
 * tab store decides which workspace's tabs are visible in the TabBar;
 * workspace-less state (zero-workspace user) shows the overlay instead.
 *
 * The root index route stays as a harmless safety net. With per-workspace
 * tabs, nothing should construct a tab at `/` — but if one ever slips
 * through (malformed persisted state that dodges the migration, direct
 * router.navigate from unforeseen code), the index falls back to null
 * rather than 404; App.tsx's bootstrap repoints activeWorkspaceSlug on the
 * next render pass.
 */
```

**File:** apps/desktop/src/renderer/src/routes.tsx (L109-210)
```typescript
export const appRoutes: RouteObject[] = [
  {
    element: <PageShell />,
    children: [
      { index: true, element: null },
      {
        path: ":workspaceSlug",
        element: <WorkspaceRouteLayout />,
        children: [
          { index: true, element: <Navigate to="issues" replace /> },
          {
            path: "issues",
            element: (
              <ErrorBoundary>
                <IssuesPage />
              </ErrorBoundary>
            ),
            handle: { title: "Issues" },
          },
          {
            path: "issues/:id",
            element: <IssueDetailPage />,
            handle: { title: "Issue" },
          },
          {
            path: "projects",
            element: <ProjectsPage />,
            handle: { title: "Projects" },
          },
          {
            path: "projects/:id",
            element: <ProjectDetailPage />,
            handle: { title: "Project" },
          },
          {
            path: "autopilots",
            element: <AutopilotsPage />,
            handle: { title: "Autopilot" },
          },
          {
            path: "autopilots/:id",
            element: <AutopilotDetailPage />,
            handle: { title: "Autopilot" },
          },
          {
            path: "my-issues",
            element: <MyIssuesPage />,
            handle: { title: "My Issues" },
          },
          {
            path: "runtimes",
            element: <DesktopRuntimesPage />,
            handle: { title: "Runtimes" },
          },
          {
            path: "runtimes/:id",
            element: <RuntimeDetailPage />,
            handle: { title: "Runtime" },
          },
          { path: "skills", element: <SkillsPage />, handle: { title: "Skills" } },
          {
            path: "skills/:id",
            element: <SkillDetailPage />,
            handle: { title: "Skill" },
          },
          { path: "agents", element: <AgentsPage />, handle: { title: "Agents" } },
          {
            path: "agents/:id",
            element: <AgentDetailPage />,
            handle: { title: "Agent" },
          },
          {
            path: "members/:id",
            element: <MemberDetailPage />,
            handle: { title: "Member" },
          },
          { path: "squads", element: <SquadsPage />, handle: { title: "Squads" } },
          {
            path: "squads/:id",
            element: <SquadDetailPageView />,
            handle: { title: "Squad" },
          },
          { path: "inbox", element: <InboxPage />, handle: { title: "Inbox" } },
          {
            path: "attachments/:id/preview",
            element: <AttachmentPreviewRoute />,
            handle: { title: "Attachment" },
          },
          {
            path: "usage",
            element: <DashboardPage />,
            handle: { title: "Usage" },
          },
          {
            path: "settings",
            element: <DesktopSettingsRoute />,
            handle: { title: "Settings" },
          },
        ],
      },
    ],
  },
```

**File:** apps/mobile/app/(app)/[workspace]/_layout.tsx (L133-222)
```typescript
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="issue/[id]"
          options={{
            title: "Issue",
            headerBackTitle: "Back",
          }}
        />
        <Stack.Screen
          name="project/[id]"
          options={{
            title: "Project",
            headerBackTitle: "Back",
          }}
        />
        <Stack.Screen
          name="project/[id]/edit"
          options={{
            title: "Edit Project",
            presentation: "modal",
            headerLeft: () => <ModalCloseButton />,
          }}
        />
        <Stack.Screen
          name="issue/[id]/edit"
          options={{
            title: "Edit Issue",
            presentation: "modal",
            headerLeft: () => <ModalCloseButton />,
          }}
        />
        <Stack.Screen
          name="project/new"
          options={{
            title: "New Project",
            presentation: "modal",
            headerLeft: () => <ModalCloseButton />,
          }}
        />
        {/* Issue-detail formSheet pickers. All share the same sheet config:
            explicit numeric detents to dodge expo/expo#42904+#42965 (the
            `fitToContents` zero-size / padding bugs on iOS 26 + Expo 55),
            iOS native grabber, and contentStyle.height=100% as a safety
            net against the same zero-size class of bugs. */}
        <Stack.Screen
          name="issue/[id]/picker/status"
          options={SHEET_OPTIONS}
        />
        <Stack.Screen
          name="issue/[id]/picker/priority"
          options={SHEET_OPTIONS}
        />
        {/* Experiment: assignee uses iOS-native nav header + UISearchController
            instead of the body-rendered header pattern in SHEET_OPTIONS.
            Eliminates the #3634 overlap class of bugs and the focus-loss
            footgun of a custom TextInput inside ListHeaderComponent. The
            route file wires `headerSearchBarOptions` via setOptions. If this
            proves out, propagate to label / project / other search pickers
            and update CLAUDE.md Lesson 6 with a carve-out. */}
        <Stack.Screen
          name="issue/[id]/picker/assignee"
          options={{
            ...SHEET_OPTIONS,
            headerShown: true,
            title: "Assignee",
          }}
        />
        <Stack.Screen
          name="issue/[id]/picker/label"
          options={SHEET_OPTIONS}
        />
        <Stack.Screen
          name="mention-picker"
          options={{
            ...SHEET_OPTIONS,
            headerShown: true,
            title: "Mention",
          }}
        />
        <Stack.Screen
          name="issue/[id]/picker/project"
          options={SHEET_OPTIONS}
        />
        <Stack.Screen
          name="issue/[id]/picker/due-date"
          options={SHEET_OPTIONS}
        />
        <Stack.Screen name="issue/[id]/runs" options={SHEET_OPTIONS} />
        {/* Full emoji picker for a comment reaction. Pushed from the "+"
```

**File:** apps/mobile/app/(app)/[workspace]/switch-workspace.tsx (L1-38)
```typescript
/**
 * Workspace switcher — presented as a formSheet by the parent Stack.
 *
 * Reached from the More popover's WorkspaceCard (collapsed single-row entry).
 * Lists every workspace the user belongs to, current one disabled with a
 * checkmark. Tapping a non-current row triggers an iOS-native `Alert.alert`
 * confirm — only after the user confirms do we dismiss the sheet and
 * `router.replace` to the target slug.
 *
 * Why a confirm step:
 *   The previous flow ("popover → tap row → instant switch") had no friction
 *   against fat-finger taps in the cramped popover, and the user lost their
 *   entire navigation context (tabs, scroll position) with one accidental
 *   tap. iOS Alert is the platform-correct gate (mobile/CLAUDE.md Principle
 *   3 — iOS native > RNR > discuss).
 *
 * Switching itself stays minimal: `router.dismiss()` to close this sheet,
 * then `router.replace(/${slug}/inbox)`. The downstream WorkspaceRouteLayout
 * handles `setCurrentWorkspace(slug, uuid)` on mount.
 */
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  View,
} from "react-native";
import { Image as ExpoImage } from "expo-image";
import { router } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import type { Workspace } from "@multica/core/types";
import { Text } from "@/components/ui/text";
import { workspaceListOptions } from "@/data/queries/workspaces";
import { useWorkspaceStore } from "@/data/workspace-store";
import { useColorScheme } from "@/lib/use-color-scheme";
import { THEME } from "@/lib/theme";
import { cn } from "@/lib/utils";

```
