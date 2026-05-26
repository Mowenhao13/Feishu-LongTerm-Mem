from __future__ import annotations

import re
from typing import Optional

from src.detect.types import (
    DecisionLevel,
    DetectContext,
    DetectionResult,
    DetectorMode,
    DocType,
    ScoreBreakdown,
    SignalDetail,
)


class LexicalAnalyzer:
    def __init__(self) -> None:
        self._high_weight = [
            (["决定", "已决定", "决定了", "最终决定"], 1.0, "explicit_decision"),
            (["确认", "已确认", "确认了", "确认一下"], 0.9, "explicit_confirm"),
            (["通过", "已通过", "通过了", "审批通过"], 0.9, "explicit_approve"),
            (["定下来", "就这样", "就这么办", "定了"], 0.95, "finalize"),
            (["结论", "最终结论", "结论是"], 0.9, "conclusion"),
            (["不再讨论", "不讨论", "到此为止"], 0.85, "close_discussion"),
        ]
        self._medium_weight = [
            (["采用", "选用", "使用", "用这个"], 0.65, "adopt"),
            (["选", "选择", "选型", "方案", "技术栈", "开发语言", "语言"], 0.55, "selection"),
            (["建议", "推荐", "提议"], 0.50, "proposal"),
            (["approve", "lgtm", "LGTM", "approved", "confirmed", "agreed"], 0.70, "eng_approve"),
            (["decided", "decision", "finalize"], 0.75, "eng_decision"),
            (["需要", "必须", "务必", "一定要", "尽快"], 0.50, "requirement"),
            (["暂不", "不采用", "否决", "驳回", "不同意"], 0.60, "rejection"),
            (["todo", "to do", "action item", "待办"], 0.55, "action_item"),
            (["责任人", "负责", "执行人", "owner"], 0.50, "assign_owner"),
        ]
        self._low_weight = [
            (["可以", "没问题", "ok", "OK", "好的"], 0.20, "agreement"),
            (["对比", "比较", "vs", "还是", "或者", "alternative"], 0.35, "comparison"),
            (["我觉", "我认为", "个人认为", "观点"], 0.25, "opinion"),
            (["计划", "安排", "排期", "时间"], 0.30, "planning"),
            (["问题", "bug", "issue", "修复"], 0.30, "problem"),
        ]

    def analyze(self, content: str) -> list[SignalDetail]:
        signals: list[SignalDetail] = []
        lower = content.lower()

        for keywords, weight, name in self._high_weight:
            matched = _match_weighted(lower, keywords)
            if matched:
                signals.append(SignalDetail(category="lexical", name=name, weight=weight, matched=matched))

        for keywords, weight, name in self._medium_weight:
            matched = _match_weighted(lower, keywords)
            if matched:
                signals.append(SignalDetail(category="lexical", name=name, weight=weight, matched=matched))

        for keywords, weight, name in self._low_weight:
            matched = _match_weighted(lower, keywords)
            if matched:
                signals.append(SignalDetail(category="lexical", name=name, weight=weight, matched=matched))

        return signals


class StructuralAnalyzer:
    def analyze(self, content: str) -> list[SignalDetail]:
        signals: list[SignalDetail] = []

        matched = _contains_any(content, ["1.", "2.", "3.", "第一", "第二", "第三", "首先", "其次", "最后"])
        if matched:
            signals.append(SignalDetail(category="structural", name="numbered_list", weight=0.40, matched=matched[0]))

        matched = _contains_any(content, ["/", "vs", "VS", "对比"])
        if matched:
            signals.append(SignalDetail(category="structural", name="option_comparison", weight=0.35, matched=matched[0]))

        if '"' in content or "「" in content or "『" in content:
            signals.append(SignalDetail(category="structural", name="quoted_content", weight=0.20, matched="quotes_found"))

        rune_count = len(content)
        has_tech = _contains_any(content, [
            "接口", "API", "数据库", "服务", "部署", "架构",
            "前端", "后端", "客户端", "协议", "格式", "版本",
        ])
        if rune_count > 50 and has_tech:
            signals.append(SignalDetail(category="structural", name="technical_detail", weight=0.35, matched="long_tech_message"))

        matched = _contains_any(content, [
            "来负责", "来处", "来做", "由你", "由我", "由他",
            "assign", "负责", "owner",
        ])
        if matched:
            signals.append(SignalDetail(category="structural", name="task_assignment", weight=0.45, matched=matched[0]))

        return signals


