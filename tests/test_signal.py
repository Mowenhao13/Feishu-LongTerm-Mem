import re
from datetime import datetime

import pytest

from src.signal.detector import (
    DynamicAnalyzer,
    EnhancedDetector,
    LexicalAnalyzer,
    PatternMatcherV2,
    StructuralAnalyzer,
    classify_doc_type,
    _contains_any,
    _is_mostly_emoji,
    _is_pure_question,
)
from src.signal.emitter import (
    CalendarEmitter,
    ContactEmitter,
    DetectChange,
    DetectResult,
    DocsEmitter,
    IMEmitter,
    OKREmitter,
    TaskEmitter,
    VCEmitter,
    WikiEmitter,
    new_emitters,
)
from src.signal.types import (
    AdapterType,
    ChangeType,
    DecisionLevel,
    DetectContext,
    DetectionResult,
    DocType,
    SignalStrength,
    StateChangeSignal,
    new_signal,
)


class TestTypes:
    def test_adapter_type_values(self):
        assert AdapterType.IM == "IM"
        assert AdapterType.DOCS == "Docs"

    def test_new_signal_defaults(self):
        sig = new_signal(AdapterType.IM, "test summary")
        assert sig.adapter == AdapterType.IM
        assert sig.change_summary == "test summary"
        assert sig.strength == SignalStrength.MEDIUM
        assert sig.signal_id.startswith("sig-")

    def test_signal_with_context(self):
        sig = StateChangeSignal(
            signal_id="test-1",
            adapter=AdapterType.DOCS,
            change_summary="doc update",
            strength=SignalStrength.STRONG,
            primary_id="doc_123",
        )
        assert sig.adapter == AdapterType.DOCS
        assert sig.strength == SignalStrength.STRONG
        assert sig.primary_id == "doc_123"


class TestUtilityFunctions:
    def test_contains_any_found(self):
        result = _contains_any("今天天气真好", ["天气", "你好"])
        assert "天气" in result

    def test_contains_any_not_found(self):
        result = _contains_any("今天天气真好", ["你好", "hello"])
        assert result == []

    def test_contains_any_case_insensitive(self):
        result = _contains_any("Hello World", ["hello"])
        assert "hello" in result

    def test_is_mostly_emoji_true(self):
        assert _is_mostly_emoji("😊👍")

    def test_is_mostly_emoji_false(self):
        assert not _is_mostly_emoji("这是中文")

    def test_is_mostly_emoji_long_string(self):
        assert not _is_mostly_emoji("a" * 20)

    def test_is_pure_question_true(self):
        assert _is_pure_question("你吃了吗？")

    def test_is_pure_question_with_decision_word(self):
        assert not _is_pure_question("用这个方案吗？")

    def test_is_pure_question_no_question_mark(self):
        assert not _is_pure_question("好的")


class TestLexicalAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = LexicalAnalyzer()

    def test_high_weight_decision_keyword(self):
        signals = self.analyzer.analyze("我们决定使用 PostgreSQL")
        names = [s.name for s in signals]
        assert "explicit_decision" in names
        high_sigs = [s for s in signals if s.name == "explicit_decision"]
        assert high_sigs[0].weight == 1.0

    def test_medium_weight_adopt_keyword(self):
        signals = self.analyzer.analyze("采用微服务架构")
        names = [s.name for s in signals]
        assert "adopt" in names

    def test_low_weight_agreement(self):
        signals = self.analyzer.analyze("好的，没问题")
        names = [s.name for s in signals]
        assert "agreement" in names

    def test_no_signals_for_empty(self):
        signals = self.analyzer.analyze("")
        assert signals == []

    def test_no_signals_for_irrelevant(self):
        signals = self.analyzer.analyze("今天天气不错")
        assert signals == []

    def test_multiple_signals(self):
        signals = self.analyzer.analyze("我决定选择使用Python，确认了")
        names = [s.name for s in signals]
        assert "explicit_decision" in names
        assert "selection" in names
        assert "explicit_confirm" in names


class TestStructuralAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = StructuralAnalyzer()

    def test_numbered_list(self):
        signals = self.analyzer.analyze("1. 首先 2. 其次")
        names = [s.name for s in signals]
        assert "numbered_list" in names

    def test_technical_detail(self):
        signals = self.analyzer.analyze(
            "后端服务部署方案需要评估API接口性能和数据库架构设计，"
            "还要考虑前端组件库选择和部署架构方案，以及客户端协议格式版本兼容"
        )
        names = [s.name for s in signals]
        assert "technical_detail" in names

    def test_task_assignment(self):
        signals = self.analyzer.analyze("张三来负责这个任务")
        names = [s.name for s in signals]
        assert "task_assignment" in names

    def test_option_comparison(self):
        signals = self.analyzer.analyze("方案A vs 方案B")
        names = [s.name for s in signals]
        assert "option_comparison" in names

    def test_no_signals_for_short_text(self):
        signals = self.analyzer.analyze("好的")
        assert signals == []


class TestDynamicAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = DynamicAnalyzer()

    def test_reply_signal(self):
        ctx = DetectContext(is_reply=True, has_mention=False, message_index=1)
        signals = self.analyzer.analyze("同意", ctx)
        names = [s.name for s in signals]
        assert "reply_to_discussion" in names

    def test_mention_signal(self):
        ctx = DetectContext(is_reply=False, has_mention=True, message_index=1)
        signals = self.analyzer.analyze("@张三 来看这个", ctx)
        names = [s.name for s in signals]
        assert "directed_message" in names

    def test_multi_round_signal(self):
        ctx = DetectContext(is_reply=False, has_mention=False, message_index=5)
        signals = self.analyzer.analyze("最终确认", ctx)
        names = [s.name for s in signals]
        assert "multi_round_discussion" in names

    def test_topic_continuation(self):
        ctx = DetectContext(recent_keywords=["数据库", "迁移", "方案"])
        signals = self.analyzer.analyze("数据库迁移方案确认了", ctx)
        names = [s.name for s in signals]
        assert "topic_continuation" in names

    def test_none_context(self):
        signals = self.analyzer.analyze("hello", None)
        assert signals == []

    def test_all_signals_combined(self):
        ctx = DetectContext(
            is_reply=True, has_mention=True, message_index=3,
            recent_keywords=["方案", "确认"],
        )
        signals = self.analyzer.analyze("方案确认没问题", ctx)
        names = [s.name for s in signals]
        assert "reply_to_discussion" in names
        assert "directed_message" in names
        assert "multi_round_discussion" in names
        assert "topic_continuation" in names


class TestPatternMatcherV2:
    def setup_method(self) -> None:
        self.matcher = PatternMatcherV2()

    def test_adopt_solution_pattern(self):
        signals = self.matcher.analyze("采用，方案是微服务架构")
        names = [s.name for s in signals]
        assert "adopt_solution" in names

    def test_decided_action_pattern(self):
        signals = self.matcher.analyze("决定使用Python")
        names = [s.name for s in signals]
        assert "decided_action" in names

    def test_assign_task_pattern(self):
        signals = self.matcher.analyze("由张三来负责这个任务")
        names = [s.name for s in signals]
        assert "assign_task" in names

    def test_rejection_pattern(self):
        signals = self.matcher.analyze("不考虑使用这个方案")
        names = [s.name for s in signals]
        assert "rejection" in names

    def test_no_match_for_irrelevant(self):
        signals = self.matcher.analyze("今天天气不错")
        assert signals == []

    def test_multiple_patterns(self):
        signals = self.matcher.analyze("我决定采用Python方案，结论是使用Django框架")
        names = [s.name for s in signals]
        assert "adopt_solution" in names or "decided_action" in names
        assert "conclusion_statement" in names


