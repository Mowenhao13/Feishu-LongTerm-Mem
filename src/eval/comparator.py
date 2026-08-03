"""决策比对器：将 Pipeline 输出的实际决策与 expected.jsonl 真值对比，
计算精度/召回/F1 等指标。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class EvalComparator:
    """比较实际决策与预期真值，计算评估指标。

    Usage:
        comparator = EvalComparator("eval_dataset/single_chat/expected.jsonl")
        comparator.match(actual_decisions)
        report = comparator.compute_metrics()
    """

    def __init__(self, expected_path: str, embedding_provider: Optional[Any] = None):
        self._expected_path = expected_path
        self._embedder = embedding_provider
        self._expected_decisions: List[Dict[str, Any]] = []
        self._actual_decisions: List[Dict[str, Any]] = []
        self._true_positives: List[Tuple[Dict, Dict]] = []  # (expected, actual)
        self._false_positives: List[Dict] = []
        self._false_negatives: List[Dict] = []
        self._load_expected()

    def _load_expected(self) -> None:
        """加载 expected.jsonl 真值，只保留 expected_decision=true 的行"""
        path = Path(self._expected_path)
        if not path.exists():
            raise FileNotFoundError(f"Expected file not found: {self._expected_path}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    decision = json.loads(line)
                    if decision.get("expected_decision"):
                        self._expected_decisions.append(decision)

    @staticmethod
    def _summary_similarity(s1: str, s2: str) -> float:
        """基于字符重叠率的摘要相似度（回退方案）"""
        if not s1 or not s2:
            return 0.0
        s1_chars = set(s1.lower())
        s2_chars = set(s2.lower())
        if not s1_chars or not s2_chars:
            return 0.0
        intersection = s1_chars & s2_chars
        return len(intersection) / max(len(s1_chars), len(s2_chars))

    def _build_similarity_matrix(self) -> Optional[np.ndarray]:
        """使用 embedding 构建期望决策与实际决策的余弦相似度矩阵

        Returns:
            shape=(n_expected, n_actual) 的 cosine similarity 矩阵，
            如果 embedding 不可用或失败返回 None。
        """
        if not self._embedder:
            return None

        exp_summaries = [(e.get("expected_summary") or "").strip() for e in self._expected_decisions]
        act_summaries = [(a.get("summary") or "").strip() for a in self._actual_decisions]

        # 收集所有非空摘要，去重后 batch embed
        all_texts = list(set(s for s in exp_summaries + act_summaries if s))
        if not all_texts:
            return None

        try:
            vectors = self._embedder.embed(all_texts)
        except Exception as e:
            logger.warning("Embedding similarity failed, falling back to char: %s", e)
            return None

        vec_map = dict(zip(all_texts, vectors))
        dim = len(vectors[0]) if vectors else 0

        def _get_vec(text: str) -> np.ndarray:
            if text in vec_map:
                return np.array(vec_map[text])
            return np.zeros(dim)

        # 构建余弦相似度矩阵
        n_exp = len(self._expected_decisions)
        n_act = len(self._actual_decisions)
        matrix = np.zeros((n_exp, n_act))

        for ei in range(n_exp):
            v1 = _get_vec(exp_summaries[ei])
            n1 = np.linalg.norm(v1)
            if n1 == 0:
                continue
            for ai in range(n_act):
                v2 = _get_vec(act_summaries[ai])
                n2 = np.linalg.norm(v2)
                if n2 > 0:
                    matrix[ei][ai] = float(np.dot(v1, v2) / (n1 * n2))

        return matrix

    def match(self, actual_decisions: List[Dict[str, Any]]) -> None:
        """将实际决策与真值进行匹配

        Args:
            actual_decisions: graph.get_all_decisions() 的决策列表，
                每条至少包含 topic_id, summary 字段。
        """
        self._actual_decisions = list(actual_decisions)
        self._true_positives = []
        self._false_positives = []
        self._false_negatives = []

        # 预计算 embedding 相似度矩阵（语义匹配优先）
        similarity_matrix = self._build_similarity_matrix()
        use_semantic = similarity_matrix is not None
        if use_semantic:
            logger.info("[Comparator] Using embedding similarity (%d x %d matrix)",
                        similarity_matrix.shape[0], similarity_matrix.shape[1])

        matched_actual = set()

        for ei, expected in enumerate(self._expected_decisions):
            expected_topic = (expected.get("expected_topic") or "").strip()
            expected_summary = (expected.get("expected_summary") or "").strip()
            expected_suggestion = bool(expected.get("is_suggestion", False))
            best_match_idx = None
            best_score = 0.0

            for ai, actual in enumerate(self._actual_decisions):
                if ai in matched_actual:
                    continue
                actual_topic = (actual.get("topic_id") or "").strip()
                actual_summary = (actual.get("summary") or "").strip()
                actual_suggestion = bool(actual.get("is_suggestion", False))

                # chat_id 必须匹配（多群模式下，不同群的决策不能互相匹配）
                expected_chat = expected.get("chat_id", "")
                actual_chat = actual.get("chat_id", "")
                if expected_chat and actual_chat and expected_chat != actual_chat:
                    continue

                # 话题必须匹配（但 actual_topic 为 "general" 时跳过话题约束，仅依赖 summary 匹配）
                if expected_topic and actual_topic and actual_topic != "general" and expected_topic != actual_topic:
                    continue

                # suggestion 类型匹配：同类型完全匹配优先，跨类型允许但需更高相似度
                type_match = expected_suggestion == actual_suggestion
                min_score = 0.3 if type_match else 0.45  # 跨类型需要更高的 summary 相似度

                if use_semantic:
                    score = float(similarity_matrix[ei][ai])
                else:
                    score = self._summary_similarity(expected_summary, actual_summary)

                if score >= min_score and score > best_score:
                    best_score = score
                    best_match_idx = ai

            if best_match_idx is not None:
                matched_actual.add(best_match_idx)
                self._true_positives.append((
                    expected,
                    self._actual_decisions[best_match_idx],
                ))
            else:
                self._false_negatives.append(expected)

        # 收集所有预期话题，同主题的子决策不计入误检
        expected_topics = {
            (e.get("expected_topic") or "").strip()
            for e in self._expected_decisions
            if e.get("expected_topic")
        }

        for i, actual in enumerate(self._actual_decisions):
            if i not in matched_actual:
                # 建议型决策不计入误检
                if actual.get("is_suggestion", False):
                    continue
                # 同主题下的子决策不计入误检
                actual_topic = (actual.get("topic_id") or "").strip()
                if actual_topic and actual_topic in expected_topics:
                    continue
                # generic/general 类型的决策不计入误检（泛化/上下文型）
                if actual_topic in ("general", "unknown", ""):
                    continue
                self._false_positives.append(actual)

    def compute_metrics(self) -> Dict[str, Any]:
        """计算评估指标"""
        tp = len(self._true_positives)
        fp = len(self._false_positives)
        fn = len(self._false_negatives)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # 区分决策和建议的统计
        decision_tp = 0
        decision_fn = 0
        suggestion_tp = 0
        suggestion_fn = 0
        topic_correct = 0
        status_correct = 0
        for exp, act in self._true_positives:
            exp_topic = exp.get("expected_topic", "")
            act_topic = act.get("topic_id", "")
            if exp_topic and act_topic and exp_topic == act_topic:
                topic_correct += 1
            exp_status = exp.get("expected_status", "")
            act_status = act.get("status", "")
            if exp_status and act_status and exp_status == act_status:
                status_correct += 1
            if exp.get("is_suggestion", False):
                suggestion_tp += 1
            else:
                decision_tp += 1

        for exp in self._false_negatives:
            if exp.get("is_suggestion", False):
                suggestion_fn += 1
            else:
                decision_fn += 1

        decision_precision = decision_tp / (tp + fp) if (tp + fp) > 0 else 0.0
        decision_recall = decision_tp / (decision_tp + decision_fn) if (decision_tp + decision_fn) > 0 else 0.0
        suggestion_recall = suggestion_tp / (suggestion_tp + suggestion_fn) if (suggestion_tp + suggestion_fn) > 0 else 0.0

        return {
            "total_expected": len(self._expected_decisions),
            "total_detected": len(self._actual_decisions),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "decision_metrics": {
                "decision_tp": decision_tp,
                "decision_fn": decision_fn,
                "decision_precision": round(decision_precision, 4),
                "decision_recall": round(decision_recall, 4),
                "suggestion_tp": suggestion_tp,
                "suggestion_fn": suggestion_fn,
                "suggestion_recall": round(suggestion_recall, 4),
            },
            "dimension_accuracy": {
                "topic": round(topic_correct / tp, 4) if tp > 0 else 0.0,
                "status": round(status_correct / tp, 4) if tp > 0 else 0.0,
            },
        }

    def report_by_topic(self) -> Dict[str, Dict[str, float]]:
        """按话题拆解指标"""
        topics: Dict[str, Dict] = {}
        for exp, act in self._true_positives:
            t = exp.get("expected_topic", "unknown")
            if t not in topics:
                topics[t] = {"tp": 0, "fp": 0, "fn": 0}
            topics[t]["tp"] += 1
        for exp in self._false_negatives:
            t = exp.get("expected_topic", "unknown")
            if t not in topics:
                topics[t] = {"tp": 0, "fp": 0, "fn": 0}
            topics[t]["fn"] += 1
        for act in self._false_positives:
            t = act.get("topic_id", "unknown")
            if t not in topics:
                topics[t] = {"tp": 0, "fp": 0, "fn": 0}
            topics[t]["fp"] += 1

        result = {}
        for t, v in topics.items():
            p = v["tp"] / (v["tp"] + v["fp"]) if (v["tp"] + v["fp"]) > 0 else 0.0
            r = v["tp"] / (v["tp"] + v["fn"]) if (v["tp"] + v["fn"]) > 0 else 0.0
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            result[t] = {
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f, 4),
            }
        return result

    def report_by_chat(self) -> Dict[str, Dict[str, Any]]:
        """按群聊拆解指标（多群模式）"""
        chats: Dict[str, Dict] = {}
        for exp in self._expected_decisions:
            cid = exp.get("chat_id", "unknown")
            if cid not in chats:
                chats[cid] = {"expected": 0, "tp": 0, "fn": 0, "fp": 0}
            chats[cid]["expected"] += 1
        for exp, act in self._true_positives:
            cid = exp.get("chat_id", "unknown")
            if cid in chats:
                chats[cid]["tp"] += 1
        for exp in self._false_negatives:
            cid = exp.get("chat_id", "unknown")
            if cid in chats:
                chats[cid]["fn"] += 1

        isolation_issues = 0
        total_chat_expected = sum(v["expected"] for v in chats.values())
        for act in self._false_positives:
            if "chat_id" not in act:
                continue
            expected_match = None
            for exp, a in self._true_positives:
                if a is act:
                    expected_match = exp
                    break
            if expected_match and expected_match.get("chat_id") != act.get("chat_id"):
                isolation_issues += 1

        result = {}
        for cid, v in chats.items():
            p = v["tp"] / (v["tp"] + v["fp"]) if (v["tp"] + v["fp"]) > 0 else 0.0
            r = v["tp"] / (v["tp"] + v["fn"]) if (v["tp"] + v["fn"]) > 0 else 0.0
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            result[cid] = {
                "expected": v["expected"],
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f, 4),
            }

        result["_isolation"] = {
            "issues": isolation_issues,
            "score": round(
                1.0 - (isolation_issues / total_chat_expected) if total_chat_expected > 0 else 1.0,
                4,
            ),
        }
        return result

    def to_dict(self) -> Dict[str, Any]:
        """输出完整报告"""
        metrics = self.compute_metrics()
        return {
            **metrics,
            "by_topic": self.report_by_topic(),
            "by_chat": self.report_by_chat(),
        }


class ExpandedEvalComparator(EvalComparator):
    """扩展的决策比对器 — 新增 Phase 2 高级评估指标

    - Temporal cross-session recall consistency
    - Recall-vs-time decay measurement
    - Cross-chat isolation score
    - False-positive robustness analysis
    """

    def __init__(self, expected_path: str, embedding_provider=None):
        super().__init__(expected_path, embedding_provider)
        # 跨 session 指标
        self._session_boundaries: List[Dict[str, Any]] = []
        # 时间衰减记录
        self._recall_by_session_gap: Dict[int, Dict[str, int]] = {}
        # 跨 chat 隔离记录
        self._cross_chat_leakage: List[Dict[str, Any]] = []
        # FP 鲁棒性数据
        self._fp_by_noise_ratio: Dict[float, Dict[str, int]] = {}

    def load_session_boundaries(self, boundary_path: str) -> None:
        """加载 session_boundaries.json 用于跨 session 评估"""
        path = Path(boundary_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self._session_boundaries = json.load(f)

    def compute_temporal_cross_session_recall_consistency(
        self, actual_decisions: List[Dict[str, Any]],
    ) -> float:
        """计算跨 session 召回一致性

        衡量系统在多个 session 中是否一致地检索到同一话题的历史决策。
        检查同一 chat_id 的 session 间，能否从后续 session 正确召回前序 session 的决策。

        Returns:
            0.0 ~ 1.0 的一致性分数
        """
        if not self._session_boundaries:
            return 0.0

        # 按 chat_id 分组 session
        sessions_by_chat: Dict[str, List[Dict]] = {}
        for sb in self._session_boundaries:
            cid = sb["chat_id"]
            sessions_by_chat.setdefault(cid, []).append(sb)

        consistent_count = 0
        total_checks = 0

        for chat_id, sbs in sessions_by_chat.items():
            sbs_sorted = sorted(sbs, key=lambda x: x.get("session_id", 1))

            # 按 session 分组预期决策
            expected_by_session: Dict[int, List[Dict]] = {}
            for e in self._expected_decisions:
                e_chat = e.get("chat_id", "")
                if e_chat != chat_id:
                    continue
                s_id = e.get("session_id", 1)
                expected_by_session.setdefault(s_id, []).append(e)

            # 对每对 session (i, j) 检查：j > i，session j 是否能召回 session i 的决策
            for i_idx, sb_i in enumerate(sbs_sorted):
                s1_id = sb_i.get("session_id", 1)
                s1_exp = expected_by_session.get(s1_id, [])
                if not s1_exp:
                    continue

                for sbs_j in sbs_sorted[i_idx + 1:]:
                    s2_id = sbs_j.get("session_id", 1)
                    total_checks += len(s1_exp)

                    # 检查 session j 的实际决策能否匹配 session i 的预期决策
                    for e in s1_exp:
                        exp_topic = e.get("expected_topic", "")
                        exp_summary = e.get("expected_summary", "")
                        for act in actual_decisions:
                            act_chat = act.get("chat_id", "")
                            act_topic = act.get("topic_id", "")
                            if act_chat != chat_id or act_topic != exp_topic:
                                continue
                            if self._summary_similarity(exp_summary, act.get("summary", "")) >= 0.3:
                                consistent_count += 1
                                break

        return consistent_count / total_checks if total_checks > 0 else 0.0

    def compute_recall_vs_time_decay(
        self, actual_decisions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """计算召回率随时间衰减曲线

        按 session 间天数间隔分组：0（同 session）、1、3、7、14+ 天
        每组计算召回率，分析随时间推移的衰减趋势。

        Returns:
            {
                "day_gap_recall": {"0": 0.95, "1": 0.90, "3": 0.82, "7": 0.70, "14": 0.55},
                "half_life_days": 7.5,  # 估计的半衰期（天）
                "decay_rate": 0.08,     # 平均每天的衰减率
            }
        """
        if not self._session_boundaries:
            return {"day_gap_recall": {}, "half_life_days": None, "decay_rate": None}

        gap_recall: Dict[int, Dict[str, int]] = {
            0: {"correct": 0, "total": 0},
            1: {"correct": 0, "total": 0},
            3: {"correct": 0, "total": 0},
            7: {"correct": 0, "total": 0},
            14: {"correct": 0, "total": 0},
        }

        sessions_by_chat: Dict[str, List[Dict]] = {}
        for sb in self._session_boundaries:
            cid = sb["chat_id"]
            sessions_by_chat.setdefault(cid, []).append(sb)

        for chat_id, sbs in sessions_by_chat.items():
            sbs_sorted = sorted(sbs, key=lambda x: x.get("session_id", 1))

            # 按 session 分组预期决策
            expected_by_session: Dict[int, List[Dict]] = {}
            for e in self._expected_decisions:
                e_chat = e.get("chat_id", "")
                if e_chat != chat_id:
                    continue
                s_id = e.get("session_id", 1)
                expected_by_session.setdefault(s_id, []).append(e)

            for i_idx in range(len(sbs_sorted)):
                for j_idx in range(i_idx + 1, len(sbs_sorted)):
                    day_gap = sbs_sorted[j_idx].get("day_gap", 0)
                    s1_id = sbs_sorted[i_idx].get("session_id", 1)
                    s1_exp = expected_by_session.get(s1_id, [])

                    # 四舍五入到最近的预定义 gap
                    gap_key = min(gap_recall.keys(), key=lambda k: abs(k - day_gap))

                    for e in s1_exp:
                        gap_recall[gap_key]["total"] += 1
                        exp_topic = e.get("expected_topic", "")
                        exp_summary = e.get("expected_summary", "")
                        for act in actual_decisions:
                            act_chat = act.get("chat_id", "")
                            if act_chat != chat_id:
                                continue
                            if act.get("topic_id", "") != exp_topic:
                                continue
                            if self._summary_similarity(exp_summary, act.get("summary", "")) >= 0.3:
                                gap_recall[gap_key]["correct"] += 1
                                break

        day_gap_recall = {}
        for gap, counts in sorted(gap_recall.items()):
            recall = counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0
            day_gap_recall[str(gap)] = round(recall, 4)

        # 简单的衰减率估计
        g0_recall = day_gap_recall.get("0", 0.0)
        g14_recall = day_gap_recall.get("14", 0.0)
        decay_rate = (g0_recall - g14_recall) / 14.0 if g0_recall > 0 else None

        # 半衰期估计
        half_life = None
        if decay_rate and decay_rate > 0:
            half_life = round(0.5 / decay_rate, 1) if decay_rate > 0 else None

        return {
            "day_gap_recall": day_gap_recall,
            "half_life_days": half_life,
            "decay_rate": round(decay_rate, 4) if decay_rate is not None else None,
        }

    def compute_cross_chat_isolation_score(
        self,
    ) -> float:
        """计算跨群聊隔离得分

        检查决策是否在正确的群聊范围内被匹配。
        如果来自 chat_A 的预期决策被 chat_B 的实际决策匹配（false match），
        则视为隔离违规。

        Returns:
            0.0 ~ 1.0 的隔离得分
        """
        isolation_violations = 0
        total_expected = len(self._expected_decisions)

        for e in self._expected_decisions:
            e_chat = e.get("chat_id", "")
            e_topic = e.get("expected_topic", "")

            for act in self._actual_decisions:
                act_chat = act.get("chat_id", "")
                if not e_chat or not act_chat or e_chat == act_chat:
                    continue  # Same chat or missing data — not a violation

                act_topic = act.get("topic_id", "")
                if act_topic and e_topic and act_topic == e_topic:
                    # Same topic but different chat — this is a leak!
                    isolation_violations += 1
                    self._cross_chat_leakage.append({
                        "expected_chat": e_chat,
                        "actual_chat": act_chat,
                        "topic": e_topic,
                    })

        score = 1.0 - (isolation_violations / total_expected) if total_expected > 0 else 1.0
        return round(score, 4)

    def compute_false_positive_robustness(
        self,
    ) -> Dict[str, Any]:
        """计算 FP 鲁棒性分析

        按噪声比分组分析 FP 率，评估系统在不同噪声水平下的鲁棒性。

        Returns:
            {
                "fp_by_noise_ratio": {"0.1": 0.05, "0.3": 0.08, "0.5": 0.12, "0.7": 0.25},
                "overall_fp_rate": 0.10,
                "fp_rate_variance": 0.0064,  # FP 率的方差（越低越鲁棒）
                "fp_robustness_score": 0.90,  # 综合鲁棒性得分
            }
        """
        # 按 expected 的 noise_ratio 字段分组
        fp_by_ratio: Dict[float, Dict[str, int]] = {}
        fp_total = 0
        total_actual = len(self._actual_decisions)

        for act in self._false_positives:
            fp_total += 1

        # Try to get noise_ratio from the actual decisions
        for act in self._actual_decisions:
            nr = act.get("noise_ratio", None)
            if nr is not None:
                try:
                    nr = float(nr)
                except (ValueError, TypeError):
                    nr = None
            if nr is None:
                nr = 0.0
            if nr not in fp_by_ratio:
                fp_by_ratio[nr] = {"fp": 0, "total": 0}

        for act in self._false_positives:
            nr = act.get("noise_ratio", None)
            if nr is not None:
                try:
                    nr = float(nr)
                except (ValueError, TypeError):
                    nr = 0.0
            else:
                nr = 0.0
            if nr not in fp_by_ratio:
                fp_by_ratio[nr] = {"fp": 0, "total": 0}
            fp_by_ratio[nr]["fp"] += 1

        # Count total per noise ratio
        for act in self._actual_decisions:
            nr = act.get("noise_ratio", None)
            if nr is not None:
                try:
                    nr = float(nr)
                except (ValueError, TypeError):
                    nr = 0.0
            else:
                nr = 0.0
            if nr not in fp_by_ratio:
                fp_by_ratio[nr] = {"fp": 0, "total": 0}
            fp_by_ratio[nr]["total"] += 1

        fp_rate_by_ratio = {}
        for nr, counts in sorted(fp_by_ratio.items()):
            rate = counts["fp"] / counts["total"] if counts["total"] > 0 else 0.0
            fp_rate_by_ratio[str(nr)] = round(rate, 4)

        # Overall FP rate
        overall_fp_rate = fp_total / total_actual if total_actual > 0 else 0.0

        # Variance of FP rates — lower = more robust
        rates = [v for v in fp_rate_by_ratio.values()]
        mean_rate = sum(rates) / len(rates) if rates else 0.0
        variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates) if rates else 0.0

        # Robustness score: 1.0 - average FP rate (with adjustment)
        avg_fp_rate = sum(rates) / len(rates) if rates else overall_fp_rate
        fp_robustness = max(0.0, 1.0 - avg_fp_rate)

        return {
            "fp_by_noise_ratio": fp_rate_by_ratio,
            "overall_fp_rate": round(overall_fp_rate, 4),
            "fp_rate_variance": round(variance, 4),
            "fp_robustness_score": round(fp_robustness, 4),
        }

    def compute_all_expanded_metrics(
        self, actual_decisions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """一次性计算所有扩展指标

        Args:
            actual_decisions: 实际决策列表

        Returns:
            包含所有扩展指标的 dict
        """
        # 先执行标准匹配
        self.match(actual_decisions)

        metrics = self.compute_metrics()

        # 扩展指标
        time_decay = self.compute_recall_vs_time_decay(actual_decisions)
        expanded = {
            **metrics,
            "temporal_cross_session_recall_consistency": round(
                self.compute_temporal_cross_session_recall_consistency(actual_decisions), 4),
            "recall_vs_time_decay": time_decay,
            "cross_chat_isolation_score": self.compute_cross_chat_isolation_score(),
            "false_positive_robustness": self.compute_false_positive_robustness(),
        }

        return expanded