from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from src.node.node import DecisionNode
from src.detect.types import AdapterType, StateChangeSignal


@dataclass
class CorrelationHint:
    type: str = ""
    confidence: float = 0.0
    target_sdr: str = ""
    description: str = ""


@dataclass
class AssembledContext:
    decisions: list[DecisionNode] = field(default_factory=list)
    adapter_results: dict[AdapterType, Any] = field(default_factory=dict)
    correlation_hints: list[CorrelationHint] = field(default_factory=list)
    total_tokens: int = 0


class ContextAssembler:
    def assemble(
        self,
        signal: StateChangeSignal,
        query_results: dict[AdapterType, Any],
        existing_decisions: list[DecisionNode],
        budget: int = 2000,
    ) -> AssembledContext:
        ctx = AssembledContext()

        for d in existing_decisions:
            if ctx.total_tokens >= budget:
                break
            ctx.decisions.append(d)
            ctx.total_tokens += 100

        for adapter, result in query_results.items():
            if ctx.total_tokens >= budget:
                break
            ctx.adapter_results[adapter] = result
            ctx.total_tokens += 200

        for d in existing_decisions:
            if ctx.total_tokens >= budget:
                break
            ctx.correlation_hints.append(CorrelationHint(
                type="RelatesTo",
                confidence=0.5,
                target_sdr=d.sid,
                description="Potentially related decision",
            ))

        return ctx

    def filter_decisions_by_relevance(
        self,
        decisions: list[DecisionNode],
        signal: StateChangeSignal,
    ) -> list[DecisionNode]:
        filtered: list[DecisionNode] = []
        for d in decisions:
            for kw in signal.context.keywords:
                if kw.lower() in d.summary.lower() or kw.lower() in d.full_text.lower():
                    filtered.append(d)
                    break
        return filtered


class ContextProvider(Protocol):
    def name(self) -> str:
        ...

    def get_relevant_context(
        self,
        sig: StateChangeSignal,
        all_decisions: list[DecisionNode],
    ) -> list[str]:
        ...


class IMContextProvider:
    def name(self) -> str:
        return "im"

    def get_relevant_context(
        self,
        sig: StateChangeSignal,
        all_decisions: list[DecisionNode],
    ) -> list[str]:
        summaries: list[str] = []
        search_keywords = self._extract_keywords(sig)

        for d in all_decisions:
            if len(summaries) >= 5:
                break
            if self._is_relevant_im_decision(d, search_keywords, sig):
                summaries.append(f"[Chat][{d.status.value}] {d.summary}: {d.full_text}")

        if len(summaries) < 5:
            for d in all_decisions:
                if len(summaries) >= 5:
                    break
                if d.feishu_links and len(d.feishu_links.related_chat_ids) > 0 and not self._is_relevant_im_decision(d, search_keywords, sig):
                    summaries.append(f"[Chat][{d.status.value}] {d.summary}: {d.full_text}")

        if len(summaries) < 5:
            for d in all_decisions:
                if len(summaries) >= 5:
                    break
                if (not d.feishu_links or len(d.feishu_links.related_chat_ids) == 0) and (not d.feishu_links or len(d.feishu_links.related_doc_tokens) == 0):
                    summaries.append(f"[{d.status.value}] {d.summary}: {d.full_text}")

        return summaries

    def _extract_keywords(self, sig: StateChangeSignal) -> list[str]:
        keywords: list[str] = []
        keywords.extend(sig.context.keywords)
        if sig.context.content_snippet:
            words = sig.context.content_snippet.split()
            if len(words) > 10:
                words = words[:10]
            keywords.extend(words)
        return keywords

    def _is_relevant_im_decision(
        self,
        d: DecisionNode,
        search_keywords: list[str],
        sig: StateChangeSignal,
    ) -> bool:
        if d.feishu_links and len(d.feishu_links.related_chat_ids) > 0:
            for chat_id in d.feishu_links.related_chat_ids:
                for rid in sig.related_ids:
                    if rid == chat_id:
                        return True

        if search_keywords:
            for kw in search_keywords:
                if kw.lower() in d.summary.lower() or kw.lower() in d.full_text.lower():
                    return True

        return False


