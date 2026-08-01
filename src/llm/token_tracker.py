from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import tiktoken


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: TokenUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


class TokenTracker:
    def __init__(self, model: str = "gpt-4o") -> None:
        self.model = model
        self.usage = TokenUsage()
        self.call_count = 0
        self._encoder: Optional[tiktoken.Encoding] = None

    @property
    def encoder(self) -> tiktoken.Encoding:
        if self._encoder is None:
            try:
                self._encoder = tiktoken.encoding_for_model(self.model)
            except KeyError:
                self._encoder = tiktoken.get_encoding("cl100k_base")
        return self._encoder

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def track(self, prompt: str, completion: str) -> TokenUsage:
        prompt_tokens = self.count_tokens(prompt)
        completion_tokens = self.count_tokens(completion)
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        self.usage.add(usage)
        self.call_count += 1
        return usage

    def track_from_response(self, response_prompt_tokens: int, response_completion_tokens: int) -> TokenUsage:
        usage = TokenUsage(
            prompt_tokens=response_prompt_tokens,
            completion_tokens=response_completion_tokens,
            total_tokens=response_prompt_tokens + response_completion_tokens,
        )
        self.usage.add(usage)
        self.call_count += 1
        return usage

    def summary(self) -> dict:
        return {
            "call_count": self.call_count,
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "total_tokens": self.usage.total_tokens,
        }

    def reset(self) -> None:
        self.usage = TokenUsage()
        self.call_count = 0