class TestEnhancedDetector:
    def setup_method(self) -> None:
        self.detector = EnhancedDetector()

    def test_empty_content(self):
        result = self.detector.analyze("")
        assert result.level == DecisionLevel.NONE
        assert not result.is_decision
        assert result.score == 0.0

    def test_blank_content(self):
        result = self.detector.analyze("   ")
        assert result.level == DecisionLevel.NONE
        assert not result.is_decision

    def test_greeting_anti_signal(self):
        result = self.detector.analyze("早上好，大家好")
        assert not result.is_decision

    def test_strong_decision_signal(self):
        result = self.detector.analyze("我们决定使用PostgreSQL数据库，采用分布式架构方案")
        assert result.is_decision
        assert result.level in (DecisionLevel.HIGH, DecisionLevel.MEDIUM)

    def test_medium_decision(self):
        result = self.detector.analyze("建议采用Python开发，框架用Django")
        assert result.is_decision

    def test_low_confidence_decision(self):
        result = self.detector.analyze("可以，没问题")
        assert not result.is_decision

    def test_anti_signal_overrides(self):
        result = self.detector.analyze("辛苦了，谢谢大家")
        assert not result.is_decision
        assert len(result.anti_signals) > 0

    def test_detect_context_with_mention(self):
        ctx = DetectContext(is_reply=True, has_mention=True, message_index=3)
        result = self.detector.analyze("同意，决定用这个方案就这么办", ctx)
        assert result.is_decision

    def test_score_breakdown_present(self):
        result = self.detector.analyze("确认使用Kubernetes部署方案")
        assert result.factors is not None
        assert result.factors.lexical > 0
        assert result.factors.pattern > 0

    def test_high_level_threshold(self):
        result = self.detector.analyze("决定采用PostgreSQL，通过！结论是就用这个方案")
        assert result.level == DecisionLevel.HIGH

    def test_content_with_specific_parameters(self):
        result = self.detector.analyze("需要配置 shard_count=256，决定使用 bucket_size=8192")
        assert result.is_decision

    def test_pure_question_not_decision(self):
        result = self.detector.analyze("今天天气怎么样？")
        assert not result.is_decision

    def test_status_update_not_decision(self):
        result = self.detector.analyze("已完成数据库迁移，当前进度100%")
        assert not result.is_decision

    def test_decision_with_objection_pattern(self):
        result = self.detector.analyze("我反对这个方案，因为性能有问题")
        assert result.is_decision
        names = [s.name for s in result.signal_details]
        assert "explicit_objection" in names or "reasoned_disagreement" in names


class TestEnhancedDetectorDocumentMode:
    def setup_method(self) -> None:
        self.detector = EnhancedDetector.create_document_detector()

    def test_empty_document(self):
        result = self.detector.analyze_document("", "title", DocType.UNKNOWN)
        assert not result.is_decision

    def test_design_doc_with_decision(self):
        content = "# 技术方案\\n\\n## 结论\\n采用PostgreSQL作为主数据库"
        result = self.detector.analyze_document(content, "数据库选型方案", DocType.DESIGN)
        assert result.is_decision

    def test_weekly_report_skipped(self):
        content = "本周完成了数据库迁移工作"
        result = self.detector.analyze_document(content, "周报-第20周", DocType.WEEKLY_REPORT)
        assert not result.is_decision

    def test_meeting_notes_allowed(self):
        content = "决定使用微服务架构"
        result = self.detector.analyze_document(content, "架构会议纪要", DocType.MEETING_NOTES)
        assert result.is_decision

    def test_doc_section_pattern(self):
        content = "# 技术选型\\n使用React框架"
        result = self.detector.analyze_document(content, "前端方案", DocType.UNKNOWN)
        assert result.is_decision

    def test_admin_template_skipped(self):
        content = "填写项目信息"
        result = self.detector.analyze_document(content, "项目模板", DocType.ADMINISTRATIVE)
        assert not result.is_decision

    def test_doc_type_classification_design(self):
        doc_type = classify_doc_type("数据库选型方案", "对比MySQL和PostgreSQL")
        assert doc_type == DocType.DESIGN

    def test_doc_type_classification_weekly(self):
        doc_type = classify_doc_type("", "本周工作：完成了模块A的开发")
        assert doc_type == DocType.WEEKLY_REPORT

    def test_doc_type_classification_unknown(self):
        doc_type = classify_doc_type("随笔", "今天天气真好")
        assert doc_type == DocType.UNKNOWN


