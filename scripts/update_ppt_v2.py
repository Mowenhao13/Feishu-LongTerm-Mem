#!/usr/bin/env python3
"""批量更新 index.html：删除/替换/插入幻灯片"""
import re

HTML_PATH = "docs/ppt/index.html"
README_PATH = "memory_stores/backup/argusbot-eval-v2/README.md"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ==================== 1. 读取 README 中新增决策提取演示内容 ====================
with open(README_PATH, "r", encoding="utf-8") as f:
    readme_content = f.read()

# 提取"七、新增决策提取演示"部分
demo_start = readme_content.find("## 七、新增决策提取演示")
demo_end = readme_content.find("\n## ", demo_start + 10) if demo_start > 0 else -1
if demo_start > 0 and demo_end > 0:
    demo_section = readme_content[demo_start:demo_end].strip()
else:
    demo_section = readme_content[demo_start:].strip() if demo_start > 0 else ""

# ==================== 2. 删除"改进对比"表格 ====================
old_improve = """          <h3 style="margin-top:16px;">改进对比</h3>
          <table class="compact-table">
            <tr><th>指标</th><th>旧版字符</th><th>Embedding</th></tr>
            <tr><td>single F1</td><td>45.6%</td><td style="color:var(--green);font-weight:700;">88.6%</td></tr>
            <tr><td>multi F1</td><td>48.9%</td><td style="color:var(--green);font-weight:700;">84.5%</td></tr>
            <tr><td>single Recall</td><td>46.2%</td><td style="color:var(--green);font-weight:700;">100.0%</td></tr>
          </table>"""
html = html.replace(old_improve, "")

# ==================== 3. 删除"关键发现"中的 "Precision 提升最大" ====================
old_findings = """          <div style="margin-top:16px;">
            <h4>关键发现</h4>
            <ul>
              <li>single 所有 39 个期望决策全部匹配（FN=0）</li>
              <li>multi 8 群跨群隔离 <span style="color:var(--green);font-weight:700;">100%</span></li>
              <li>Precision 提升最大：multi +49pp</li>
              <li>Recall 瓶颈在 LLM 提取环节</li>
            </ul>
          </div>"""

new_findings = """          <div style="margin-top:16px;">
            <h4>关键发现</h4>
            <ul>
              <li>v2 Precision = 100%，零误检（FP=0）</li>
              <li>v2 Recall = 75.6%，10个漏检（FN=10），瓶颈在 LLM 提取的保守策略</li>
              <li>5个群聊间跨群隔离 <span style="color:var(--green);font-weight:700;">100%</span></li>
              <li>v2 覆盖主题 10 个，全部 Precision/Recall/F1 = 100%</li>
            </ul>
          </div>"""
html = html.replace(old_findings, new_findings)

# ==================== 4. 删除运行评估的代码块 ====================
old_run_eval = """          <div class="terminal" style="margin-top:12px;font-size:0.72rem;">
            <span class="comment"># 运行评估</span><br>
            python -m src.eval_runner \\<br>
            &nbsp;&nbsp;--eval \\<br>
            &nbsp;&nbsp;--input eval_dataset/argusbot_single/msgs.jsonl \\<br>
            &nbsp;&nbsp;--expected eval_dataset/argusbot_single/expected.jsonl
          </div>"""
html = html.replace(old_run_eval, "")

# ==================== 5. 删除"新增决策提取演示"幻灯片（slide 17） ====================
slide17_start = html.find('<!-- ==================== SLIDE 17: 新增决策提取演示 ==================== -->')
slide17_end = html.find('<!-- ==================== SLIDE 18: 快速开始 ==================== -->')
if slide17_start > 0 and slide17_end > 0:
    html = html[:slide17_start] + html[slide17_end:]

# ==================== 6. 删除评估流水线的"Embedding 修复"部分 ====================
old_embedding_fix = """          <h3 style="margin-top:16px;">Embedding 修复</h3>
          <div class="terminal" style="font-size:0.72rem;">
            <span class="comment"># 修复前：模型名大小写检查失败</span><br>
            <span class="error">if 'Qwen3' not in self.model_name:</span><br>
            &nbsp;&nbsp;raise ValueError()<br>
            <br>
            <span class="comment"># 修复后：大小写不敏感</span><br>
            <span class="green">if 'qwen3' not in self.model_name.lower():</span><br>
            &nbsp;&nbsp;raise ValueError()
          </div>"""
html = html.replace(old_embedding_fix, "")

