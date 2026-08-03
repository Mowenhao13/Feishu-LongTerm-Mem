## Methodology Blueprint

### Research Paradigm
**Selected**: Pragmatist
**Justification**: The research question is inherently applied and design-oriented — "how should the evaluation methodology be designed" — not a quest for universal laws (positivist) nor a purely interpretive exploration. Pragmatism allows mixing quantitative metrics (precision/recall/F1 from existing EvalComparator) with qualitative design choices (evaluation dimensions, test data schema design), making it the natural fit for methodology engineering.

### Method
**Type**: Mixed methods — primarily design science research (DSR) methodology, with embedded experimental evaluation

| Component | Sub-method | Rationale |
|-----------|-----------|-----------|
| **Methodology Design** | Design Science Research (DSR) | The artifact is an evaluation methodology (not a hypothesis test); DSR's build-evaluate-iterate cycle maps to: design schema → build test data → run eval → refine dimensions |
| **Evaluation of dimensions** | Controlled experiment | Each evaluation dimension is a treatment condition with controlled independent variables (e.g., timeliness tested by varying temporal decay of facts) |
| **Test data construction** | Synthetic scenario generation | Following existing project pattern (scripts/generate_eval_data.py, eval_dataset/config.yaml), extend to include websearch result context |

**Specific Method**: Instrumented evaluation pipeline — design the test harness as a formal extension of the existing EvalRunner + EvalComparator architecture

**Justification**: This method directly answers the RQ ("how should the evaluation methodology be designed") by producing a concrete, implementable artifact. It leverages the project's existing infrastructure while adding the missing websearch memory dimension.

### Data Strategy
**Data Type**: Synthetic (primary, generated)

**Sources**:
- **Websearch result corpus**: Pre-constructed search results from a set of controlled domains (technology choices, API specs, project configurations) — each result is a structured `{query, url, title, snippet, full_content, source_type}` object
- **Dialogue templates**: Extend the existing `eval_dataset/config.yaml` pattern with 5+ websearch-anchored conversation scenarios (see below)
- **Ground truth definitions**: For each test case, define the exact expected memory state after the agent processes the websearch result and conversation

