from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.eval import (
    load_extraction_dialogue,
    load_extraction_qa,
    list_extraction_scenarios,
)
from src.llm.client import LLMClient
from src.config import get_storage_path
from src.storage.git_storage import GitStorage, GitStorageConfig, GitStorageError


EXTRACTION_SYSTEM_PROMPT = "你是一个对话决策分析专家。根据对话内容做选择题，只输出选项字母（A/B/C/D），不要输出其他内容。"

DIMENSION_GUIDE = {
    "detection": "",
    "content": "",
    "proposer": "\n【重要规则】提议者判断标准：\n- 提议者是第一个提出具体数值/方案的人\n- 场景：A问\"参数X设多少？\" B答\"用Y吧\" → 提议者是B（第一个给具体值的人）\n- 如果有人先问问题再自己给出更好的值，这个更好值的人仍然是第一个提出具体值的人\n- 最后总结确认的人（\"好，那就Z\"）不是提议者\n注意：只输出选项字母，不要输出解释。",
    "executor": "\n【重要规则】执行人判断标准：\n- 当对话中出现明确指派句式如\"某人来负责X\"\"X由某人做\"\"某人来做X\"时，执行人就是被指派的那个人\n- 如果有人问\"X谁来做？\"然后有人说\"我来吧\"，执行人是主动承担的人\n- 注意：选项字母对应不同的人名，请直接看各选项内容判断谁是被指派的人\n- 关键：仔细阅读对话，找到具体的指派语句，然后看对应的选项内容。只输出选项字母。",
    "impact_level": "\n【重要规则】影响级别判断标准：\n- major（重大变更）：涉及架构/技术栈替换、跨团队影响、核心流程重构，如数据库选型、框架替换\n- minor（常规变更）：在现有框架内调整参数/配置/方案，如更改阈值、锁定参数\n- advisory（建议级别）：仅供参考，非强制性",
    "status": "\n判断提示：\n- decided（已确定）：有人拍板定案，达成共识\n- in_progress（执行中）：明确提到正在做\n- completed（已完成）：明确说做完了\n- pending_confirmation（待确认）：还需要确认",
    "conflict": "\n【重要规则】冲突判断标准：\n- 当某人提出方案并得到确认（\"好\"），然后立即改口用另一个方案，就构成前后矛盾\n- 示例：甲\"用MySQL\"乙\"好\"→甲\"等等还是用PostgreSQL\"乙\"那就PostgreSQL\"→这是矛盾（前面说了MySQL后面推翻）\n- 仅仅讨论不同可能性（\"用A还是B？\"\"B不错\"\"A也行\"）没有确认过决定，不构成矛盾\n- 关键：看是否有\"明确确认后又反悔\"的模式",
}


@dataclass
class EvalResult:
    scenario: str
    dim_results: dict[str, list[bool]] = field(default_factory=dict)
    dim_accuracies: dict[str, float] = field(default_factory=dict)
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0
    token_summary: dict[str, int] = field(default_factory=dict)
    storage_stored: int = 0
    storage_verified: int = 0
    storage_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "dim_accuracies": self.dim_accuracies,
            "total": self.total,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "token_summary": self.token_summary,
            "storage_stored": self.storage_stored,
            "storage_verified": self.storage_verified,
            "storage_failed": self.storage_failed,
        }


@dataclass
class SummaryReport:
    scenario_results: list[EvalResult] = field(default_factory=list)
    overall_accuracy: float = 0.0
    overall_dim_accuracies: dict[str, float] = field(default_factory=dict)
    total_calls: int = 0
    total_tokens: int = 0
    total_stored: int = 0
    total_verified: int = 0
    total_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_accuracy": self.overall_accuracy,
            "overall_dim_accuracies": self.overall_dim_accuracies,
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_stored": self.total_stored,
            "total_verified": self.total_verified,
            "total_failed": self.total_failed,
            "scenarios": [r.to_dict() for r in self.scenario_results],
        }


def format_dialogue(dialogue_data: dict[str, Any]) -> str:
    lines: list[str] = []
    for date_key, conversations in dialogue_data.get("dialogues", {}).items():
        for conv_name, turns in conversations.items():
            lines.append(f"[{date_key} - {conv_name}]")
            for turn in turns:
                lines.append(f"  {turn.get('speaker', 'Unknown')}: {turn.get('dialogue', '')}")
            lines.append("")
    return "\n".join(lines)


