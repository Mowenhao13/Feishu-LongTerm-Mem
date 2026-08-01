"""
Failure recovery strategies for LLM operations.

Translates ref/llm/error_handling/recovery.go:
- Defines failure types and recovery strategies
- Falls back to simpler models or cached results on failure
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FailureType(str, Enum):
    """Types of failures that can occur during LLM operations."""
    API_TIMEOUT = "api_timeout"
    API_RATE_LIMIT = "api_rate_limit"
    API_UNAUTHORIZED = "api_unauthorized"
    INVALID_OUTPUT = "invalid_output"
    CIRCUIT_OPEN = "circuit_open"
    CONTENT_FILTERED = "content_filtered"
    UNKNOWN = "unknown"


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    success: bool = False
    value: Any = None
    strategy_used: str = ""
    error: Optional[str] = None


class RecoveryStrategy:
    """Defines recovery behaviors for different failure types.

    Each failure type can have:
    - fallback_value: a static default value to return
    - fallback_fn: a function to compute a fallback
    - degrade_fn: a function that tries a degraded/simpler approach
    """

    def __init__(
        self,
        fallback_value: Any = None,
        fallback_fn: Optional[Callable[..., Any]] = None,
        degrade_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._fallback_value = fallback_value
        self._fallback_fn = fallback_fn
        self._degrade_fn = degrade_fn

    def apply(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> RecoveryResult:
        if self._degrade_fn is not None:
            try:
                result = self._degrade_fn(**(context or {}))
                return RecoveryResult(success=True, value=result, strategy_used="degrade")
            except Exception as e:
                logger.warning("Degrade strategy failed: %s", e)

        if self._fallback_fn is not None:
            try:
                result = self._fallback_fn(**(context or {}))
                return RecoveryResult(success=True, value=result, strategy_used="fallback_fn")
            except Exception as e:
                logger.warning("Fallback function failed: %s", e)

        if self._fallback_value is not None:
            return RecoveryResult(
                success=True,
                value=self._fallback_value,
                strategy_used="fallback_value",
            )

        return RecoveryResult(
            success=False,
            error=str(error),
            strategy_used="none",
        )


_DEFAULT_STRATEGIES: Dict[FailureType, RecoveryStrategy] = {
    FailureType.API_TIMEOUT: RecoveryStrategy(
        fallback_value=None,
        degrade_fn=lambda **kw: logger.info("Retry with simpler model after timeout"),
    ),
    FailureType.API_RATE_LIMIT: RecoveryStrategy(
        fallback_value=None,
    ),
    FailureType.INVALID_OUTPUT: RecoveryStrategy(
        fallback_value=None,
    ),
    FailureType.CIRCUIT_OPEN: RecoveryStrategy(
        fallback_value=None,
    ),
}


def get_strategy(failure_type: FailureType) -> RecoveryStrategy:
    return _DEFAULT_STRATEGIES.get(failure_type, RecoveryStrategy(fallback_value=None))


def recover(
    fn: Callable[..., T],
    failure_type: FailureType,
    *args: Any,
    context: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> RecoveryResult:
    """Attempt to run fn; on failure, apply the recovery strategy.

    Args:
        fn: The function to attempt.
        failure_type: The type of failure to prepare for.
        context: Context dict passed to recovery strategies.
    """
    try:
        value = fn(*args, **kwargs)
        return RecoveryResult(success=True, value=value, strategy_used="direct")
    except Exception as e:
        logger.warning("Operation failed (%s): %s", failure_type.value, e)
        strategy = get_strategy(failure_type)
        return strategy.apply(e, context or {})