"""
Tests for src/node module: DecisionNode, types, and relation hypergraph.

Tests various states and operations, returning empty but not failing for 
unconfigured environments.
"""
from datetime import datetime
from typing import List

from node.node import (
    DECISION_ROLE_OPTIONS,
    DecisionNode,
    DecisionRole,
    new_decision_node,
)
from node.relation import (
    DecisionHyperedge,
    Hyperedge,
    HyperedgeType,
    Hypergraph,
    Participant,
    RelationBuilder,
)
from node.types import (
    AccessStats,
    DecisionStatus,
    FeishuLinks,
    ImpactLevel,
    Objection,
    ObjectionStatus,
    PhaseScope,
    Relation,
    RelationType,
    VersionRange,
    RELATION_TYPE_DESCRIPTIONS,
    ACTIVE_DECISION_STATUSES,
    INACTIVE_DECISION_STATUSES,
)


# ==================== DecisionStatus Tests ====================


class TestDecisionStatus:
    def test_all_statuses_valid(self) -> None:
        for status in DecisionStatus:
            assert status.is_valid()

    def test_active_statuses(self) -> None:
        for status in ACTIVE_DECISION_STATUSES:
            assert status.is_active()
            assert not status.is_inactive()

    def test_inactive_statuses(self) -> None:
        for status in INACTIVE_DECISION_STATUSES:
            assert status.is_inactive()
            assert not status.is_active()

    def test_active_status_list(self) -> None:
        statuses = DecisionStatus
        assert statuses.PENDING.is_active()
        assert statuses.IN_DISCUSSION.is_active()
        assert statuses.DECIDED.is_active()
        assert statuses.EXECUTING.is_active()
        assert statuses.COMPLETED.is_active() is False
        assert statuses.SHELVED.is_active() is False
        assert statuses.REJECTED.is_active() is False

    def test_inactive_status_list(self) -> None:
        statuses = DecisionStatus
        assert statuses.COMPLETED.is_inactive()
        assert statuses.SHELVED.is_inactive()
        assert statuses.REJECTED.is_inactive()
        assert statuses.SUPERSEDED.is_inactive()
        assert statuses.DEPRECATED.is_inactive()
        assert statuses.PENDING.is_inactive() is False
        assert statuses.DECIDED.is_inactive() is False


# ==================== DecisionRole Tests ====================


class TestDecisionRole:
    def test_role_constants(self) -> None:
        assert DecisionRole.ROLE_DECISION == "decision"
        assert DecisionRole.ROLE_PLAN == "plan"
        assert DecisionRole.ROLE_CONSIDERATION == "consideration"
        assert DecisionRole.ROLE_ACTION == "action"

    def test_role_options(self) -> None:
        assert "decision" in DECISION_ROLE_OPTIONS
        assert "plan" in DECISION_ROLE_OPTIONS
        assert len(DECISION_ROLE_OPTIONS) == 4


# ==================== ImpactLevel Tests ====================


class TestImpactLevel:
    def test_all_levels_valid(self) -> None:
        assert ImpactLevel.ADVISORY.is_valid()
        assert ImpactLevel.MINOR.is_valid()
        assert ImpactLevel.MAJOR.is_valid()
        assert ImpactLevel.CRITICAL.is_valid()


# ==================== ObjectionStatus Tests ====================


class TestObjectionStatus:
    def test_valid_statuses(self) -> None:
        assert ObjectionStatus.ACTIVE.is_valid()
        assert ObjectionStatus.RESOLVED.is_valid()
        assert ObjectionStatus.OVERRULED.is_valid()


# ==================== DecisionNode Creation Tests ====================