class DynamicAnalyzer:
    def analyze(self, content: str, ctx: Optional[DetectContext]) -> list[SignalDetail]:
        if ctx is None:
            return []
        signals: list[SignalDetail] = []

        if ctx.is_reply:
            signals.append(SignalDetail(category="dynamic", name="reply_to_discussion", weight=0.35, matched="is_reply"))

        if ctx.has_mention:
            signals.append(SignalDetail(category="dynamic", name="directed_message", weight=0.40, matched="has_mention"))

        if ctx.message_index > 2:
            signals.append(SignalDetail(category="dynamic", name="multi_round_discussion", weight=0.25, matched="message_index"))

        lower = content.lower()
        if ctx.recent_keywords:
            overlap_count = 0
            for kw in ctx.recent_keywords:
                if kw.lower() in lower:
                    overlap_count += 1
            if overlap_count >= 2:
                signals.append(SignalDetail(category="dynamic", name="topic_continuation", weight=0.30, matched="topic_overlap"))

        return signals


class PatternMatcherV2:
    def __init__(self, patterns: Optional[list[_DecisionPattern]] = None) -> None:
        self._patterns = patterns if patterns is not None else _compile_patterns()

    def analyze(self, content: str) -> list[SignalDetail]:
        signals: list[SignalDetail] = []
        for p in self._patterns:
            m = p.regex.search(content)
            if m:
                signals.append(SignalDetail(category="pattern", name=p.name, weight=p.weight, matched=m.group(0)))
        return signals


class _DecisionPattern:
    def __init__(self, name: str, regex: re.Pattern, weight: float) -> None:
        self.name = name
        self.regex = regex
        self.weight = weight


def _compile_patterns() -> list[_DecisionPattern]:
    raw = [
        ("adopt_solution", r"(采用|选用|使用|用)\s*[，,。.\s]*(方案|方式|方法|技术|框架|工具)", 0.75),
        ("decide_solution", r"就[用定选]", 0.70),
        ("decided_action", r"(决定|确认|同意)\s*(使用|采用|用|选|选择)", 0.80),
        ("final_plan", r"(最终|最后)[的决定的方案]", 0.50),
        ("confirm_plan", r"(可以|没问题|ok|好的|行)[，,。.．！!\s]*(就|按|照|这样)", 0.45),
        ("approve_proposal", r"(同意|批准|通过|approve)\s*(这个|该|此)", 0.80),
        ("preference", r"(倾向于|偏向|建议|推荐)\s*(使用|采用|选|用)", 0.60),
        ("recommend", r"我\s*(建议|推荐|觉得)\s*[我们]?\s*[采用使用选用]", 0.55),
        ("conclusion_therefore", r"(因此|所以|那[就么]|那就)", 0.30),
        ("conclusion_finally", r"总结[一下]?[：:,，]", 0.65),
        ("conclusion_statement", r"结论[是就]", 0.75),
        ("assign_task", r"(由|让|请)\s*[@]?\S{1,10}[来去]\s*(负责|处理|跟进|做|完成)", 0.55),
        ("owner_assign", r"([\u4e00-\u9fff\w]{2,10})\s*(负责|owner|owner是)", 0.50),
        ("ab_selection", r"(用|选|采用)\s*\S{1,10}\s*(还是|或|or|vs)\s*\S{1,10}", 0.45),
        ("rejection", r"(不|别|不用|不需要|没必要)\s*(考虑|使用|采用|选)", 0.55),
        ("reject_proposal", r"(否决|驳回|不同意|反对)\s*(这个|该|此)", 0.75),
        ("explicit_objection", r"(我反对|我不同意|持保留意见|有异议|不认同)", 0.80),
        ("alternative_proposal", r"(应该用|不如用|建议用|推荐用|换成|改用)\s*\S+\s*(代替|替代|而不是|而非)", 0.70),
        ("reasoned_disagreement", r"(不同意|反对|不认可).{2,20}(因为|原因是|理由|风险|问题)", 0.85),
        ("reject_decision", r"(这个决定|这个方案|这个选择).{0,10}(有问题|不合适|不对|不好|不行)", 0.75),
        ("deadline", r"(截止|之前|前|ddl|deadline)\s*[：:为]?\s*\d{1,2}[月/.]", 0.40),
        ("voting", r"(投票|表决|举手表决|投票决定|投票结果)", 0.70),
    ]
    compiled: list[_DecisionPattern] = []
    for name, regex_str, weight in raw:
        try:
            compiled.append(_DecisionPattern(name=name, regex=re.compile(regex_str), weight=weight))
        except re.error:
            pass
    return compiled


