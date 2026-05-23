from __future__ import annotations

import math
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Protocol, Set

from src.node.node import DecisionNode
from src.node.types import Relation, RelationType


class GitReader(Protocol):
    """Git 读取接口 — 对应 Go 版 GitReader interface."""

    def list_decisions(self, project: str, topic: str) -> List[Dict]:
        ...

    def list_topics(self, project: str) -> List[str]:
        ...

    def list_decision_branches(self) -> List[str]:
        ...

    def read_decision(self, project: str, topic: str, sdr_id: str) -> Dict:
        ...

    def read_decision_from_branch(self, branch: str, sdr_id: str) -> Dict:
        ...


class Conflict:
    def __init__(
        self,
        conflict_id: str = "",
        decision_a: str = "",
        decision_b: str = "",
        description: str = "",
        contradiction_score: float = 0.0,
    ) -> None:
        self.conflict_id = conflict_id
        self.decision_a = decision_a
        self.decision_b = decision_b
        self.description = description
        self.contradiction_score = contradiction_score


class MemoryGraph:
    """内存决策图 — 运行时加速

    对应 Go 版 ref/core/memory_graph.go MemoryGraph。
    5 个索引映射 + 脏标记，提供完整的内存级决策检索能力。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

        self._decisions: Dict[str, DecisionNode] = {}
        self._topics: Dict[str, List[str]] = {}
        self._relations: Dict[str, List[Relation]] = {}
        self._cross_topic_refs: Dict[str, List[str]] = {}
        self._projects: Dict[str, List[str]] = {}
        self._dirty_decisions: Set[str] = set()

    def load_from_git(self, reader: GitReader, project: str) -> None:
        with self._lock:
            branches = reader.list_decision_branches()
            branch_prefix = "decision/"

            for branch in branches:
                sdr_id = branch[len(branch_prefix):] if branch.startswith(branch_prefix) else ""
                if not sdr_id:
                    continue
                try:
                    node = reader.read_decision_from_branch(branch, sdr_id)
                    parsed = self._dict_to_node(node)
                    self._add_decision_internal(parsed, project)
                except Exception:
                    continue

            try:
                dummy = reader.read_decision(project, "general", "dummy")
                if dummy:
                    parsed = self._dict_to_node(dummy)
                    self._add_decision_internal(parsed, project)
            except Exception:
                pass

    def _add_decision_internal(self, node: DecisionNode, project: str) -> None:
        self._decisions[node.sid] = node

        topic_key = f"{project}/{node.topic_id}" if node.topic_id else f"{project}/general"
        if topic_key not in self._topics:
            self._topics[topic_key] = []
        if node.sid not in self._topics[topic_key]:
            self._topics[topic_key].append(node.sid)

        topic_name = node.topic_id if node.topic_id else "general"
        if project not in self._projects:
            self._projects[project] = []
        if topic_name not in self._projects[project]:
            self._projects[project].append(topic_name)

        if node.relations:
            if node.sid not in self._relations:
                self._relations[node.sid] = []
            self._relations[node.sid].extend(node.relations)

    def query_by_topic(self, project: str, topic: str) -> List[DecisionNode]:
        with self._lock:
            key = f"{project}/{topic}"
            sdr_ids = self._topics.get(key, [])
            return [self._decisions[sid] for sid in sdr_ids if sid in self._decisions and self._decisions[sid].status.is_active()]

    def query_cross_topic(self, project: str, topic: str) -> List[DecisionNode]:
        with self._lock:
            key = f"{project}/{topic}"
            result: List[DecisionNode] = []

            sdr_ids = self._topics.get(key, [])
            for sid in sdr_ids:
                if sid in self._decisions:
                    result.append(self._decisions[sid])

            for ref_key in self._cross_topic_refs.get(key, []):
                for sid in self._topics.get(ref_key, []):
                    if sid in self._decisions:
                        result.append(self._decisions[sid])

            return result

    def get_decision(self, sdr_id: str) -> Optional[DecisionNode]:
        with self._lock:
            return self._decisions.get(sdr_id)

    def upsert_decision(self, node: DecisionNode, project: str) -> None:
        with self._lock:
            self._add_decision_internal(node, project)
            self._dirty_decisions.add(node.sid)

    def delete_decision(self, sdr_id: str) -> None:
        with self._lock:
            self._decisions.pop(sdr_id, None)
            self._dirty_decisions.discard(sdr_id)

    def count(self) -> int:
        with self._lock:
            return len(self._decisions)

    def topic_count(self, project: str) -> int:
        with self._lock:
            return len(self._projects.get(project, []))

    def list_all_topics(self, project: str) -> List[str]:
        with self._lock:
            return list(self._projects.get(project, []))

    def detect_conflicts(self, new_node: DecisionNode) -> List[Conflict]:
        with self._lock:
            conflicts: List[Conflict] = []

            for sdr_id, relations in self._relations.items():
                for rel in relations:
                    if rel.type == RelationType.CONFLICTS_WITH and rel.target_id == new_node.sid:
                        other = self._decisions.get(sdr_id)
                        if other:
                            conflicts.append(Conflict(
                                conflict_id=f"conflict_{sdr_id}_{new_node.sid}",
                                decision_a=sdr_id,
                                decision_b=new_node.sid,
                                description=f"Conflict between '{other.summary}' and '{new_node.summary}'",
                            ))

            return conflicts

    def search_by_keywords(self, query: str, topic: str = "") -> List[DecisionNode]:
        with self._lock:
            result: List[DecisionNode] = []
            q = query.lower()

            for d in self._decisions.values():
                if not d.status.is_active():
                    continue
                if topic and d.topic_id != topic:
                    continue
                if (q in d.summary.lower() or
                        q in d.full_text.lower() or
                        q in d.topic_id.lower()):
                    result.append(d)

            return result

    def get_all_decisions(self) -> List[DecisionNode]:
        with self._lock:
            return list(self._decisions.values())

    def get_relations(self, sdr_id: str) -> List[Relation]:
        with self._lock:
            return list(self._relations.get(sdr_id, []))

    def get_related_decisions(self, sdr_id: str) -> List[DecisionNode]:
        with self._lock:
            relations = self._relations.get(sdr_id, [])
            return [self._decisions[rel.target_id] for rel in relations if rel.target_id in self._decisions]

    def update_access_stats(self, sdr_id: str) -> None:
        with self._lock:
            d = self._decisions.get(sdr_id)
            if d:
                d.access_stats.record_access()
                self._dirty_decisions.add(sdr_id)

    def record_reference(self, sdr_id: str) -> None:
        with self._lock:
            d = self._decisions.get(sdr_id)
            if d:
                d.access_stats.record_reference()
                self._dirty_decisions.add(sdr_id)

    def recalculate_hot_score(self, sdr_id: str) -> None:
        with self._lock:
            d = self._decisions.get(sdr_id)
            if not d:
                return

            ref_score = min(100.0, float(d.access_stats.reference_count) * 20.0)
            access_score = min(100.0, float(d.access_stats.access_count) * 15.0)
            relation_score = min(100.0, float(len(d.relations)) * 25.0)

            days_since_created = 0.0
            if d.created_at:
                days_since_created = max(0.0, (datetime.now() - d.created_at).total_seconds() / 86400.0)
            base_score = min(25.0, 25.0 - days_since_created * 1.5)

            hot_score = ref_score * 0.40 + access_score * 0.20 + relation_score * 0.15 + base_score
            hot_score = max(0.0, min(100.0, hot_score))

            d.access_stats.hot_score = hot_score
            d.access_stats.last_calculated = datetime.now()
            self._dirty_decisions.add(sdr_id)

    def get_dirty_and_clean(self) -> List[DecisionNode]:
        with self._lock:
            result = [self._decisions[sid] for sid in self._dirty_decisions if sid in self._decisions]
            self._dirty_decisions.clear()
            return result

    def get_decisions_by_hot_score(self, min_score: float = 0.0) -> List[DecisionNode]:
        with self._lock:
            result = [d for d in self._decisions.values() if d.status.is_active() and d.access_stats.hot_score >= min_score]
            result.sort(key=lambda x: x.access_stats.hot_score, reverse=True)
            return result

    def get_recent_decisions(self, since: datetime) -> List[DecisionNode]:
        with self._lock:
            result = [d for d in self._decisions.values() if d.status.is_active() and d.created_at and d.created_at > since]
            result.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
            return result

    @staticmethod
    def _dict_to_node(data: dict) -> DecisionNode:
        from src.node.node import DecisionNode
        from src.node.types import DecisionStatus, ImpactLevel

        sid = data.get("sid", "") or data.get("id", "")
        topic_id = data.get("topic_id", "") or data.get("topic", "general")
        summary = data.get("title", "") or data.get("summary", "")
        full_text = data.get("content", "") or data.get("decision", "")

        status_str = data.get("status", "pending")
        try:
            status = DecisionStatus(status_str)
        except ValueError:
            status = DecisionStatus.PENDING

        impact_str = data.get("impact_level", "minor")
        try:
            impact = ImpactLevel(impact_str)
        except ValueError:
            impact = ImpactLevel.MINOR

        return DecisionNode(
            sid=sid,
            topic_id=topic_id,
            summary=summary,
            full_text=full_text,
            status=status,
            impact_level=impact,
            tags=data.get("tags", []),
            confidence=data.get("confidence", 1.0),
            authority=data.get("proposer", ""),
            assignee=data.get("executor", ""),
        )

    def node_to_dict(self, node: DecisionNode) -> dict:
        return {
            "sid": node.sid,
            "topic_id": node.topic_id,
            "title": node.summary,
            "decision": node.full_text,
            "status": node.status.value,
            "impact_level": node.impact_level.value,
            "tags": node.tags,
            "confidence": node.confidence,
            "proposer": node.authority,
            "executor": node.assignee,
            "version": getattr(node, "version", 0),
            "project": "feishu-mem",
        }