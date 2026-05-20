"""
Error handling module: circuit breaker, guardrails, and recovery.

Replaces ref/llm/error_handling Go code with Python equivalents:
- pybreaker.CircuitBreaker → circuit breaker
- tenacity.retry → retry with exponential backoff
- Pydantic validation → guardrails/output safety
"""
from .circuit_breaker import LLMCircuitBreaker, llm_call_with_retry, llm_breaker
from .guardrails import validate_llm_output, LLMOutputValidator
from .recovery import RecoveryStrategy, FailureType, RecoveryResult, recover

__all__ = [
    "LLMCircuitBreaker",
    "llm_call_with_retry",
    "llm_breaker",
    "validate_llm_output",
    "LLMOutputValidator",
    "RecoveryStrategy",
    "FailureType",
    "RecoveryResult",
    "recover",
]