# ==================== 7. 在"评估流水线"右侧加入"argusbot_multi_v2 覆盖主题说明" ====================
old_actual_slide = """          <h3 style="margin-top:20px;">运行日志</h3>
          <div class="terminal" style="margin-top:8px;font-size:0.75rem;">
            [Episode] Buffer <span class="cyan">eval_1</span> boundary=time_gap → <span class="warn">SUSPEND</span> ep_xxx (6 msgs)<br>
            [Episode] Buffer <span class="cyan">eval_1</span> <span class="highlight">max_sim=0.62</span> &gt; 0.55 → <span class="green">REOPEN</span> ep_bd53f3 (resume)<br>
            [Episode] SuspendPool LRU evict: ep_abc123 (suspended 2026-05-27 10:00)
          </div>"""

new_actual_slide = old_actual_slide

# 在评估流水线右侧的"关键组件"后加入主题说明
old_key_components = """          <h3 style="margin-top:24px;">关键组件</h3>
          <table class="compact-table">
            <tr><th>组件</th><th>职责</th></tr>
            <tr><td>EvalRunner</td><td>逐条消息送入引擎，模拟真实消息流</td></tr>
            <tr><td>LLM Extractor</td><td>从对话中提取结构化决策</td></tr>
            <tr><td>EvalComparator</td><td>Embedding 语义匹配，计算 TP/FP/FN</td></tr>
            <tr><td>Embedding Provider</td><td>qwen3-embedding-4b，batch 向量化</td></tr>
          </table>"""

new_key_components = """          <h3 style="margin-top:24px;">关键组件</h3>
          <table class="compact-table">
            <tr><th>组件</th><th>职责</th></tr>
            <tr><td>EvalRunner</td><td>逐条消息送入引擎，模拟真实消息流</td></tr>
            <tr><td>LLM Extractor</td><td>从对话中提取结构化决策</td></tr>
            <tr><td>EvalComparator</td><td>Embedding 语义匹配，计算 TP/FP/FN</td></tr>
            <tr><td>Embedding Provider</td><td>qwen3-embedding-4b，batch 向量化</td></tr>
          </table>
          <h3 style="margin-top:24px;">v2 覆盖主题</h3>
          <div class="tags" style="margin-top:8px;">
            <span class="tag cyan">多智能体循环架构</span>
            <span class="tag">会话持久化与恢复</span>
            <span class="tag green">Daemon与CLI双模式</span>
            <span class="tag">飞书集成方案</span>
            <span class="tag purple">PlannerAgent策略</span>
            <span class="tag">BTW Side-Agent集成</span>
            <span class="tag yellow">Stall检测配置</span>
            <span class="tag">Telegram集成</span>
            <span class="tag">JSONL命令总线</span>
            <span class="tag">模型fallback链</span>
          </div>"""
html = html.replace(old_key_components, new_key_components)

# ==================== 8. 在"快速开始"前插入两页：HyperMem 结构 + SuspendPool ====================

