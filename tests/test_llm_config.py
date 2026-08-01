from __future__ import annotations

import os

import pytest

from src.llm.config import LLMConfig, get_llm_config, set_llm_config


class TestLLMConfig:
    def test_default_config_no_env(self):
        config = LLMConfig()
        assert isinstance(config.model_name, str)
        assert isinstance(config.base_url, str)
        assert config.max_tokens == 4096
        assert config.temperature == 0.1

    def test_config_valid_with_api_key(self):
        config = LLMConfig(api_key="sk-test")
        assert config.is_valid()

    def test_config_invalid_without_api_key(self):
        config = LLMConfig(api_key="")
        assert not config.is_valid()

    def test_custom_config_values(self):
        config = LLMConfig(
            model_name="gpt-4o-mini",
            base_url="https://custom.api.com/v1",
            api_key="sk-custom",
            max_tokens=2048,
            temperature=0.5,
        )
        assert config.model_name == "gpt-4o-mini"
        assert config.base_url == "https://custom.api.com/v1"
        assert config.api_key == "sk-custom"
        assert config.max_tokens == 2048
        assert config.temperature == 0.5

    def test_get_set_llm_config(self):
        original = get_llm_config()
        try:
            custom = LLMConfig(api_key="sk-test-override")
            set_llm_config(custom)
            assert get_llm_config() is custom
        finally:
            set_llm_config(original)

    def test_get_llm_config_returns_singleton(self):
        c1 = get_llm_config()
        c2 = get_llm_config()
        assert c1 is c2


class TestLLMClient:
    def test_client_requires_api_key(self):
        from src.llm.client import LLMClient

        config = LLMConfig(api_key="", base_url="https://test.api.com/v1")
        client = LLMClient(config=config)
        with pytest.raises(ValueError, match="API_KEY"):
            _ = client.client

    def test_client_with_config(self):
        from src.llm.client import LLMClient

        config = LLMConfig(api_key="sk-test", base_url="https://test.api.com/v1")
        client = LLMClient(config=config)
        assert client.config.api_key == "sk-test"
        assert client.config.base_url == "https://test.api.com/v1"
        assert client._client is None  # lazy init

    def test_client_reset(self):
        from src.llm.client import LLMClient

        config = LLMConfig(api_key="sk-test", base_url="https://test.api.com/v1")
        client = LLMClient(config=config)
        client._client = "fake"
        client.reset_client()
        assert client._client is None