def _compile_doc_patterns() -> list[_DecisionPattern]:
    raw = [
        ("adopt_solution", r"(采用|选用|使用|用)\s*[，,。.\s]*(方案|方式|方法|技术|框架|工具)", 0.75),
        ("decided_action", r"(决定|确认|同意)\s*(使用|采用|用|选|选择)", 0.80),
        ("conclusion_statement", r"结论[是就]", 0.75),
        ("approve_proposal", r"(同意|批准|通过)\s*(这个|该|此)", 0.80),
        ("rejection", r"(不|别|不用|不需要|没必要)\s*(考虑|使用|采用|选)", 0.55),
        ("doc_decision_section", r"#+\s*(决定|结论|决策|方案选择|技术选型)", 0.80),
        ("doc_architecture_section", r"#+\s*(架构|设计|方案|技术方案)", 0.65),
        ("doc_rationale_section", r"#+\s*(理由|原因|依据|考量|权衡|对比)", 0.55),
        ("doc_pros_cons", r"(优点|缺点|优势|劣势|Pros|Cons|好处|坏处)", 0.55),
        ("doc_option_list", r"(方案[一二三123ABC]|Option\s*[ABC]|对比项)", 0.50),
        ("doc_tech_selection", r"(技术选型|框架选择|工具选择|数据库选型)", 0.80),
        ("doc_final_recommendation", r"(最终推荐|推荐方案|建议方案|最终选择)", 0.85),
        ("doc_tech_stack_statement", r"(技术栈|使用|采用|选用)[：:]\s*\S+", 0.75),
        ("doc_tech_choice", r"(使用|采用|选用|选择)\s*(Gin|React|Vue|Go|Python|Java|MySQL|PostgreSQL|Redis|MongoDB|Kubernetes|Docker)", 0.80),
    ]
    compiled: list[_DecisionPattern] = []
    for name, regex_str, weight in raw:
        try:
            compiled.append(_DecisionPattern(name=name, regex=re.compile(regex_str), weight=weight))
        except re.error:
            pass
    return compiled