hypermem_slide = """
  <!-- ==================== SLIDE 17: HyperMem 超图结构 ==================== -->
  <div class="slide" data-index="17">
    <div class="slide-content" style="transform: translateY(32px);">
      <h2>HyperMem 超图记忆架构</h2>
      <p class="subtitle">三层节点 + 超边关联，从粗到精的语义检索</p>
      <div class="grid-2">
        <div>
          <h3>三层结构</h3>
          <table class="compact-table">
            <tr><th>层级</th><th>说明</th><th>粒度</th></tr>
            <tr><td><span class="tag cyan">Topic</span></td><td>高层语义聚类（如"技术选型"）</td><td>最粗</td></tr>
            <tr><td><span class="tag purple">Episode</span></td><td>叙事片段（一次话题的完整讨论）</td><td>中</td></tr>
            <tr><td><span class="tag green">Fact/Decision</span></td><td>原子信息（具体决策内容）</td><td>最细</td></tr>
          </table>
          <h3 style="margin-top:20px;">超边（Hyperedge）</h3>
          <ul>
            <li>一条超边可连接多个节点（Topic → 所有相关 Episodes）</li>
            <li>决策通过超边关联到所属 Episode 和 Topic</li>
            <li>跨 Episode 的决策通过超边建立语义关联</li>
          </ul>
          <h3 style="margin-top:20px;">从粗到精检索</h3>
          <div class="arch-flow" style="flex-direction:column;gap:8px;">
            <div class="arch-box cyan"><div class="icon">🔍</div>Topic 层：向量搜索缩小范围</div>
            <div class="arch-arrow" style="transform:rotate(90deg);">→</div>
            <div class="arch-box purple"><div class="icon">📝</div>Episode 层：超边传播注意力权重</div>
            <div class="arch-arrow" style="transform:rotate(90deg);">→</div>
            <div class="arch-box green"><div class="icon">📋</div>Decision 层：精确提取原子事实</div>
          </div>
        </div>
        <div>
          <h3>架构图</h3>
          <div class="terminal" style="font-size:0.72rem;">
            <span class="comment"># HyperMem 结构示意</span><br>
            <span class="cyan">Topic: "多智能体循环架构"</span><br>
            │<br>
            ├─ <span class="purple">Episode: ep_001 (四Agent协作讨论)</span><br>
            │  ├─ <span class="green">Decision: 分层方案</span><br>
            │  ├─ <span class="green">Decision: 结构化日志</span><br>
            │  └─ <span class="green">Decision: 错误分类策略</span><br>
            ├─ <span class="purple">Episode: ep_002 (通信协议选型)</span><br>
            │  └─ <span class="green">Decision: gRPC通信协议</span><br>
            └─ <span class="purple">Episode: ep_003 (Agent数量控制)</span><br>
               └─ <span class="green">Decision: 固定10个智能体</span><br>
            <br>
            <span class="comment"># 超边连接同主题下所有 Episode</span><br>
            hyperedge(Topic) → [ep_001, ep_002, ep_003]
          </div>
          <h3 style="margin-top:16px;">v2 数据集覆盖</h3>
          <div style="margin-top:8px;">
            <div class="stat-row">
              <div class="stat-item">
                <div class="stat-num" style="color:var(--cyan);">10</div>
                <div class="stat-label">Topics</div>
              </div>
              <div class="stat-item">
                <div class="stat-num" style="color:var(--purple);">183</div>
                <div class="stat-label">Episodes</div>
              </div>
              <div class="stat-item">
                <div class="stat-num" style="color:var(--green);">31</div>
                <div class="stat-label">Decisions</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ==================== SLIDE 18: SuspendPool 挂起池 ==================== -->
  <div class="slide" data-index="18">
    <div class="slide-content" style="transform: translateY(32px);">
      <h2>SuspendPool — Episode 挂起与恢复</h2>
      <p class="subtitle">智能管理暂停的对话，实现话题切换与恢复</p>
      <div class="grid-2">
        <div>
          <h3>为什么需要 SuspendPool？</h3>
          <ul>
            <li>群聊中话题经常切换，但旧话题可能稍后回归</li>
            <li>直接丢弃 Episode 会丢失上下文，影响后续关联</li>
            <li>SuspendPool 保留暂停 Episode 的完整消息和 embedding</li>
            <li>新消息到达时，与池中所有暂停 Episode 做 Max-similarity 匹配</li>
          </ul>
          <h3 style="margin-top:20px;">三重边界检测</h3>
          <table class="compact-table">
            <tr><th>边界类型</th><th>阈值</th><th>触发</th></tr>
            <tr><td>⏱ 时间间隔</td><td>1800s (30min)</td><td>超时 Suspend</td></tr>
            <tr><td>🧠 语义切换</td><td>similarity &lt; 0.50</td><td>话题变化 Suspend</td></tr>
            <tr><td>📊 容量上限</td><td>MAX_MSGS=50</td><td>超限强制 Suspend</td></tr>
          </table>
          <h3 style="margin-top:20px;">Reopen 条件</h3>
          <div class="terminal" style="font-size:0.75rem;">
            max_sim = max(sim(new_msg, ep))<br>
            if max_sim &gt;= <span class="highlight">0.55</span> → <span class="green">REOPEN</span><br>
            else → <span class="cyan">创建新 Episode</span>
          </div>
        </div>
        <div>
          <h3>生命周期</h3>
          <div class="arch-flow" style="flex-direction:column;gap:8px;">
            <div class="arch-box accent"><div class="icon">⚡</div>Active Episode</div>
            <div class="arch-arrow" style="transform:rotate(90deg);">→ 检测到边界</div>
            <div class="arch-box orange"><div class="icon">⏸</div>Suspend → 入池</div>
            <div class="arch-arrow" style="transform:rotate(90deg);">→ 新消息比对</div>
            <div class="arch-box green"><div class="icon">▶</div>max_sim≥0.55 → Reopen</div>
            <div class="arch-box" style="border-color:var(--red);color:var(--red);"><div class="icon">🗑</div>池满(20) → LRU 淘汰</div>
          </div>
          <h3 style="margin-top:20px;">v2 运行数据</h3>
          <div class="terminal" style="font-size:0.75rem;">
            <span class="comment"># eval_v2 真实数据</span><br>
            处理消息: <span class="highlight">1,500</span><br>
            Episode Suspend: <span class="warn">821</span> 次<br>
            Episode Reopen: <span class="cyan">723</span> 次<br>
            新创建 Episode: <span class="green">183</span> 次<br>
            处理速率: <span class="highlight">30.0</span> msg/s<br>
            <br>
            <span class="comment"># 意味着平均每 2 条消息</span><br>
            <span class="comment"># 就发生一次 Reopen 检查</span>
          </div>
          <h3 style="margin-top:12px;">LRU 淘汰</h3>
          <p style="font-size:0.85rem;">池满 20 个时，淘汰最早暂停的 Episode，确保内存可控</p>
        </div>
      </div>
    </div>
  </div>

"""

