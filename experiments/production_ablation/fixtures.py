"""Chat-specific fixtures for production-path ablation tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FixtureNeo4jSync:
    """In-memory history fixture that records every production history read."""

    entities_by_chat: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    decisions_by_chat: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    entity_reads: list[str] = field(default_factory=list)
    decision_reads: list[str] = field(default_factory=list)

    async def get_historical_entity_context(self, chat_id: str, limit: int = 50) -> list[dict[str, str]]:
        self.entity_reads.append(chat_id)
        return self.entities_by_chat.get(chat_id, [])[:limit]

    async def get_historical_decisions(self, chat_id: str, limit: int = 20) -> list[dict[str, str]]:
        self.decision_reads.append(chat_id)
        return self.decisions_by_chat.get(chat_id, [])[:limit]

    async def sync_all(self, *args: Any, **kwargs: Any) -> dict[str, int]:
        return {}