class TestDecisionNodeCreation:
    def test_create_minimal_node(self) -> None:
        node = DecisionNode(sid="test-001")
        assert node.sid == "test-001"
        assert node.status == DecisionStatus.PENDING
        assert node.impact_level == ImpactLevel.MINOR
        assert node.phase_scope == PhaseScope.POINT
        assert node.decision_role == DecisionRole.ROLE_DECISION
        assert node.topic_id == ""
        assert node.version == "v1.0"
        assert not hasattr(node, "project")

    def test_create_full_node(self) -> None:
        node = DecisionNode(
            sid="test-002",
            topic_id="topic-1",
            tags=["architecture", "backend"],
            summary="Use Python 3.12",
            full_text="We should use Python 3.12 for the new backend service",
            status=DecisionStatus.IN_DISCUSSION,
            decision_role=DecisionRole.ROLE_PLAN,
            phase_scope=PhaseScope.SPAN,
            impact_level=ImpactLevel.MAJOR,
            confidence=0.85,
            authority="Alice",
            assignee="Bob",
            source_type="im",
            source_message_id="om_msg_1",
            source_chat_id="oc_chat_1",
        )
        assert node.sid == "test-002"
        assert node.topic_id == "topic-1"
        assert node.tags == ["architecture", "backend"]
        assert node.status == DecisionStatus.IN_DISCUSSION
        assert node.confidence == 0.85
        assert node.authority == "Alice"

    def test_is_active(self) -> None:
        active = DecisionNode(sid="a1")
        assert active.is_active()
        decided = DecisionNode(sid="a2", status=DecisionStatus.DECIDED)
        assert decided.is_active()
        completed = DecisionNode(sid="a3", status=DecisionStatus.COMPLETED)
        assert not completed.is_active()

    def test_is_decided(self) -> None:
        pending = DecisionNode(sid="d1")
        assert not pending.is_decided()
        decided = DecisionNode(sid="d2", status=DecisionStatus.DECIDED)
        assert decided.is_decided()
        executing = DecisionNode(sid="d3", status=DecisionStatus.EXECUTING)
        assert executing.is_decided()
        completed = DecisionNode(sid="d4", status=DecisionStatus.COMPLETED)
        assert completed.is_decided()

    def test_change_status(self) -> None:
        node = DecisionNode(sid="s1")
        assert node.status == DecisionStatus.PENDING
        node.change_status(DecisionStatus.DECIDED)
        assert node.status == DecisionStatus.DECIDED
        assert node.decided_at is not None

    def test_change_status_no_decided_time(self) -> None:
        node = DecisionNode(sid="s2")
        node.change_status(DecisionStatus.EXECUTING)
        assert node.decided_at is None


# ==================== Version Tests ====================


class TestVersion:
    def test_branch_version_default(self) -> None:
        node = DecisionNode(sid="v1")
        assert node.branch_version() == "v1.0"

    def test_branch_version_custom(self) -> None:
        node = DecisionNode(sid="v2", version="v2.3")
        assert node.branch_version() == "v2.3"

    def test_next_version_no_current(self) -> None:
        node = DecisionNode(sid="v3")
        assert node.next_version() == "v1.1"
        node.version = ""
        assert node.next_version("v0.1") == "v0.1"

    def test_next_version_increment(self) -> None:
        node = DecisionNode(sid="v4", version="v1.0")
        assert node.next_version() == "v1.1"
        node2 = DecisionNode(sid="v5", version="v2.5")
        assert node2.next_version() == "v2.6"

    def test_next_major_version(self) -> None:
        node = DecisionNode(sid="v6", version="v3.0")
        assert node.next_major_version() == "v4.0"


# ==================== Conflict Tests ====================


