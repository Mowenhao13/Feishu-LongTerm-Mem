import pytest

from src.prompts.decision_prompts import (
    CONFLICT_ASSESSMENT_PROMPT,
    CONFLICT_RESOLVE_PROMPT,
    DECISION_EXTRACTION_PROMPT,
    DECISION_EXTRACTION_PROMPT_SHORT,
    DECISION_ROLE_ASSIGNMENT_PROMPT,
    DECISION_STATUS_DESCRIPTIONS,
    DECISION_STATUS_LIFECYCLE,
    DEDUP_DECISION_PROMPT,
)
from src.prompts.topic_prompts import (
    CLASSIFICATION_PROMPT,
    CROSS_TOPIC_DETECT_PROMPT,
    EPISODE_ROLE_WEIGHT_ASSIGNMENT_PROMPT,
    TOPIC_EXTRACTION_PROMPT,
    TOPIC_MATCH_PROMPT,
    TOPIC_UPDATE_PROMPT,
)


class TestDecisionStatus:
    def test_descriptions_has_all_statuses(self):
        assert len(DECISION_STATUS_DESCRIPTIONS) == 10
        for status in [
            "pending", "pending_confirmation", "in_discussion", "decided",
            "executing", "completed", "shelved", "rejected", "superseded", "deprecated",
        ]:
            assert status in DECISION_STATUS_DESCRIPTIONS

    def test_lifecycle_has_active_and_inactive(self):
        assert "active" in DECISION_STATUS_LIFECYCLE
        assert "inactive" in DECISION_STATUS_LIFECYCLE
        assert "pending" in DECISION_STATUS_LIFECYCLE["active"]
        assert "completed" in DECISION_STATUS_LIFECYCLE["inactive"]


class TestDecisionExtractionPrompts:
    def test_extraction_prompt_has_placeholders(self):
        assert "{topic_id}" in DECISION_EXTRACTION_PROMPT
        assert "{topic_title}" in DECISION_EXTRACTION_PROMPT
        assert "{episodes_content}" in DECISION_EXTRACTION_PROMPT

    def test_extraction_prompt_short_has_placeholder(self):
        assert "{conversation_text}" in DECISION_EXTRACTION_PROMPT_SHORT

    def test_role_assignment_prompt_has_placeholders(self):
        assert "{topic_id}" in DECISION_ROLE_ASSIGNMENT_PROMPT
        assert "{decisions_text}" in DECISION_ROLE_ASSIGNMENT_PROMPT


class TestConflictAndDedupPrompts:
    def test_conflict_assessment_prompt_has_key_sections(self):
        assert "contradiction_score" in CONFLICT_ASSESSMENT_PROMPT
        assert "contradiction_type" in CONFLICT_ASSESSMENT_PROMPT
        assert "直接矛盾" in CONFLICT_ASSESSMENT_PROMPT
        assert "参数矛盾" in CONFLICT_ASSESSMENT_PROMPT

    def test_dedup_prompt_has_action_choices(self):
        assert "skip" in DEDUP_DECISION_PROMPT
        assert "update" in DEDUP_DECISION_PROMPT
        assert "conflict" in DEDUP_DECISION_PROMPT
        assert "action" in DEDUP_DECISION_PROMPT

    def test_conflict_resolve_prompt_has_merge_keep_both(self):
        assert "merge" in CONFLICT_RESOLVE_PROMPT
        assert "keep_both" in CONFLICT_RESOLVE_PROMPT
        assert "可自动合并" in CONFLICT_RESOLVE_PROMPT
        assert "需人工介入" in CONFLICT_RESOLVE_PROMPT


class TestTopicPrompts:
    def test_extraction_prompt_has_placeholders(self):
        assert "{episode_count}" in TOPIC_EXTRACTION_PROMPT
        assert "{episodes}" in TOPIC_EXTRACTION_PROMPT

    def test_update_prompt_has_placeholders(self):
        assert "{existing_topic}" in TOPIC_UPDATE_PROMPT
        assert "{new_episode}" in TOPIC_UPDATE_PROMPT

    def test_match_prompt_has_placeholders(self):
        assert "{episode_subject}" in TOPIC_MATCH_PROMPT
        assert "{episode_summary}" in TOPIC_MATCH_PROMPT
        assert "{num_topics}" in TOPIC_MATCH_PROMPT

    def test_episode_role_weight_prompt_has_placeholders(self):
        assert "{topic_content}" in EPISODE_ROLE_WEIGHT_ASSIGNMENT_PROMPT
        assert "{episodes}" in EPISODE_ROLE_WEIGHT_ASSIGNMENT_PROMPT


class TestClassificationAndCrossTopicPrompts:
    def test_classification_prompt_has_key_fields(self):
        assert "topic" in CLASSIFICATION_PROMPT
        assert "confidence" in CLASSIFICATION_PROMPT
        assert "alternative_topics" in CLASSIFICATION_PROMPT
        assert "议题分类器" in CLASSIFICATION_PROMPT

    def test_classification_prompt_rules(self):
        assert ">=" in CLASSIFICATION_PROMPT
        assert "< 0.7" in CLASSIFICATION_PROMPT or "< 0.7 " in CLASSIFICATION_PROMPT

    def test_cross_topic_prompt_has_key_fields(self):
        assert "is_cross_topic" in CROSS_TOPIC_DETECT_PROMPT
        assert "cross_topic_refs" in CROSS_TOPIC_DETECT_PROMPT
        assert "reasons" in CROSS_TOPIC_DETECT_PROMPT
        assert "跨议题影响检测器" in CROSS_TOPIC_DETECT_PROMPT

    def test_cross_topic_prompt_dimensions(self):
        assert "决策类型" in CROSS_TOPIC_DETECT_PROMPT
        assert "模块名提及" in CROSS_TOPIC_DETECT_PROMPT
        assert "技术依赖" in CROSS_TOPIC_DETECT_PROMPT


class TestPromptsModuleExports:
    def test_all_constants_importable_from_package(self):
        from src.prompts import (
            CONFLICT_ASSESSMENT_PROMPT as ca,
            CONFLICT_RESOLVE_PROMPT as cr,
            DEDUP_DECISION_PROMPT as dd,
            CLASSIFICATION_PROMPT as cl,
            CROSS_TOPIC_DETECT_PROMPT as ct,
        )
        assert len(ca) > 100
        assert len(cr) > 100
        assert len(dd) > 100
        assert len(cl) > 100
        assert len(ct) > 100


class TestPromptContentQuality:
    def test_conflict_assessment_has_score_thresholds(self):
        assert "< 0.3" in CONFLICT_ASSESSMENT_PROMPT
        assert "0.3-0.6" in CONFLICT_ASSESSMENT_PROMPT
        assert "> 0.6" in CONFLICT_ASSESSMENT_PROMPT

    def test_cross_topic_has_max_topics(self):
        assert "5 个" in CROSS_TOPIC_DETECT_PROMPT

    def test_dedup_has_examples(self):
        assert "Python" in DEDUP_DECISION_PROMPT
        assert "PostgreSQL" in DEDUP_DECISION_PROMPT