def select_sub_dialogue(turns: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for turn in turns:
        lines.append(f"{turn.get('speaker', 'Unknown')}: {turn.get('dialogue', '')}")
    return "\n".join(lines)


def extract_all_conversations(dialogue_data: dict[str, Any]) -> list[tuple[str, str, str, list[dict[str, str]]]]:
    convs: list[tuple[str, str, str, list[dict[str, str]]]] = []
    for date_key, conversations in dialogue_data.get("dialogues", {}).items():
        for conv_name, turns in conversations.items():
            convs.append((date_key, conv_name, f"{date_key} - {conv_name}", turns))
    return convs


def _normalize_answer(raw: str, valid_keys: list[str]) -> str:
    cleaned = raw.strip().upper()
    for k in valid_keys:
        if cleaned.startswith(k.upper()):
            return k.upper()
    for token in cleaned.split():
        if token in valid_keys:
            return token
    return cleaned[:1] if cleaned else ""


def evaluate_extraction(
    llm_client: LLMClient,
    scenario: str,
    max_tokens: int = 10,
    storage: Optional[GitStorage] = None,
) -> EvalResult:
    dialogue_data = load_extraction_dialogue(scenario)
    qa_data = load_extraction_qa(scenario)
    assert dialogue_data is not None, f"dialogue.json not found for {scenario}"
    assert qa_data is not None, f"qa.json not found for {scenario}"

    conversations = extract_all_conversations(dialogue_data)
    qa_items = qa_data.get("qars", [])
    if not qa_items:
        return EvalResult(scenario=scenario)

    items_by_id: dict[str, dict[str, Any]] = {}
    for item in qa_items:
        parts = item["id"].rsplit("_", 1)
        prefix = parts[0]
        if prefix not in items_by_id:
            items_by_id[prefix] = []
        items_by_id[prefix].append(item)

    dim_correct: dict[str, list[bool]] = {}
    total = 0
    correct = 0
    storage_stored = 0
    storage_verified = 0
    storage_failed = 0

    qa_groups = list(items_by_id.values())

    for group_idx, group in enumerate(qa_groups):
        if group_idx >= len(conversations):
            break
        _, _, conv_label, turns = conversations[group_idx]
        dialogue_text = select_sub_dialogue(turns)

        for qa_item in group:
            question = qa_item["Q"]
            expected = qa_item["A"]
            options = qa_item.get("options", {})
            options_text = "\n".join(f"{k}. {v}" for k, v in options.items())
            dim = qa_item.get("dimension", "unknown")
            guide = DIMENSION_GUIDE.get(dim, "")

            user_content = f"对话内容：\n{dialogue_text}\n\n问题：{question}\n\n选项：\n{options_text}{guide}\n\n请只输出一个选项字母（{', '.join(options.keys())}）。"

            messages = [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            raw_answer = llm_client.chat(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            answer = _normalize_answer(raw_answer, list(options.keys()))
            is_correct = answer == expected.upper()
            if dim not in dim_correct:
                dim_correct[dim] = []
            dim_correct[dim].append(is_correct)
            total += 1
            if is_correct:
                correct += 1

        if storage:
            try:
                expected_by_dim = {item["dimension"]: item for item in group}
                sid = group[0]["id"].rsplit("_", 1)[0]
                content_item = expected_by_dim.get("content")
                executor_item = expected_by_dim.get("executor")
                proposer_item = expected_by_dim.get("proposer")
                status_item = expected_by_dim.get("status")
                impact_item = expected_by_dim.get("impact_level")

                decision: dict[str, Any] = {
                    "sid": sid,
                    "topic_id": scenario,
                    "project": "eval",
                    "full_text": dialogue_text,
                    "source_type": "eval",
                }
                if content_item:
                    decision["summary"] = content_item["options"].get(content_item["A"], "")
                if executor_item:
                    decision["assignee"] = executor_item["options"].get(executor_item["A"], "")
                if proposer_item:
                    decision["authority"] = proposer_item["options"].get(proposer_item["A"], "")
                if status_item:
                    decision["status"] = status_item["options"].get(status_item["A"], "")
                if impact_item:
                    decision["impact_level"] = impact_item["options"].get(impact_item["A"], "")

                commit_hash = storage.write_decision(decision)
                stored_count = 1
                verified_count = 0
                if commit_hash:
                    read_back = storage.read_decision("eval", scenario, sid)
                    if read_back and read_back.get("sid", "") == sid:
                        verified_count = 1
                storage_stored += stored_count
                storage_verified += verified_count
            except (GitStorageError, Exception):
                storage_failed += 1

    dim_accuracies = {
        dim: sum(results) / len(results) if results else 0.0
        for dim, results in dim_correct.items()
    }

    result = EvalResult(
        scenario=scenario,
        dim_results=dim_correct,
        dim_accuracies=dim_accuracies,
        total=total,
        correct=correct,
        accuracy=correct / total if total > 0 else 0.0,
        token_summary=llm_client.token_tracker.summary(),
        storage_stored=storage_stored,
        storage_verified=storage_verified,
        storage_failed=storage_failed,
    )
    return result


def run_extraction_eval(
    llm_client: LLMClient,
    scenarios: Optional[list[str]] = None,
    max_tokens: int = 10,
    enable_storage: bool = False,
) -> SummaryReport:
    if scenarios is None:
        scenarios = list_extraction_scenarios()

    storage: Optional[GitStorage] = None
    if enable_storage:
        storage = GitStorage(config=GitStorageConfig(work_dir=get_storage_path()))

    llm_client.token_tracker.reset()
    results: list[EvalResult] = []

    for scenario in scenarios:
        result = evaluate_extraction(llm_client, scenario, max_tokens=max_tokens, storage=storage)
        results.append(result)

    all_dim_correct: dict[str, list[bool]] = {}
    total_correct = 0
    total_q = 0
    total_stored = 0
    total_verified = 0
    total_failed = 0
    for r in results:
        total_correct += r.correct
        total_q += r.total
        total_stored += r.storage_stored
        total_verified += r.storage_verified
        total_failed += r.storage_failed
        for dim, outcomes in r.dim_results.items():
            if dim not in all_dim_correct:
                all_dim_correct[dim] = []
            all_dim_correct[dim].extend(outcomes)

    overall_dim_accuracies = {
        dim: sum(v) / len(v) if v else 0.0
        for dim, v in all_dim_correct.items()
    }

    token_summary = llm_client.token_tracker.summary()

    return SummaryReport(
        scenario_results=results,
        overall_accuracy=total_correct / total_q if total_q > 0 else 0.0,
        overall_dim_accuracies=overall_dim_accuracies,
        total_calls=token_summary["call_count"],
        total_tokens=token_summary["total_tokens"],
        total_stored=total_stored,
        total_verified=total_verified,
        total_failed=total_failed,
    )