**Scenarios** (covering each sub-question's gap):

| # | Scenario | Controlled Variables | Gap Addressed |
|---|----------|---------------------|---------------|
| 1 | **Simple fact extraction**: Agent reads a websearch result about a tech spec, conversation extracts it as a decision | Search content clarity (clear/ambiguous), conversation directness (explicit/implicit) | Extraction accuracy |
| 2 | **Fact update**: Agent previously remembered fact A; new search returns fact B ≠ A, conversation adopts B | Conflict severity (minor detail vs. fundamental change), time gap between A and B | Update correctness + conflict detection |
| 3 | **Stale fact rejection**: After N hours, stale search result is re-fetched; agent should NOT revert to it | Time decay (1h/6h/24h/7d), stale result vs. current memory confidence | Temporal consistency |
| 4 | **Cross-session recall**: Session 1 remembers fact via search; Session 2 (no search) must retrieve it from memory | Overlap ratio (partial/full), time between sessions | Cross-session retrieval |
| 5 | **Multi-source merge**: Two websearch results from different sources conflict; conversation resolves the conflict | Source authority (same/different levels), resolution explicitness (explicit vs. implicit) | Conflict resolution quality |
| 6 | **Distractor tolerance**: Websearch returns irrelevant results; agent must filter and not extract noise as decisions | Noise ratio (30%/50%/70%), relevance signal strength | Precision (noise filtering) |

**Sampling**: Per-scenario, 10–20 test cases with controlled difficulty levels (easy/medium/hard) following the existing `config.yaml` pattern. Total target: **~100 test cases** across all 6 scenarios.

**Time Frame**: The test data is static/generated, so no data collection time window. Evaluation runs measure the system's state at a single point in time.

### Analytical Framework
**Technique**: Multi-dimensional accuracy analysis with confusion matrix per dimension

**Steps**:
1. **Load test data**: Each JSONL test case contains (a) conversation history, (b) websearch result context, (c) expected memory state, (d) scenario metadata
2. **Run pipeline**: Feed into existing EvalRunner → MemoryEngine processes messages → decisions extracted and stored
3. **Compare output**: Extend EvalComparator to compare actual memory state against expected state for each evaluation dimension
4. **Aggregate metrics**: Compute per-dimension and overall scores
5. **Scenario breakdown**: Report accuracy by scenario, difficulty, and dimension

**Metrics**:

| Dimension | Metric | Formula | Existing/New |
|-----------|--------|---------|-------------|
| **Extraction precision** | Precision | TP / (TP + FP) | ✅ Existing (EvalComparator) |
| **Extraction recall** | Recall | TP / (TP + FN) | ✅ Existing (EvalComparator) |
| **Extraction F1** | F1 | 2 × P × R / (P + R) | ✅ Existing (EvalComparator) |
| **Update correctness** | Edit accuracy | Correct updates / total updates | 🔧 Extend comparator |
| **Conflict detection** | Detection rate | TP_detect / (TP_detect + FN_detect) | 🔧 Extend comparator |
| **Conflict detection** | Detection FPR | FP_detect / total non-conflict cases | 🔧 Extend comparator |
| **Conflict resolution** | Resolution accuracy | Correctly resolved / total detected conflicts | 🆕 New metric |
| **Conflict resolution** | Resolution efficiency | Avg. resolution turns vs. expected turns per case | 🆕 New metric |
| **Timeliness** | Stale retention rate | Stale facts retained / total stale facts presented | 🆕 New metric |
| **Cross-session recall** | Session recall | Facts retrieved across sessions / total cross-session facts | 🆕 New metric |
| **Noise filtering** | Noise-F1 | F1 treating distractor results as negative class | 🆕 New metric |
| **Multi-source coherence** | Merge accuracy | Correctly merged facts / total multi-source cases | 🆕 New metric |

**Tools**:
- Python: extend `src/eval/evaluator.py` with `websearch` evaluation dimension group
- Python: extend `src/eval/comparator.py` with additional metric computation
- JSONL format: extend `messages.jsonl` schema with `websearch_context` field
- Existing: `scripts/run_eval.py` as integration entry point

### Data Schema (JSONL Extension)

Each test case in the messages JSONL gains an optional `websearch_context` field:

```jsonl
{
  "chat_id": "chat_web_01",
  "msg_id": "m001",
  "speaker": "User",
  "msg": "Kubernetes 1.29 has been released, let's discuss upgrading from 1.28",
  "expected_decision": true,
  "websearch_context": {
    "scenario_id": "web_tech_update",
    "search_results": [
      {
        "url": "https://kubernetes.io/blog/2024/01/kubernetes-129-release/",
        "title": "Kubernetes 1.29 Release Announcement",
        "snippet": "Kubernetes 1.29 introduces several new features including ...",
        "full_content": "Kubernetes 1.29, codenamed 'Mandala', was released on January 15, 2024...",
        "source_type": "official",
        "relevance_score": 0.95,
        "timestamp": 1705300000.0,
        "expiry_after_turns": 10,
        "expiry_after_seconds": null
      }
    ],
    "search_intent": "Find latest K8s version release info",
    "expected_effect": {
      "type": "new_decision",
      "expected_topic": "Kubernetes升级策略",
      "expected_summary": "团队决定升级K8s至1.29版本",
      "expected_status": "decided"
    },
    "conflict_with_prior": false,
    "prior_memory_state": null
  },
  "timestamp": 1705300200.0
}
```

**Conflict detection — full schema example** (scenario 2/5):
```jsonl
{
  "chat_id": "chat_web_conflict_01",
  "msg_id": "m003",
  "speaker": "Alice",
  "msg": "Actually the pricing page says $200/month now, not $150. Let's use that.",
  "expected_decision": true,
  "websearch_context": {
    "scenario_id": "web_fact_update",
    "conflict_with_prior": true,
    "prior_memory_state": {
      "expected_topic": "服务定价方案",
      "expected_summary": "团队决定定价$150/月",
      "expected_status": "decided",
      "override_status": "superseded",
      "memorized_at": 1705300000.0
    },
    "search_results": [{
      "url": "https://example.com/pricing",
      "title": "Enterprise Pricing",
      "snippet": "Monthly subscription $200 per month",
      "source_type": "official",
      "relevance_score": 0.98,
      "timestamp": 1705310000.0
    }],
    "expected_effect": {
      "type": "update_decision",
      "conflict_detection_expected": true,
      "conflict_resolution_expected_turns": 2,
      "expected_topic": "服务定价方案",
      "expected_summary": "团队更新定价至$200/月",
      "expected_status": "decided"
    }
  },
  "timestamp": 1705310200.0
}
```

**Control variables encoded in the schema**:
- **`source_type`**: `official` / `community` / `vendor` (controls authority perception)
- **`relevance_score`**: 0.0–1.0 (controls noise level)
- **`timestamp`**: controls relative recency for staleness detection
- **`conflict_with_prior`**: boolean, whether this result contradicts existing memory (for conflict scenarios)
- **`prior_memory_state`**: optional, the expected memory state before this search result is processed

#### 补充：过时判定标准（响应 Squad Leader 建议）

场景 3（过时事实拒绝）的 `expiry_window` 判定规则：

| 判定信号 | Schema 字段 | 用法 |
|----------|------------|------|
| **对话轮次计数** | `expiry_after_turns: int` | 从首次采纳该 fact 起，经过 N 轮对话后标记为过期 |
| **墙钟时间** | `timestamp` + `expiry_after_seconds: int` | 从 fact 最初记录到记忆的时间戳起，经过指定秒数后视为过期 |
| **显式覆盖事件** | `prior_memory_state.override_status: "active"\|"superseded"` | JSONL 中显式标记某 prior memory 已被后续事实覆盖 |

优先使用**轮次计数 + 显式标记的组合策略**作为默认判定方式，`expiry_after_seconds` 作为备选。理由：在合成测试数据中，轮次计数比 wall-clock 时间更可控且可重复；真实场景下两者应互补使用。

#### 补充：跨 session 测试的双文件约定（响应 Squad Leader 建议）

场景 4 采用以下命名约定：

```
eval_dataset/argusbot_websearch/
├── config.yaml                       # 场景配置（继承现有模式）
├── session1_messages.jsonl           # Session 1：websearch result → 记忆建立
├── session1_expected.jsonl           # Session 1 真值
├── session2_messages.jsonl           # Session 2：仅对话（无搜索），依赖记忆检索
├── session2_expected.jsonl           # Session 2 真值
└── cross_session_expected.jsonl      # 跨 session 组合评估的真值（期望跨 session 召回的结果）
```

`run_eval.py --mode websearch --websearch-sessions` 模式下自动：
1. 先加载 session1 的 messages + websearch_context，运行至完成
2. 记录当前 memory state 的 snapshot
3. 加载 session2 的 messages（不含 websearch_context），运行
4. 用 cross_session_expected.jsonl 评估 Session 2 是否正确从记忆检索了 Session 1 的事实

#### 补充：冲突评分粒度细化（响应 Squad Leader 建议）

将场景 2 与场景 5 的冲突相关指标拆分为两个子维度：

| 父维度 | 子维度 | 度量 | 说明 |
|--------|--------|------|------|
| **Conflict detection** | Detection rate | 检出冲突数 / 应检出冲突总数 | 系统是否发现了冲突（二进制：发现/没发现） |
| **Conflict detection** | Detection FPR | 误报数 / 无冲突场景总数 | 系统是否在没有冲突时误报警告 |
| **Conflict resolution** | Resolution accuracy | 正确解决的冲突 / 检出的冲突总数 | 系统发现冲突后，最终记忆状态是否与 `expected_effect` 一致 |
| **Conflict resolution** | Resolution efficiency | 平均解决轮数（对话交互次） | 从发现冲突到记忆状态收敛的对话轮次。合成数据中由 `websearch_context.expected_effect.conflict_resolution_expected_turns` 标注预期值 |

### Validity Criteria

| Criterion | Strategy to Ensure |
|-----------|-------------------|
| **Construct validity** (measure what we claim to measure) | Each evaluation dimension maps to a precisely defined metric with an unambiguous computation formula. Web scenarios model real websearch behavior (agent queries → reads results → converses → stores). |
| **Internal validity** (causal attribution) | Controlled variables in the JSONL schema ensure only the intended dimension varies per scenario. Difficulty levels (easy/medium/hard) are calibrated via pilot tests. |
| **External validity** (generalizability) | 6 scenarios cover the full spectrum of websearch memory failure modes. Source types include official docs, community posts, and vendor pages to avoid overfitting to one source type. |
| **Reliability** | Static test data + deterministic comparison (EvalComparator) = same results on every run. No stochastic model dependence at the comparison layer. |
| **Integration validity** (fits existing system) | Schema designed as an extension to existing messages.jsonl — backward compatible. All tooling reuses EvalRunner + EvalComparator architecture. Backward compatibility guaranteed: existing eval datasets load without modification (websearch_context field absent = no-op). |

### Limitations (By Design)
- **Synthetic data limitation**: Generated conversations may not capture the full messiness of real-world IM discussions where websearch results are shared via links, screenshots, or forwarded messages — mitigatable by including link-in-message variants in 20% of test cases
- **Static search results**: Real websearch varies results over time; the test suite fixes search results to ensure reproducibility — acceptable tradeoff since the goal is evaluation, not websearch engine testing
- **Single-turn extraction focus**: The current design assumes extraction happens on a bounded conversation segment; long-running extraction pipelines (spanning days with multiple interleaved websearch events) are out of scope for this phase

### Ethical Considerations
- No human subjects involved: all test data is synthetically generated
- No real web queries executed during evaluation: all search results are pre-baked into the test data
- The evaluation framework does not access or expose any real user conversations or search histories

### IRB Plan
- **IRB level**: Not applicable — synthetic data only, no human subjects

### Reporting Standard
- **Recommended guideline**: SQUIRE 2.0 (Standards for QUality Improvement Reporting Excellence) — the project's eval infrastructure is a quality improvement effort on the system's memory extraction pipeline, and SQUIRE's structured improvement framework fits methodology design studies

### Preregistration
- **Recommended**: No
- **Platform**: N/A
- **Status**: Not applicable — the work is design science/methodology engineering, not hypothesis testing. If specific metric thresholds are defined later (e.g., "F1 ≥ 0.85 required to ship"), those thresholds should be preregistered at that stage on OSF.

### Integration Plan with Existing Infrastructure

```
scripts/run_eval.py (existing entry point)
        |
        v
src/eval_runner.py (existing — add websearch_context parsing)
        |
        +--- feeds messages into MemoryEngine (existing pipeline)
        |
        v
Decisions stored in memory (existing)
        |
        v
src/eval/comparator.py (extend — add websearch-specific metrics)
        |
        v
src/eval/evaluator.py (extend — add "websearch" dimension group to DIMENSION_GUIDE)
        |
        v
eval_results/eval_v2_report.json (existing — new dimensions added to report)
```

### Recommendation for Phase 3+

The output of this methodology blueprint should feed into:
1. **Phase 3 — Test Data Generation**: Implement the generation script (`scripts/generate_websearch_eval_data.py`) following the config-driven patterns in `eval_dataset/config.yaml`, producing ~100 test cases across the 6 scenarios
2. **Phase 4 — Evaluation Dimension Implementation**: Extend `evaluator.py` and `comparator.py` with websearch-specific dimensions and metrics
3. **Phase 5 — Integration Test**: Run the full pipeline and verify that (a) backward compatibility holds, (b) the 6 new scenarios produce meaningful accuracy scores, (c) the metrics surface specific bottlenecks in websearch→memory processing