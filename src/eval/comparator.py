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
        """加载 expected.jsonl 真值"""
        path = Path(self._expected_path)
        if not path.exists():
            raise FileNotFoundError(f"Expected file not found: {self._expected_path}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._expected_decisions.append(json.loads(line))

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

        for i, actual in enumerate(self._actual_decisions):
            if i not in matched_actual:
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