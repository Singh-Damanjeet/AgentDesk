import asyncio
import json
import logging
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
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_REQUEST_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.25
CONNECTION_TEST_MAX_OUTPUT_TOKENS = 256
REQUEST_ID_HEADERS = (
    "x-request-id",
    "x-goog-request-id",
    "request-id",
)
SUPPORTED_JSON_SCHEMA_KEYS = frozenset(
    {
        "$id",
        "$defs",
        "$ref",
        "$anchor",
        "type",
        "format",
        "title",
        "description",
        "enum",
        "items",
        "prefixItems",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "anyOf",
        "oneOf",
        "properties",
        "additionalProperties",
        "required",
        "propertyOrdering",
    }
)

logger = logging.getLogger(__name__)

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
            raw_schema_definition = schema.model_json_schema()
            schema_definition = self._sanitize_json_schema(
                raw_schema_definition
            )
            if not isinstance(schema_definition, dict):
                raise TypeError("The Pydantic schema was not an object.")

            json.dumps(
                schema_definition,
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
                    "Return only the requested structured object. Do not add "
                    "markdown or explanatory text."
                ),
            ),
        ]

        response = await self._generate_content(
            structured_messages,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=schema_definition,
        )

        try:
            parsed = json.loads(self._strip_json_fence(response.content))
            return schema.model_validate(parsed)
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
            raise LLMStructuredOutputError(
                "The AI provider returned data that did not match the requested "
                "schema.",
                diagnostics=self._structured_output_diagnostics(exc),
            ) from exc

    async def test_connection(self) -> None:
        await self.chat(
            [
                ChatMessage(
                    role="user",
                    content="Reply with exactly OK.",
                )
            ],
            temperature=0.0,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_output_tokens=CONNECTION_TEST_MAX_OUTPUT_TOKENS,
        )

    async def _generate_content(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None,
        timeout_seconds: float | None,
        max_output_tokens: int | None,
        response_mime_type: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
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
            response_json_schema=response_json_schema,
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

                    logger.warning(
                        "Gemini request timed out provider=%s model=%s "
                        "timeout_seconds=%s attempt=%s",
                        self.provider,
                        self.model,
                        timeout_seconds,
                        attempt + 1,
                    )
                    raise LLMTimeoutError(
                        "The AI provider did not respond in time.",
                        diagnostics={
                            "transport_error_type": type(exc).__name__,
                        },
                    ) from exc
                except httpx.RequestError as exc:
                    if attempt < MAX_REQUEST_ATTEMPTS - 1:
                        await self._sleep_before_retry(attempt)
                        continue

                    logger.warning(
                        "Gemini request failed before response provider=%s "
                        "model=%s error_type=%s attempt=%s",
                        self.provider,
                        self.model,
                        type(exc).__name__,
                        attempt + 1,
                    )
                    raise LLMProviderError(
                        "The AI provider is temporarily unavailable.",
                        diagnostics={
                            "transport_error_type": type(exc).__name__,
                        },
                    ) from exc
                except httpx.HTTPError as exc:
                    logger.warning(
                        "Gemini request failed provider=%s model=%s "
                        "error_type=%s attempt=%s",
                        self.provider,
                        self.model,
                        type(exc).__name__,
                        attempt + 1,
                    )
                    raise LLMProviderError(
                        "The AI provider is temporarily unavailable.",
                        diagnostics={
                            "transport_error_type": type(exc).__name__,
                        },
                    ) from exc

                if 200 <= response.status_code < 300:
                    return response

                self._log_provider_failure(response, attempt=attempt)
                error = self._error_for_status(response.status_code)
                error.diagnostics.update(
                    self._safe_provider_diagnostics(response)
                )
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

    def _log_provider_failure(
        self,
        response: httpx.Response,
        *,
        attempt: int,
    ) -> None:
        google_error_code, google_error_status = (
            self._safe_google_error_metadata(response)
        )
        request_id = self._response_request_id(response)

        logger.warning(
            "Gemini request failed provider=%s model=%s http_status=%s "
            "google_error_status=%s google_error_code=%s request_id=%s "
            "attempt=%s",
            self.provider,
            self.model,
            response.status_code,
            google_error_status,
            google_error_code,
            request_id,
            attempt + 1,
        )

    def _safe_provider_diagnostics(
        self,
        response: httpx.Response,
    ) -> dict[str, object]:
        google_error_code, google_error_status = (
            self._safe_google_error_metadata(response)
        )
        return {
            "http_status": response.status_code,
            "google_error_status": google_error_status,
            "google_error_code": google_error_code,
            "request_id": self._response_request_id(response),
        }

    @staticmethod
    def _safe_google_error_metadata(
        response: httpx.Response,
    ) -> tuple[int | None, str | None]:
        try:
            payload = response.json()
        except ValueError:
            return None, None

        if not isinstance(payload, dict):
            return None, None

        error = payload.get("error")
        if not isinstance(error, dict):
            return None, None

        raw_code = error.get("code")
        code = (
            raw_code
            if isinstance(raw_code, int) and not isinstance(raw_code, bool)
            else None
        )
        raw_status = error.get("status")
        status = (
            raw_status.strip()[:64]
            if isinstance(raw_status, str) and raw_status.strip()
            else None
        )

        return code, status

    @staticmethod
    def _response_request_id(response: httpx.Response) -> str | None:
        for header_name in REQUEST_ID_HEADERS:
            value = response.headers.get(header_name)
            if value:
                return value[:128]

        return None

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
        response_json_schema: dict[str, Any] | None,
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

        if response_json_schema is not None:
            generation_config["responseJsonSchema"] = response_json_schema

        if generation_config:
            payload["generationConfig"] = generation_config

        return payload

    @classmethod
    def _sanitize_json_schema(cls, value: object) -> object:
        if isinstance(value, dict):
            sanitized: dict[str, object] = {}
            for key, item in value.items():
                if key not in SUPPORTED_JSON_SCHEMA_KEYS:
                    continue

                if key in {"properties", "$defs"}:
                    if not isinstance(item, dict):
                        continue
                    sanitized[key] = {
                        property_name: cls._sanitize_json_schema(
                            property_schema
                        )
                        for property_name, property_schema in item.items()
                        if isinstance(property_name, str)
                    }
                    continue

                sanitized[key] = cls._sanitize_json_schema(item)

            return sanitized

        if isinstance(value, list):
            return [cls._sanitize_json_schema(item) for item in value]

        return value

    @staticmethod
    def _structured_output_diagnostics(
        error: Exception,
    ) -> dict[str, object]:
        if isinstance(error, json.JSONDecodeError):
            return {
                "structured_output_failure": "invalid_json",
                "json_error_type": error.msg[:128],
            }

        if isinstance(error, ValidationError):
            fields = sorted(
                {
                    str(location)
                    for validation_error in error.errors()
                    for location in validation_error.get("loc", ())
                }
            )
            error_types = sorted(
                {
                    str(validation_error.get("type"))
                    for validation_error in error.errors()
                    if validation_error.get("type") is not None
                }
            )
            return {
                "structured_output_failure": "schema_validation",
                "validation_fields": fields,
                "validation_error_types": error_types,
            }

        return {
            "structured_output_failure": "invalid_structured_response",
            "cause_type": type(error).__name__,
        }

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
        if status_code == 400:
            return LLMInputError(
                "Gemini rejected the request as invalid."
            )

        if status_code in {401, 403}:
            return LLMAuthenticationError(
                "Gemini API credentials are invalid or unauthorized."
            )

        if status_code == 404:
            return LLMConfigurationError(
                "The configured Gemini model or endpoint was not found."
            )

        if status_code == 429:
            return LLMRateLimitError(
                "The Gemini API is rate limited or quota is exhausted."
            )

        if status_code >= 500:
            return LLMProviderError(
                "The Gemini API is temporarily unavailable."
            )

        return LLMProviderError(
            "The Gemini API rejected the request."
        )

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        normalized = content.strip()

        if normalized.startswith("```") and normalized.endswith("```"):
            lines = normalized.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()

        return normalized