class DocContextProvider:
    def name(self) -> str:
        return "doc"

    def get_relevant_context(
        self,
        sig: StateChangeSignal,
        all_decisions: list[DecisionNode],
    ) -> list[str]:
        summaries: list[str] = []
        search_keywords = self._extract_keywords(sig)
        doc_ids = self._extract_doc_ids(sig)

        for d in all_decisions:
            if len(summaries) >= 5:
                break
            if self._is_relevant_doc_decision(d, doc_ids, search_keywords):
                summaries.append(f"[Doc][{d.status.value}] {d.summary}: {d.full_text}")

        if len(summaries) < 5:
            for d in all_decisions:
                if len(summaries) >= 5:
                    break
                if d.feishu_links and len(d.feishu_links.related_doc_tokens) > 0 and not self._is_relevant_doc_decision(d, doc_ids, search_keywords):
                    summaries.append(f"[Doc][{d.status.value}] {d.summary}: {d.full_text}")

        if len(summaries) < 5:
            for d in all_decisions:
                if len(summaries) >= 5:
                    break
                if (not d.feishu_links or len(d.feishu_links.related_doc_tokens) == 0) and (not d.feishu_links or len(d.feishu_links.related_chat_ids) == 0):
                    summaries.append(f"[{d.status.value}] {d.summary}: {d.full_text}")

        return summaries

    def _extract_keywords(self, sig: StateChangeSignal) -> list[str]:
        keywords: list[str] = []
        keywords.extend(sig.context.keywords)
        if sig.context.content_snippet:
            words = sig.context.content_snippet.split()
            if len(words) > 10:
                words = words[:10]
            keywords.extend(words)
        return keywords

    def _extract_doc_ids(self, sig: StateChangeSignal) -> list[str]:
        ids: list[str] = []
        if sig.primary_id:
            ids.append(sig.primary_id)
        ids.extend(sig.related_ids)
        for url in sig.context.embedded_urls:
            if url.url_type == "doc":
                ids.append(url.extracted_token)
        return ids

    def _is_relevant_doc_decision(
        self,
        d: DecisionNode,
        doc_ids: list[str],
        search_keywords: list[str],
    ) -> bool:
        if d.feishu_links:
            for token in d.feishu_links.related_doc_tokens:
                for did in doc_ids:
                    if token == did:
                        return True

        if search_keywords:
            for kw in search_keywords:
                if kw.lower() in d.summary.lower() or kw.lower() in d.full_text.lower():
                    return True

        return False


class WikiContextProvider:
    def name(self) -> str:
        return "wiki"

    def get_relevant_context(
        self,
        sig: StateChangeSignal,
        all_decisions: list[DecisionNode],
    ) -> list[str]:
        summaries: list[str] = []
        search_keywords = self._extract_keywords(sig)
        wiki_ids = self._extract_wiki_ids(sig)

        for d in all_decisions:
            if len(summaries) >= 5:
                break
            if self._is_relevant_wiki_decision(d, wiki_ids, search_keywords):
                summaries.append(f"[Wiki][{d.status.value}] {d.summary}: {d.full_text}")

        if len(summaries) < 5:
            for d in all_decisions:
                if len(summaries) >= 5:
                    break
                if d.feishu_links and len(d.feishu_links.related_doc_tokens) > 0 and not self._is_relevant_wiki_decision(d, wiki_ids, search_keywords):
                    summaries.append(f"[Wiki][{d.status.value}] {d.summary}: {d.full_text}")

        if len(summaries) < 5:
            for d in all_decisions:
                if len(summaries) >= 5:
                    break
                if (not d.feishu_links or len(d.feishu_links.related_doc_tokens) == 0) and (not d.feishu_links or len(d.feishu_links.related_chat_ids) == 0):
                    summaries.append(f"[{d.status.value}] {d.summary}: {d.full_text}")

        return summaries

    def _extract_keywords(self, sig: StateChangeSignal) -> list[str]:
        keywords: list[str] = []
        keywords.extend(sig.context.keywords)
        if sig.context.content_snippet:
            words = sig.context.content_snippet.split()
            if len(words) > 10:
                words = words[:10]
            keywords.extend(words)
        return keywords

    def _extract_wiki_ids(self, sig: StateChangeSignal) -> list[str]:
        ids: list[str] = []
        if sig.primary_id:
            ids.append(sig.primary_id)
        ids.extend(sig.related_ids)
        for url in sig.context.embedded_urls:
            if url.url_type == "wiki":
                ids.append(url.extracted_token)
        return ids

    def _is_relevant_wiki_decision(
        self,
        d: DecisionNode,
        wiki_ids: list[str],
        search_keywords: list[str],
    ) -> bool:
        if d.feishu_links:
            for token in d.feishu_links.related_doc_tokens:
                for wid in wiki_ids:
                    if token == wid:
                        return True

        if search_keywords:
            for kw in search_keywords:
                if kw.lower() in d.summary.lower() or kw.lower() in d.full_text.lower():
                    return True

        return False


class GenericContextProvider:
    def name(self) -> str:
        return "generic"

    def get_relevant_context(
        self,
        sig: StateChangeSignal,
        all_decisions: list[DecisionNode],
    ) -> list[str]:
        summaries: list[str] = []
        for d in all_decisions:
            if len(summaries) >= 5:
                break
            summaries.append(f"[{d.status.value}] {d.summary}: {d.full_text}")
        return summaries


class ContextProviderFactory:
    def __init__(self) -> None:
        self._providers: dict[AdapterType, ContextProvider] = {
            AdapterType.IM: IMContextProvider(),
            AdapterType.DOCS: DocContextProvider(),
            AdapterType.WIKI: WikiContextProvider(),
            AdapterType.CALENDAR: GenericContextProvider(),
            AdapterType.TASK: GenericContextProvider(),
            AdapterType.VC: GenericContextProvider(),
        }

    def get_provider(self, adapter_type: AdapterType) -> ContextProvider:
        return self._providers.get(adapter_type, GenericContextProvider())