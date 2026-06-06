#!/usr/bin/env python3
"""
1. 将 HyperMem 和 SuspendPool 幻灯片移到 "系统架构" 之后
2. 将 SuspendPool 生命周期箭头从纵向改为横向
3. 重新编号所有 data-index 和页码
"""

HTML_PATH = "docs/ppt/index.html"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ========== 1. 提取 HyperMem 和 SuspendPool 幻灯片 ==========
hypermem_start = html.find('<!-- ==================== SLIDE 17: HyperMem 超图结构 ==================== -->')
suspendpool_end = html.find('<!-- ==================== SLIDE 19: 快速开始 ==================== -->')
# 获取 SuspendPool 开始位置
suspendpool_start = html.find('<!-- ==================== SLIDE 18: SuspendPool 挂起池 ==================== -->')

# 提取两个幻灯片的内容（从 HyperMem 开始到快速开始前结束）
slides_to_move = html[hypermem_start:suspendpool_end]
# 去掉末尾的空白
slides_to_move = slides_to_move.rstrip()

# ========== 2. 从原位置删除 ==========
html_before = html[:hypermem_start]
html_after = html[suspendpool_end:]
html = html_before + html_after

# ========== 3. 修正 SuspendPool 生命周期箭头为横向 ==========
# 把纵向 arch-flow 改成横向 flow-row
old_lifecycle = """          <h3>生命周期</h3>
          <div class="arch-flow" style="flex-direction:column;gap:8px;">
            <div class="arch-box accent"><div class="icon">⚡</div>Active Episode</div>
            <div class="arch-arrow" style="transform:rotate(90deg);">→ 检测到边界</div>
            <div class="arch-box orange"><div class="icon">⏸</div>Suspend → 入池</div>
            <div class="arch-arrow" style="transform:rotate(90deg);">→ 新消息比对</div>
            <div class="arch-box green"><div class="icon">▶</div>max_sim≥0.55 → Reopen</div>
            <div class="arch-box" style="border-color:var(--red);color:var(--red);"><div class="icon">🗑</div>池满(20) → LRU 淘汰</div>
          </div>"""

new_lifecycle = """          <h3>生命周期</h3>
          <div class="flow-row">
            <span class="flow-step" style="border-color:var(--accent);color:var(--accent);">⚡ Active</span>
            <span class="flow-arrow">→ 检测到边界</span>
            <span class="flow-step" style="border-color:var(--yellow);color:var(--yellow);">⏸ Suspend</span>
            <span class="flow-arrow">→ 新消息比对</span>
            <span class="flow-step" style="border-color:var(--green);color:var(--green);">▶ Reopen</span>
            <span class="flow-arrow">或</span>
            <span class="flow-step" style="border-color:var(--red);color:var(--red);">🗑 LRU淘汰</span>
          </div>"""

slides_to_move = slides_to_move.replace(old_lifecycle, new_lifecycle)

# ========== 4. 插入到 "系统架构" 幻灯片之后 ==========
arch_marker = '  <!-- ==================== SLIDE 4: 飞书 IM 集成 ==================== -->'
html = html.replace(arch_marker, slides_to_move + '\n\n' + arch_marker)

# ========== 5. 重新编号所有 data-index ==========
import re
indices = [m.group(1) for m in re.finditer(r'data-index="([^"]+)"', html)]
for i, old_idx in enumerate(indices):
    old_attr = f'data-index="{old_idx}"'
    new_attr = f'data-index="{i}"'
    html = html.replace(old_attr, new_attr, 1)

# ========== 6. 更新页码 ==========
page_count = len(indices)
html = html.replace(f'1 / {page_count - 1}', f'1 / {page_count}')
# 也处理可能已经错误设置的值
html = re.sub(r'1 / \d+', f'1 / {page_count}', html)

# ========== 7. 更新幻灯片注释编号 ==========
# 重新生成所有 SLIDE 注释
slide_comments = re.findall(r'<!-- ==================== (SLIDE \d+: [^-]+) ==================== -->', html)
for i, comment in enumerate(slide_comments, 1):
    old_comment = f'SLIDE {i}:'
    # 找到注释文本
    pass

# 用更精确的方式重编号注释
comment_mapping = {
    'SLIDE 1:': 'SLIDE 1:',   # COVER (不动)
}

# 实际上注释编号不影响功能，data-index 才是关键
# 只修正可能出现的重复编号

# 保存
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

# 打印当前幻灯片顺序
for i, comment in enumerate(slide_comments, 1):
    print(f"  Slide {i}: {comment}")

print(f"\n✅ 总数: {page_count} 页")
print("✅ HyperMem 和 SuspendPool 已移到系统架构之后")
print("✅ SuspendPool 生命周期箭头已改为横向")