class TestConflictStatus:
    def test_completed_resolves_conflict(self) -> None:
        assert DecisionNode.conflict_status(DecisionStatus.DECIDED, DecisionStatus.COMPLETED) == "resolved"
        assert DecisionNode.conflict_status(DecisionStatus.COMPLETED, DecisionStatus.DECIDED) == "resolved"

    def test_superseded_status(self) -> None:
        assert DecisionNode.conflict_status(DecisionStatus.SUPERSEDED, DecisionStatus.DECIDED) == "superseded"

    def test_deprecated_status(self) -> None:
        assert DecisionNode.conflict_status(DecisionStatus.DEPRECATED, DecisionStatus.DECIDED) == "deprecated"

    def test_shelved_status(self) -> None:
        assert DecisionNode.conflict_status(DecisionStatus.SHELVED, DecisionStatus.DECIDED) == "shelved"

    def test_active_conflict(self) -> None:
        assert DecisionNode.conflict_status(DecisionStatus.DECIDED, DecisionStatus.DECIDED) == "conflict_active"

    def test_unknown(self) -> None:
        assert DecisionNode.conflict_status(DecisionStatus.PENDING, DecisionStatus.PENDING) == "unknown"


# ==================== Objection Tests ====================


class TestObjection:
    def test_create_objection(self) -> None:
        obj = Objection(
            oid="obj-001",
            objection_content="方案成本过高",
            rationale="需要额外3台服务器",
            alternative="使用云服务",
            objector="Charlie",
            status=ObjectionStatus.ACTIVE,
            references_decision="test-001",
            source_type="im",
            source_message_id="om_msg_2",
        )
        assert obj.oid == "obj-001"
        assert obj.status == ObjectionStatus.ACTIVE
        assert obj.objection_content == "方案成本过高"

    def test_add_objection_to_node(self) -> None:
        node = DecisionNode(sid="test-010")
        obj = Objection(oid="obj-002", objection_content="测试反对")
        node.add_objection(obj)
        assert len(node.objections) == 1
        assert obj.created_at is not None

    def test_active_objections(self) -> None:
        node = DecisionNode(sid="test-011")
        node.add_objection(Objection(oid="o1", objection_content="active"))
        node.add_objection(Objection(oid="o2", objection_content="resolved", status=ObjectionStatus.RESOLVED))
        node.add_objection(Objection(oid="o3", objection_content="overruled", status=ObjectionStatus.OVERRULED))
        assert len(node.active_objections()) == 1
        assert node.active_objections()[0].oid == "o1"
        assert node.has_active_objections()

    def test_no_active_objections(self) -> None:
        node = DecisionNode(sid="test-012")
        assert not node.has_active_objections()
        node.add_objection(Objection(oid="o1", objection_content="done", status=ObjectionStatus.RESOLVED))
        assert not node.has_active_objections()


# ==================== Relation Tests ====================


class TestRelation:
    def test_create_relation(self) -> None:
        rel = Relation(
            type=RelationType.DEPENDS_ON,
            target_id="target-001",
            description="depends on target",
        )
        assert rel.type == RelationType.DEPENDS_ON
        assert rel.target_id == "target-001"

    def test_add_relation_to_node(self) -> None:
        node = DecisionNode(sid="test-020")
        rel = Relation(type=RelationType.RELATES_TO, target_id="target-001")
        node.add_relation(rel)
        assert len(node.relations) == 1

    def test_relation_type_descriptions(self) -> None:
        assert len(RELATION_TYPE_DESCRIPTIONS) == 6
        assert RelationType.DEPENDS_ON in RELATION_TYPE_DESCRIPTIONS
        assert RelationType.CONFLICTS_WITH in RELATION_TYPE_DESCRIPTIONS


# ==================== Topic Association Tests ====================


class TestTopicAssociation:
    def test_set_topic(self) -> None:
        node = DecisionNode(sid="test-030")
        assert node.topic_id == ""
        node.set_topic("topic-architecture")
        assert node.topic_id == "topic-architecture"

    def test_topic_in_creation(self) -> None:
        node = DecisionNode(sid="test-031", topic_id="topic-infra")
        assert node.topic_id == "topic-infra"


# ==================== new_decision_node Helper Tests ====================