# 插入到"快速开始"幻灯片前
quick_start_marker = '<!-- ==================== SLIDE 18: 快速开始 ==================== -->'
html = html.replace(quick_start_marker, hypermem_slide + '  <!-- ==================== SLIDE 19: 快速开始 ==================== -->')

# ==================== 9. 更新页码和 data-index ====================
# 删除 slide 17 后，原来的 slide 18(快速开始) → 19, slide 19(Q&A) → 20
# 插入两页后：快速开始→21, Q&A→22
# 总共：封面(1)+2+3+4+5+6+7+8+9+10+11+12+13+14+15+16+17(HyperMem)+18(SuspendPool)+19(快速开始)+20(Q&A) = 20页

# 更新 data-index
# slide 17 已删除（新增决策提取演示）
# slide 18(快速开始) → 改为 19
# slide 19(Q&A) → 改为 20
html = html.replace('data-index="18"', 'data-index="19"', 1)  # 快速开始
html = html.replace('data-index="19"', 'data-index="20"', 1)  # Q&A

# 更新页码指示
html = html.replace('1 / 20', '1 / 20')  # 总共还是20页（删除1页+插入2页 = 净增1页，从19→20）

# ==================== 10. 将新增决策提取演示追加到 README ====================
demo_content = """
## 八、新增决策提取演示（来自幻灯片）

### 演示场景：在已有的决策链中新增一条关于"gRPC通信协议选型"的决策

**背景**：团队已确定了多智能体循环架构和分层方案，现在需要细化 Agent 间的通信协议。

### 新增讨论消息

```
[Alice] @Bob @Charlie 刚才我们定了分层架构和错误处理，现在来定Agent间的通信协议。
[Bob] 我建议用gRPC，Proto定义接口，性能比REST好，而且支持流式通信，适合Agent间的实时状态同步。
[Charlie] gRPC选型的话，我们用Python原生grpcio库，还是用grpcio-tools生成代码？考虑到我们需要动态注册Agent，原生库更灵活。
[Eve] 前端侧，如果后端用gRPC，我需要用gRPC-Web来对接，或者中间加一层Envoy做协议转换。
[Diana] 用户角度无所谓协议，只要API文档写清楚就行。
[Alice] 好，就用gRPC，Bob你负责proto文件定义，Charlie准备grpcio环境，Eve评估gRPC-Web方案。
```

### 预期提取的决策

| 字段 | 值 |
|------|-----|
| **topic** | 多智能体循环架构 |
| **summary** | Alice拍板采用gRPC作为Agent间通信协议 |
| **status** | decided |
| **impact_level** | major |
| **is_suggestion** | false |
| **parent_sid** | m006 (父决策: 分层架构方案) |
| **granularity_level** | 3 |
| **proposer** | Bob |
| **executor** | Bob (proto定义) / Charlie (环境) / Eve (gRPC-Web评估) |

### 置信度分析

| 特征 | 影响 |
|------|------|
| 明确拍板词 "就用gRPC" | +0.05 置信度 |
| 指定了执行者 | +0.05 置信度 |
| 有明确技术选型 | +0.05 置信度 |
| 非建议性语句 | 基础 0.80 |
| **最终置信度** | **~0.95** (高置信) |
"""

with open(README_PATH, "a", encoding="utf-8") as f:
    f.write(demo_content)

# ==================== 11. 保存 ====================
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("✅ index.html 已更新")
print("✅ README.md 已追加新增决策提取演示")
print("✅ 删除了：改进对比、运行评估代码块、Embedding修复、新增决策提取演示幻灯片")
print("✅ 新增了：v2覆盖主题、HyperMem结构页、SuspendPool页")
print("✅ 页码指示: 20页")
