from __future__ import annotations

import json
from typing import Any, Optional

from openai import OpenAI

from src.llm.config import LLMConfig, get_llm_config
from src.llm.error_handling import llm_call_with_retry
from src.llm.langfuse_config import get_langfuse, should_sample
from src.llm.token_tracker import TokenTracker, TokenUsage


class LLMClient:
    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or get_llm_config()
        self._client: Optional[OpenAI] = None
        self.token_tracker = TokenTracker(model=self.config.model_name)
        self._last_usage: Optional[TokenUsage] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self.config.api_key:
                raise ValueError(
                    "API_KEY is not set. Set MODEL_NAME, BASE_URL, API_KEY in .env file."
                )
            self._client = OpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        response_format: Optional[dict[str, str]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "max_tokens": max_tokens or self.config.max_new_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        if top_p is not None:
            kwargs["top_p"] = top_p
        elif self.config.top_p < 1.0:
            kwargs["top_p"] = self.config.top_p
        if self.config.frequency_penalty > 0.0:
            kwargs["frequency_penalty"] = self.config.frequency_penalty
        if self.config.presence_penalty > 0.0:
            kwargs["presence_penalty"] = self.config.presence_penalty
        if response_format:
            kwargs["response_format"] = response_format

        # Langfuse 埋点
        langfuse = get_langfuse()
        f_trace = None
        f_span = None
        if langfuse and should_sample():
            f_trace = langfuse.trace(
                name="llm_chat",
                input={"messages": messages[-2:] if messages else []},
                metadata={
                    "model": self.config.model_name,
                    "trace_id": trace_id or "",
                },
            )
            f_span = f_trace.span(name="openai_call")

        try:
            resp = self.client.chat.completions.create(**kwargs)

            if f_span and f_trace:
                usage = resp.usage
                if usage:
                    f_span.generation(
                        model=self.config.model_name,
                        input=messages,
                        output=resp.choices[0].message.content,
                        usage={"input": usage.prompt_tokens, "output": usage.completion_tokens},
                    )
                f_span.end(output={"status": "success", "tokens": ...})
                f_trace.end()

            if resp.usage:
                self._last_usage = self.token_tracker.track_from_response(
                    response_prompt_tokens=resp.usage.prompt_tokens or 0,
                    response_completion_tokens=resp.usage.completion_tokens or 0,
                )
            return resp.choices[0].message.content or ""

        except Exception as e:
            if f_span:
                f_span.end(output={"status": "error", "error": str(e)})
            if f_trace:
                f_trace.end()
            raise

    def chat_with_retry(
        self,
        messages: list[dict[str, str]],
        response_format: Optional[dict[str, str]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        def _call() -> str:
            return self.chat(messages, response_format, max_tokens, temperature, top_p, trace_id=trace_id)

        return llm_call_with_retry(_call)

    def chat_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> dict[str, Any]:
        content = self.chat_with_retry(
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        return json.loads(content)

    def reset_client(self) -> None:
        self._client = None