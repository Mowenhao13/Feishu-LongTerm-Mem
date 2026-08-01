# Wiki 技术报告书补全 Spec

## Why

项目 docs/wiki 目录下已有 11 个 Markdown 文件，每个文件仅有英文子标题骨架，无实质内容。需要补全所有已创建文件的内容，转换为中文，并生成可渲染的 Mermaid 流程图，形成完整的技术报告书。

## What Changes

- 将所有 11 个现有 md 文件的子标题和内容改为中文
- 为每个标有 `[生成流程图]` 的位置编写符合 Mermaid 语法的图表
- 遵循 DeepWiki 风格：不展示完整项目代码，必要时用代码块展示关键片段
- 文档内引用仅限跨文档导航，不创建代码文件引用

## Impact

- Affected specs: 文档/Wiki
- Affected code: 仅 docs/wiki/ 目录下的 11 个 md 文件

## 涉及文件清单

| 分类目录 | 文件名 |
|---------|--------|
| project_overview/ | System Architecture & Data Flow.md |
| project_overview/ | Getting Started & Configuration.md |
| ingestion_and_detection_layer/ | Feishu IM Detector.md |
| ingestion_and_detection_layer/ | Episode Management.md |
| memory_graph_and_storage/ | MemoryGraph (In-Memory Index).md |
| memory_graph_and_storage/ | Hypergraph Structure & Retrieval.md |
| memory_graph_and_storage/ | Git Storage Backend.md |
| core_engine_and_pipeline/ | MemoryEngine Lifecycle.md |
| core_engine_and_pipeline/ | DecisionNode & Mutation Model.md |
| notification_and_push_system/ | PushEngine & Scheduling.md |
| notification_and_push_system/ | Card Renderer.md |

## ADDED Requirements

### Requirement: 内容补全

每个 md 文件 SHALL 包含：
- 中文子标题（基于原有英文子标题翻译并适当优化）
- 针对每个子标题的实质性技术说明
- 关键流程/数据流/架构的简要文字描述
- 不带完整项目代码，仅展示必要的代码片段

### Requirement: 流程图生成

每个标有 `[生成流程图]` 的位置 SHALL 替换为：
- 有效的 Mermaid 语法图表（flowchart / sequenceDiagram / classDiagram 等）
- 使用成熟 Mermaid 语法，避免不支持的新特性
- 图表应准确反映项目实际逻辑

### Requirement: 风格规范

- 所有内容使用中文书写
- 不添加代码文件路径引用
- 跨文档引用使用 `参见 [文档名](relative-path)` 格式
- 符合 DeepWiki 技术报告风格：叙述性、结构性、清晰