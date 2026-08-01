前端通过 Markdown 渲染器支持富文本展示，Web 和 Mobile 端采用不同的渲染策略。 [1](#8-0) [2](#8-1) 

---

## Web 端富文本渲染

### 核心组件
Web 端使用 `packages/ui/markdown/Markdown.tsx` 组件，基于 `react-markdown` [1](#8-0) 。

### 渲染插件链
```typescript
remarkPlugins={[remarkMath, remarkBreaks, [remarkGfm, { singleTilde: false }]]}
rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeKatex]}
```

- **remarkGFM** - GitHub Flavored Markdown（表格、任务列表、删除线） [3](#8-2) 
- **remarkBreaks** - 单换行符转换为 `<br>` [4](#8-3) 
- **remarkMath + rehypeKatex** - LaTeX 数学公式渲染 [5](#8-4) 
- **rehypeRaw** - 原始 HTML 透传（用于文件卡片等自定义组件） [6](#8-5) 
- **rehypeSanitize** - HTML 安全清理 [7](#8-6) 

### 代码高亮
使用 Shiki 进行语法高亮，支持双主题（light/dark） [8](#8-7) 。

### 三种渲染模式
- **terminal** - 最小格式化，用于调试输出
- **minimal** - 干净渲染，用于聊天消息
- **full** - 完整富文本，用于文档 [9](#8-8) 

### 自定义组件
- **Mention** - `@member` / `@agent` / `#issue` 提及渲染
- **FileCard** - 文件附件卡片
- **Image** - 图片渲染（支持 lightbox） [10](#8-9) 

## Mobile 端富文本渲染

### 混合渲染架构
Mobile 端使用分段混合渲染器，根据内容类型分发到不同渲染路径 [2](#8-1) 。

### 分段策略
```
content
  ↓ preprocessMobileMarkdown
  ↓ splitMarkdown (marked.lexer)
  ↓ render per-segment
     prose  → EnrichedMarkdownText (native md4c)
     code   → CodeBlock (Shiki)
     image  → MarkdownImage (expo-image)
```

### 渲染路径
- **Prose**（段落、列表、引用、表格）→ `react-native-enriched-markdown`（原生 md4c → NSAttributedString） [11](#8-10) 
- **Code blocks** → 自定义 `CodeBlock`，使用 `react-native-shiki-engine` 进行语法高亮 [12](#8-11) 
- **Images** → 自定义 `MarkdownImage`，使用 `expo-image` + tap-to-lightbox [13](#8-12) 

### 为什么使用混合渲染
`react-native-enriched-markdown` 不支持自定义 React 组件注入（设计限制），无法实现语法高亮和图片 lightbox [14](#8-13) 。混合渲染在保持原生性能的同时，为代码块和图片提供自定义渲染。

## 编辑器富文本输入

### Tiptap 编辑器
Web 端使用 Tiptap 作为富文本编辑器，支持：
- Mention 扩展（@提及） [15](#8-14) 
- 表格扩展 [16](#8-15) 
- 图片扩展 [17](#8-16) 
- 链接扩展 [18](#8-17) 
- Markdown 导入/导出 [19](#8-18) 

### 只读渲染
编辑器内容通过 `ReadonlyContent` 组件渲染，使用与 Markdown 相同的渲染管道 [20](#8-19) 。

## 关键差异对比

| 特性 | Web 端 | Mobile 端 |
|------|--------|-----------|
| 渲染引擎 | `react-markdown` | `react-native-enriched-markdown` + 自定义组件 |
| 代码高亮 | Shiki (Web) | Shiki (react-native-shiki-engine) |
| 数学公式 | KaTeX | 不支持（V3+） |
| 表格 | GFM 表格 | 简化垂直布局（V2.3+） |
| 图片 | HTML `<img>` | `expo-image` + lightbox |
| 提及渲染 | 自定义 React 组件 | 链接样式（brand-colored） |

## Notes

Web 和 Mobile 端虽然使用不同的渲染引擎，但都支持相同的 Markdown 语法集（除数学公式和 Mermaid 图表外）。Mobile 端的混合渲染架构是为了在 React Native 平台限制下实现 Web 端的富文本功能，特别是代码高亮和图片 lightbox [21](#8-20) 。

Wiki pages you might want to explore:
- [Chat Sessions with Agents (multica-ai/multica)](/wiki/multica-ai/multica#5.5)

Wiki pages you might want to explore:
- [Overview (multica-ai/multica)](/wiki/multica-ai/multica#1)

### Citations

**File:** packages/ui/markdown/Markdown.tsx (L1-30)
```typescript
import * as React from 'react'
import ReactMarkdown, { type Components, defaultUrlTransform } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { FileText, Download } from 'lucide-react'
import { cn } from '@multica/ui/lib/utils'
import { CodeBlock, CODE_LIGATURE_CLASS, InlineCode } from './CodeBlock'
import { isAllowedFileCardHref, preprocessFileCards } from './file-cards'
import { preprocessLinks } from './linkify'
import { preprocessMentionShortcodes } from './mentions'
import 'katex/dist/katex.min.css'
import './markdown.css'

/**
 * Render modes for markdown content:
 *
 * - 'terminal': Raw output with minimal formatting, control chars visible
 *   Best for: Debug output, raw logs, when you want to see exactly what's there
 *
 * - 'minimal': Clean rendering with syntax highlighting but no extra chrome
 *   Best for: Chat messages, inline content, when you want readability without clutter
 *
 * - 'full': Rich rendering with beautiful tables, styled code blocks, proper typography
 *   Best for: Documentation, long-form content, when presentation matters
 */
export type RenderMode = 'terminal' | 'minimal' | 'full'
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

**File:** packages/views/package.json (L65-67)
```json
    "@tiptap/extension-image": "^3.22.1",
    "@tiptap/extension-link": "^3.22.1",
    "@tiptap/extension-list": "^3.22.1",
```

**File:** packages/views/package.json (L68-69)
```json
    "@tiptap/extension-mention": "^3.22.1",
    "@tiptap/extension-paragraph": "^3.22.1",
```

**File:** packages/views/package.json (L71-75)
```json
    "@tiptap/extension-table": "^3.22.1",
    "@tiptap/extension-table-cell": "^3.22.1",
    "@tiptap/extension-table-header": "^3.22.1",
    "@tiptap/extension-table-row": "^3.22.1",
    "@tiptap/extension-text": "^3.22.1",
```

**File:** packages/views/package.json (L77-78)
```json
    "@tiptap/markdown": "^3.22.1",
    "@tiptap/pm": "^3.22.1",
```

**File:** packages/views/package.json (L93-97)
```json
    "rehype-katex": "catalog:",
    "rehype-raw": "^7.0.0",
    "remark-breaks": "^4.0.0",
    "remark-gfm": "^4.0.1",
    "remark-math": "catalog:",
```

**File:** packages/views/package.json (L98-99)
```json
    "rehype-sanitize": "^6.0.0",
    "sonner": "^2.0.7"
```

**File:** packages/ui/markdown/CodeBlock.tsx (L54-67)
```typescript
 * CodeBlock - Syntax highlighted code block using Shiki
 *
 * Uses Shiki dual themes with CSS variables for light/dark switching.
 * No JS-based dark mode detection needed — theme switching is handled
 * entirely via CSS (see globals.css for .shiki/.dark .shiki rules).
 *
 * @see https://shiki.style/guide/dual-themes
 */
export function CodeBlock({
  code,
  language = 'text',
  className,
  mode = 'full'
}: CodeBlockProps): React.JSX.Element {
```

**File:** packages/views/common/markdown.tsx (L30-38)
```typescript
/**
 * Default renderMention that delegates to IssueMentionCard for issue mentions
 * and renders a styled span for other mention types.
 */
function defaultRenderMention({
  type,
  id,
}: {
  type: string;
```

**File:** apps/mobile/docs/markdown-rendering-adr.md (L1-260)
```markdown
# ADR — Markdown rendering on `apps/mobile/`

**Status**: Accepted
**Date**: 2026-05-19
**Supersedes**: nothing (formalises what `markdown-renderer-research.md` was
already documenting in research form)

This is the durable architecture-decision record for how the mobile app
renders markdown. `markdown-renderer-research.md` continues to hold the
detailed history and incident log; this file is the **one-page answer**
to "what are we using and why" with A-tier sources.

---

## Context — what the RN ecosystem actually offers (2026-05)

There are exactly three rendering paths available for markdown in React
Native today. Each has hard, library-independent constraints rooted in
the RN platform itself:

| Path | How it renders | Strengths | Hard limits |
|---|---|---|---|
| **A — Native** | md4c parses → iOS `NSAttributedString` / Android Spannable | Fastest, doesn't touch RN's nested-`<Text>` layout path | Cannot inject custom React for any leaf node (`enriched-markdown` issue [#54](https://github.com/software-mansion-labs/react-native-enriched-markdown/issues/54), [#232](https://github.com/software-mansion-labs/react-native-enriched-markdown/issues/232), maintainer: "no custom renderers, by design") |
| **B — React tree** | Parse to AST → walk → render every token as nested `<Text>` / `<View>` | Full custom React rendering for every node | Triggers RN's 10-year-old nested-`<Text>` bugs: [#10775](https://github.com/facebook/react-native/issues/10775), [#45925](https://github.com/facebook/react-native/issues/45925), [#6728](https://github.com/facebook/react-native/issues/6728) — `borderWidth` / `padding` / `margin` are not `NSAttributedString` attributes and either silently drop or force-break inline runs. CJK paragraphs amplify the symptom via UAX #14 / Kinsoku. |
| **C — WebView** | Web markdown lib (e.g. `react-markdown`) inside `react-native-webview` / Expo DOM Components | Identical to web output | Slower startup (no Hermes bytecode), async JSON-only bridge, native UI cannot embed inside the WebView, scroll & keyboard UX divergent. Expo's own docs acknowledge these are public trade-offs ([dom-components.mdx](https://docs.expo.dev/guides/dom-components/)) |

**Fact**: as of 2026-05, **no single library satisfies path A + path B
simultaneously** — i.e. native rendering performance AND custom React
component for arbitrary leaf nodes. This is an ecosystem-level constraint,
not a Multica problem.

### Concrete library survey (2026-05)

| Library | Path | Last release | Verdict for Multica |
|---|---|---|---|
| [`react-native-enriched-markdown`](https://github.com/software-mansion-labs/react-native-enriched-markdown) | A | v0.5.0 (Apr 2026) | **Selected for prose.** Expo officially recommends it in [Edit rich text](https://docs.expo.dev/guides/editing-richtext/) — A-tier endorsement. Software Mansion (same team as Reanimated / Gesture Handler) |
| [`react-native-streamdown`](https://github.com/software-mansion-labs/react-native-streamdown) | A + worklets | active 2026 | Not adopted. Built on enriched-markdown, optimised for AI streaming. Web/desktop don't use a streaming-specific renderer either, mobile streaming isn't currently a top product pain |
| [`react-native-marked`](https://github.com/gmsgowtham/react-native-marked) | B | v8.1.0 (2026-05-14) | Not adopted. v7 removed `CustomToken`, v8 added "React component embedding" but no token-level customisation. Pure `<Text>` tree → would trigger nested-text bugs |
| [`amilmohd155/react-native-markdown`](https://github.com/amilmohd155/react-native-markdown) | B | v0.8.5 (Jan 2026) | Not adopted. Same nested-`<Text>` constraint as `react-native-marked`. 14 ⭐, single maintainer, not production-validated |
| [`react-native-markdown-display`](https://www.npmjs.com/package/react-native-markdown-display) | B | ~2 years stale | Maintainer publicly recommends migrating away |
| Expo DOM Components (web `react-markdown` inside WebView) | C | Expo SDK 53+ stable | Not adopted as primary. Reserved as escape hatch for future LaTeX / Mermaid / very wide tables |
| [`vercel/streamdown`](https://github.com/vercel/streamdown) | n/a | active 2026 | Not applicable — name collides with SM's RN library but Vercel's `streamdown` is **web-only** (Next.js, AI SDK). Documented here only to dispel confusion |

Closed-source production references like Stream Chat's [`StreamingMessageView`](https://getstream.io/blog/react-native-assistant/) and [assistant-ui](https://www.assistant-ui.com/blog/2026-03-launch-week) do not publish their RN markdown implementation. There is **no public industry standard**.

---

## Decision

Multica mobile uses a **segment-based hybrid renderer** that dispatches
each markdown token type to the renderer that doesn't trip on that
token's specific platform trap.

```
content (string)
  ↓ preprocessMobileMarkdown
     legacy mention shortcode  →  [@name](mention://type/id)
     legacy file-card lines    →  [📎 name](url)
     HTML <br>                 →  CommonMark "  \n" hard break
  ↓ splitMarkdown                 (marked@18 lexer; we use the AST only)
     code fence          → { type:'code',  lang, code }
     paragraph w/ image  → image promoted to block, text rejoins prose
     everything else     → { type:'prose', content: token.raw }
  ↓ render per-segment
     prose  → <EnrichedMarkdownText>   path A
     code   → <CodeBlock>              path B (controlled — no CJK mixing)
     image  → <MarkdownImage>          path B (controlled — single element)
```

Each per-segment routing decision avoids the failure mode of the path it
chose:

| Segment | Routing | Trap avoided |
|---|---|---|
| Prose (paragraphs, headings, lists, quotes, tables, inline code, links, strong/em) | enriched-markdown (path A) | Would otherwise need React tree → CJK + inline-code chip = 5-7 line breakage per chip (the 2026-05-09 incident) |
| Fenced code block | own `CodeBlock` with one `<Text>` per line, token spans nested but **content is code only — no CJK paragraphs to trigger UAX #14**. Shiki for highlighting | Native rendering can't expose Shiki tokens; React tree of code-only doesn't trigger the CJK amplification of the nested-text bug |
| Image | `expo-image` wrapped in `Pressable` for lightbox dispatch. **One element, no nested-text mixing** | RN `<Image>` can't be inline in `<Text>`; lightbox needs `Pressable` not addressable inside attributed string |
| (future) LaTeX / Mermaid | not yet — when needed, separate component running Expo DOM Components | path C is the only one that gets these for free, but the WebView penalty isn't worth paying for prose |

### Marked@18 is used as a **lexer only**

`marked.lexer(input)` produces a token list. We never feed `marked`'s
HTML output to anything. `marked` is a 10-year-old, A-tier-maintained
CommonMark/GFM lexer ([marked.js docs](https://marked.js.org/)), and
running it as a pure JS function on every markdown body is cheap.

This is necessary because enriched-markdown's internal md4c AST is not
exposed — we'd have no way to find segment boundaries otherwise.

### Theming

Colors flow from the RNR design system:

- `global.css` defines CSS variables under `:root` (light) and
  `.dark:root` (dark)
- `lib/theme.ts` mirrors these as pre-resolved `hsl(...)` strings
  (CSS variable syntax doesn't work in RN imperative style objects)
- `lib/use-color-scheme.ts` is the single source of truth for the
  current scheme, persisted in `expo-secure-store`

For prose (path A, must use imperative style object — enriched is native
md4c, no className support), `useMarkdownStyle()` derives the full style
object from `THEME[scheme]`. For non-prose (paths B controlled), all
container styling uses NativeWind className like the rest of RNR.

### enriched-markdown's hidden-default trap (documented for posterity)

enriched-markdown's `normalizeMarkdownStyle.js` carries a frozen table of
~30 hardcoded **light-mode** color defaults. Fields not explicitly
overridden in `useMarkdownStyle()` use those hardcoded values and
disappear (or render garishly) in dark mode. Every color field must be
explicitly mapped to a `THEME[scheme]` token. **When upgrading
enriched-markdown (v0.6+), re-audit `normalizeMarkdownStyle.js` for
newly-added color fields** — they will also ship light-mode defaults.

---

## Consequences

### What we get

- Native attributed-string performance for the 95% case (prose)
- Web-parity syntax highlighting (Shiki, same themes as web)
- Image lightbox with native `expo-image` caching
- Full GFM support via enriched-markdown's `flavor="github"`
- Light / dark mode that follows `lib/use-color-scheme`
- Expo's own A-tier recommendation as our prose engine

### What we pay

- Three rendering paths to maintain instead of one
- Theme integration: every enriched color field must be explicitly mapped;
  hidden-default trap re-emerges on every enriched upgrade
- Code blocks nested in a list item stay with the enriched prose stream
  (don't get Shiki) — top-level code is the >95% case, acceptable
- LaTeX / Mermaid not currently supported

### Known limitations and mitigations

**Inline code chip top-heavy padding** — visible as `~13pt empty space
above` vs `~3pt below` glyphs in chips inside CJK paragraphs (seen in
#MUL-2397 and #MUL-2395 dark screenshots, 2026-05-19).

- **Root cause**: enriched-markdown applies hardcoded internal padding
  to inline code that cannot be turned off via `markdownStyle.code`. The
  `CodeStyle` schema does not expose `padding*` / `baselineOffset` /
  `lineHeight` knobs.
- **Not an RN/iOS platform issue**: Discord, Slack, Telegram, Mattermost
  mobile all render inline code with background + monospace and **do
  not** show this asymmetry — confirming the artifact is library-specific.
- **Upstream tracking**: [`software-mansion-labs/react-native-enriched-markdown#255`](https://github.com/software-mansion-labs/react-native-enriched-markdown/issues/255)
  (filed 2026-04-20 by `@xindixu`, maintainer unresponsive as of 2026-05-19).
- **Failed mitigation (reverted)**: reducing `MD_LINE.body` from 24 to
  20 shrinks absolute padding but does not change the asymmetry ratio —
  net negative (cost CJK leading, didn't fix the chip). See
  `markdown-renderer-research.md` decision log 2026-05-19.

**Mitigation applied (2026-05-19)** — inline code rendered WITHOUT a
background:

```ts
code: {
  color: t.brand,
  backgroundColor: "transparent",
  borderColor: "transparent",
  fontFamily: MONO_FONT,  // Menlo on iOS, monospace on Android
},
```

- `backgroundColor: "transparent"` — enriched still paints the padding
  rectangle internally, but it's invisible, so the top-heavy artifact
  disappears. Glyph baselines are unaffected (baseline is a font-metric
  property, not a background-painting property).
- `fontFamily: MONO_FONT` — enriched's native default for `code` is `''`
  (inherit from paragraph), so without this override mobile inline code
  would lose its only visual identity once the chip is removed.
- `color: t.brand` — secondary identification tint, distinguishes inline
  code from regular prose alongside the monospace.
- **Visual trade-off**: mobile no longer matches web/desktop chip style.
  Inline code on mobile reads as "tinted monospace span". Acceptable
  given that the alternative is the top-heavy chip artifact.
- **Revisit when**: upstream issue #255 ships a padding control. At
  that point switch back to a tinted-background chip for cross-platform
  parity.

**Why we did NOT** fork the library or rewrite the prose layer to a
React-tree renderer:

- Forking enriched-markdown means maintaining a native-code (ObjC/Swift
  + Kotlin) patch indefinitely; the ROI for one styling fix is poor.
- Rewriting the prose layer to a React-tree renderer (e.g.
  `react-native-marked`) would re-introduce the RN nested-`<Text>`
  platform bugs documented above — same root cause as the 2026-05-09
  inline-code CJK line-breakage incident.

### What's explicitly out of scope

- **Replacing the whole stack with a single library**: every alternative
  surveyed above either drops path A (perf) or drops custom React (lightbox /
  syntax highlight). No path forward there until the ecosystem ships a
  library that satisfies both.
- **Migrating chat to streamdown**: web/desktop have no streaming-specific
  renderer either; mobile parity demands the same. Reconsider only if
  AI-chat streaming becomes a top user complaint.

---

## When to revisit this ADR

- enriched-markdown ships custom React leaf-node rendering (currently
  not on roadmap — roadmap addresses `EnrichedMarkdownTextInput`, the
  *editor*, not the *renderer*)
- A new library appears that satisfies path A + path B simultaneously
- Expo SDK ships a first-party markdown renderer (currently doesn't)
- The product team commits to LaTeX / Mermaid as core features — Expo
  DOM Components becomes the right answer for that surface

---

## Sources (A-tier only)

### Official documentation

- [Expo — Edit rich text guide](https://docs.expo.dev/guides/editing-richtext/) — directly recommends `react-native-enriched-markdown`
- [Expo — Using React DOM in Expo native apps](https://docs.expo.dev/guides/dom-components/) — DOM Components trade-offs (path C)

### Library sources (maintainer-authoritative)

- [`software-mansion-labs/react-native-enriched-markdown`](https://github.com/software-mansion-labs/react-native-enriched-markdown) — path A primary
- [`software-mansion-labs/react-native-streamdown`](https://github.com/software-mansion-labs/react-native-streamdown) — surveyed, not adopted
- [`gmsgowtham/react-native-marked`](https://github.com/gmsgowtham/react-native-marked) — path B surveyed
- [`amilmohd155/react-native-markdown`](https://github.com/amilmohd155/react-native-markdown) — path B surveyed
- [`vercel/streamdown`](https://github.com/vercel/streamdown) — web only, documented to dispel naming collision
- [marked.js documentation](https://marked.js.org/) — lexer we use
- [Shiki](https://shiki.style/) + [`react-native-shiki-engine`](https://www.npmjs.com/package/react-native-shiki-engine) — code highlighting
- [`expo-image`](https://docs.expo.dev/versions/latest/sdk/image/) + [`jobtoday/react-native-image-viewing`](https://github.com/jobtoday/react-native-image-viewing) — image rendering
- [md4c](https://github.com/mity/md4c) — the C library that backs enriched-markdown on native

### Platform constraint sources (the "why we can't just use path B everywhere")

- [`facebook/react-native#10775`](https://github.com/facebook/react-native/issues/10775) — nested-`<Text>` border ignored (Nov 2016, locked, no fix)
- [`facebook/react-native#45925`](https://github.com/facebook/react-native/issues/45925) — same bug re-filed, still open under New Architecture
- [`facebook/react-native#6728`](https://github.com/facebook/react-native/issues/6728) — `margin` / `padding` ignored on nested `<Text>`
- [`react-native-community/discussions-and-proposals#695`](https://github.com/react-native-community/discussions-and-proposals/issues/695) — official statement on inline-text styling limits

### Reference implementations (same-pattern peers)

- [Mattermost mobile — `app/components/markdown/`](https://github.com/mattermost/mattermost-mobile/tree/main/app/components/markdown) — same segment-dispatch pattern, different engines
- Stream Chat [`StreamingMessageView`](https://getstream.io/blog/react-native-assistant/) — closed-source, recorded only as evidence that "no public standard exists"
- [assistant-ui multi-platform launch](https://www.assistant-ui.com/blog/2026-03-launch-week) — closed-source

### In-repo cross-references

- `apps/mobile/lib/markdown/markdown.tsx` — entry point
- `apps/mobile/lib/markdown/split-markdown.ts` — segment splitter
- `apps/mobile/lib/markdown/markdown-style.ts` — `useMarkdownStyle()` theme bridge
- `apps/mobile/lib/markdown/code-block.tsx` — Shiki-powered code segment
- `apps/mobile/lib/markdown/markdown-image.tsx` — lightbox-aware image segment
- `apps/mobile/docs/markdown-renderer-research.md` — full incident log and historical context
- `apps/mobile/CLAUDE.md` — mobile-wide rules including theme/CSS-variable system
```

**File:** apps/mobile/lib/markdown/code-block.tsx (L1-53)
```typescript
/**
 * Fenced code block. Three pieces stacked:
 *
 *   ┌───────────────────────────────┐
 *   │ TS                       ⎘    │  ← header: lang label + copy button
 *   ├───────────────────────────────┤
 *   │ const x = 1;                  │  ← code, horizontal-scroll, selectable
 *   └───────────────────────────────┘
 *
 * Two render paths:
 *
 *   1. Known language + Shiki ready: token runs from `codeToTokensBase`
 *      rendered as nested `<Text>` children, each carrying its theme color
 *      via inline `style.color`. Per-line wrapping is preserved by giving
 *      each line its own outer `<Text>`.
 *
 *   2. Unknown language, engine unavailable, or first frame before init
 *      finishes: plain `<Text>` of the raw source. Visually identical to
 *      pre-Shiki behavior.
 *
 * Theme tracks `useColorScheme()` so the palette flips with system dark
 * mode without a remount.
 *
 * Copy button is PERSISTENTLY visible (no hover on touch). Tap copies the
 * raw code to the system clipboard, plays a light haptic, and flips to a
 * check mark for 2s — iOS does not surface a system notice on clipboard
 * write, so we own the feedback.
 */
import { useEffect, useRef, useState } from "react";
import {
  Pressable,
  ScrollView,
  View,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import * as Haptics from "expo-haptics";
import Svg, { Path, Rect } from "react-native-svg";
import { Text } from "@/components/ui/text";
import { THEME } from "@/lib/theme";
import { useColorScheme } from "@/lib/use-color-scheme";
import {
  CODE_BLOCK_CONTAINER_CLASS,
  CODE_BLOCK_LANG_LABEL_CLASS,
  CODE_BLOCK_TEXT_CLASS,
} from "./tokens";
import {
  highlight,
  resolveLang,
  SHIKI_THEME_DARK,
  SHIKI_THEME_LIGHT,
  type HighlightedLine,
} from "./shiki";

```

**File:** packages/views/editor/readonly-content.tsx (L170-344)
```typescript
function buildComponents(): Partial<Components> {
  return {
    // Links — route mention:// to mention components, others show preview card
    a: ReadonlyLink,

    // Images — unified through <Attachment>. The resolver context provided
    // by AttachmentDownloadProvider (mounted in ReadonlyContent below) turns
    // a CDN URL into a full record when possible; external URLs render as
    // plain images with lightbox-via-preview-modal. forceKind is mandatory
    // here because markdown `![]()` carries no content-type and alt is
    // commonly empty or descriptive — without it images fall through to
    // the file-card chrome.
    img: ({ src, alt }) => (
      <AttachmentRenderer
        attachment={{
          kind: "url",
          url: typeof src === "string" ? src : "",
          filename: alt ?? "",
          forceKind: "image",
        }}
      />
    ),

    // FileCard — intercept <div data-type="fileCard"> from preprocessMarkdown
    div: ({ node, children, ...props }) => {
      const dataType = node?.properties?.dataType as string | undefined;
      if (dataType === "fileCard") {
        const rawHref = (node?.properties?.dataHref as string) || "";
        const href = isAllowedFileCardHref(rawHref) ? rawHref : "";
        const filename = (node?.properties?.dataFilename as string) || "";
        return (
          <AttachmentRenderer
            attachment={{ kind: "url", url: href, filename }}
          />
        );
      }
      return <div {...props}>{children}</div>;
    },

    // Tables — wrap in tableWrapper div for border/radius/scroll (matches Tiptap)
    table: ({ children }) => (
      <div className="tableWrapper">
        <table>{children}</table>
      </div>
    ),

    // Code — lowlight highlighting for blocks, plain render for inline
    code: ({ className, children, node, ...props }) => {
      const lang = /language-(\w+)/.exec(className || "")?.[1];
      const isBlock =
        node?.position &&
        node.position.start.line !== node.position.end.line;

      if (isBlock && lang === "mermaid") {
        return <MermaidDiagram chart={String(children).replace(/\n$/, "")} />;
      }
      if (isBlock && lang === "html") {
        // Like Mermaid, return the React element directly here and rely on
        // the `pre` renderer below to unwrap it — react-markdown otherwise
        // wraps `code` children in a `<pre>` whose monospace + overflow
        // styles would clamp the preview iframe.
        return <HtmlBlockPreview html={String(children).replace(/\n$/, "")} />;
      }

      if (!isBlock && !lang) {
        // Inline code — CSS handles styling via .rich-text-editor code
        return <code {...props}>{children}</code>;
      }

      // Block code — highlight with lowlight, output hljs classes
      const code = String(children).replace(/\n$/, "");
      try {
        const tree = lang
          ? lowlight.highlight(lang, code)
          : lowlight.highlightAuto(code);
        const html = toHtml(tree);
        if (html) {
          return (
            <code
              className={cn("hljs", lang && `language-${lang}`)}
              dangerouslySetInnerHTML={{ __html: html }}
            />
          );
        }
      } catch {
        // fall through to plain render
      }
      return (
        <code className={cn("hljs", className)} {...props}>
          {children}
        </code>
      );
    },

    // Pre — pass through (CSS handles styling via .rich-text-editor pre).
    // Special-case Mermaid / HtmlBlockPreview returned from the `code`
    // renderer above so the outer `<pre>` does not wrap them — this is the
    // standard two-layer pattern used to escape react-markdown's default
    // `<pre><code>` envelope.
    pre: ({ children }) => {
      // react-markdown calls `pre` BEFORE invoking the `code` renderer —
      // `children` is the unrendered `<code>` element from the AST. So we
      // identify "this block was meant to be unwrapped" by inspecting the
      // child's className (`language-mermaid`, `language-html`), not by
      // checking `children.type === MermaidDiagram`, which never matches.
      //
      // Match by exact class token: a substring `includes("language-html")`
      // would also fire on neighboring languages like `language-htmlbars`
      // and silently strip their <pre> wrapper.
      if (isValidElement(children)) {
        const childProps = children.props as { className?: string };
        if (PRE_UNWRAP_RE.test(childProps.className ?? "")) {
          return <>{children}</>;
        }
      }
      return <pre>{children}</pre>;
    },
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ReadonlyContentProps {
  content: string;
  className?: string;
  /**
   * Attachments associated with the surrounding entity (comment / issue
   * body). When the markdown contains an inline `<img>` or file card whose
   * URL matches one of these attachments, the download button re-signs the
   * URL at click time via `useDownloadAttachment` instead of opening the
   * potentially stale link embedded in the markdown.
   *
   * Callers SHOULD pass a stable reference (e.g. the field on a memoized
   * timeline entry); a fresh array on every parent render busts the memo.
   */
  attachments?: Attachment[];
}

// Memoized so a long timeline of comments (Inbox + IssueDetail) does not
// re-run the full react-markdown + rehype-* + lowlight pipeline on every
// parent re-render. Props are `content`/`className`/`attachments`, all
// shallow-comparable; stability is the caller's responsibility for the
// array.
export const ReadonlyContent = memo(function ReadonlyContent({
  content,
  className,
  attachments,
}: ReadonlyContentProps) {
  const processed = useMemo(() => preprocessMarkdown(content), [content]);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const hover = useLinkHover(wrapperRef);

  // Components map is now static — all attachment-aware logic lives in
  // <Attachment>, which reads the surrounding AttachmentDownloadProvider.
  const components = useMemo(() => buildComponents(), []);

  return (
    <AttachmentDownloadProvider attachments={attachments}>
      <div ref={wrapperRef} className={cn("rich-text-editor readonly text-sm", className)}>
        <ReactMarkdown
          remarkPlugins={[remarkMath, remarkBreaks, [remarkGfm, { singleTilde: false }]]}
          rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeKatex]}
          urlTransform={urlTransform}
          components={components}
        >
          {processed}
        </ReactMarkdown>
        <LinkHoverCard {...hover} />
      </div>
    </AttachmentDownloadProvider>
  );
});

```
