"""Test local Qwen3-4B model decision extraction stability."""

import json
import os
import sys
import requests

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.prompts.decision_prompts import DECISION_EXTRACTION_PROMPT_SHORT

# Test data: lines 25-40 from conflict_chat_data.txt
# Context: 打包体积争论 → 做POC → 暂定React和Vue候选方案，Svelte调研
TEST_CONVERSATION = """25→还有打包体积的问题，同样一个页面，Svelte打包后的js只有React的1/3左右，首屏加载差距很明显
26→首屏加载可以用SSR啊，Next.js渲染出来直接就HTML了，体积不是问题
27→Nuxt也能SSR，这个点拉不开差距
28→性能方面Svelte确实有点东西，没有虚拟DOM，直接编译成原生DOM操作，benchmark一直很靠前
29→但React的并发模式和Fiber架构在处理复杂交互时优势还是有的，特别是在需要高优先级更新的场景
30→现在是2025年了，Vue 3的性能已经不差了，而且Vapor Mode直接跳过虚拟DOM，到时候性能差距会更小
31→我觉得还有一个关键点：组件库和模板市场。React有MUI、Ant Design、Shadcn/ui，Vue有Element Plus、Naive UI，Svelte的选择就很少
32→Element Plus确实好用，中文文档完善，而且跟Element UI一脉相承，我们从Vue 2升级到Vue 3很平滑
33→Shadcn/ui虽然不是传统组件库，但它的设计理念太先进了，直接copy代码到项目里，完全掌控样式，自定义程度最高
34→每次一到选型就纠结，上次也是讨论了好久最后换人了才定下来
35→要不这样，先拿一个小模块用不同框架做个POC，对比下开发效率、性能、打包体积，用数据说话
36→做POC可以，但时间成本也要算进去，而且POC做出来的效果跟正式项目差距挺大的
37→我坚持React，生态优势摆在那里，以后加功能、找外包、招人都方便
38→我还是倾向Vue，开发效率确实是三种里最高的，而且这个项目周期紧，Vue上手快能快速出活
39→Svelte虽然我用着爽，但它要面对的不仅是技术选型，还有人才和团队接受度的现实问题
40→算了今天定不了，先各自整理一份选型报告，下周再讨论，暂定React和Vue两个候选方案，Svelte作为调研方向先跟进"""

MODEL_NAME = "qwen3-4b"
BASE_URL = "http://localhost:8002/v1/chat/completions"

system_prompt = "You are an expert in extracting decisions from group chat messages."
# Escape all { } in the prompt template first, then fill the actual placeholder
_prompt_escaped = DECISION_EXTRACTION_PROMPT_SHORT.replace("{", "{{").replace("}", "}}")
# Un-escape the specific placeholder we want to fill
_prompt_escaped = _prompt_escaped.replace("{{conversation_text}}", "{conversation_text}")
user_prompt = _prompt_escaped.format(conversation_text=TEST_CONVERSATION)

print(f"Model: {MODEL_NAME}")
print(f"Base URL: {BASE_URL}")
print(f"System prompt length: {len(system_prompt)} chars")
print(f"User prompt length: {len(user_prompt)} chars")
print(f"Total conversation: {len(TEST_CONVERSATION)} chars")
print("=" * 60)

try:
    response = requests.post(
        BASE_URL,
        json={
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        },
        headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
        timeout=120,
    )
    response.raise_for_status()
    result_data = response.json()
    raw_output = result_data["choices"][0]["message"]["content"]

    print("\n📤 Raw LLM Output:")
    print("-" * 60)
    print(raw_output)
    print("-" * 60)

    # Extract JSON from output
    json_text = raw_output
    if "```json" in raw_output:
        json_text = raw_output.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_output:
        json_text = raw_output.split("```")[1].split("```")[0].strip()

    # Try to parse JSON
    try:
        result = json.loads(json_text)
        print("\n✅ Parsed JSON result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # Validation checks
        decisions = result.get("decisions", [])
        has_decisions = result.get("has_decisions", False)
        print(f"\n📊 Extraction Summary:")
        print(f"  has_decisions: {has_decisions}")
        print(f"  decisions_count: {len(decisions)}")

        for i, dec in enumerate(decisions, 1):
            print(f"\n  Decision {i}:")
            print(f"    title: {dec.get('title', 'N/A')}")
            print(f"    confidence: {dec.get('confidence', 'N/A')}")
            print(f"    impact_level: {dec.get('impact_level', 'N/A')}")
            print(f"    proposer: {dec.get('proposer', 'N/A')}")
            content_preview = dec.get("content", "")[:80]
            print(f"    content_preview: {content_preview}...")

    except json.JSONDecodeError as e:
        print(f"\n❌ Failed to parse JSON: {e}")
        print(f"Extracted text:\n{json_text}")

except requests.exceptions.RequestException as e:
    print(f"\n❌ LLM request failed: {e}")
    print(f"Make sure the model is running at {BASE_URL}")