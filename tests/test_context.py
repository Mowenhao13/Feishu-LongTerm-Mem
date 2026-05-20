from __future__ import annotations

import pytest

from src.node.node import DecisionNode
from src.node.types import DecisionStatus
from src.signal.context import (
    AssembledContext,
    ContextAssembler,
    ContextProviderFactory,
    CorrelationHint,
    DocContextProvider,
    GenericContextProvider,
    IMContextProvider,
    WikiContextProvider,
)
from src.signal.types import AdapterType, EmbeddedURL, SignalContext, StateChangeSignal


def make_signal(
    adapter: AdapterType = AdapterType.IM,
    keywords: list[str] | None = None,
    snippet: str = "",
    primary_id: str = "",
    related_ids: list[str] | None = None,
) -> StateChangeSignal:
    return StateChangeSignal(
        signal_id="test-sig",
        adapter=adapter,
        context=SignalContext(
            keywords=keywords or [],
            content_snippet=snippet,
            embedded_urls=[
                EmbeddedURL(raw_url="doc_url", extracted_token="doc_abc", url_type="doc"),
                EmbeddedURL(raw_url="wiki_url", extracted_token="wiki_xyz", url_type="wiki"),
            ],
        ),
        primary_id=primary_id,
        related_ids=related_ids or [],
    )


def make_decision(
    sid: str,
    summary: str = "test",
    full_text: str = "decision text",
    status: DecisionStatus = DecisionStatus.DECIDED,
    chat_ids: list[str] | None = None,
    doc_tokens: list[str] | None = None,
) -> DecisionNode:
    return DecisionNode(
        sid=sid,
        summary=summary,
        full_text=full_text,
        status=status,
        feishu_links={
            "related_chat_ids": chat_ids or [],
            "related_doc_tokens": doc_tokens or [],
        },
    )


class TestCorrelationHint:
    def test_defaults(self):
        hint = CorrelationHint()
        assert hint.type == ""
        assert hint.confidence == 0.0
        assert hint.target_sdr == ""
        assert hint.description == ""

    def test_custom(self):
        hint = CorrelationHint(type="RelatesTo", confidence=0.8, target_sdr="SDR-001", description="related")
        assert hint.type == "RelatesTo"
        assert hint.confidence == 0.8


class TestAssembledContext:
    def test_defaults(self):
        ctx = AssembledContext()
        assert ctx.decisions == []
        assert ctx.adapter_results == {}
        assert ctx.correlation_hints == []
        assert ctx.total_tokens == 0


class TestContextAssembler:
    def setup_method(self) -> None:
        self.assembler = ContextAssembler()

    def test_assemble_empty(self):
        sig = make_signal()
        ctx = self.assembler.assemble(sig, {}, [])
        assert len(ctx.decisions) == 0
        assert len(ctx.adapter_results) == 0
        assert len(ctx.correlation_hints) == 0
        assert ctx.total_tokens == 0

    def test_assemble_with_decisions_and_results(self):
        sig = make_signal()
        decisions = [
            make_decision("SDR-001", summary="dec1"),
            make_decision("SDR-002", summary="dec2"),
        ]
        results = {AdapterType.IM: "im_data", AdapterType.DOCS: "doc_data"}
        ctx = self.assembler.assemble(sig, results, decisions, budget=5000)
        assert len(ctx.decisions) == 2
        assert len(ctx.adapter_results) == 2
        assert len(ctx.correlation_hints) == 2
        assert ctx.total_tokens > 0

    def test_assemble_budget_limit(self):
        sig = make_signal()
        decisions = [make_decision(f"SDR-{i:03d}") for i in range(20)]
        ctx = self.assembler.assemble(sig, {}, decisions, budget=300)
        assert ctx.total_tokens <= 300
        # with 100 tokens per decision, max 3 should fit
        assert len(ctx.decisions) <= 3

    def test_filter_by_keywords(self):
        sig = make_signal(keywords=["database"])
        decisions = [
            make_decision("SDR-001", summary="about database"),
            make_decision("SDR-002", summary="frontend stuff"),
            make_decision("SDR-003", full_text="database migration plan"),
        ]
        filtered = self.assembler.filter_decisions_by_relevance(decisions, sig)
        assert len(filtered) == 2
        sids = [d.sid for d in filtered]
        assert "SDR-001" in sids
        assert "SDR-003" in sids
        assert "SDR-002" not in sids

    def test_filter_no_keywords(self):
        sig = make_signal(keywords=[])
        decisions = [make_decision("SDR-001"), make_decision("SDR-002")]
        filtered = self.assembler.filter_decisions_by_relevance(decisions, sig)
        assert len(filtered) == 0


