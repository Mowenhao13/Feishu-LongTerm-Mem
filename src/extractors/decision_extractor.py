import json
import uuid
import asyncio
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

from src.utils.logger import get_logger
from model.llm_provider import LLMProvider
from types import Decision, DecisionStatus, Episode, Topic
from prompts.decision_prompts import (
    DECISION_EXTRACTION_PROMPT,
    DECISION_ROLE_ASSIGNMENT_PROMPT,
)

logger = get_logger(__name__)


@dataclass
class DecisionExtractResult:
    topic_id: str
    decisions: List[Decision]
    reasoning: str = ""

    def __post_init__(self):
        self.decision_count = len(self.decisions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "decision_count": self.decision_count,
            "decisions": [d.to_dict() for d in self.decisions],
            "reasoning": self.reasoning,
        }


@dataclass
class DecisionRoleAssignmentResult:
    decision_roles: Dict[str, str]
    decision_priorities: Dict[str, str]
    extraction_confidence: float
    reasoning: str


class DecisionExtractor:
    def __init__(self, llm_provider: LLMProvider, chat_id: str = "", **llm_kwargs):
        self.llm_provider = llm_provider
        self.chat_id = chat_id
        self.llm_kwargs = llm_kwargs

    def _format_topic_context(self, topic: Topic) -> Tuple[str, str, str]:
        return topic.topic_id, topic.title, topic.summary

    def _format_episodes_content(self, episodes: List[Episode]) -> str:
        lines = []
        for i, episode in enumerate(episodes):
            lines.append(f"--- Episode {i+1} (ID: episode_{i+1}) ---")
            if episode.subject:
                lines.append(f"Subject: {episode.subject}")
            if episode.summary:
                lines.append(f"Summary: {episode.summary}")
            if episode.episode_description:
                lines.append(f"Episode: {episode.episode_description}")
            if episode.keywords:
                lines.append(f"Keywords: {', '.join(episode.keywords)}")
            if episode.original_data:
                lines.append("Original Content:")
                for j, data in enumerate(episode.original_data):
                    if isinstance(data, dict):
                        speaker = data.get("speaker_name", "Unknown")
                        content = data.get("content", "")
                        lines.append(f"  [{j+1}] {speaker}: {content}")
                    else:
                        lines.append(f"  [{j+1}] {data}")
            lines.append("")
        return "\n".join(lines)

    def _format_decisions(self, decisions: List[Decision]) -> str:
        lines = []
        for i, dec in enumerate(decisions):
            lines.append(f"--- Decision {i+1} ---")
            lines.append(f"ID: dec_{i+1}")
            lines.append(f"Title: {dec.title}")
            lines.append(f"Content: {dec.content}")
            lines.append(f"Confidence: {dec.confidence}")
            lines.append(f"Rationale: {dec.rationale}")
            if dec.proposer:
                lines.append(f"Proposer: {dec.proposer}")
            if dec.executor:
                lines.append(f"Executor: {dec.executor}")
            lines.append(f"Impact Level: {dec.impact_level}")
            lines.append("")
        return "\n".join(lines)

    def _get_reference_time(self, episodes: List[Episode]) -> str:
        if not episodes:
            return "Not specified"
        latest_timestamp = None
        for episode in episodes:
            if episode.timestamp:
                if latest_timestamp is None or episode.timestamp > latest_timestamp:
                    latest_timestamp = episode.timestamp
        if latest_timestamp:
            if isinstance(latest_timestamp, datetime):
                return latest_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            return str(latest_timestamp)
        return "Not specified"

    def _validate_decision_extraction(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        if "decisions" not in data:
            errors.append("Missing required field 'decisions'")
            return False, errors
        decisions = data.get("decisions", [])
        if not isinstance(decisions, list):
            errors.append("'decisions' must be a list")
            return False, errors
        decision_ids = set()
        for i, dec in enumerate(decisions):
            if not isinstance(dec, dict):
                errors.append(f"Decision #{i+1} must be a dict")
                continue
            for field in ["decision_id", "title", "content"]:
                if field not in dec or not dec.get(field):
                    errors.append(f"Decision #{i+1} missing or empty field '{field}'")
            dec_id = dec.get("decision_id", "")
            if dec_id in decision_ids:
                errors.append(f"Duplicate decision_id: {dec_id}")
            decision_ids.add(dec_id)
            confidence = dec.get("confidence", 0)
            try:
                cf = float(confidence)
                if cf < 0.6:
                    errors.append(f"Decision '{dec_id}' confidence {cf} < 0.6, should skip")
            except (ValueError, TypeError):
                errors.append(f"Decision '{dec_id}' confidence must be numeric")
            impact = dec.get("impact_level", "minor")
            if impact not in ("major", "minor", "advisory"):
                errors.append(f"Decision '{dec_id}' invalid impact_level: {impact}")
        return len(errors) == 0, errors

    async def extract_decisions(
        self,
        topic: Topic,
        episodes: List[Episode],
    ) -> DecisionExtractResult:
        logger.info(f"[DecisionExtractor] Extracting decisions for topic {topic.topic_id}")

        topic_id, topic_title, topic_summary = self._format_topic_context(topic)
        episodes_content = self._format_episodes_content(episodes)
        reference_time = self._get_reference_time(episodes)

        simple_to_real = {f"episode_{i+1}": ep.event_id for i, ep in enumerate(episodes)}

        prompt = DECISION_EXTRACTION_PROMPT.format(
            topic_id=topic_id,
            topic_title=topic_title,
            topic_summary=topic_summary,
            episodes_content=episodes_content,
            reference_time=reference_time,
        )

        resp = await self.llm_provider.generate(prompt, response_format={"type": "json_object"})

        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            if HAS_JSON_REPAIR:
                data = json_repair.loads(resp)
            else:
                raise

        has_decisions = data.get("has_decisions", False)
        if not has_decisions:
            logger.info(f"[DecisionExtractor] No decisions found for topic {topic.topic_id}")
            return DecisionExtractResult(topic_id=topic_id, decisions=[], reasoning=data.get("reasoning", ""))

        is_valid, errors = self._validate_decision_extraction(data)
        if not is_valid:
            for err in errors:
                logger.warning(f"[DecisionExtractor] Validation: {err}")

        decisions = []
        for item in data.get("decisions", []):
            dec_id = f"decision_{str(uuid.uuid4())}"
            confidence = float(item.get("confidence", 0.7))
            dec = Decision(
                decision_id=dec_id,
                title=item.get("title", "Untitled Decision"),
                content=item.get("content", ""),
                confidence=confidence,
                status=DecisionStatus.PENDING if confidence >= 0.8 else DecisionStatus.PENDING_CONFIRMATION,
                chat_id=self.chat_id,
                source_episode_id="",
                source_topic_ids=[topic_id],
                rationale=item.get("rationale", ""),
                proposer=item.get("proposer"),
                executor=item.get("executor"),
                impact_level=item.get("impact_level", "minor"),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            decisions.append(dec)

        reasoning = data.get("reasoning", "")
        logger.info(f"[DecisionExtractor] Extracted {len(decisions)} decisions")
        return DecisionExtractResult(topic_id=topic_id, decisions=decisions, reasoning=reasoning)

    async def assign_roles(
        self,
        topic: Topic,
        decisions: List[Decision],
    ) -> Optional[DecisionRoleAssignmentResult]:
        if not decisions:
            return None

        topic_id, topic_title, topic_summary = self._format_topic_context(topic)
        decisions_text = self._format_decisions(decisions)

        prompt = DECISION_ROLE_ASSIGNMENT_PROMPT.format(
            topic_id=topic_id,
            topic_title=topic_title,
            topic_summary=topic_summary,
            decisions_text=decisions_text,
        )

        resp = await self.llm_provider.generate(prompt, response_format={"type": "json_object"})

        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            if HAS_JSON_REPAIR:
                data = json_repair.loads(resp)
            else:
                raise

        llm_id_to_real = {}
        for i, dec in enumerate(decisions):
            llm_id_to_real[f"dec_{i+1}"] = dec.decision_id

        decision_roles = {}
        decision_priorities = {}
        for item in data.get("decision_roles", []):
            llm_id = item.get("decision_id", "")
            real_id = llm_id_to_real.get(llm_id, llm_id)
            decision_roles[real_id] = item.get("category", "other")
            decision_priorities[real_id] = item.get("priority", "medium")

        return DecisionRoleAssignmentResult(
            decision_roles=decision_roles,
            decision_priorities=decision_priorities,
            extraction_confidence=float(data.get("extraction_confidence", 0.8)),
            reasoning=data.get("reasoning", ""),
        )

    # Synchronous version for CLI use
    def extract_decisions_sync(
        self,
        topic: Topic,
        episodes: List[Episode],
    ) -> DecisionExtractResult:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.extract_decisions(topic, episodes))