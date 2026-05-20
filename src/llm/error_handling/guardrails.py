"""
Output validation guardrails for LLM responses.

Translates ref/llm/error_handling/guardrails.go:
- Uses Pydantic model validation instead of Go's guardrails
- Validates LLM output structure, content, and field constraints
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DecisionOutput(BaseModel):
    """Validated decision output schema for LLM extraction."""
    title: str = Field(default="untitled", min_length=0, max_length=200)
    content: str = Field(default="", max_length=10000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(default="pending")
    rationale: str = Field(default="", max_length=5000)
    proposer: str = Field(default="", max_length=100)
    executor: str = Field(default="", max_length=100)
    impact_level: str = Field(default="minor")
    tags: List[str] = Field(default_factory=list)


class TopicOutput(BaseModel):
    """Validated topic output schema."""
    topic: str = Field(..., min_length=1, max_length=200)
    keywords: List[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class GuardrailsValidationError(Exception):
    pass


def validate_llm_output(
    raw_output: str,
    schema: Type[T],
    strict: bool = True,
) -> T:
    """Validate LLM output string against a Pydantic schema.

    Args:
        raw_output: Raw string output from LLM (can be JSON or plain text).
        schema: Pydantic model class to validate against.
        strict: If True, raises on validation error. If False, logs warning.

    Returns:
        Validated model instance.

    Raises:
        GuardrailsValidationError: If strict=True and validation fails.
    """
    try:
        parsed = _parse_output(raw_output)
        return schema(**parsed)
    except (json.JSONDecodeError, ValidationError) as e:
        if strict:
            raise GuardrailsValidationError(
                f"LLM output validation failed against {schema.__name__}: {e}"
            )
        logger.warning("LLM output validation failed (non-strict): %s", e)
        return schema()


class LLMOutputValidator(Generic[T]):
    """Reusable validator for a specific output schema."""

    def __init__(self, schema: Type[T], strict: bool = True) -> None:
        self._schema = schema
        self._strict = strict

    def validate(self, raw_output: str) -> T:
        return validate_llm_output(raw_output, self._schema, self._strict)

    @property
    def schema(self) -> Type[T]:
        return self._schema


def _parse_output(raw: str) -> Dict[str, Any]:
    """Try to parse LLM output as JSON, or wrap plain text."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("` \t\n\r")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"content": text}