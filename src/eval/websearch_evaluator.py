"""WebSearch 记忆评测维度分组：将 Pipeline 输出的实际决策与 websearch_context 真值对比，
计算提取精度、更新正确率、冲突检测/分辨、时效一致性、跨 session 召回、
多源合并质量、噪声过滤比等 7 项新增指标。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class WebSearchEvalMetrics:
    """单次 WebSearch 评测的结果指标"""
    extraction_accuracy: float = 0.0
    update_correctness: float = 0.0
    conflict_detection_rate: float = 0.0
    conflict_detection_fpr: float = 0.0
    conflict_resolution_accuracy: float = 0.0
    stale_consistency: float = 0.0
    cross_session_recall: float = 0.0
    merge_quality: float = 0.0
    noise_filter_ratio: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "extraction_accuracy": round(self.extraction_accuracy, 4),
            "update_correctness": round(self.update_correctness, 4),
            "conflict_detection_rate": round(self.conflict_detection_rate, 4),
            "conflict_detection_fpr": round(self.conflict_detection_fpr, 4),
            "conflict_resolution_accuracy": round(self.conflict_resolution_accuracy, 4),
            "stale_consistency": round(self.stale_consistency, 4),
            "cross_session_recall": round(self.cross_session_recall, 4),
            "merge_quality": round(self.merge_quality, 4),
            "noise_filter_ratio": round(self.noise_filter_ratio, 4),
        }


def _topic_match(expected_topic: str, actual_topic: str) -> bool:
    return expected_topic and actual_topic and expected_topic == actual_topic


def _summary_match(expected_summary: str, actual_summary: str, threshold: float = 0.3) -> bool:
    """基于字符重叠率的摘要匹配"""
    if not expected_summary or not actual_summary:
        return False
    e_chars = set(expected_summary.lower())
    a_chars = set(actual_summary.lower())
    if not e_chars or not a_chars:
        return False
    intersection = e_chars & a_chars
    similarity = len(intersection) / max(len(e_chars), len(a_chars))
    return similarity >= threshold


def _extract_scenario_id(expected: Dict[str, Any]) -> str:
    """从 expected 行提取 websearch 场景 ID"""
    return expected.get("websearch_scenario_id", "")


def _get_effect_type(expected: Dict[str, Any]) -> str:
    return expected.get("expected_effect_type", "")


def classify_expected_lines(expected_lines: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """将 expected.jsonl 行按场景 ID 分类"""
    by_scenario: Dict[str, List[Dict[str, Any]]] = {}
    for line in expected_lines:
        sid = _extract_scenario_id(line) or "unknown"
        if sid not in by_scenario:
            by_scenario[sid] = []
        by_scenario[sid].append(line)
    return by_scenario


class WebSearchComparator:
    """WebSearch 维度比对器：接受 expected.jsonl + 实际决策列表，
    分场景计算 7 项新增指标。

    Usage:
        wc = WebSearchComparator(expected_path)
        wc.match(actual_decisions)
        metrics = wc.compute_metrics()
    """

    def __init__(self, expected_path: str):
        self._expected_path = expected_path
        self._expected_lines: List[Dict[str, Any]] = []
        self._actual_decisions: List[Dict[str, Any]] = []
        # 各指标内部计数器
        self._extraction_tp = 0
        self._extraction_total = 0
        self._update_correct = 0
        self._update_total = 0
        self._conflict_detected_tp = 0
        self._conflict_detected_fn = 0
        self._conflict_detected_fp = 0
        self._conflict_non_conflict_total = 0
        self._conflict_resolved_correct = 0
        self._conflict_resolved_total = 0
        self._stale_consistent = 0
        self._stale_total = 0
        self._cross_session_correct = 0
        self._cross_session_total = 0
        self._merge_correct = 0
        self._merge_total = 0
        self._noise_filtered_correct = 0
        self._noise_total = 0
        self._load_expected()

    def _load_expected(self) -> None:
        path = Path(self._expected_path)
        if not path.exists():
            raise FileNotFoundError(f"Expected file not found: {self._expected_path}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._expected_lines.append(json.loads(line))

    def match(self, actual_decisions: List[Dict[str, Any]]) -> None:
        """匹配实际决策与 websearch 预期，累计计数

        Args:
            actual_decisions: graph.get_all_decisions() 的决策列表，
                每条至少包含 topic_id, summary, chat_id 字段。
        """
        self._actual_decisions = list(actual_decisions)
        self._reset_counts()

        # 构建 actual 索引：{(chat_id, topic_id) → [decisions]}
        actual_by_chat_topic: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for d in self._actual_decisions:
            key = (d.get("chat_id", ""), d.get("topic_id", ""))
            if key not in actual_by_chat_topic:
                actual_by_chat_topic[key] = []
            actual_by_chat_topic[key].append(d)

        for exp in self._expected_lines:
            sid = _extract_scenario_id(exp)
            effect_type = _get_effect_type(exp)
            chat_id = exp.get("chat_id", "")
            exp_topic = exp.get("expected_topic", "")
            exp_summary = exp.get("expected_summary", "")
            exp_effect_summary = exp.get("expected_effect_summary", "")
            has_conflict = exp.get("conflict_with_prior", False)
            expected_status = exp.get("expected_status", "")

            # Skip lines with no scenario_id (e.g. stale_no_change or system-only markers)
            if not sid or sid == "unknown":
                continue

            # 获取实际决策：同一 (chat_id, topic_id) 下
            actual_list = actual_by_chat_topic.get((chat_id, exp_topic), [])

            # 找最佳匹配的 actual
            best_match = None
            best_score = 0.0
            for act in actual_list:
                score = _summary_match(exp_effect_summary or exp_summary, act.get("summary", ""))
                if score and score > best_score:
                    best_score = score
                    best_match = act

            matched = best_match is not None

            # === Dimension 1: Extraction accuracy (scenario: web_simple_extract) ===
            # Phase 3 uses scenario_id to differentiate; effect_type="new_decision" is shared
            if sid == "web_simple_extract":
                self._extraction_total += 1
                if matched:
                    self._extraction_tp += 1

            # === Dimension 2: Update correctness (scenario: web_fact_update) ===
            if sid == "web_fact_update":
                self._update_total += 1
                if matched:
                    act_summary = best_match.get("summary", "")
                    if _summary_match(exp_effect_summary, act_summary, threshold=0.3):
                        self._update_correct += 1

            # === Dimension 3 + 4: Conflict detection & resolution ===
            if has_conflict:
                self._conflict_detected_fn += 1  # assume not detected; matched = detected
                if matched:
                    self._conflict_detected_tp += 1
                    self._conflict_detected_fn -= 1
                    # Conflict resolution: only scored when conflict was detected
                    self._conflict_resolved_total += 1
                    if _summary_match(exp_effect_summary or exp_summary, best_match.get("summary", ""), threshold=0.3):
                        self._conflict_resolved_correct += 1
            else:
                # Non-conflict cases for FPR counting
                self._conflict_non_conflict_total += 1

            # === Dimension 5: Stale consistency (scenario: web_stale_rejection) ===
            if sid == "web_stale_rejection":
                self._stale_total += 1
                # Correct = system correctly did NOT create a new decision for stale info
                # stale entries have effect_type="reject_decision" or "no_change"
                if not matched:
                    self._stale_consistent += 1

            # === Dimension 6: Cross-session recall (scenario: web_cross_session) ===
            if sid == "web_cross_session":
                self._cross_session_total += 1
                if matched:
                    act_summary = best_match.get("summary", "")
                    if _summary_match(exp_effect_summary or exp_summary, act_summary, threshold=0.3):
                        self._cross_session_correct += 1

            # === Dimension 7: Merge quality (scenario: web_multi_source_merge) ===
            if sid == "web_multi_source_merge":
                self._merge_total += 1
                if matched and _summary_match(exp_effect_summary or exp_summary, best_match.get("summary", ""), threshold=0.3):
                    self._merge_correct += 1

            # === Dimension 8: Noise filter ratio (scenario: web_distractor_tolerance) ===
            # For noise scenario, each expected.jsonl line represents a message.
            # Messages where expected_effect_type="new_decision" should produce a decision;
            # messages where expected_effect_type="no_change" are distractors that should be filtered.
            if sid == "web_distractor_tolerance":
                self._noise_total += 1
                expected_effect_type = effect_type
                if expected_effect_type == "new_decision" and matched:
                    self._noise_filtered_correct += 1
                elif expected_effect_type in ("no_change", "") and not matched:
                    self._noise_filtered_correct += 1

    def _reset_counts(self) -> None:
        self._extraction_tp = 0
        self._extraction_total = 0
        self._update_correct = 0
        self._update_total = 0
        self._conflict_detected_tp = 0
        self._conflict_detected_fn = 0
        self._conflict_detected_fp = 0
        self._conflict_non_conflict_total = 0
        self._conflict_resolved_correct = 0
        self._conflict_resolved_total = 0
        self._stale_consistent = 0
        self._stale_total = 0
        self._cross_session_correct = 0
        self._cross_session_total = 0
        self._merge_correct = 0
        self._merge_total = 0
        self._noise_filtered_correct = 0
        self._noise_total = 0

    def compute_metrics(self) -> WebSearchEvalMetrics:
        m = WebSearchEvalMetrics()
        m.extraction_accuracy = (self._extraction_tp / self._extraction_total
                                 if self._extraction_total > 0 else 0.0)
        m.update_correctness = (self._update_correct / self._update_total
                                if self._update_total > 0 else 0.0)
        m.conflict_detection_rate = (self._conflict_detected_tp /
                                     (self._conflict_detected_tp + self._conflict_detected_fn)
                                     if (self._conflict_detected_tp + self._conflict_detected_fn) > 0 else 0.0)
        m.conflict_detection_fpr = (self._conflict_detected_fp / self._conflict_non_conflict_total
                                    if self._conflict_non_conflict_total > 0 else 0.0)
        m.conflict_resolution_accuracy = (self._conflict_resolved_correct / self._conflict_resolved_total
                                          if self._conflict_resolved_total > 0 else 0.0)
        m.stale_consistency = (self._stale_consistent / self._stale_total
                               if self._stale_total > 0 else 0.0)
        m.cross_session_recall = (self._cross_session_correct / self._cross_session_total
                                  if self._cross_session_total > 0 else 0.0)
        m.merge_quality = (self._merge_correct / self._merge_total
                           if self._merge_total > 0 else 0.0)
        m.noise_filter_ratio = (self._noise_filtered_correct / self._noise_total
                                if self._noise_total > 0 else 0.0)
        return m

    def to_dict(self) -> Dict[str, Any]:
        return self.compute_metrics().to_dict()


def compute_websearch_cross_session_recall(
    session2_expected_path: str,
    cross_session_expected_path: str,
    actual_decisions: List[Dict[str, Any]],
) -> float:
    """独立计算跨 session 召回率：检查 Session 2 中能否检索到 Session 1 的记忆。

    Matches cross_session_expected 中的摘要与 actual_decisions。
    """
    expected_paths = [session2_expected_path, cross_session_expected_path]
    expected_lines: List[Dict[str, Any]] = []
    for p in expected_paths:
        path = Path(p)
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    expected_lines.append(json.loads(line))

    correct = 0
    total = 0
    matched_topics: set = set()
    for act in actual_decisions:
        key = (act.get("chat_id", ""), act.get("topic_id", ""))
        if key not in matched_topics and act.get("topic_id"):
            matched_topics.add(key)

    for exp in expected_lines:
        effect_summary = exp.get("expected_effect_summary") or exp.get("expected_summary", "")
        exp_topic = exp.get("expected_topic", "")
        chat_id = exp.get("chat_id", "")
        if not effect_summary:
            continue
        total += 1
        # 检查实际决策中是否有匹配的
        for act in actual_decisions:
            if act.get("chat_id", "") != chat_id:
                continue
            if _topic_match(exp_topic, act.get("topic_id", "")):
                if _summary_match(effect_summary, act.get("summary", ""), threshold=0.3):
                    correct += 1
                    break

    return correct / total if total > 0 else 0.0