class TestNewDecisionNode:
    def test_new_decision_node_defaults(self) -> None:
        node = new_decision_node(sid="test-040")
        assert node.sid == "test-040"
        assert node.status == DecisionStatus.PENDING
        assert node.decision_role == DecisionRole.ROLE_DECISION
        assert node.impact_level == ImpactLevel.MINOR
        assert node.topic_id == ""

    def test_new_decision_node_custom(self) -> None:
        node = new_decision_node(
            sid="test-041",
            topic_id="topic-custom",
            summary="Custom decision",
            full_text="Full text here",
            decision_role=DecisionRole.ROLE_PLAN,
            status=DecisionStatus.IN_DISCUSSION,
            impact_level=ImpactLevel.MAJOR,
            confidence=0.9,
            authority="Admin",
            assignee="DevTeam",
            source_type="doc",
            source_message_id="om_doc_1",
        )
        assert node.topic_id == "topic-custom"
        assert node.summary == "Custom decision"
        assert node.confidence == 0.9
        assert node.extra == {}

    def test_new_decision_node_extra(self) -> None:
        node = new_decision_node(sid="test-042", custom_field="hello", number=42)
        assert node.extra == {"custom_field": "hello", "number": 42}


# ==================== RelationBuilder Hyperedge Tests ====================


class TestRelationBuilder:
    def test_build_dependency(self) -> None:
        rel, he = RelationBuilder.build_dependency("A", "B", "A needs B")
        assert rel.type == RelationType.DEPENDS_ON
        assert rel.target_id == "B"
        assert he.edge_type == HyperedgeType.DECISION_DEPENDENCY.value
        assert "A" in he.participant_ids()
        assert "B" in he.participant_ids()
        assert he.is_directed

    def test_build_conflict(self) -> None:
        rel, he = RelationBuilder.build_conflict("A", "B")
        assert rel.type == RelationType.CONFLICTS_WITH
        assert not he.is_directed

    def test_build_supersede(self) -> None:
        rel, he = RelationBuilder.build_supersede("A", "B")
        assert rel.type == RelationType.SUPERSEDES
        assert he.is_directed
        assert he.roles.get("A") == "superseding"
        assert he.roles.get("B") == "superseded"

    def test_build_refinement(self) -> None:
        rel, he = RelationBuilder.build_refinement("A", "B")
        assert rel.type == RelationType.REFINES
        assert he.roles.get("A") == "specialization"

    def test_build_related(self) -> None:
        rel, he = RelationBuilder.build_related("A", "B", "related stuff")
        assert rel.type == RelationType.RELATES_TO
        assert not he.is_directed

    def test_hyperedge_hyperedge_id_format(self) -> None:
        rel, he = RelationBuilder.build_dependency("A", "B")
        assert "he_" in he.hyperedge_id
        assert "DEPENDS_ON" in he.hyperedge_id


# ==================== Hyperedge Tests ====================


class TestHyperedge:
    def test_add_participant(self) -> None:
        he = Hyperedge(hyperedge_id="he_test", edge_type="test")
        he.add_participant("node-1", role="primary", weight=0.8)
        assert he.participant_count() == 1
        assert he.participant_ids() == ["node-1"]

    def test_has_node(self) -> None:
        he = Hyperedge(hyperedge_id="he_test", edge_type="test")
        he.add_participant("node-1")
        assert he.has_node("node-1")
        assert not he.has_node("node-2")

    def test_remove_node(self) -> None:
        he = Hyperedge(hyperedge_id="he_test", edge_type="test")
        he.add_participant("node-1")
        he.add_participant("node-2")
        assert he.remove_node("node-1") is True
        assert he.participant_count() == 1
        assert he.remove_node("nonexistent") is False

    def test_decision_hyperedge_sync(self) -> None:
        dhe = DecisionHyperedge(
            hyperedge_id="he_decision",
            edge_type=HyperedgeType.DECISION_DEPENDENCY.value,
            nodes=["A", "B", "C"],
            roles={"A": "primary", "B": "secondary", "C": "observer"},
        )
        assert dhe.participant_count() == 0
        dhe.sync_participants()
        assert dhe.participant_count() == 3
        assert dhe.has_node("A")