class TestEmitters:
    def test_im_emitter_with_decision(self):
        emitter = IMEmitter()
        result = DetectResult(
            has_changes=True,
            source="chat_123",
            changes=[DetectChange(type="new_text", summary="决定使用Python", entity_type="message")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None
        assert signal.adapter == AdapterType.IM

    def test_im_emitter_no_changes(self):
        emitter = IMEmitter()
        result = DetectResult(has_changes=False)
        signal = emitter.emit_signal(result)
        assert signal is None

    def test_im_emitter_pin_message(self):
        emitter = IMEmitter()
        result = DetectResult(
            has_changes=True,
            source="chat_123",
            changes=[DetectChange(type="pin_message", summary="重要通知", entity_type="pin_message")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None
        assert signal.strength == SignalStrength.STRONG

    def test_vc_emitter_minutes_available(self):
        emitter = VCEmitter()
        result = DetectResult(
            has_changes=True,
            source="vc_123",
            changes=[DetectChange(type="meeting_minutes_available", summary="会议纪要已生成")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None
        assert signal.strength == SignalStrength.STRONG
        assert "ai_summary" in signal.context.decision_signals

    def test_vc_emitter_no_changes(self):
        emitter = VCEmitter()
        signal = emitter.emit_signal(DetectResult(has_changes=False))
        assert signal is None

    def test_docs_emitter_decision_doc(self):
        emitter = DocsEmitter()
        result = DetectResult(
            has_changes=True,
            source="doc_123",
            changes=[DetectChange(type="doc_decision", summary="决策文档更新")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None
        assert "decision_doc" in signal.context.decision_signals

    def test_docs_emitter_comment(self):
        emitter = DocsEmitter()
        result = DetectResult(
            has_changes=True,
            source="doc_123",
            changes=[DetectChange(type="doc_comment_added", summary="新的评论")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None

    def test_calendar_emitter(self):
        emitter = CalendarEmitter()
        result = DetectResult(
            has_changes=True,
            source="cal_123",
            changes=[DetectChange(type="decision_meeting", summary="决策会议")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None

    def test_task_emitter_completed(self):
        emitter = TaskEmitter()
        result = DetectResult(
            has_changes=True,
            source="task_123",
            changes=[DetectChange(type="task_completed", summary="任务完成")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None
        assert "task_done" in signal.context.decision_signals

    def test_task_emitter_created(self):
        emitter = TaskEmitter()
        result = DetectResult(
            has_changes=True,
            source="task_123",
            changes=[DetectChange(type="task_created", summary="新任务")],
        )
        signal = emitter.emit_signal(result)
        assert signal is None

    def test_wiki_emitter(self):
        emitter = WikiEmitter()
        result = DetectResult(
            has_changes=True,
            source="wiki_123",
            changes=[DetectChange(type="updated", summary="Wiki更新")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None

    def test_okr_emitter(self):
        emitter = OKREmitter()
        result = DetectResult(
            has_changes=True,
            source="okr_123",
            changes=[DetectChange(type="updated", summary="OKR更新")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None
        assert signal.strength == SignalStrength.MEDIUM

    def test_contact_emitter(self):
        emitter = ContactEmitter()
        result = DetectResult(
            has_changes=True,
            source="contact_123",
            changes=[DetectChange(type="updated", summary="联系人更新")],
        )
        signal = emitter.emit_signal(result)
        assert signal is not None
        assert signal.strength == SignalStrength.WEAK

    def test_new_emitters_all_types(self):
        emitters = new_emitters()
        assert AdapterType.IM in emitters
        assert AdapterType.VC in emitters
        assert AdapterType.DOCS in emitters
        assert AdapterType.CALENDAR in emitters
        assert AdapterType.TASK in emitters
        assert AdapterType.OKR in emitters
        assert AdapterType.CONTACT in emitters
        assert AdapterType.WIKI in emitters
        assert len(emitters) == 8


class TestNewSignal:
    def test_unique_signal_ids(self):
        sig1 = new_signal(AdapterType.IM, "test1")
        sig2 = new_signal(AdapterType.IM, "test2")
        assert sig1.signal_id != sig2.signal_id

    def test_timestamp_set(self):
        sig = new_signal(AdapterType.IM, "test")
        assert sig.timestamp is not None


class TestDetectionResult:
    def test_default_values(self):
        result = DetectionResult()
        assert result.score == 0.0
        assert result.level == DecisionLevel.NONE
        assert not result.is_decision
        assert result.signal_details == []
        assert result.anti_signals == []
        assert result.factors is None

    def test_custom_values(self):
        result = DetectionResult(
            score=0.85,
            level=DecisionLevel.HIGH,
            is_decision=True,
            signal_details=[],
            anti_signals=["greeting:早上好"],
        )
        assert result.score == 0.85
        assert result.level == DecisionLevel.HIGH
        assert result.is_decision
        assert "greeting:早上好" in result.anti_signals