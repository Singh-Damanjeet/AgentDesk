import asyncio
import json
import time
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMInputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.ai.llm.types import ChatMessage, LLMResponse, LLMUsage
from app.core.ai_providers import (
    GEMINI_PROVIDER,
    SUPPORTED_GEMINI_MODELS,
)


GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_REQUEST_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.25

SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class GeminiLLMAdapter:
    """Gemini REST adapter implementing the provider-independent LLM contract."""

    def __init__(self, api_key: str, model: str):
        normalized_key = api_key.strip()
        normalized_model = model.removeprefix("models/").strip()

        if not normalized_key:
            raise LLMConfigurationError(
                "A Gemini API key is required."
            )

        if len(normalized_key) > 4096:
            raise LLMConfigurationError(
                "The Gemini API key is too long."
            )

        if normalized_model not in SUPPORTED_GEMINI_MODELS:
            raise LLMConfigurationError(
                "The selected Gemini model is not supported."
            )

        self._api_key = normalized_key
        self._model = normalized_model

    @property
    def provider(self) -> str:
        return GEMINI_PROVIDER

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        return await self._generate_content(
            messages,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaModel],
        *,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> SchemaModel:
        if not isinstance(schema, type) or not issubclass(schema, BaseModel):
            raise LLMInputError(
                "A Pydantic schema is required for structured output."
            )

        try:
            schema_json = json.dumps(
                schema.model_json_schema(),
                ensure_ascii=False,
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise LLMInputError(
                "The requested structured-output schema is invalid."
            ) from exc

        structured_messages = [
            *messages,
            ChatMessage(
                role="user",
                content=(
                    "Return exactly one JSON object and no markdown. "
                    "The JSON must conform to this schema: "
                    f"{schema_json}"
                ),
            ),
        ]

        response = await self._generate_content(
            structured_messages,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        )

        try:
            parsed = json.loads(self._strip_json_fence(response.content))
            return schema.model_validate(parsed)
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
            raise LLMStructuredOutputError(
                "The AI provider returned data that did not match the requested schema."
            ) from exc

    async def test_connection(self) -> None:
        await self._request(
            method="GET",
            url=(
                f"{GEMINI_API_BASE_URL}/models/"
                f"{self._model}"
            ),
            json_payload=None,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )

    async def _generate_content(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None,
        timeout_seconds: float | None,
        max_output_tokens: int | None,
        response_mime_type: str | None = None,
    ) -> LLMResponse:
        self._validate_generation_options(
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        normalized_messages = self._normalize_messages(messages)
        payload = self._build_payload(
            normalized_messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type,
        )
        started_at = time.perf_counter()

        response = await self._request(
            method="POST",
            url=(
                f"{GEMINI_API_BASE_URL}/models/"
                f"{self._model}:generateContent"
            ),
            json_payload=payload,
            timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
        )

        latency_ms = max(
            0,
            round((time.perf_counter() - started_at) * 1000),
        )
        response_payload = self._parse_response_payload(response)

        return self._normalize_response(
            response_payload,
            latency_ms=latency_ms,
        )

    async def _request(
        self,
        *,
        method: str,
        url: str,
        json_payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> httpx.Response:
        headers = {
            "x-goog-api-key": self._api_key,
        }

        if method == "POST":
            headers["content-type"] = "application/json"

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            for attempt in range(MAX_REQUEST_ATTEMPTS):
                try:
                    if method == "GET":
                        response = await client.get(
                            url,
                            headers=headers,
                        )
                    else:
                        response = await client.post(
                            url,
                            headers=headers,
                            json=json_payload,
                        )
                except httpx.TimeoutException as exc:
                    if attempt < MAX_REQUEST_ATTEMPTS - 1:
                        await self._sleep_before_retry(attempt)
                        continue

                    raise LLMTimeoutError(
                        "The AI provider did not respond in time."
                    ) from exc
                except httpx.RequestError as exc:
                    if attempt < MAX_REQUEST_ATTEMPTS - 1:
                        await self._sleep_before_retry(attempt)
                        continue

                    raise LLMProviderError(
                        "The AI provider is temporarily unavailable."
                    ) from exc
                except httpx.HTTPError as exc:
                    raise LLMProviderError(
                        "The AI provider is temporarily unavailable."
                    ) from exc

                if 200 <= response.status_code < 300:
                    return response

                error = self._error_for_status(response.status_code)
                is_transient = (
                    response.status_code == 429
                    or response.status_code >= 500
                )

                if is_transient and attempt < MAX_REQUEST_ATTEMPTS - 1:
                    await self._sleep_before_retry(attempt)
                    continue

                raise error

        raise LLMProviderError(
            "The AI provider is temporarily unavailable."
        )

    @staticmethod
    async def _sleep_before_retry(attempt: int) -> None:
        await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))

    @staticmethod
    def _validate_generation_options(
        *,
        temperature: float | None,
        timeout_seconds: float | None,
        max_output_tokens: int | None,
    ) -> None:
        if temperature is not None and not 0 <= temperature <= 2:
            raise LLMInputError(
                "Temperature must be between 0 and 2."
            )

        if (
            timeout_seconds is not None
            and not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise LLMInputError(
                "The AI request timeout is outside the supported range."
            )

        if max_output_tokens is not None and max_output_tokens <= 0:
            raise LLMInputError(
                "Maximum output tokens must be greater than zero."
            )

    @staticmethod
    def _normalize_messages(
        messages: Sequence[ChatMessage],
    ) -> list[ChatMessage]:
        normalized = list(messages)

        if not normalized:
            raise LLMInputError(
                "At least one chat message is required."
            )

        if not all(isinstance(message, ChatMessage) for message in normalized):
            raise LLMInputError(
                "Chat messages must use the AgentDesk message model."
            )

        if not any(message.role != "system" for message in normalized):
            raise LLMInputError(
                "At least one user or assistant message is required."
            )

        return normalized

    @staticmethod
    def _build_payload(
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None,
        max_output_tokens: int | None,
        response_mime_type: str | None,
    ) -> dict[str, Any]:
        system_messages = [
            message.content
            for message in messages
            if message.role == "system"
        ]
        contents = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
            for message in messages
            if message.role != "system"
        ]

        payload: dict[str, Any] = {
            "contents": contents,
        }

        if system_messages:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_messages)}],
            }

        generation_config: dict[str, Any] = {}

        if temperature is not None:
            generation_config["temperature"] = temperature

        if max_output_tokens is not None:
            generation_config["maxOutputTokens"] = max_output_tokens

        if response_mime_type is not None:
            generation_config["responseMimeType"] = response_mime_type

        if generation_config:
            payload["generationConfig"] = generation_config

        return payload

    @staticmethod
    def _parse_response_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                "The AI provider returned an invalid response."
            ) from exc

        if not isinstance(payload, dict):
            raise LLMResponseError(
                "The AI provider returned an invalid response."
            )

        return payload

    def _normalize_response(
        self,
        payload: dict[str, Any],
        *,
        latency_ms: int,
    ) -> LLMResponse:
        candidates = payload.get("candidates")

        if not isinstance(candidates, list) or not candidates:
            raise LLMResponseError(
                "The AI provider returned an empty response."
            )

        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise LLMResponseError(
                "The AI provider returned an invalid response."
            )

        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        text_parts = [
            part.get("text")
            for part in parts or []
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        normalized_content = "".join(text_parts).strip()

        if not normalized_content:
            raise LLMResponseError(
                "The AI provider returned an empty response."
            )

        return LLMResponse(
            content=normalized_content,
            provider=self.provider,
            model=self.model,
            latency_ms=latency_ms,
            finish_reason=(
                candidate.get("finishReason")
                if isinstance(candidate.get("finishReason"), str)
                else None
            ),
            usage=self._normalize_usage(payload.get("usageMetadata")),
        )

    @staticmethod
    def _normalize_usage(value: Any) -> LLMUsage | None:
        if not isinstance(value, dict):
            return None

        def as_non_negative_int(key: str) -> int | None:
            raw_value = value.get(key)
            if isinstance(raw_value, bool):
                return None

            try:
                normalized = int(raw_value)
            except (TypeError, ValueError):
                return None

            return normalized if normalized >= 0 else None

        prompt_tokens = as_non_negative_int("promptTokenCount")
        completion_tokens = as_non_negative_int("candidatesTokenCount")
        total_tokens = as_non_negative_int("totalTokenCount")

        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None

        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _error_for_status(status_code: int) -> LLMError:
        if status_code in {401, 403}:
            return LLMAuthenticationError(
                "Gemini API credentials are invalid or unauthorized."
            )

        if status_code == 404:
            return LLMConfigurationError(
                "The configured Gemini model is unavailable."
            )

        if status_code == 429:
            return LLMRateLimitError(
                "The AI provider is temporarily rate limited."
            )

        if status_code >= 500:
            return LLMProviderError(
                "The AI provider is temporarily unavailable."
            )

        return LLMProviderError(
            "The AI provider rejected the request."
        )

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        normalized = content.strip()

        if normalized.startswith("```") and normalized.endswith("```"):
            lines = normalized.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()

        return normalized
