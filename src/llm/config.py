from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class LLMConfig:
    model_name: str = field(default_factory=lambda: os.environ.get("MODEL_NAME", "gpt-4o"))
    base_url: str = field(default_factory=lambda: os.environ.get("BASE_URL", "https://api.openai.com/v1"))
    api_key: str = field(default_factory=lambda: os.environ.get("API_KEY", ""))
    max_tokens: int = 4096
    max_new_tokens: int = 256
    temperature: float = 0.1
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    def is_valid(self) -> bool:
        return bool(self.api_key)


_default_config: Optional[LLMConfig] = None


def get_llm_config() -> LLMConfig:
    global _default_config
    if _default_config is None:
        _default_config = LLMConfig(
            model_name=os.environ.get("MODEL_NAME", "gpt-4o"),
            base_url=os.environ.get("BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("API_KEY", ""),
            max_tokens=int(os.environ.get("MAX_TOKENS", "4096")),
            max_new_tokens=int(os.environ.get("MAX_NEW_TOKENS", "256")),
        )
    return _default_config


def set_llm_config(config: LLMConfig) -> None:
    global _default_config
    _default_config = config