"""
Circuit breaker with retry for LLM API calls.

Translates ref/llm/error_handling/circuit_breaker.go:
- pybreaker.CircuitBreaker: fail_max=3 → open, reset_timeout=60 → half-open
- tenacity: exponential backoff retry (1s, 2s, 4s max 10s)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

import pybreaker
from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Shared circuit breaker instance (singleton pattern)
llm_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=60,
    name="llm_api",
)


class LLMCircuitBreaker:
    """Wrapper that applies both circuit breaker and retry to an LLM call."""

    def __init__(
        self,
        fail_max: int = 3,
        reset_timeout: float = 60.0,
        max_retries: int = 3,
        min_wait: float = 1.0,
        max_wait: float = 10.0,
    ) -> None:
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            name="llm_api",
        )
        self._max_retries = max_retries
        self._min_wait = min_wait
        self._max_wait = max_wait

    @property
    def breaker(self) -> pybreaker.CircuitBreaker:
        return self._breaker

    def protect(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        retry_decorator = retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(
                multiplier=self._min_wait,
                max=self._max_wait,
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

        @self._breaker
        @retry_decorator
        def wrapped() -> T:
            return fn(*args, **kwargs)

        return wrapped()


def llm_call_with_retry(
    fn: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Decorated LLM call with circuit breaker + exponential backoff retry.

    Usage:
        result = llm_call_with_retry(my_llm_function, prompt="hello")
    """
    protector = LLMCircuitBreaker()
    return protector.protect(fn, *args, **kwargs)