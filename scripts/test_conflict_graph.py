#!/usr/bin/env python3
"""
测试脚本：验证新系统（MemoryGraph + PipelineEngine + GitStorage）与 05-conflict-decisions 数据的适配

流程：
1. 加载 05-conflict-decisions 的 dialogue.json + qa.json
2. 对每个对话组，用 LLM 提取最终决策
3. 通过 PipelineEngine 将决策写入 MemoryGraph + GitStorage
4. 验证冲突检测、存储持久化、快照保存
"""

import hashlib
import json
import sys
import time
from pathlib import Path

# 确保可以从 project root 导入
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.llm.client import LLMClient
from src.core.mutations import DecisionMutation, MutationType
from src.core.engine import PipelineEngine
from src.core.engine_config import EngineConfig
from src.graph.memory_graph import MemoryGraph
from src.graph.snapshot import DetectorSnapshot, SnapshotManager
from src.node.node import DecisionNode
from src.node.types import DecisionStatus, ImpactLevel
from src.storage.git_storage import GitStorage, GitStorageConfig
from src.config import get_storage_path

DATA_DIR = Path(__file__).resolve().parent.parent / "eval_data" / "decision_extraction" / "05-conflict-decisions"
PROJECT = "feishu-mem"
TOPIC = "conflict-decisions"


def load_dialogues() -> dict:
    with open(DATA_DIR / "dialogue.json") as f:
        return json.load(f)["dialogues"]


def load_qa() -> list[dict]:
    with open(DATA_DIR / "qa.json") as f:
        return json.load(f)["qars"]


def format_dialogue_text(group_name: str, messages: list[dict]) -> str:
    lines = [f"--- {group_name} ---"]
    for msg in messages:
        lines.append(f"[{msg['time']}] {msg['speaker']}: {msg['dialogue']}")
    return "\n".join(lines)


def extract_decision_via_llm(client: LLMClient, dialogue_text: str, group_name: str) -> dict:
    prompt = f"""你是一个决策提取专家。请从以下对话中提取最受到的决策信息。

对话内容：
{dialogue_text}

请分析这段对话，提取最终的决策信息，以 JSON 格式返回：

{{
  "has_decision": true/false,
  "final_decision": "决策内容摘要",
  "proposer": "提议者姓名（如果对话中有多个提议变更，返回最终决定的提议者）",
  "executor": "执行者（如果未明确指定，返回空字符串）",
  "status": "decided/pending/in_progress/completed/superseded",
  "impact_level": "major/minor/advisory",
  "has_conflict": true/false,
  "conflict_description": "如果存在冲突（如决策中途变更），请描述"
}}

只返回 JSON，不要包含其他内容。"""
    
    resp = client.chat(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.1,
    )
    
    # 尝试解析 JSON
    resp_clean = resp.strip()
    if resp_clean.startswith("```json"):
        resp_clean = resp_clean[7:]
    if resp_clean.endswith("```"):
        resp_clean = resp_clean[:-3]
    resp_clean = resp_clean.strip()
    
    try:
        return json.loads(resp_clean)
    except json.JSONDecodeError:
        print(f"  [WARN] LLM 返回非 JSON，尝试修复: {resp_clean[:100]}...")
        return {"has_decision": False, "final_decision": resp_clean[:200]}


def build_decision_node(extracted: dict, group_name: str, index: int) -> DecisionNode:
    content = extracted.get("final_decision", "")
    sid = hashlib.md5(f"{group_name}:{content}".encode()).hexdigest()[:12]
    
    status_str = extracted.get("status", "pending")
    try:
        status = DecisionStatus(status_str)
    except ValueError:
        status = DecisionStatus.DECIDED
    
    impact_str = extracted.get("impact_level", "minor")
    try:
        impact = ImpactLevel(impact_str)
    except ValueError:
        impact = ImpactLevel.MINOR
    
    return DecisionNode(
        sid=sid,
        topic_id=TOPIC,
        summary=content[:200],
        full_text=content,
        status=status,
        impact_level=impact,
        authority=extracted.get("proposer", ""),
        assignee=extracted.get("executor", ""),
        tags=["conflict-decisions", group_name],
    )


