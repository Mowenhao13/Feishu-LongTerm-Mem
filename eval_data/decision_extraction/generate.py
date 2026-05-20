"""
Generate decision extraction evaluation dataset.

Produces 12 scenario directories under evaldata/decision_extraction/,
each with dialogue.json and qa.json in EverMemBench-compatible format.
Total: 170 samples, ~650 QA questions.
"""
import json
import os
import random
from pathlib import Path
from typing import List, Dict, Optional

random.seed(42)

OUTPUT_DIR = Path(__file__).parent

SPEAKERS_TECH = ["张三", "李四", "王五", "赵六", "陈七"]
TOPICS_DB = ["PostgreSQL", "MySQL", "MongoDB", "Redis", "ElasticSearch"]
TOPICS_FRAMEWORK = ["React", "Vue", "Angular", "Svelte", "Next.js"]
TOPICS_ARCH = ["微服务架构", "单体架构", "事件驱动架构", "分层架构"]
TOPICS_INFRA = ["Docker", "Kubernetes", "Terraform", "Jenkins", "Kafka"]


def make_dialogue(messages: List[Dict], date: str = "2025-01-15",
                  group: str = "技术讨论") -> Dict:
    entries = []
    for i, m in enumerate(messages):
        h = 10 + (i // 6)
        mi = (i * 2) % 60
        time_str = f"{date} {h:02d}:{mi:02d}:00"
        entries.append({
            "speaker": m["speaker"],
            "time": time_str,
            "dialogue": m["content"],
        })
    return {"dialogues": {date: {group: entries}}}


def make_qa(qars: List[Dict]) -> Dict:
    return {"qars": qars}


def write_scenario(dir_name: str, dialogues_list: List[Dict], qas_list: List[Dict]):
    scenario_dir = OUTPUT_DIR / dir_name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    merged_dialogues = {}
    for i, d in enumerate(dialogues_list):
        day = 15 + i
        month = 1
        if day > 28:
            day = day - 28
            month = 2
        sample_date = f"2025-{month:02d}-{day:02d}"
        for date_key, groups in d.get("dialogues", {}).items():
            for group_name, msgs in groups.items():
                for msg in msgs:
                    old_time = msg.get("time", "")
                    if old_time and len(old_time) >= 10:
                        msg["time"] = sample_date + old_time[10:]
                merged_dialogues[sample_date] = {group_name: msgs}
    with open(scenario_dir / "dialogue.json", "w", encoding="utf-8") as f:
        json.dump({"dialogues": merged_dialogues}, f, ensure_ascii=False, indent=2)
    all_qars = []
    for qa in qas_list:
        all_qars.extend(qa.get("qars", []))
    with open(scenario_dir / "qa.json", "w", encoding="utf-8") as f:
        json.dump({"qars": all_qars}, f, ensure_ascii=False, indent=2)


def generate_technical_selection():
    dialogues = []
    qas = []
    for i in range(20):
        s = random.sample(SPEAKERS_TECH, 3)
        db = TOPICS_DB[i % len(TOPICS_DB)]
        alt_db = TOPICS_DB[(i + 1) % len(TOPICS_DB)]
        if i < 10:
            msgs = [
                {"speaker": s[0], "content": f"数据库选型，大家有什么建议？"},
                {"speaker": s[1], "content": f"我推荐用{db}，成熟稳定"},
                {"speaker": s[2], "content": f"{alt_db}也不错，生态好"},
                {"speaker": s[1], "content": f"{db}团队经验丰富，维护成本低"},
                {"speaker": s[0], "content": f"好，那就定{db}吧"},
                {"speaker": s[2], "content": "同意"},
            ]
        elif i < 15:
            options_list = random.sample(TOPICS_DB, 3)
            selected = options_list[0]
            msgs = [
                {"speaker": s[0], "content": f"候选方案：{'、'.join(options_list)}"},
                {"speaker": s[1], "content": f"{selected}最符合我们需求"},
                {"speaker": s[2], "content": f"支持{selected}"},
                {"speaker": s[0], "content": f"那就选{selected}"},
            ]
        else:
            msgs = [
                {"speaker": s[0], "content": f"这次我们用{db}吧"},
                {"speaker": s[1], "content": "可以"},
                {"speaker": s[0], "content": f"就这么定了，用{db}"},
            ]
        dialogue = make_dialogue(msgs, group=f"技术选型-{chr(65+i)}")
        dialogues.append(dialogue)
        detection_options = {"A": "是，做出了技术选型决策", "B": "否，只是在讨论"}
        content_options = {"A": f"使用{TOPICS_DB[(i+1) % len(TOPICS_DB)]}", "B": f"使用{db}", "C": "暂不决定", "D": "使用其他方案"}
        proposer_options = {"A": s[0], "B": s[1], "C": s[2], "D": "无法确定"}
        executor_options = {"A": s[0], "B": s[1], "C": s[2], "D": "未明确指定执行人"}
        impact_options = {"A": "major（重大变更）", "B": "minor（常规变更）", "C": "advisory（建议级别）"}
        status_options = {"A": "decided", "B": "in_progress", "C": "completed", "D": "pending_confirmation"}
        qa = make_qa([
            {"id": f"de_01_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "A", "options": detection_options, "dimension": "detection"},
            {"id": f"de_01_{i:03d}_content", "Q": "决策内容是什么？", "A": "B", "options": content_options, "dimension": "content"},
            {"id": f"de_01_{i:03d}_proposer", "Q": "这个决策是谁提出的？", "A": "B", "options": proposer_options, "dimension": "proposer"},
            {"id": f"de_01_{i:03d}_executor", "Q": "这个决策由谁执行？", "A": "D", "options": executor_options, "dimension": "executor"},
            {"id": f"de_01_{i:03d}_impact", "Q": "这个决策的影响级别是？", "A": "A", "options": impact_options, "dimension": "impact_level"},
            {"id": f"de_01_{i:03d}_status", "Q": "这个决策的当前状态是？", "A": "A", "options": status_options, "dimension": "status"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_task_assignment():
    dialogues = []
    qas = []
    task_pool = ["数据库迁移", "API改造", "前端重构", "性能优化", "文档编写", "测试用例", "部署配置"]
    for i in range(15):
        s = random.sample(SPEAKERS_TECH, 3)
        task = task_pool[i % len(task_pool)]
        if i < 5:
            assigner = s[0]
            assignee = s[1]
            msgs = [
                {"speaker": assigner, "content": f"{assignee}来负责{task}"},
                {"speaker": assignee, "content": "好的，我来处理"},
                {"speaker": s[2], "content": "辛苦"},
            ]
            executor = assignee
        elif i < 10:
            volunteer = s[1]
            msgs = [
                {"speaker": s[0], "content": f"{task}谁来做？"},
                {"speaker": volunteer, "content": "我来吧"},
                {"speaker": s[0], "content": "好，交给你了"},
            ]
            executor = volunteer
        else:
            msgs = [
                {"speaker": s[0], "content": f"{task}由前端团队负责"},
                {"speaker": s[2], "content": "收到"},
                {"speaker": s[0], "content": "下周二前完成"},
            ]
            executor = "前端团队"
        dialogue = make_dialogue(msgs, group=f"任务分配-{chr(65+i)}")
        dialogues.append(dialogue)
        detection_options = {"A": "是，分配了任务", "B": "否，只是在讨论"}
        content_options = {"A": "不做这个任务", "B": f"由{executor}负责{task}", "C": task}
        proposer_options = {"A": s[0], "B": s[1], "C": s[2], "D": "无法确定"}
        executor_options = {"A": s[0], "B": s[1], "C": "前端团队" if executor == "前端团队" else s[2], "D": executor}
        impact_options = {"A": "major", "B": "minor", "C": "advisory"}
        status_options = {"A": "decided", "B": "in_progress", "C": "completed", "D": "pending_confirmation"}
        qa = make_qa([
            {"id": f"de_02_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "A", "options": detection_options, "dimension": "detection"},
            {"id": f"de_02_{i:03d}_content", "Q": "决策内容是什么？", "A": "B", "options": content_options, "dimension": "content"},
            {"id": f"de_02_{i:03d}_proposer", "Q": "这个任务是谁分配的？", "A": "A", "options": proposer_options, "dimension": "proposer"},
            {"id": f"de_02_{i:03d}_executor", "Q": f"谁负责{task}？", "A": "D", "options": executor_options, "dimension": "executor"},
            {"id": f"de_02_{i:03d}_impact", "Q": "这个决策的影响级别是？", "A": "B", "options": impact_options, "dimension": "impact_level"},
            {"id": f"de_02_{i:03d}_status", "Q": "这个决策的当前状态是？", "A": "A", "options": status_options, "dimension": "status"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_parameter_lock():
    dialogues = []
    qas = []
    params = [
        ("索引分片数", "shard_count=256", "128", "512"),
        ("超时时间", "timeout=30s", "15s", "60s"),
        ("并发限制", "max_connections=100", "50", "200"),
        ("缓存过期时间", "cache_ttl=3600s", "1800s", "7200s"),
        ("日志级别", "log_level=INFO", "DEBUG", "WARN"),
        ("部署副本数", "replicas=3", "1", "5"),
        ("内存限制", "memory_limit=4GB", "2GB", "8GB"),
        ("端口配置", "port=8080", "3000", "9090"),
        ("重试次数", "max_retries=3", "1", "5"),
        ("批处理大小", "batch_size=1000", "500", "2000"),
    ]
    for i, (param_name, param_value, alt_a, alt_b) in enumerate(params):
        s = random.sample(SPEAKERS_TECH, 2)
        msgs = [
            {"speaker": s[0], "content": f"{param_name}设多少合适？"},
            {"speaker": s[1], "content": f"用{alt_a}吧"},
            {"speaker": s[0], "content": f"还是{param_value}更合理"},
            {"speaker": s[1], "content": f"好，那就{param_value}"},
        ]
        dialogue = make_dialogue(msgs, group=f"参数配置-{chr(65+i)}")
        dialogues.append(dialogue)
        content_options = {"A": alt_a, "B": param_value, "C": alt_b, "D": "暂不决定"}
        qa = make_qa([
            {"id": f"de_03_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "A", "options": {"A": "是，参数已锁定", "B": "否"}, "dimension": "detection"},
            {"id": f"de_03_{i:03d}_content", "Q": f"{param_name}最终设定为？", "A": "B", "options": content_options, "dimension": "content"},
            {"id": f"de_03_{i:03d}_proposer", "Q": "参数设置是谁提出的？", "A": "B", "options": {"A": s[0], "B": s[1], "C": "无法确定"}, "dimension": "proposer"},
            {"id": f"de_03_{i:03d}_executor", "Q": "这个配置由谁执行？", "A": "C", "options": {"A": s[0], "B": s[1], "C": "未明确指定"}, "dimension": "executor"},
            {"id": f"de_03_{i:03d}_impact", "Q": "这个决策的影响级别是？", "A": "B", "options": {"A": "major", "B": "minor", "C": "advisory"}, "dimension": "impact_level"},
            {"id": f"de_03_{i:03d}_status", "Q": "这个决策的当前状态是？", "A": "A", "options": {"A": "decided", "B": "in_progress", "C": "pending_confirmation"}, "dimension": "status"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_implicit_consensus():
    dialogues = []
    qas = []
    for i in range(15):
        s = random.sample(SPEAKERS_TECH, 2)
        pattern_idx = i % 3
        if pattern_idx == 0:
            phrase = random.choice(["确定了", "ok按你说的办", "好"])
            msgs = [
                {"speaker": s[0], "content": f"我建议用{TOPICS_FRAMEWORK[i % len(TOPICS_FRAMEWORK)]}"},
                {"speaker": s[1], "content": phrase},
            ]
        elif pattern_idx == 1:
            msgs = [
                {"speaker": s[0], "content": f"我用{TOPICS_FRAMEWORK[i % len(TOPICS_FRAMEWORK)]}重构吧"},
                {"speaker": s[1], "content": "可以"},
                {"speaker": s[0], "content": "那我开始做了"},
            ]
        else:
            msgs = [
                {"speaker": s[0], "content": f"用{TOPICS_INFRA[i % len(TOPICS_INFRA)]}部署，大家没意见吧"},
                {"speaker": s[1], "content": "👍"},
                {"speaker": s[0], "content": "那就定了"},
            ]
        dialogue = make_dialogue(msgs, group=f"隐式共识-{chr(65+i)}")
        dialogues.append(dialogue)
        qa = make_qa([
            {"id": f"de_04_{i:03d}_detection", "Q": "以上对话中是否形成了决策？", "A": "A", "options": {"A": "是，达成了共识", "B": "否，没有明确结论"}, "dimension": "detection"},
            {"id": f"de_04_{i:03d}_content", "Q": "达成的共识是什么？", "A": "A" if pattern_idx < 2 else "B", "options": {"A": "有技术方案共识", "B": "有部署方案共识", "C": "没有共识"}, "dimension": "content"},
            {"id": f"de_04_{i:03d}_proposer", "Q": "这个决策是谁提出的？", "A": "A", "options": {"A": s[0], "B": s[1], "C": "无法确定"}, "dimension": "proposer"},
            {"id": f"de_04_{i:03d}_executor", "Q": "谁负责执行？", "A": "C", "options": {"A": s[0], "B": s[1], "C": "未明确指定"}, "dimension": "executor"},
            {"id": f"de_04_{i:03d}_impact", "Q": "影响级别是？", "A": "B", "options": {"A": "major", "B": "minor", "C": "advisory"}, "dimension": "impact_level"},
            {"id": f"de_04_{i:03d}_status", "Q": "决策状态是？", "A": "A", "options": {"A": "decided", "B": "pending_confirmation", "C": "in_progress"}, "dimension": "status"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_conflict_decisions():
    dialogues = []
    qas = []
    conflicts = [
        ("MySQL", "PostgreSQL"),
        ("React", "Vue"),
        ("微服务", "单体架构"),
        ("timeout=30s", "timeout=60s"),
        ("Kubernetes", "Docker Compose"),
    ]
    for i, (choice_a, choice_b) in enumerate(conflicts):
        for copy in range(2):
            idx = i * 2 + copy
            s = random.sample(SPEAKERS_TECH, 3)
            msgs = [
                {"speaker": s[0], "content": f"用{choice_a}吧"},
                {"speaker": s[1], "content": "好"},
                {"speaker": s[0], "content": f"等等，还是用{choice_b}吧"},
                {"speaker": s[2], "content": f"为什么换{choice_b}？"},
                {"speaker": s[0], "content": f"{choice_b}更适合我们的场景"},
                {"speaker": s[1], "content": f"那就{choice_b}"},
            ]
            dialogue = make_dialogue(msgs, group=f"冲突决策-{chr(65+idx)}")
            dialogues.append(dialogue)
            qa = make_qa([
                {"id": f"de_05_{idx:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "A", "options": {"A": "是，有多个决策", "B": "否"}, "dimension": "detection"},
                {"id": f"de_05_{idx:03d}_content", "Q": "最终决定是什么？", "A": "B", "options": {"A": choice_a, "B": choice_b, "C": "未决定"}, "dimension": "content"},
                {"id": f"de_05_{idx:03d}_conflict", "Q": "对话中的决策是否存在冲突？", "A": "A", "options": {"A": "是，前后决策矛盾", "B": "否，不矛盾"}, "dimension": "conflict"},
                {"id": f"de_05_{idx:03d}_proposer", "Q": "最终决策是谁提出的？", "A": "A", "options": {"A": s[0], "B": s[1], "C": s[2], "D": "无法确定"}, "dimension": "proposer"},
                {"id": f"de_05_{idx:03d}_executor", "Q": "谁执行？", "A": "D", "options": {"A": s[0], "B": s[1], "C": s[2], "D": "未明确指定"}, "dimension": "executor"},
                {"id": f"de_05_{idx:03d}_impact", "Q": "影响级别是？", "A": "A", "options": {"A": "major", "B": "minor", "C": "advisory"}, "dimension": "impact_level"},
                {"id": f"de_05_{idx:03d}_status", "Q": "最终决策状态是？", "A": "A", "options": {"A": "decided", "B": "pending_confirmation", "C": "superseded"}, "dimension": "status"},
            ])
            qas.append(qa)
    return dialogues, qas


def generate_rejection_override():
    dialogues = []
    qas = []
    overrides = [
        ("Jenkins", "GitHub Actions"),
        ("Webpack", "Vite"),
        ("npm", "yarn"),
        ("Redux", "Zustand"),
        ("Flask", "FastAPI"),
    ]
    for i, (old, new) in enumerate(overrides):
        for copy in range(2):
            idx = i * 2 + copy
            s = random.sample(SPEAKERS_TECH, 3)
            msgs = [
                {"speaker": s[0], "content": f"之前定了用{old}，现在决定改用{new}"},
                {"speaker": s[1], "content": f"为什么换？"},
                {"speaker": s[0], "content": f"{new}性能更好"},
                {"speaker": s[2], "content": "同意"},
                {"speaker": s[0], "content": f"那就{new}了"},
            ]
            dialogue = make_dialogue(msgs, group=f"推翻决策-{chr(65+idx)}")
            dialogues.append(dialogue)
            qa = make_qa([
                {"id": f"de_06_{idx:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "A", "options": {"A": "是，做出了新决策", "B": "否"}, "dimension": "detection"},
                {"id": f"de_06_{idx:03d}_content", "Q": "最终决定用什么？", "A": "B", "options": {"A": old, "B": new, "C": "两个都用", "D": "都不选"}, "dimension": "content"},
                {"id": f"de_06_{idx:03d}_status", "Q": "旧决策的状态应该是？", "A": "C", "options": {"A": "decided", "B": "in_progress", "C": "superseded", "D": "completed"}, "dimension": "status"},
                {"id": f"de_06_{idx:03d}_proposer", "Q": "新决策是谁提出的？", "A": "A", "options": {"A": s[0], "B": s[1], "C": s[2], "D": "无法确定"}, "dimension": "proposer"},
                {"id": f"de_06_{idx:03d}_executor", "Q": "谁执行？", "A": "D", "options": {"A": s[0], "B": s[1], "C": s[2], "D": "未明确指定"}, "dimension": "executor"},
                {"id": f"de_06_{idx:03d}_impact", "Q": "影响级别是？", "A": "A", "options": {"A": "major", "B": "minor", "C": "advisory"}, "dimension": "impact_level"},
            ])
            qas.append(qa)
    return dialogues, qas


def generate_pure_discussion():
    dialogues = []
    qas = []
    for i in range(20):
        s = random.sample(SPEAKERS_TECH, 3)
        if i < 8:
            opts = random.sample(TOPICS_DB, 3)
            msgs = [
                {"speaker": s[0], "content": f"候选方案有{'、'.join(opts)}"},
                {"speaker": s[1], "content": f"{opts[0]}不错"},
                {"speaker": s[2], "content": f"{opts[1]}也可以"},
                {"speaker": s[0], "content": "大家再想想，下次会议定"},
            ]
        elif i < 15:
            tech = random.choice(TOPICS_DB + TOPICS_FRAMEWORK + TOPICS_INFRA)
            msgs = [
                {"speaker": s[0], "content": f"用{tech}怎么样？"},
                {"speaker": s[1], "content": "成本太高了"},
                {"speaker": s[2], "content": "但是性能好"},
                {"speaker": s[0], "content": "确实需要考虑一下"},
            ]
        else:
            msgs = [
                {"speaker": s[0], "content": "大家有什么需求？"},
                {"speaker": s[1], "content": "需要支持高并发"},
                {"speaker": s[2], "content": "还要方便扩展"},
                {"speaker": s[0], "content": "好的，我整理一下"},
            ]
        dialogue = make_dialogue(msgs, group=f"纯讨论-{chr(65+i)}")
        dialogues.append(dialogue)
        qa = make_qa([
            {"id": f"de_07_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "B", "options": {"A": "是", "B": "否，只是在讨论没有结论"}, "dimension": "detection"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_status_update():
    dialogues = []
    qas = []
    updates = [
        "已完成数据库迁移", "API改造正在进行中", "前端页面开发完成",
        "测试覆盖率已达80%", "部署脚本已写好", "文档正在更新",
        "代码审查进行中", "性能测试通过了", "环境配置完成",
        "日志系统已上线", "缓存优化已完成", "用户认证模块开发中",
        "接口联调进行中", "自动化测试已配置", "监控告警已接入",
    ]
    for i, update in enumerate(updates):
        s = random.sample(SPEAKERS_TECH, 2)
        msgs = [
            {"speaker": s[0], "content": update},
            {"speaker": s[1], "content": "收到，辛苦了"},
        ]
        dialogue = make_dialogue(msgs, group=f"状态更新-{chr(65+i)}")
        dialogues.append(dialogue)
        qa = make_qa([
            {"id": f"de_08_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "B", "options": {"A": "是", "B": "否，只是状态更新"}, "dimension": "detection"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_suggestion_only():
    dialogues = []
    qas = []
    suggestions = [
        "建议用Kubernetes", "我推荐使用GraphQL", "可以考虑用gRPC",
        "建议升级到Python3.12", "推荐用Redis做缓存",
    ]
    for i in range(15):
        s = random.sample(SPEAKERS_TECH, 2)
        suggestion = suggestions[i % len(suggestions)]
        msgs = [
            {"speaker": s[0], "content": suggestion},
            {"speaker": s[1], "content": "我了解一下"},
        ]
        dialogue = make_dialogue(msgs, group=f"建议-{chr(65+i)}")
        dialogues.append(dialogue)
        qa = make_qa([
            {"id": f"de_09_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "B", "options": {"A": "是", "B": "否，只是建议未落地"}, "dimension": "detection"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_small_talk():
    dialogues = []
    qas = []
    talks = [
        ("早上好", "早"), ("今晚吃火锅", "好呀"), ("周末去哪玩", "还没想好"),
        ("凌晨两点还在改bug，太累了", "辛苦了"), ("今天天气不错", "是啊"),
        ("新年快乐", "新年快乐"), ("午饭去吃啥", "随便"), ("这个周末加班吗", "不用"),
        ("团建去哪", "大家有建议吗"), ("下班了", "明天见"),
    ]
    for i, (talk_a, talk_b) in enumerate(talks):
        s = random.sample(SPEAKERS_TECH, 2)
        msgs = [
            {"speaker": s[0], "content": talk_a},
            {"speaker": s[1], "content": talk_b},
        ]
        dialogue = make_dialogue(msgs, group=f"闲聊-{chr(65+i)}")
        dialogues.append(dialogue)
        qa = make_qa([
            {"id": f"de_10_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "B", "options": {"A": "是", "B": "否，只是闲聊"}, "dimension": "detection"},
        ])
        qas.append(qa)
    return dialogues, qas


def generate_mixed_scenario():
    dialogues = []
    qas = []
    for i in range(20):
        s = random.sample(SPEAKERS_TECH, 3)
        if i < 10:
            db = random.choice(TOPICS_DB)
            msgs = [
                {"speaker": s[0], "content": "今天有三个议题"},
                {"speaker": s[0], "content": f"第一，数据库选型"},
                {"speaker": s[1], "content": f"用{db}吧"},
                {"speaker": s[2], "content": "同意"},
                {"speaker": s[0], "content": f"好，数据库定{db}"},
                {"speaker": s[0], "content": "第二，部署方案讨论"},
                {"speaker": s[1], "content": "Docker和K8s都可以"},
                {"speaker": s[2], "content": "下次再定吧"},
                {"speaker": s[0], "content": "第三，测试策略"},
                {"speaker": s[1], "content": "单元测试覆盖率目标讨论一下"},
                {"speaker": s[2], "content": "先定80%"},
                {"speaker": s[0], "content": "后续再调整"},
            ]
            has_decision = True
        else:
            msgs = [
                {"speaker": s[0], "content": "数据库和部署方案一起讨论下"},
                {"speaker": s[1], "content": "MySQL历史数据多"},
                {"speaker": s[2], "content": "Docker比较方便"},
                {"speaker": s[1], "content": "PG的功能更强"},
                {"speaker": s[0], "content": "下周找时间再讨论"},
            ]
            has_decision = False
        dialogue = make_dialogue(msgs, group=f"混合议题-{chr(65+i)}")
        dialogues.append(dialogue)
        if has_decision:
            qa = make_qa([
                {"id": f"de_11_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "A", "options": {"A": "是，部分议题有决策", "B": "否"}, "dimension": "detection"},
                {"id": f"de_11_{i:03d}_content", "Q": "哪个议题形成了决策？", "A": "A", "options": {"A": "数据库选型", "B": "部署方案", "C": "测试策略", "D": "都没有"}, "dimension": "content"},
                {"id": f"de_11_{i:03d}_status", "Q": "决策状态是？", "A": "A", "options": {"A": "decided", "B": "pending_confirmation", "C": "in_progress"}, "dimension": "status"},
                {"id": f"de_11_{i:03d}_proposer", "Q": "谁提出的？", "A": "B", "options": {"A": s[0], "B": s[1], "C": s[2], "D": "无法确定"}, "dimension": "proposer"},
                {"id": f"de_11_{i:03d}_executor", "Q": "谁执行？", "A": "D", "options": {"A": s[0], "B": s[1], "C": s[2], "D": "未明确指定"}, "dimension": "executor"},
                {"id": f"de_11_{i:03d}_impact", "Q": "影响级别是？", "A": "A", "options": {"A": "major", "B": "minor", "C": "advisory"}, "dimension": "impact_level"},
            ])
        else:
            qa = make_qa([
                {"id": f"de_11_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "B", "options": {"A": "是", "B": "否，没有形成任何决策"}, "dimension": "detection"},
            ])
        qas.append(qa)
    return dialogues, qas


def generate_boundary_case():
    dialogues = []
    qas = []
    boundary_cases = [
        ([{"speaker": "张三", "content": "我倾向于方案A，但最终由领导决定"}, {"speaker": "李四", "content": "等领导确认吧"}], False),
        ([{"speaker": "张三", "content": "approve the PR please"}, {"speaker": "李四", "content": "我来review"}], False),
        ([{"speaker": "张三", "content": "我决定辞职"}, {"speaker": "李四", "content": "什么时候走？"}], False),
        ([{"speaker": "张三", "content": "反对引入新的ORM框架，增加维护成本"}, {"speaker": "李四", "content": "有道理，再考虑一下"}], False),
        ([{"speaker": "张三", "content": "如果流量大的话可以考虑用Kafka"}, {"speaker": "李四", "content": "先记下来"}], False),
        ([{"speaker": "张三", "content": "先方案A上线，后续再优化"}, {"speaker": "李四", "content": "行"}], True),
        ([{"speaker": "张三", "content": "A方案成本低但风险高，B方案成本高但稳定"}, {"speaker": "李四", "content": "选A吧，先上线再说"}, {"speaker": "张三", "content": "好"}], True),
        ([{"speaker": "张三", "content": "这个API接口需要增加超时控制"}, {"speaker": "李四", "content": "设30s吧"}, {"speaker": "张三", "content": "可以"}], True),
        ([{"speaker": "张三", "content": "我们有三条路：A用原生Go、B用框架、C自己造轮子"}, {"speaker": "李四", "content": "B吧，效率高"}, {"speaker": "张三", "content": "那就B"}], True),
        ([{"speaker": "张三", "content": "好的收到"}], False),
    ]
    for i, (msgs, is_decision) in enumerate(boundary_cases):
        dialogue = make_dialogue(msgs, group=f"边界-{chr(65+i)}")
        dialogues.append(dialogue)
        if is_decision:
            qa = make_qa([
                {"id": f"de_12_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "A", "options": {"A": "是", "B": "否"}, "dimension": "detection"},
                {"id": f"de_12_{i:03d}_content", "Q": "决策内容是什么？", "A": "A", "options": {"A": "选择了具体方案", "B": "没有明确方案"}, "dimension": "content"},
            ])
        else:
            qa = make_qa([
                {"id": f"de_12_{i:03d}_detection", "Q": "以上对话中是否做出了决策？", "A": "B", "options": {"A": "是", "B": "否"}, "dimension": "detection"},
            ])
        qas.append(qa)
    return dialogues, qas


def main():
    generators = [
        ("01-technical-selection", generate_technical_selection),
        ("02-task-assignment", generate_task_assignment),
        ("03-parameter-lock", generate_parameter_lock),
        ("04-implicit-consensus", generate_implicit_consensus),
        ("05-conflict-decisions", generate_conflict_decisions),
        ("06-rejection-override", generate_rejection_override),
        ("07-pure-discussion", generate_pure_discussion),
        ("08-status-update", generate_status_update),
        ("09-suggestion-only", generate_suggestion_only),
        ("10-small-talk", generate_small_talk),
        ("11-mixed-scenario", generate_mixed_scenario),
        ("12-boundary-case", generate_boundary_case),
    ]
    print("Generating decision extraction evaluation dataset...")
    total_samples = 0
    total_qas = 0
    for dir_name, gen_func in generators:
        dialogues, qas = gen_func()
        write_scenario(dir_name, dialogues, qas)
        sample_count = len(dialogues)
        qa_count = sum(len(q.get("qars", [])) for q in qas)
        total_samples += sample_count
        total_qas += qa_count
        print(f"  {dir_name}: {sample_count} samples, {qa_count} QAs")
    print(f"\nTotal: {total_samples} samples, {total_qas} QAs")
    print("Dataset generation complete.")


if __name__ == "__main__":
    main()