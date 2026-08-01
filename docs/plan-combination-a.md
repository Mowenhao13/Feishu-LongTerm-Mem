# 组合A 集成实现计划

> **Goal:** 将 ref/git, ref/llm, ref/signal 的 Go 代码按组合A方案翻译/改造为 Python，融入现有项目。
> **Architecture:** 保持超图内存存储+Git文件持久化双层共存；prompts合并到src/prompts；signal核心逻辑融入adapter；error handling用pybreaker+tenacity替代。
> **Tech Stack:** Python 3.12, lark_oapi, pybreaker, tenacity, pydantic, mcp(python), uvloop, asyncio, pyyaml

---

## 文件结构

```
src/
├── storage/                    # [NEW] Git存储层 (ref/git → Python)
│   ├── __init__.py
│   ├── git_cli.py              # git_ops.go → GitCLI
│   ├── git_format.py           # format.go → YAML frontmatter + MD
│   └── git_storage.py          # git_storage.go → GitStorage CRUD
├── llm/
│   └── error_handling/         # [MODIFY] 重写为pybreaker+tenacity
│       ├── __init__.py
│       ├── circuit_breaker.py
│       ├── guardrails.py
│       └── recovery.py
├── prompts/
│   ├── decision_prompts.py     # [MODIFY] 新增冲突/去重/冲突解决prompt
│   └── topic_prompts.py        # [MODIFY] 新增跨议题检测/分类prompt
├── adapter/
│   ├── context.py              # [NEW] signal.go类型 + context.go
│   ├── context_provider.py     # [NEW] context_provider.go IM+Docs
│   ├── context_assembler.py    # [NEW] context.go 装配器
│   ├── enhanced_detector.py    # [NEW] detector.go Analyze逻辑
│   └── lark_im_detector.py     # [NEW] IM决策信号检测器
├── mcp/                        # [NEW] MCP Python SDK tools
│   ├── __init__.py
│   ├── server.py
│   └── tools/
│       ├── search.py
│       ├── decision.py
│       └── extract.py
tests/
├── test_storage.py
├── test_error_handling.py
├── test_adapter_detector.py
├── test_prompts.py
└── test_mcp.py
```

---

### Task 1: Git Storage 翻译

**Files:**
- Create: `src/storage/__init__.py`
- Create: `src/storage/git_cli.py`
- Create: `src/storage/git_format.py`
- Create: `src/storage/git_storage.py`
- Create: `tests/test_storage.py`
- Ref: `ref/git/git_ops.go`, `ref/git/format.go`, `ref/git/git_storage.go`

### Task 2: Error Handling 重写

**Files:**
- Create: `src/llm/error_handling/__init__.py`
- Create: `src/llm/error_handling/circuit_breaker.py`
- Create: `src/llm/error_handling/guardrails.py`
- Create: `src/llm/error_handling/recovery.py`
- Create: `tests/test_error_handling.py`
- Ref: `src/llm/error_handling/README.md`, `ref/llm/error_handling/circuit_breaker.go`
- Dependencies: `uv add pybreaker tenacity`

### Task 3: Prompts 合并

**Files:**
- Modify: `src/prompts/decision_prompts.py` (新增冲突评估/去重/冲突解决 prompt)
- Modify: `src/prompts/topic_prompts.py` (新增跨议题检测/分类 prompt)
- Create: `tests/test_prompts.py`
- Ref: `ref/llm/prompts/manager.go` 的 extraction_doc, conflict, dedup, crosstopic prompt内容

### Task 4: MCP

**Files:**
- Create: `src/mcp/__init__.py`
- Create: `src/mcp/server.py`
- Create: `src/mcp/tools/__init__.py`
- Create: `src/mcp/tools/search.py`
- Create: `src/mcp/tools/decision.py`
- Create: `src/mcp/tools/extract.py`
- Create: `tests/test_mcp.py`
- Dependencies: `uv add mcp`

### Task 5: EnhancedDetector

**Files:**
- Create: `src/adapter/enhanced_detector.py`
- Create: `src/adapter/lark_im_detector.py`
- Ref: `ref/signal/detector.go` (只看Analyze逻辑, 删激活矩阵)
- Delete: `ref/signal/router.go`, `ref/signal/emitter.go`, `ref/signal/worker.go`

### Task 6: Context

**Files:**
- Create: `src/adapter/context.py` (信号类型)
- Create: `src/adapter/context_provider.py` (IM+Docs上下文提供者)
- Create: `src/adapter/context_assembler.py` (上下文装配器)
- Create: `tests/test_adapter_detector.py`
- Ref: `ref/signal/context.go`, `ref/signal/context_provider.go`

### Task 7: Async

**Files:**
- Modify: `src/adapter/lark_im.py` (添加async检测器兼容)
- Dependencies: `uv add uvloop`