class TestIMContextProvider:
    def setup_method(self) -> None:
        self.provider = IMContextProvider()

    def test_name(self):
        assert self.provider.name() == "im"

    def test_no_decisions(self):
        sig = make_signal()
        summaries = self.provider.get_relevant_context(sig, [])
        assert summaries == []

    def test_chat_id_match(self):
        sig = make_signal(related_ids=["chat_123"])
        decisions = [
            make_decision("SDR-001", chat_ids=["chat_123"]),
            make_decision("SDR-002", chat_ids=["chat_456"]),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1
        assert "[Chat]" in summaries[0]

    def test_keyword_match(self):
        sig = make_signal(keywords=["database"])
        decisions = [
            make_decision("SDR-001", summary="database migration", chat_ids=["chat_123"]),
            make_decision("SDR-002", summary="frontend design", chat_ids=["chat_456"]),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1

    def test_priority_ordering(self):
        sig = make_signal(keywords=["cache"], related_ids=["chat_001"])
        decisions = [
            make_decision("SDR-A", summary="redis cache", chat_ids=["chat_001"]),
            make_decision("SDR-B", summary="random", chat_ids=["chat_002"]),
            make_decision("SDR-C", summary="no links"),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 3

    def test_max_five_results(self):
        sig = make_signal(keywords=["topic"])
        decisions = [make_decision(f"SDR-{i:03d}", summary=f"topic {i}") for i in range(20)]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) <= 5


class TestDocContextProvider:
    def setup_method(self) -> None:
        self.provider = DocContextProvider()

    def test_name(self):
        assert self.provider.name() == "doc"

    def test_doc_token_match(self):
        sig = make_signal(primary_id="doc_abc")
        decisions = [
            make_decision("SDR-001", doc_tokens=["doc_abc"]),
            make_decision("SDR-002", doc_tokens=["doc_xyz"]),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1
        assert "[Doc]" in summaries[0]

    def test_embedded_url_extraction(self):
        sig = make_signal()
        sig.context.embedded_urls = [
            EmbeddedURL(raw_url="url", extracted_token="doc_embedded", url_type="doc"),
        ]
        decisions = [
            make_decision("SDR-001", doc_tokens=["doc_embedded"]),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1

    def test_keyword_match(self):
        sig = make_signal(keywords=["migration"])
        decisions = [
            make_decision("SDR-001", summary="database migration", doc_tokens=[]),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1

    def test_max_five_results(self):
        sig = make_signal(keywords=["test"])
        decisions = [make_decision(f"SDR-{i:03d}", summary=f"test {i}") for i in range(20)]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) <= 5


class TestWikiContextProvider:
    def setup_method(self) -> None:
        self.provider = WikiContextProvider()

    def test_name(self):
        assert self.provider.name() == "wiki"

    def test_wiki_token_match(self):
        sig = make_signal(primary_id="wiki_xyz")
        decisions = [
            make_decision("SDR-001", doc_tokens=["wiki_xyz"]),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1
        assert "[Wiki]" in summaries[0]

    def test_embedded_wiki_url(self):
        sig = make_signal()
        sig.context.embedded_urls = [
            EmbeddedURL(raw_url="url", extracted_token="wiki_embedded", url_type="wiki"),
        ]
        decisions = [
            make_decision("SDR-001", doc_tokens=["wiki_embedded"]),
        ]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1


class TestGenericContextProvider:
    def setup_method(self) -> None:
        self.provider = GenericContextProvider()

    def test_name(self):
        assert self.provider.name() == "generic"

    def test_returns_five_decisions(self):
        sig = make_signal()
        decisions = [make_decision(f"SDR-{i:03d}") for i in range(10)]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) == 5

    def test_returns_all_if_less_than_five(self):
        sig = make_signal()
        decisions = [make_decision("SDR-001"), make_decision("SDR-002")]
        summaries = self.provider.get_relevant_context(sig, decisions)
        assert len(summaries) == 2


class TestContextProviderFactory:
    def test_get_im_provider(self) -> None:
        factory = ContextProviderFactory()
        provider = factory.get_provider(AdapterType.IM)
        assert provider.name() == "im"

    def test_get_doc_provider(self) -> None:
        factory = ContextProviderFactory()
        provider = factory.get_provider(AdapterType.DOCS)
        assert provider.name() == "doc"

    def test_get_wiki_provider(self) -> None:
        factory = ContextProviderFactory()
        provider = factory.get_provider(AdapterType.WIKI)
        assert provider.name() == "wiki"

    def test_unknown_adapter_falls_back_to_generic(self):
        factory = ContextProviderFactory()
        provider = factory.get_provider(AdapterType.MINUTES)
        assert provider.name() == "generic"

    def test_cached_providers(self):
        factory = ContextProviderFactory()
        p1 = factory.get_provider(AdapterType.IM)
        p2 = factory.get_provider(AdapterType.IM)
        assert p1 is p2


class TestContextIntegration:
    def test_assembler_and_provider_roundtrip(self):
        sig = make_signal(keywords=["redis"], related_ids=["chat_001"])
        decisions = [
            make_decision("SDR-001", summary="redis cache", chat_ids=["chat_001"]),
            make_decision("SDR-002", summary="postgres", chat_ids=["chat_002"]),
        ]

        factory = ContextProviderFactory()
        provider = factory.get_provider(AdapterType.IM)
        summaries = provider.get_relevant_context(sig, decisions)
        assert len(summaries) >= 1

        assembler = ContextAssembler()
        ctx = assembler.assemble(sig, {}, decisions, budget=5000)
        assert len(ctx.decisions) == 2
        filtered = assembler.filter_decisions_by_relevance(decisions, sig)
        assert len(filtered) == 1


class TestDecisionStatus:
    def test_values_valid(self):
        assert DecisionStatus.PENDING.value == "pending"
        assert DecisionStatus.DECIDED.value == "decided"
        assert DecisionStatus.COMPLETED.value == "completed"

    def test_fstring_uses_value(self):
        d = make_decision("SDR-001", status=DecisionStatus.COMPLETED)
        formatted = f"[{d.status.value}]"
        assert formatted == "[completed]"


class TestEmbeddedURL:
    def test_extracted_token_access(self):
        url = EmbeddedURL(raw_url="https://example.com/doc/doc_abc", extracted_token="doc_abc", url_type="doc")
        assert url.url_type == "doc"
        assert url.extracted_token == "doc_abc"