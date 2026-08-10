"""Stage 1: Memory Extractor

Extracts entities, relationships, and facts from episode text in a single LLM call.
Uses OntologyManager for dynamic type definitions and existing entity context
to avoid duplication.

Usage:
    extractor = MemoryExtractor(llm_provider, ontology_manager)
    result = await extractor.extract(episode_text, episode_id="ep_123")
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.extractors.memory_types import (
    ExtractedEntity,
    ExtractedFact,
    ExtractedRelationship,
    MemoryExtractionResult,
)
from src.ontology.manager import OntologyManager
from src.prompts.memory_prompts import MEMORY_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Stage 1 memory extractor — extracts entities, relationships, and facts."""

    def __init__(
        self,
        llm_provider: Any,
        ontology_manager: Optional[OntologyManager] = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        self._llm = llm_provider
        self._ontology = ontology_manager or OntologyManager.get_instance()
        self._confidence_threshold = confidence_threshold
        self._trace_id: Optional[str] = None
        self.last_error: Optional[str] = None

        logger.info(
            "[MemoryExtractor] Initialized with provider=%s, confidence_threshold=%.2f",
            type(llm_provider).__name__,
            confidence_threshold,
        )

    def set_trace_id(self, trace_id: Optional[str]) -> None:
        """Set the current trace_id for Langfuse tracing."""
        self._trace_id = trace_id

    async def extract(
        self,
        content: str,
        episode_id: str = "",
        existing_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> MemoryExtractionResult:
        """Extract entities, relationships, and facts from episode text.

        Args:
            content: The episode text to analyze.
            episode_id: Optional episode identifier for provenance tracking.
            existing_entities: Optional list of already-known entity dicts
                (name, entity_type). Used to avoid duplication.

        Returns:
            MemoryExtractionResult with filtered entities/relationships/facts.
        """
        if not content or not content.strip():
            logger.info("[MemoryExtractor] Empty content, skipping")
            return MemoryExtractionResult()
        self.last_error = None

        # Build ontology context
        ontology_context = self._ontology.to_prompt_context()
        logger.debug("[MemoryExtractor] Ontology context: %d chars", len(ontology_context))

        # Build existing entities context
        existing_entities_context = self._format_existing_entities(existing_entities)

        # Escape braces for format()
        safe_content = content.replace("{", "{{").replace("}", "}}")
        safe_ontology = ontology_context.replace("{", "{{").replace("}", "}}")
        safe_existing = existing_entities_context.replace("{", "{{").replace("}", "}}")

        prompt = MEMORY_EXTRACTION_PROMPT.format(
            episode_content=safe_content,
            ontology_context=safe_ontology,
            existing_entities_context=safe_existing,
        )
        logger.info("[MemoryExtractor] >>> Calling LLM (prompt len=%d)", len(prompt))

        try:
            resp = await self._llm.generate(
                prompt,
                response_format={"type": "json_object"},
                trace_id=self._trace_id,
            )
            logger.debug("[MemoryExtractor] <<< LLM response len=%d preview=%.200s", len(resp), resp[:200])

            raw = resp.strip()
            if "```json" in raw:
                start = raw.index("```json") + 7
                end = raw.index("```", start) if "```" in raw[start:] else len(raw)
                raw = raw[start:end].strip()

            data = json.loads(raw)
            logger.info(
                "[MemoryExtractor] Parsed result: entities=%d, rels=%d, facts=%d",
                len(data.get("entities", [])),
                len(data.get("relationships", [])),
                len(data.get("facts", [])),
            )

            result = self._parse_result(data, episode_id)
            result.filter_by_confidence(self._confidence_threshold)

            logger.info(
                "[MemoryExtractor] After confidence filter: entities=%d, rels=%d, facts=%d",
                len(result.entities),
                len(result.relationships),
                len(result.facts),
            )
            return result

        except json.JSONDecodeError as e:
            self.last_error = f"json_parse_error: {e}"
            logger.error("[MemoryExtractor] Failed to parse LLM response: %s", e)
            logger.error("[MemoryExtractor] Raw response: %.300s", resp[:300] if resp else "(empty)")
            return MemoryExtractionResult()
        except Exception as e:
            self.last_error = f"llm_call_error: {e}"
            import traceback
            logger.error("[MemoryExtractor] LLM call failed: %s", e)
            logger.error("[MemoryExtractor] Traceback: %s", traceback.format_exc())
            return MemoryExtractionResult()

    # ─────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────

    def _parse_result(
        self, data: Dict[str, Any], episode_id: str
    ) -> MemoryExtractionResult:
        """Parse the LLM JSON response into a MemoryExtractionResult."""
        entities = []
        for ent in data.get("entities", []):
            try:
                entities.append(
                    ExtractedEntity(
                        name=str(ent.get("name", "")),
                        entity_type=str(ent.get("entity_type", "Concept")),
                        attributes=ent.get("attributes", {}),
                        confidence=float(ent.get("confidence", 0.0)),
                        source_episode_id=episode_id,
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning("[MemoryExtractor] Skipping malformed entity: %s", e)

        relationships = []
        for rel in data.get("relationships", []):
            try:
                relationships.append(
                    ExtractedRelationship(
                        source_name=str(rel.get("source_name", "")),
                        relationship_type=str(rel.get("relationship_type", "")),
                        target_name=str(rel.get("target_name", "")),
                        confidence=float(rel.get("confidence", 0.0)),
                        valid_at=rel.get("valid_at"),
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning("[MemoryExtractor] Skipping malformed relationship: %s", e)

        facts = []
        for fact in data.get("facts", []):
            try:
                facts.append(
                    ExtractedFact(
                        content=str(fact.get("content", "")),
                        confidence=float(fact.get("confidence", 0.0)),
                        related_entity_names=fact.get("related_entity_names", []),
                        source_episode_id=episode_id,
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning("[MemoryExtractor] Skipping malformed fact: %s", e)

        return MemoryExtractionResult(
            entities=entities,
            relationships=relationships,
            facts=facts,
            reasoning=data.get("reasoning", ""),
        )

    @staticmethod
    def _format_existing_entities(
        existing_entities: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Format existing entity list for injection into the prompt."""
        if not existing_entities:
            return "No existing entities."

        lines: List[str] = []
        for ent in existing_entities:
            name = ent.get("name", "?")
            etype = ent.get("entity_type", "?")
            lines.append(f"- {name} ({etype})")

        if not lines:
            return "No existing entities."

        return "\n".join(lines)