class EnhancedDetector:
    def __init__(self, mode: DetectorMode = DetectorMode.IM) -> None:
        self._lexical = LexicalAnalyzer()
        self._structural = StructuralAnalyzer()
        self._dynamic = DynamicAnalyzer()
        self._pattern = PatternMatcherV2()
        self._doc_pattern: Optional[PatternMatcherV2] = None
        self._mode = mode

    @classmethod
    def create_im_detector(cls) -> EnhancedDetector:
        return cls(mode=DetectorMode.IM)

    @classmethod
    def create_document_detector(cls) -> EnhancedDetector:
        det = cls(mode=DetectorMode.DOC)
        det._doc_pattern = PatternMatcherV2(_compile_doc_patterns())
        det._dynamic = None  # document mode has no dynamic analyzer
        return det

    def analyze(self, content: str, ctx: Optional[DetectContext] = None) -> DetectionResult:
        content = content.strip()
        if not content:
            return DetectionResult(score=0.0, level=DecisionLevel.NONE, is_decision=False)

        result = DetectionResult(factors=ScoreBreakdown())

        anti_signals = self._detect_anti_signals(content)
        result.anti_signals = anti_signals
        anti_score = self._calculate_anti_score(anti_signals)
        result.factors.anti_score = anti_score
        if anti_score >= 0.6:
            result.level = DecisionLevel.NONE
            result.is_decision = False
            return result

        lex_signals = self._lexical.analyze(content)
        lex_score = self._calculate_category_score(lex_signals)
        result.factors.lexical = lex_score
        result.signal_details.extend(lex_signals)

        struct_signals = self._structural.analyze(content)
        struct_score = self._calculate_category_score(struct_signals)
        result.factors.structural = struct_score
        result.signal_details.extend(struct_signals)

        dyn_signals: list[SignalDetail] = []
        if self._dynamic is not None:
            dyn_signals = self._dynamic.analyze(content, ctx)
        dyn_score = self._calculate_category_score(dyn_signals)
        result.factors.dynamic = dyn_score
        result.signal_details.extend(dyn_signals)

        pat_signals = self._pattern.analyze(content)
        pat_score = self._calculate_category_score(pat_signals)
        result.factors.pattern = pat_score
        result.signal_details.extend(pat_signals)

        final_score = self._compute_final_score(lex_score, struct_score, dyn_score, pat_score, anti_score)
        result.factors.final = final_score
        result.score = final_score

        result.level = self._classify_level(final_score)
        result.is_decision = result.level in (DecisionLevel.HIGH, DecisionLevel.MEDIUM)

        return result

    def analyze_document(self, content: str, title: str, doc_type: DocType = DocType.UNKNOWN) -> DetectionResult:
        content = content.strip()
        if not content:
            return DetectionResult(score=0.0, level=DecisionLevel.NONE, is_decision=False)

        result = DetectionResult(factors=ScoreBreakdown())

        anti_signals = self._detect_doc_anti_signals(title, content, doc_type)
        result.anti_signals = anti_signals
        anti_score = self._calculate_anti_score(anti_signals)
        result.factors.anti_score = anti_score

        if anti_score >= 0.6 or doc_type in (DocType.WEEKLY_REPORT, DocType.ADMINISTRATIVE):
            result.level = DecisionLevel.NONE
            result.is_decision = False
            return result

        lex_signals = self._lexical.analyze(content)
        lex_score = self._calculate_category_score(lex_signals)
        result.factors.lexical = lex_score
        result.signal_details.extend(lex_signals)

        struct_signals = self._structural.analyze(content)
        struct_score = self._calculate_category_score(struct_signals)
        result.factors.structural = struct_score
        result.signal_details.extend(struct_signals)

        if self._doc_pattern is not None:
            pat_signals = self._doc_pattern.analyze(content)
        else:
            pat_signals = self._pattern.analyze(content)
        pat_score = self._calculate_category_score(pat_signals)
        result.factors.pattern = pat_score
        result.signal_details.extend(pat_signals)

        final_score = lex_score * 0.40 + struct_score * 0.20 + pat_score * 0.35
        final_score *= (1.0 - anti_score * 0.2)
        final_score = max(0.0, min(1.0, final_score))

        result.factors.final = final_score
        result.score = final_score

        if final_score >= 0.45:
            result.level = DecisionLevel.HIGH
        elif final_score >= 0.30:
            result.level = DecisionLevel.MEDIUM
        elif final_score >= 0.15:
            result.level = DecisionLevel.LOW
        else:
            result.level = DecisionLevel.NONE
        result.is_decision = result.level in (DecisionLevel.HIGH, DecisionLevel.MEDIUM)

        return result

    def _detect_anti_signals(self, content: str) -> list[str]:
        signals: list[str] = []

        matched = _contains_any(content, [
            "早上好", "下午好", "晚上好", "大家好", "hello", "hi ", "hey",
            "辛苦了", "谢谢", "感谢", "拜拜", "再见", "see you",
        ])
        if matched:
            signals.append("greeting:" + matched[0])

        if _is_mostly_emoji(content):
            signals.append("pure_emoji")

        matched = _contains_any(content, [
            "可能", "也许", "大概", "或许", "不一定",
            "maybe", "perhaps", "probably", "not sure",
            "再看看", "再想想", "考虑一下", "讨论一下",
            "再说", "以后再说",
        ])
        if matched:
            signals.append("uncertain:" + matched[0])

        if _is_pure_question(content):
            signals.append("pure_question")

        matched = _contains_any(content, ["吃", "喝", "玩", "天气", "八卦"])
        if matched and len(content) < 20:
            signals.append("small_talk:" + matched[0])

        matched = _contains_any(content, [
            "已完成", "正在处理", "进度", "进展", "更新一下",
            "update", "完工", "当前状态", "目前",
        ])
        if matched:
            signals.append("status_update:" + matched[0])

        matched = _contains_any(content, [
            "分享", "通知", "告知", "FYI", "fyi",
            "仅供参考", "参考",
        ])
        if matched:
            signals.append("information_sharing:" + matched[0])

        matched = _contains_any(content, [
            "打算", "想试试", "准备做", "计划做", "考虑使用",
            "考虑采用",
        ])
        if matched:
            signals.append("aspirational:" + matched[0])

        matched = _contains_any(content, ["他说", "她说", "反馈说", "提到", "提及"])
        if matched:
            signals.append("reporting_others:" + matched[0])

        return signals

    def _detect_doc_anti_signals(self, title: str, content: str, doc_type: DocType) -> list[str]:
        signals: list[str] = []

        if doc_type == DocType.WEEKLY_REPORT:
            signals.append("weekly_report:" + title)
        if doc_type == DocType.MEETING_NOTES:
            signals.append("meeting_notes:" + title)
        if doc_type == DocType.ADMINISTRATIVE:
            signals.append("template_doc:" + title)

        lower = content.lower()
        has_decision_signal = False
        decision_keywords = [
            "技术栈", "框架", "选用", "使用", "采用", "决定", "选择",
            "方案", "选型", "架构", "Gin", "React", "Vue", "Go",
            "Python", "Java", "MySQL", "PostgreSQL", "Redis", "MongoDB",
        ]
        for kw in decision_keywords:
            if kw.lower() in lower:
                has_decision_signal = True
                break

        if len(lower) < 50 and not has_decision_signal:
            signals.append("minor_edit:short_change")

        matched = _contains_any(lower, ["fix typo", "format", "格式", "错别字", "排版"])
        if matched:
            signals.append("minor_edit:" + matched[0])

        matched = _contains_any(lower, ["TODO", "FIXME", "待完成", "待办"])
        if matched:
            signals.append("todo_list:" + matched[0])

        return signals

    def _calculate_anti_score(self, signals: list[str]) -> float:
        if not signals:
            return 0.0
        score = 0.0
        for s in signals:
            if s.startswith("greeting:"):
                score += 0.3
            elif s == "pure_emoji":
                score += 0.5
            elif s.startswith("uncertain:"):
                score += 0.4
            elif s == "pure_question":
                score += 0.3
            elif s.startswith("small_talk:"):
                score += 0.5
            elif s.startswith("status_update:"):
                score += 0.5
            elif s.startswith("information_sharing:"):
                score += 0.4
            elif s.startswith("aspirational:"):
                score += 0.3
            elif s.startswith("reporting_others:"):
                score += 0.35
            else:
                score += 0.2
        return min(score, 1.0)

    def _calculate_category_score(self, signals: list[SignalDetail]) -> float:
        if not signals:
            return 0.0
        max_weight = max(s.weight for s in signals)
        if len(signals) >= 3:
            max_weight += 0.1
        return min(max_weight, 1.0)

    def _compute_final_score(self, lexical: float, structural: float, dynamic: float, pattern: float, anti: float) -> float:
        final = lexical * 0.45 + structural * 0.15 + dynamic * 0.05 + pattern * 0.35

        if pattern >= 0.7 and final < pattern:
            final = final * 0.5 + pattern * 0.5

        final *= (1.0 - anti * 0.5)
        final = max(0.0, min(1.0, final))
        return final

    def _classify_level(self, score: float) -> DecisionLevel:
        if score >= 0.65:
            return DecisionLevel.HIGH
        elif score >= 0.50:
            return DecisionLevel.MEDIUM
        elif score >= 0.20:
            return DecisionLevel.LOW
        return DecisionLevel.NONE


