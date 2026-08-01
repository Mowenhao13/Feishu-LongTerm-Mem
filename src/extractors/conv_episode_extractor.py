"""
Conversation Episode Extractor

Detects episode boundaries in conversation data and extracts
structured Episode objects with episodic memory generation.
"""

import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
import uuid
import json
import re
import asyncio

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

from model.llm_provider import LLMProvider
from types import RawDataType, Episode
from prompts.conv_prompts import CONV_BOUNDARY_DETECTION_PROMPT
from prompts.episode_prompts import (
    EPISODE_GENERATION_PROMPT,
    DEFAULT_CUSTOM_INSTRUCTIONS,
)
from extractors.episode_extractor import (
    EpisodeExtractor, RawData, StatusResult, EpisodeExtractRequest
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BoundaryDetectionResult:
    """Boundary detection result."""
    should_end: bool
    should_wait: bool
    reasoning: str
    confidence: float
    topic_summary: Optional[str] = None


@dataclass
class ConvEpisodeExtractRequest(EpisodeExtractRequest):
    pass


class ConvEpisodeExtractor(EpisodeExtractor):
    def __init__(self, llm_provider=LLMProvider, max_wait_messages=0, max_wait_seconds=0, **llm_kwargs):
        super().__init__(RawDataType.CONVERSATION, llm_provider, **llm_kwargs)
        self.llm_provider = llm_provider
        self.max_wait_messages = max_wait_messages
        self.max_wait_seconds = max_wait_seconds

    def _extract_participant_ids(self, chat_raw_data_list):
        participant_ids = set()
        for raw_data in chat_raw_data_list:
            if 'speaker_id' in raw_data and raw_data['speaker_id']:
                participant_ids.add(raw_data['speaker_id'])
            if 'referList' in raw_data and raw_data['referList']:
                for refer_item in raw_data['referList']:
                    if isinstance(refer_item, dict):
                        if '_id' in refer_item:
                            participant_ids.add(str(refer_item['_id']))
                        elif 'id' in refer_item:
                            participant_ids.add(refer_item['id'])
                    elif isinstance(refer_item, str):
                        participant_ids.add(refer_item)
        return list(participant_ids)

    def _format_conversation_dicts(self, messages, include_timestamps=False):
        lines = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            speaker_name = msg.get("speaker_name", "")
            timestamp = msg.get("timestamp", "")
            if content:
                if include_timestamps and timestamp:
                    try:
                        if isinstance(timestamp, datetime):
                            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        elif isinstance(timestamp, str):
                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            lines.append(f"{speaker_name}: {content}")
                            continue
                        lines.append(f"[{time_str}] {speaker_name}: {content}")
                    except (ValueError, AttributeError, TypeError):
                        lines.append(f"{speaker_name}: {content}")
                else:
                    lines.append(f"{speaker_name}: {content}")
        return "\n".join(lines)

    def _format_conversation_json_text(self, data_list):
        lines = []
        for data in data_list:
            speaker = data.get('speaker_name') or data.get('sender', 'Unknown')
            content = data.get('content', '')
            timestamp = data.get('timestamp', '')
            if timestamp:
                lines.append(f'\n                {{\n                    "timestamp": {timestamp},\n                    "speaker": {speaker},\n                    "content": {content}\n                }}')
            else:
                lines.append(f'\n                {{\n                    "speaker": {speaker},\n                    "content": {content}\n                }}')
        return "\n".join(lines)

    def _parse_timestamp(self, timestamp):
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            try:
                if timestamp.isdigit():
                    return datetime.fromtimestamp(int(timestamp))
                else:
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return datetime.now()
        else:
            return datetime.now()

    def _format_timestamp(self, dt):
        weekday = dt.strftime("%A")
        month_day = dt.strftime("%B %d, %Y")
        time_of_day = dt.strftime("%I:%M %p")
        return f"{month_day} ({weekday}) at {time_of_day} UTC"

    def _calculate_time_gap(self, conversation_history, new_messages):
        if not conversation_history or not new_messages:
            return "No time gap information available"
        try:
            last_history_msg = conversation_history[-1]
            first_new_msg = new_messages[0]
            last_timestamp_str = last_history_msg.get("timestamp", "")
            first_timestamp_str = first_new_msg.get("timestamp", "")
            if not last_timestamp_str or not first_timestamp_str:
                return "No timestamp information available"
            try:
                if isinstance(last_timestamp_str, datetime):
                    last_time = last_timestamp_str
                elif isinstance(last_timestamp_str, str):
                    last_time = datetime.fromisoformat(last_timestamp_str.replace("Z", "+00:00"))
                else:
                    return "Invalid timestamp format for last message"
                if isinstance(first_timestamp_str, datetime):
                    first_time = first_timestamp_str
                elif isinstance(first_timestamp_str, str):
                    first_time = datetime.fromisoformat(first_timestamp_str.replace("Z", "+00:00"))
                else:
                    return "Invalid timestamp format for first message"
            except (ValueError, TypeError):
                return "Failed to parse timestamps"
            time_diff = first_time - last_time
            total_seconds = time_diff.total_seconds()
            if total_seconds < 0:
                return "Time gap: Messages appear to be out of order"
            elif total_seconds < 60:
                return f"Time gap: {int(total_seconds)} seconds (immediate response)"
            elif total_seconds < 3600:
                minutes = int(total_seconds // 60)
                return f"Time gap: {minutes} minutes (recent conversation)"
            elif total_seconds < 86400:
                hours = int(total_seconds // 3600)
                return f"Time gap: {hours} hours (same day, but significant pause)"
            else:
                days = int(total_seconds // 86400)
                return f"Time gap: {days} days (long gap, likely new conversation)"
        except (ValueError, KeyError, AttributeError) as e:
            return f"Time gap calculation error: {str(e)}"

    async def _detect_boundary(self, conversation_history, new_messages):
        if not conversation_history:
            return BoundaryDetectionResult(should_end=False, should_wait=False, reasoning="First messages in conversation", confidence=1.0, topic_summary="")
        history_text = self._format_conversation_dicts(conversation_history, include_timestamps=True)
        new_text = self._format_conversation_dicts(new_messages, include_timestamps=True)
        time_gap_info = self._calculate_time_gap(conversation_history, new_messages)
        prompt = CONV_BOUNDARY_DETECTION_PROMPT.format(conversation_history=history_text, new_messages=new_text, time_gap_info=time_gap_info)
        resp = await self.llm_provider.generate(prompt, response_format={"type": "json_object"})
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            return BoundaryDetectionResult(should_end=False, should_wait=True, reasoning="Failed to parse LLM response", confidence=1.0, topic_summary="")
        return BoundaryDetectionResult(
            should_end=data.get("should_end", False),
            should_wait=data.get("should_wait", True),
            reasoning=data.get("reasoning", "No reason provided"),
            confidence=data.get("confidence", 1.0),
            topic_summary=data.get("topic_summary", ""),
        )

    async def _generate_episode_memory(self, episode, message_dict_list):
        conversation_text = self._format_conversation_json_text(message_dict_list)
        start_time = self._parse_timestamp(episode.timestamp)
        start_time_str = self._format_timestamp(start_time)
        prompt = EPISODE_GENERATION_PROMPT.format(
            conversation_start_time=start_time_str,
            conversation=conversation_text,
            custom_instructions=DEFAULT_CUSTOM_INSTRUCTIONS,
        )
        response = await self.llm_provider.generate(prompt, response_format={"type": "json_object"})
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            if HAS_JSON_REPAIR:
                data = json_repair.loads(response)
            else:
                raise
        episode.subject = data.get("title", "Conversation Episode")
        episode.summary = data.get("summary", data.get("content", conversation_text)[:200] + "...")
        episode.episode_description = data.get("content", conversation_text)
        return episode

    async def extract_episode(self, request):
        history_message_dict_list = []
        for raw_data in request.history_raw_data_list:
            processed_data = self._data_process(raw_data)
            if processed_data is not None:
                history_message_dict_list.append(processed_data)
        if request.new_raw_data_list and self._data_process(request.new_raw_data_list[-1]) is None:
            return (None, StatusResult(should_wait=True))
        new_message_dict_list = []
        for new_raw_data in request.new_raw_data_list:
            processed_data = self._data_process(new_raw_data)
            if processed_data is not None:
                new_message_dict_list.append(processed_data)
        if not new_message_dict_list:
            return (None, StatusResult(should_wait=True))
        if request.smart_mask_flag:
            boundary_detection_result = await self._detect_boundary(conversation_history=history_message_dict_list[:-1], new_messages=new_message_dict_list)
        else:
            boundary_detection_result = await self._detect_boundary(conversation_history=history_message_dict_list, new_messages=new_message_dict_list)
        should_end = boundary_detection_result.should_end
        should_wait = boundary_detection_result.should_wait
        status_control_result = StatusResult(should_wait=should_wait)

        total_messages = len(history_message_dict_list) + len(new_message_dict_list)
        force_end = False
        force_reason = ""
        if not should_end and should_wait:
            if self.max_wait_messages > 0 and total_messages >= self.max_wait_messages:
                force_end = True
                force_reason = f"force_end by max_wait_messages ({total_messages} >= {self.max_wait_messages})"
            if self.max_wait_seconds > 0 and history_message_dict_list:
                first_ts = history_message_dict_list[0].get("timestamp")
                if first_ts:
                    now = datetime.now()
                    if isinstance(first_ts, datetime):
                        first_dt = first_ts
                    elif isinstance(first_ts, (int, float)):
                        first_dt = datetime.fromtimestamp(first_ts)
                    else:
                        first_dt = None
                    if first_dt:
                        elapsed = (now - first_dt).total_seconds()
                        if elapsed >= self.max_wait_seconds:
                            force_end = True
                            force_reason = f"force_end by max_wait_seconds ({elapsed:.0f}s >= {self.max_wait_seconds}s)"

        if should_end or force_end:
            if force_end:
                status_control_result = StatusResult(should_wait=False)
                logger.info(f"[ConvEpisodeExtractor] {force_reason}")
            timestamp = history_message_dict_list[-1].get("timestamp")
            if isinstance(timestamp, str):
                timestamp = int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
            participants = self._extract_participant_ids(history_message_dict_list)
            episode = Episode(
                event_id=str(uuid.uuid4()),
                user_id_list=request.user_id_list,
                original_data=history_message_dict_list,
                timestamp=timestamp,
                summary=boundary_detection_result.topic_summary or "",
                participants=participants,
                type=self.raw_data_type,
            )
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    episode = await self._generate_episode_memory(episode, history_message_dict_list)
                    return (episode, status_control_result)
                except Exception as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                    else:
                        pass
            return (episode, status_control_result)
        elif should_wait:
            pass
        return (None, status_control_result)

    def _data_process(self, raw_data):
        content = raw_data.content.copy() if isinstance(raw_data.content, dict) else raw_data.content
        msg_type = content.get('msgType') if isinstance(content, dict) else None
        SUPPORTED_MSG_TYPES = {1: None, 2: "[Image]", 3: "[Video]", 4: "[Audio]", 5: "[File]", 6: "[File]"}
        if isinstance(content, dict) and msg_type is not None:
            if msg_type not in SUPPORTED_MSG_TYPES:
                return None
            placeholder = SUPPORTED_MSG_TYPES[msg_type]
            if placeholder is not None:
                content = content.copy()
                content['content'] = placeholder
        return content

    # Synchronous version for CLI use
    def extract_episode_sync(self, request):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.extract_episode(request))
    # Synchronous version for _generate_episode_memory
    def _generate_episode_memory_sync(self, episode, message_dict_list):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._generate_episode_memory(episode, message_dict_list))