def main():
    print("=" * 60)
    print("超图记忆系统 - 冲突决策存储测试")
    print("=" * 60)
    
    storage_path = get_storage_path()
    print(f"\n存储路径: {storage_path}")
    
    # 1. 初始化系统
    print("\n[1/6] 初始化 LLM 客户端...")
    client = LLMClient()
    
    print("[2/6] 初始化 MemoryGraph...")
    graph = MemoryGraph()
    
    print("[3/6] 初始化 GitStorage...")
    storage = GitStorage(config=GitStorageConfig(work_dir=storage_path))
    
    print("[4/6] 初始化 PipelineEngine...")
    config = EngineConfig(storage_path=storage_path)
    pipeline = PipelineEngine(memory_graph=graph, git_storage=storage, config=config)
    
    print("[5/6] 初始化 SnapshotManager...")
    snapshot_mgr = SnapshotManager(storage_path=storage_path)
    
    # 2. 加载数据
    print("\n[6/6] 加载 05-conflict-decisions 数据...")
    dialogues = load_dialogues()
    qa = load_qa()
    
    # 构建预期答案字典 (用于后续对比)
    expected: dict[str, dict] = {}
    for qar in qa:
        gid = qar["id"].rsplit("_", 1)[0]  # de_05_000 -> de_05_00X -> group index
        dim = qar["dimension"]
        expected.setdefault(gid, {})[dim] = {
            "answer": qar["A"],
            "options": qar["options"],
        }
    
    print(f"  载入 {len(dialogues)} 个日期分组，共 {sum(len(v) for v in dialogues.values())} 个对话组")
    
    # 3. 遍历所有对话组
    total_groups = 0
    created_decisions = 0
    detected_conflicts = 0
    stored_files = 0
    snapshots_saved = 0
    
    for date, groups in dialogues.items():
        for group_name, messages in groups.items():
            total_groups += 1
            print(f"\n{'─' * 50}")
            print(f"[{total_groups}] {date} / {group_name}")
            
            # 3a. 格式化对话文本
            dialogue_text = format_dialogue_text(group_name, messages)
            
            # 3b. LLM 提取决策
            print(f"  调用 LLM 提取决策...", end=" ", flush=True)
            extracted = extract_decision_via_llm(client, dialogue_text, group_name)
            
            has_decision = extracted.get("has_decision", False)
            final_decision = extracted.get("final_decision", "")
            has_conflict = extracted.get("has_conflict", False)
            conflict_desc = extracted.get("conflict_description", "")
            
            print(f"{'✓ 有决策' if has_decision else '✗ 无决策'}")
            if final_decision:
                print(f"  最终决策: {final_decision[:60]}{'...' if len(final_decision) > 60 else ''}")
            if has_conflict:
                print(f"  冲突: {conflict_desc[:60]}{'...' if len(conflict_desc) > 60 else ''}")
            
            if has_decision:
                # 3c. 构建 DecisionNode
                node = build_decision_node(extracted, group_name, total_groups)
                
                # 3d. 创建 Mutation 并应用
                mut = DecisionMutation(
                    mtype=MutationType.CREATE,
                    sdr_id=node.sid,
                    project=PROJECT,
                    topic=node.topic_id,
                    summary=node.summary,
                    full_text=node.full_text,
                    proposer=node.authority,
                    executor=node.assignee,
                    tags=node.tags,
                    confidence=0.85,
                    new_status=node.status.value,
                    new_impact_level=node.impact_level.value,
                )
                
                success = pipeline.apply_mutation(mut)
                if success:
                    created_decisions += 1
                    print(f"  ✓ 决策已写入: {node.sid}")
                else:
                    print(f"  ✗ 决策写入失败")
                
                # 3e. 保存快照 (模拟检测器行为)
                from src.detect.types import DetectionResult, DecisionLevel, ScoreBreakdown
                fake_result = DetectionResult(
                    score=0.85,
                    level=DecisionLevel.HIGH,
                    is_decision=True,
                    factors=ScoreBreakdown(lexical=1.0, structural=0.5, dynamic=0.0, pattern=0.8, anti_score=0.0, final=0.82),
                )
                snapshot = DetectorSnapshot.from_detection(dialogue_text[:200], "eval_test", fake_result)
                snapshot_mgr.save_snapshot(snapshot)
                snapshots_saved += 1
            
            # 3f. 冲突检测
            if has_conflict:
                detected_conflicts += 1
            
            time.sleep(0.5)  # 避免 API 限流
    
    # 4. 验证存储
    print(f"\n{'=' * 60}")
    print("验证结果")
    print(f"{'=' * 60}")
    
    # 4a. MemoryGraph 状态
    print(f"\n📊 MemoryGraph 状态:")
    print(f"  决策总数: {graph.count()}")
    print(f"  话题数: {graph.topic_count(PROJECT)}")
    
    # 4b. 存储目录
    decision_dir = Path(storage_path) / "decisions" / PROJECT / TOPIC
    if decision_dir.exists():
        md_files = list(decision_dir.glob("*.md"))
        stored_files = len(md_files)
        print(f"\n📁 GitStorage 持久化文件:")
        print(f"  目录: {decision_dir}")
        print(f"  文件数: {stored_files}")
        for f in sorted(md_files)[:5]:
            print(f"    ├ {f.name}")
        if stored_files > 5:
            print(f"    └ ... 还有 {stored_files - 5} 个")
    
    # 4c. 快照目录
    snap_dir = Path(storage_path) / "snapshots"
    if snap_dir.exists():
        snap_files = list(snap_dir.glob("*.json"))
        print(f"\n📸 检测快照文件:")
        print(f"  目录: {snap_dir}")
        print(f"  文件数: {len(snap_files)}")
    
    # 4d. 冲突检测
    print(f"\n⚡ 冲突检测:")
    print(f"  LLM 识别到的冲突对话: {detected_conflicts}/{total_groups}")
    
    # 4e. 从存储读取验证
    print(f"\n🔍 存储读取验证:")
    try:
        topics = storage.list_topics(PROJECT)
        print(f"  存储中的话题: {topics}")
        if TOPIC in topics:
            decisions_on_disk = storage.list_decisions(PROJECT, TOPIC)
            print(f"  list_decisions 读取(当前分支): {len(decisions_on_disk)} 个")
            print(f"  (每个决策存储在独立 git 分支上，list_decisions 仅读取当前分支)")
    except Exception as e:
        print(f"  ✗ 存储读取失败: {e}")
    
    # 4f. Git 分支验证 - 检查所有决策是否在独立分支中
    branches = storage.list_branches()
    decision_branches = [b for b in branches if b.startswith("decision/")]
    print(f"\n  Git 分支层面验证:")
    print(f"  总分支数: {len(branches)} (含 main + {len(decision_branches)} 个决策分支)")
    print(f"  决策分支列表:")
    for b in sorted(decision_branches)[:10]:
        print(f"    ├ {b}")
    
    # 4g. 随机验证一个决策是否可从分支读取
    if decision_branches:
        sample_branch = decision_branches[0]
        sample_sid = sample_branch.split("decision/", 1)[1]
        try:
            from_branch = storage.read_decision_from_branch(sample_branch, sample_sid)
            print(f"\n  分支读取验证 ({sample_branch}):")
            print(f"    决策内容: {from_branch.get('title', 'N/A')[:60]}")
            print(f"  ✓ 从 git 分支读取成功")
        except Exception as e:
            print(f"  ✗ 分支读取失败: {e}")
    
    # 5. 总报告
    print(f"\n{'=' * 60}")
    print("测试报告")
    print(f"{'=' * 60}")
    print(f"  对话组总数:     {total_groups}")
    print(f"  决策提取并写入: {created_decisions}")
    print(f"  冲突对话数:     {detected_conflicts}")
    print(f"  存储文件数:     {stored_files}")
    print(f"  快照文件数:     {snapshots_saved}")
    print(f"  Pipeline 状态:  {pipeline.get_status_summary()}")
    print(f"\n{'✅ 测试完成' if created_decisions > 0 else '❌ 测试失败'}")


if __name__ == "__main__":
    main()