from __future__ import annotations

import json
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError, RateLimitError

from app.core.config import settings
from app.llm.exceptions import LLMProviderError
from app.llm.types import LLMResult, TokenUsage, ToolCallRequest, ToolTurnResult


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self.client: AsyncOpenAI | None = None
        if settings.openai_api_key:
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
            )

    def _require_client(self) -> AsyncOpenAI:
        if self.client is None:
            raise LLMProviderError(
                "OPENAI_API_KEY is not configured",
                code="missing_api_key",
                retryable=False,
            )
        return self.client

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

    @staticmethod
    def _usage(response: Any) -> TokenUsage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return TokenUsage()

        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        return TokenUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            cached_input_tokens=int(getattr(input_details, "cached_tokens", 0) or 0),
            cache_write_tokens=int(getattr(input_details, "cache_write_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            reasoning_tokens=int(getattr(output_details, "reasoning_tokens", 0) or 0),
            total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        )

    @staticmethod
    def _translate_error(exc: Exception) -> LLMProviderError:
        if isinstance(exc, RateLimitError):
            return LLMProviderError(str(exc), code="rate_limit", retryable=True)
        if isinstance(exc, APITimeoutError):
            return LLMProviderError(str(exc), code="timeout", retryable=True)
        if isinstance(exc, APIConnectionError):
            return LLMProviderError(str(exc), code="connection_error", retryable=True)
        if isinstance(exc, APIStatusError):
            retryable = exc.status_code >= 500 or exc.status_code in {408, 409, 429}
            return LLMProviderError(str(exc), code=f"http_{exc.status_code}", retryable=retryable)
        return LLMProviderError(str(exc), code="openai_error", retryable=False)

    async def generate(self, *, input_text: str, instructions: str, model: str) -> LLMResult:
        try:
            response = await self._require_client().responses.create(
                model=model,
                instructions=instructions,
                input=input_text,
                reasoning={"effort": settings.openai_reasoning_effort},
                store=False,
            )
        except OpenAIError as exc:
            raise self._translate_error(exc) from exc

        if getattr(response, "status", None) not in {None, "completed"}:
            raise LLMProviderError(
                f"OpenAI response ended with status={response.status}",
                code="incomplete_response",
                retryable=False,
            )

        text = response.output_text or ""
        if not text:
            raise LLMProviderError("OpenAI returned no output_text", code="empty_output")

        return LLMResult(
            provider=self.name,
            model=response.model or model,
            text=text,
            request_id=getattr(response, "_request_id", None),
            usage=self._usage(response),
        )

    async def generate_structured(
        self,
        *,
        input_text: str,
        instructions: str,
        model: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> LLMResult:
        try:
            response = await self._require_client().responses.create(
                model=model,
                instructions=instructions,
                input=input_text,
                reasoning={"effort": settings.openai_reasoning_effort},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": json_schema,
                    }
                },
                store=False,
            )
        except OpenAIError as exc:
            raise self._translate_error(exc) from exc

        text = response.output_text or ""
        if not text:
            raise LLMProviderError("OpenAI returned no structured output", code="empty_output")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("Structured output was not valid JSON", code="structured_parse_error") from exc

        return LLMResult(
            provider=self.name,
            model=response.model or model,
            text=text,
            request_id=getattr(response, "_request_id", None),
            usage=self._usage(response),
            structured_data=data,
        )

    async def generate_with_tools(
        self,
        *,
        input_data: str | list[Any],
        instructions: str,
        model: str,
        tools: list[dict[str, Any]],
    ) -> ToolTurnResult:
        try:
            response = await self._require_client().responses.create(
                model=model,
                instructions=instructions,
                input=input_data,
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=False,
                reasoning={"effort": settings.openai_reasoning_effort},
                include=["reasoning.encrypted_content"],
                store=False,
            )
        except OpenAIError as exc:
            raise self._translate_error(exc) from exc

        calls: list[ToolCallRequest] = []
        for item in response.output:
            if getattr(item, "type", None) != "function_call":
                continue
            try:
                arguments = json.loads(item.arguments)
            except json.JSONDecodeError as exc:
                raise LLMProviderError(
                    f"Tool arguments for {item.name!r} were not valid JSON",
                    code="tool_arguments_parse_error",
                    retryable=False,
                ) from exc
            calls.append(ToolCallRequest(call_id=item.call_id, name=item.name, arguments=arguments))

        return ToolTurnResult(
            provider=self.name,
            model=response.model or model,
            text=response.output_text or "",
            request_id=getattr(response, "_request_id", None),
            usage=self._usage(response),
            tool_calls=calls,
            # Official Responses guidance permits feeding response.output items back as input.
            # Keeping SDK objects also preserves reasoning items needed for stateless tool loops.
            continuation_items=list(response.output),
        )
