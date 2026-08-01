"""
Tests for src/llm/error_handling module.
"""
from typing import Any, Dict

import pytest

from llm.error_handling import (
    FailureType,
    LLMCircuitBreaker,
    LLMOutputValidator,
    RecoveryResult,
    RecoveryStrategy,
    recover,
    validate_llm_output,
)
from llm.error_handling.circuit_breaker import llm_call_with_retry
from llm.error_handling.guardrails import DecisionOutput, TopicOutput


# ==================== Circuit Breaker Tests ====================


class TestLLMCircuitBreaker:
    def test_direct_success(self) -> None:
        cb = LLMCircuitBreaker()
        result = cb.protect(lambda: "hello")
        assert result == "hello"

    def test_state_closed_after_create(self) -> None:
        cb = LLMCircuitBreaker()
        assert str(cb.breaker.current_state) == "closed"

    def test_llm_call_with_retry_success(self) -> None:
        result = llm_call_with_retry(lambda x: f"result: {x}", "test")
        assert result == "result: test"


# ==================== Guardrails Tests ====================


class TestValidateLLMOutput:
    def test_validate_json_output(self) -> None:
        raw = '{"title": "Test", "content": "hello", "confidence": 0.9}'
        result = validate_llm_output(raw, DecisionOutput)
        assert result.title == "Test"
        assert result.confidence == 0.9

    def test_validate_with_code_block(self) -> None:
        raw = '```json\n{"title": "Code Block", "content": "test"}\n```'
        result = validate_llm_output(raw, DecisionOutput)
        assert result.title == "Code Block"

    def test_validate_failure_strict(self) -> None:
        with pytest.raises(Exception):
            validate_llm_output(
                '{"title": "x", "confidence": 999}',
                DecisionOutput,
                strict=True,
            )

    def test_validate_failure_non_strict(self) -> None:
        result = validate_llm_output("not json", DecisionOutput, strict=False)
        assert isinstance(result, DecisionOutput)

    def test_topic_output(self) -> None:
        raw = '{"topic": "AI", "keywords": ["ml", "dl"], "confidence": 0.8}'
        result = validate_llm_output(raw, TopicOutput)
        assert result.topic == "AI"
        assert "ml" in result.keywords

    def test_llm_output_validator(self) -> None:
        validator = LLMOutputValidator(DecisionOutput)
        raw = '{"title": "Validated", "content": "ok"}'
        result = validator.validate(raw)
        assert result.title == "Validated"

    def test_default_values(self) -> None:
        result = validate_llm_output('{"title": "Minimal"}', DecisionOutput)
        assert result.content == ""
        assert result.confidence == 1.0
        assert result.status == "pending"


# ==================== Recovery Tests ====================


class TestRecovery:
    def test_direct_success(self) -> None:
        result = recover(lambda: 42, FailureType.API_TIMEOUT)
        assert result.success
        assert result.value == 42
        assert result.strategy_used == "direct"

    def test_recover_with_fallback_value(self) -> None:
        strategy = RecoveryStrategy(fallback_value="backup")
        result = strategy.apply(ValueError("failed"))
        assert result.success
        assert result.value == "backup"
        assert result.strategy_used == "fallback_value"

    def test_recover_with_fallback_fn(self) -> None:
        strategy = RecoveryStrategy(fallback_fn=lambda **kw: "computed")
        result = strategy.apply(ValueError("failed"))
        assert result.success
        assert result.value == "computed"
        assert result.strategy_used == "fallback_fn"

    def test_recover_no_strategy(self) -> None:
        strategy = RecoveryStrategy()
        result = strategy.apply(ValueError("no fallback"))
        assert not result.success
        assert "no fallback" in (result.error or "")

    def test_recover_operation_failure(self) -> None:
        def failing() -> None:
            raise ValueError("operation failed")

        result = recover(failing, FailureType.INVALID_OUTPUT)
        assert not result.success

    def test_failure_type_enum(self) -> None:
        assert FailureType.API_TIMEOUT.value == "api_timeout"
        assert FailureType.API_RATE_LIMIT.value == "api_rate_limit"
        assert FailureType.CIRCUIT_OPEN.value == "circuit_open"
        assert FailureType.UNKNOWN.value == "unknown"


