前端通过 WebSocket 实时接收流式内容，并使用不同的 Markdown 渲染器处理 Web 和 Mobile 端的显示。 [1](#4-0) [2](#4-1) 

---

## 流式输出机制

### Web 端流式接收
前端使用 TanStack Query 的 `useQuery` 配合 `taskMessagesOptions` 获取实时任务消息 [1](#4-0) 。WebSocket 事件通过 `useRealtimeSync` 实时更新缓存，触发重新渲染。

```typescript
const { data: liveTaskMessages } = useQuery({
  ...taskMessagesOptions(pendingTaskId ?? ""),
  enabled: canFetchLiveTimeline,
});
const liveTimeline: ChatTimelineItem[] = (liveTaskMessages ?? []).map(toTimelineItem);
```

### 时间线渲染
`TimelineView` 组件接收流式内容，使用 `splitTimeline` 将内容分为三部分：preface（前置文本）、middle（思考/工具调用）、final（最终回复） [3](#4-2) 。流式时默认展开 middle 部分。

## Markdown 渲染

### Web 端渲染
Web 端使用 `packages/views/common/markdown.tsx` 的 `Markdown` 组件，基于 `react-markdown` [2](#4-1) 。

**特性**：
- 支持语法高亮（Shiki）
- GFM 支持（表格、任务列表、删除线）
- 自定义组件渲染（mention、file-card、image）
- 三种渲染模式：terminal、minimal、full

**预处理**：
```typescript
const processedContent = React.useMemo(
  () => {
    let result = preprocessMentionShortcodes(children)
    result = preprocessLinks(result)
    result = preprocessFileCards(result, cdnDomain ?? '')
    return result
  },
  [children, cdnDomain]
)
```

### Mobile 端渲染
Mobile 端使用混合渲染器 `apps/mobile/lib/markdown/markdown.tsx` [4](#4-3) 。

**分段策略**：
- **Prose**（段落、列表、引用等）→ `EnrichedMarkdownText`（原生 md4c 渲染）
- **Code blocks** → `CodeBlock`（Shiki 语法高亮）
- **Images** → `MarkdownImage`（expo-image + lightbox）

**分段逻辑**：
```typescript
// splitMarkdown 使用 marked.lexer 分割内容
const segments = splitMarkdown(preprocessMobileMarkdown(content))
```

## 数据流

```
Claude CLI stdout (NDJSON)
  ↓
后端 handleAssistant 解析
  ↓
WebSocket 实时推送 (task:message 事件)
  ↓
前端 useRealtimeSync 更新 taskMessages 缓存
  ↓
ChatTimelineItem 转换
  ↓
TimelineView 分割内容
  ↓
Markdown 组件渲染（Web: react-markdown, Mobile: hybrid）
```

## 关键差异

| 特性 | Web 端 | Mobile 端 |
|------|--------|-----------|
| 渲染引擎 | `react-markdown` | `react-native-enriched-markdown` + 自定义组件 |
| 代码高亮 | Shiki (react-markdown 插件) | Shiki (独立 CodeBlock) |
| 图片渲染 | HTML `<img>` | `expo-image` + lightbox |
| 流式优化 | MemoizedMarkdown | FlashList + maintainVisibleContentPosition |

## Notes

Web 和 Mobile 端虽然使用不同的渲染引擎，但都支持相同的 Markdown 语法集。Mobile 端的混合渲染器是为了解决 React Native 的嵌套 `<Text>` 限制，同时保持原生性能。流式输出在两端都通过 WebSocket + Query Cache 实现，确保实时性。

Wiki pages you might want to explore:
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)
- [File Attachments and Storage (multica-ai/multica)](/wiki/multica-ai/multica#8.2)

Wiki pages you might want to explore:
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)
- [File Attachments and Storage (multica-ai/multica)](/wiki/multica-ai/multica#8.2)

### Citations

**File:** packages/views/chat/components/chat-message-list.tsx (L69-76)
```typescript
  const showLiveTimeline = !!pendingTaskId && !pendingAlreadyPersisted;
  const canFetchLiveTimeline = isTaskMessageTaskId(pendingTaskId) && !pendingAlreadyPersisted;
  const { data: liveTaskMessages } = useQuery({
    ...taskMessagesOptions(pendingTaskId ?? ""),
    enabled: canFetchLiveTimeline,
  });
  const liveTimeline: ChatTimelineItem[] = (liveTaskMessages ?? []).map(toTimelineItem);
  const hasLive = showLiveTimeline && liveTimeline.length > 0;
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

**File:** packages/views/common/markdown.tsx (L77-103)
```typescript
/**
 * App-level Markdown wrapper. Injects:
 *   - IssueMentionCard for issue mentions
 *   - cdnDomain from the config store (drives fileCard preprocessing)
 *   - unified <Attachment> as the image / file-card renderer
 *   - AttachmentDownloadProvider so url → record resolution works inside
 *     the injected <Attachment> components
 */
export function Markdown(props: MarkdownProps): React.JSX.Element {
  const cdnDomain = useConfigStore((s) => s.cdnDomain);
  const { attachments, ...rest } = props;
  return (
    <AttachmentDownloadProvider attachments={attachments}>
      <MarkdownBase
        renderMention={defaultRenderMention}
        renderImage={renderImage}
        renderFileCard={renderFileCard}
        cdnDomain={cdnDomain}
        {...rest}
      />
    </AttachmentDownloadProvider>
  );
}

export const MemoizedMarkdown = React.memo(Markdown);
MemoizedMarkdown.displayName = "MemoizedMarkdown";

```

**File:** apps/mobile/lib/markdown/markdown.tsx (L1-39)
```typescript
/**
 * Public Markdown component for the mobile app. Hybrid renderer:
 *
 *   - Prose (paragraphs, headings, lists, quotes, tables, inline code,
 *     links, mentions) → `EnrichedMarkdownText` (react-native-enriched-
 *     markdown, native md4c → NSAttributedString / Spannable). One
 *     instance per prose island.
 *   - Fenced code blocks → in-house `CodeBlock` with Shiki syntax
 *     highlighting, copy button, and horizontal scroll. Shares the
 *     `github-light` / `github-dark` themes with web for byte-identical
 *     palettes.
 *   - Images → in-house `MarkdownImage` with expo-image + auto aspect
 *     ratio + tap-to-lightbox dispatch.
 *
 * Why hybrid instead of pure enriched: enriched does not let us inject
 * React for any leaf node (issues #54, #232 — maintainer: "no custom
 * renderers, by design"), which would permanently lock out syntax
 * highlighting and tap-to-lightbox. The maintainer themselves
 * recommends this split in #246: "split them out and render with
 * another instance of enriched-markdown".
 *
 * Pipeline:
 *
 *   content
 *     ↓ preprocessMobileMarkdown    legacy mention shortcodes + file
 *                                   cards + HTML strip with `<br>` →
 *                                   "  \n" (canonical CommonMark hard
 *                                   break)
 *     ↓ splitMarkdown               marked.lexer → segments[]
 *     ↓ render per-segment          prose / code / image components
 *
 * Mention chip note: mobile renders `mention://` links via enriched's
 * default link styling (brand-colored, underlined), matching web's
 * fallback behavior when no `renderMention` is provided
 * (`packages/ui/markdown/Markdown.tsx:173-178`). The avatar pill
 * variant only ever existed on web in specific contexts that supplied
 * a custom renderer — mobile doesn't lose anything that exists by
 * default elsewhere.
 */
```
mermaid语法都不拿去给meraid渲染下 md语法为什么要放到doc里 还不如直接交一个md文件