def classify_doc_type(title: str, content: str) -> DocType:
    if not title:
        title = content[:100] if content else ""

    title_lower = title.lower()
    if _contains_any(title_lower, ["周报", "weekly", "日报", "daily", "月报", "双周报"]):
        return DocType.WEEKLY_REPORT
    if _contains_any(title_lower, ["会议", "纪要", "minutes", "meeting note"]):
        return DocType.MEETING_NOTES
    if _contains_any(title_lower, ["模板", "template", "模版"]):
        return DocType.ADMINISTRATIVE
    if _contains_any(title_lower, ["方案", "设计", "架构", "技术选型", "选型"]):
        return DocType.DESIGN
    if _contains_any(title_lower, ["规格", "spec", "需求", "requirement"]):
        return DocType.SPEC
    if _contains_any(title_lower, ["决定", "决策", "decision log", "决策记录", "changelog"]):
        return DocType.DECISION_LOG

    content_prefix = content.lower()[:200] if content else ""
    if _contains_any(content_prefix, ["本周工作", "下周计划", "进度同步"]):
        return DocType.WEEKLY_REPORT
    if _contains_any(content_prefix, ["会议时间", "参会人", "议程"]):
        return DocType.MEETING_NOTES
    if _contains_any(content_prefix, ["背景", "目标", "方案对比", "技术方案"]):
        return DocType.DESIGN

    return DocType.UNKNOWN