# ==================== Hypergraph Tests ====================


class TestHypergraph:
    def test_add_and_get(self) -> None:
        hg = Hypergraph()
        he = Hyperedge(hyperedge_id="he_1", edge_type="test")
        hg.add_hyperedge(he)
        assert hg.size() == 1
        assert hg.get_hyperedge("he_1") is he

    def test_get_edges_for_node(self) -> None:
        hg = Hypergraph()
        he1 = Hyperedge(hyperedge_id="he_1", edge_type="test")
        he1.add_participant("A")
        he2 = Hyperedge(hyperedge_id="he_2", edge_type="test")
        he2.add_participant("A")
        he3 = Hyperedge(hyperedge_id="he_3", edge_type="test")
        he3.add_participant("B")
        hg.add_hyperedge(he1)
        hg.add_hyperedge(he2)
        hg.add_hyperedge(he3)
        edges = hg.get_edges_for_node("A")
        assert len(edges) == 2

    def test_get_connected_nodes(self) -> None:
        hg = Hypergraph()
        he = Hyperedge(hyperedge_id="he", edge_type="test")
        he.add_participant("A")
        he.add_participant("B")
        he.add_participant("C")
        hg.add_hyperedge(he)
        connected = hg.get_connected_nodes("A")
        assert "B" in connected
        assert "C" in connected
        assert "A" not in connected

    def test_remove_hyperedge(self) -> None:
        hg = Hypergraph()
        hg.add_hyperedge(Hyperedge(hyperedge_id="he_1", edge_type="test"))
        assert hg.remove_hyperedge("he_1") is True
        assert hg.size() == 0
        assert hg.remove_hyperedge("nonexistent") is False


# ==================== Phase Scope Tests ====================


class TestPhaseScope:
    def test_phase_values(self) -> None:
        assert PhaseScope.POINT.value == "Point"
        assert PhaseScope.SPAN.value == "Span"
        assert PhaseScope.RETROACTIVE.value == "Retroactive"


# ==================== VersionRange Tests ====================


class TestVersionRange:
    def test_default(self) -> None:
        vr = VersionRange()
        assert vr.from_version == ""
        assert vr.to is None

    def test_custom(self) -> None:
        vr = VersionRange(from_version="v1.0", to="v2.0")
        assert vr.from_version == "v1.0"
        assert vr.to == "v2.0"


# ==================== FeishuLinks Tests ====================


class TestFeishuLinks:
    def test_default(self) -> None:
        fl = FeishuLinks()
        assert fl.related_chat_ids == []
        assert fl.related_message_ids == []

    def test_add_links(self) -> None:
        fl = FeishuLinks()
        fl.related_chat_ids.append("oc_chat_1")
        fl.related_message_ids.append("om_msg_1")
        assert len(fl.related_chat_ids) == 1
        assert len(fl.related_message_ids) == 1


# ==================== AccessStats Tests ====================


class TestAccessStats:
    def test_default(self) -> None:
        stats = AccessStats()
        assert stats.access_count == 0
        assert stats.reference_count == 0
        assert stats.hot_score == 100.0

    def test_record_access(self) -> None:
        stats = AccessStats()
        stats.record_access()
        assert stats.access_count == 1
        assert stats.last_accessed_at is not None

    def test_record_reference(self) -> None:
        stats = AccessStats()
        stats.record_reference()
        assert stats.reference_count == 1


# ==================== RelationType Descriptions Tests ====================


class TestRelationTypeDescriptions:
    def test_all_types_have_description(self) -> None:
        for rt in RelationType:
            assert rt in RELATION_TYPE_DESCRIPTIONS

    def test_description_content(self) -> None:
        assert "depends on" in RELATION_TYPE_DESCRIPTIONS[RelationType.DEPENDS_ON]
        assert "supersedes" in RELATION_TYPE_DESCRIPTIONS[RelationType.SUPERSEDES]