def _match_weighted(content: str, keywords: list[str]) -> str:
    for kw in keywords:
        if kw.lower() in content:
            return kw
    return ""


def _contains_any(s: str, keywords: list[str]) -> list[str]:
    matched: list[str] = []
    lower = s.lower()
    for kw in keywords:
        if kw.lower() in lower:
            matched.append(kw)
    return matched


def _is_mostly_emoji(s: str) -> bool:
    if len(s) > 10:
        return False
    emoji_count = 0
    total_runes = len(s)
    for ch in s:
        cp = ord(ch)
        if (0x1F300 <= cp <= 0x1F9FF) or (0x2600 <= cp <= 0x27BF) or (0xFE00 <= cp <= 0xFE0F) or cp in (0x2764, 0x2763, 0x2615):
            emoji_count += 1
    if total_runes == 0:
        return False
    return emoji_count / total_runes > 0.5


def _is_pure_question(s: str) -> bool:
    s = s.strip()
    if not (s.endswith("?") or s.endswith("？") or s.endswith("吗") or s.endswith("吧") or s.endswith("么")):
        return False
    if _contains_any(s, ["决定", "确认", "通过", "用", "选"]):
        return False
    return True


async def async_detect(content: str, source: str = "im") -> dict[str, Any]:
    detector = EnhancedDetector.create_im_detector() if source == "im" else EnhancedDetector.create_document_detector()
    ctx = DetectContext(message_index=1)
    result = detector.analyze(content, ctx)
    return {
        "score": result.score,
        "level": result.level.value,
        "is_decision": result.is_decision,
        "anti_signals": result.anti_signals,
        "signal_count": len(result.signal_details),
    }