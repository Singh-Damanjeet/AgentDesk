import asyncio
import json
import logging
import re
import time
from collections.abc import Sequence
from typing import Any, NoReturn, TypeVar

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
    OPENROUTER_PROVIDER,
    is_valid_openrouter_model,
)
from app.schemas.agent import ClassificationResult


OPENROUTER_API_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_REQUEST_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.25
# Keep the probe aligned with the production classifier budget. Some
# reasoning-capable OpenRouter models can exhaust a smaller completion budget
# before emitting their structured response content.
CONNECTION_TEST_MAX_OUTPUT_TOKENS = 1_024
REQUEST_ID_HEADERS = (
    "x-request-id",
    "x-openrouter-request-id",
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
    }
)
MAX_RESPONSE_MODEL_LENGTH = 255
CLASSIFICATION_SCHEMA_NAME = "agentdesk_classification"
FINISH_REASON_REFUSAL_VALUES = frozenset(
    {
        "blocked",
        "content_filter",
        "refusal",
        "safety",
    }
)
FINISH_REASON_ERROR_VALUES = frozenset(
    {
        "error",
        "failed",
        "provider_error",
    }
)

logger = logging.getLogger(__name__)

SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class OpenRouterLLMAdapter:
    """OpenAI-compatible OpenRouter adapter for the shared LLM contract."""

    def __init__(self, api_key: str, model: str):
        normalized_key = api_key.strip()
        normalized_model = model.strip()

        if not normalized_key:
            raise LLMConfigurationError(
                "An OpenRouter API key is required."
            )

        if len(normalized_key) > 4096:
            raise LLMConfigurationError(
                "The OpenRouter API key is too long."
            )

        if not is_valid_openrouter_model(normalized_model):
            raise LLMConfigurationError(
                "Invalid OpenRouter model slug."
            )

        self._api_key = normalized_key
        self._model = normalized_model

    @property
    def provider(self) -> str:
        return OPENROUTER_PROVIDER

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
        return await self._generate_chat(
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

        schema_definition = self._schema_definition(schema)
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

        response = await self._generate_chat(
            structured_messages,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": self._structured_schema_name(schema),
                    "strict": True,
                    "schema": schema_definition,
                },
            },
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
        """Validate generation and the structured output required by AgentDesk."""

        try:
            result = await self.structured_output(
                [
                    ChatMessage(
                        role="user",
                        content=(
                            "Classify this support request using the AgentDesk "
                            "classification schema.\n"
                            "Customer request: How long do I have to request "
                            "a refund?"
                        ),
                    ),
                ],
                ClassificationResult,
                temperature=0.0,
                timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                max_output_tokens=CONNECTION_TEST_MAX_OUTPUT_TOKENS,
            )
        except (LLMInputError, LLMResponseError, LLMStructuredOutputError) as exc:
            raise LLMConfigurationError(
                "The selected OpenRouter model does not support AgentDesk "
                "structured output.",
                diagnostics=exc.diagnostics,
            ) from exc

        if not isinstance(result, ClassificationResult):
            raise LLMConfigurationError(
                "The selected OpenRouter model failed the AgentDesk "
                "compatibility test."
            )

    async def _generate_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None,
        timeout_seconds: float | None,
        max_output_tokens: int | None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self._validate_generation_options(
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        normalized_messages = self._normalize_messages(messages)
        payload = self._build_payload(
            normalized_messages,
            model=self._model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_format=response_format,
        )
        started_at = time.perf_counter()

        response = await self._request(
            url=f"{OPENROUTER_API_BASE_URL}/chat/completions",
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
            response=response,
        )

    async def _request(
        self,
        *,
        url: str,
        json_payload: dict[str, Any],
        timeout_seconds: float,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            for attempt in range(MAX_REQUEST_ATTEMPTS):
                try:
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
                        "OpenRouter request timed out provider=%s model=%s "
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
                        "OpenRouter request failed before response provider=%s "
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
                        "OpenRouter request failed provider=%s model=%s "
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
                error = self._error_for_response(response)
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
        diagnostics = self._safe_provider_diagnostics(response)
        logger.warning(
            "OpenRouter request failed provider=%s model=%s http_status=%s "
            "provider_error_status=%s provider_error_code=%s request_id=%s "
            "attempt=%s",
            self.provider,
            self.model,
            diagnostics["http_status"],
            diagnostics["provider_error_status"],
            diagnostics["provider_error_code"],
            diagnostics["request_id"],
            attempt + 1,
        )

    def _safe_provider_diagnostics(
        self,
        response: httpx.Response,
    ) -> dict[str, object]:
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None

        diagnostics = self._response_shape_diagnostics(
            response_payload,
            response=response,
            response_failure="http_non_2xx",
        )
        error = self._safe_provider_error(response)
        diagnostics["model"] = self.model
        diagnostics.update(
            {
                "provider_error_code": error.get("code"),
                "provider_error_type": error.get("type"),
                "provider_error_status": error.get("status"),
            }
        )
        return diagnostics

    @staticmethod
    def _safe_provider_error(response: httpx.Response) -> dict[str, object]:
        try:
            payload = response.json()
        except ValueError:
            return {}

        if not isinstance(payload, dict):
            return {}

        error = payload.get("error")
        if not isinstance(error, dict):
            return {}

        safe_error: dict[str, object] = {}
        raw_code = error.get("code")
        if isinstance(raw_code, int) and not isinstance(raw_code, bool):
            safe_error["code"] = raw_code
        elif isinstance(raw_code, str) and raw_code.strip():
            safe_error["code"] = raw_code.strip()[:128]

        for key in ("type", "status"):
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                safe_error[key] = value.strip()[:64]

        return safe_error

    @staticmethod
    def _response_request_id(
        response: httpx.Response,
        payload: object | None = None,
    ) -> str | None:
        for header_name in REQUEST_ID_HEADERS:
            value = response.headers.get(header_name)
            if value:
                return value[:128]

        if isinstance(payload, dict):
            response_id = payload.get("id")
            if isinstance(response_id, str) and response_id.strip():
                return response_id.strip()[:128]

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
        model: str,
        temperature: float | None,
        max_output_tokens: int | None,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
        }

        if temperature is not None:
            payload["temperature"] = temperature

        if max_output_tokens is not None:
            payload["max_tokens"] = max_output_tokens

        if response_format is not None:
            payload["response_format"] = response_format
            payload["provider"] = {
                "require_parameters": True,
            }

        payload["stream"] = False

        return payload

    @classmethod
    def _schema_definition(
        cls,
        schema: type[SchemaModel],
    ) -> dict[str, Any]:
        try:
            raw_schema_definition = schema.model_json_schema()
            schema_definition = cls._sanitize_json_schema(
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

        return schema_definition

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
    def _schema_name(schema: type[BaseModel]) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]", "_", schema.__name__)
        normalized = normalized.strip("_")[:64]
        return normalized or "agentdesk_response"

    @classmethod
    def _structured_schema_name(cls, schema: type[BaseModel]) -> str:
        if schema is ClassificationResult:
            return CLASSIFICATION_SCHEMA_NAME

        return cls._schema_name(schema)

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

    def _parse_response_payload(
        self,
        response: httpx.Response,
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            self._raise_response_error(
                "The AI provider returned a non-JSON response.",
                payload=None,
                response=response,
                response_failure="invalid_response_json",
                cause=exc,
            )

        if not isinstance(payload, dict):
            self._raise_response_error(
                "The AI provider returned an invalid response object.",
                payload=payload,
                response=response,
                response_failure="invalid_response_object",
            )

        return payload

    def _normalize_response(
        self,
        payload: dict[str, Any],
        *,
        latency_ms: int,
        response: httpx.Response | None = None,
    ) -> LLMResponse:
        if payload.get("error") is not None:
            self._raise_response_error(
                "The AI provider returned an error response.",
                payload=payload,
                response=response,
                response_failure="top_level_error",
            )

        choices = payload.get("choices")
        if not isinstance(choices, list):
            response_failure = (
                "choices_missing"
                if "choices" not in payload
                else "choices_invalid"
            )
            self._raise_response_error(
                "The AI provider response did not include a valid choices "
                "array.",
                payload=payload,
                response=response,
                response_failure=response_failure,
            )

        if not choices:
            self._raise_response_error(
                "The AI provider returned an empty choices array.",
                payload=payload,
                response=response,
                response_failure="empty_choices",
            )

        choice = choices[0]
        if not isinstance(choice, dict):
            self._raise_response_error(
                "The AI provider response did not include a first choice.",
                payload=payload,
                response=response,
                response_failure="first_choice_missing",
            )

        message = choice.get("message")
        if message is None:
            self._raise_response_error(
                "The AI provider response did not include a message.",
                payload=payload,
                response=response,
                response_failure="message_missing",
            )

        if not isinstance(message, dict):
            self._raise_response_error(
                "The AI provider response included an invalid message.",
                payload=payload,
                response=response,
                response_failure="message_invalid",
            )

        if "content" not in message:
            self._raise_response_error(
                "The AI provider response did not include message content.",
                payload=payload,
                response=response,
                response_failure="content_missing",
            )

        content = message["content"]
        if content is None:
            self._raise_response_error(
                "The AI provider returned null message content.",
                payload=payload,
                response=response,
                response_failure="content_null",
            )

        normalized_content = self._normalize_content(content)
        if not normalized_content:
            if isinstance(content, (str, list)):
                response_failure = "content_empty"
            else:
                response_failure = "content_type_unexpected"

            self._raise_response_error(
                "The AI provider returned unusable message content.",
                payload=payload,
                response=response,
                response_failure=response_failure,
            )

        response_model = self.model
        raw_response_model = payload.get("model")
        if isinstance(raw_response_model, str) and raw_response_model.strip():
            candidate_model = raw_response_model.strip()
            if len(candidate_model) <= MAX_RESPONSE_MODEL_LENGTH:
                response_model = candidate_model

        finish_reason = choice.get("finish_reason")

        return LLMResponse(
            content=normalized_content,
            provider=self.provider,
            model=response_model,
            latency_ms=latency_ms,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            usage=self._normalize_usage(payload.get("usage")),
        )

    def _raise_response_error(
        self,
        message: str,
        *,
        payload: object,
        response: httpx.Response | None,
        response_failure: str,
        cause: BaseException | None = None,
    ) -> NoReturn:
        diagnostics = self._response_shape_diagnostics(
            payload,
            response=response,
            response_failure=response_failure,
        )
        logger.warning(
            "OpenRouter response shape failure provider=%s "
            "response_model=%s http_status=%s choices_count=%s "
            "finish_reason=%s content_present=%s content_type=%s "
            "refusal_present=%s top_level_error_present=%s "
            "usage_completion_tokens=%s request_id=%s response_failure=%s",
            diagnostics["provider"],
            diagnostics["response_model"],
            diagnostics["http_status"],
            diagnostics["choices_count"],
            diagnostics["finish_reason"],
            diagnostics["content_present"],
            diagnostics["content_type"],
            diagnostics["refusal_present"],
            diagnostics["top_level_error_present"],
            diagnostics["usage_completion_tokens"],
            diagnostics["request_id"],
            diagnostics["response_failure"],
        )
        error = LLMResponseError(
            message,
            diagnostics=diagnostics,
        )
        if cause is not None:
            raise error from cause

        raise error

    def _response_shape_diagnostics(
        self,
        payload: object,
        *,
        response: httpx.Response | None,
        response_failure: str,
    ) -> dict[str, object]:
        payload_dict = payload if isinstance(payload, dict) else {}
        choices = payload_dict.get("choices")
        choices_count = len(choices) if isinstance(choices, list) else None

        choice = choices[0] if isinstance(choices, list) and choices else None
        finish_reason: str | None = None
        message: dict[str, Any] | None = None
        if isinstance(choice, dict):
            raw_finish_reason = choice.get("finish_reason")
            if isinstance(raw_finish_reason, str) and raw_finish_reason.strip():
                finish_reason = raw_finish_reason.strip()[:64]
            raw_message = choice.get("message")
            if isinstance(raw_message, dict):
                message = raw_message

        content_present: bool | None = None
        content_type: str | None = None
        refusal_present: bool | None = None
        if message is not None:
            if "content" in message:
                content = message["content"]
                content_present = content is not None
                content_type = type(content).__name__
            if "refusal" in message:
                refusal_present = bool(message["refusal"])

        raw_response_model = payload_dict.get("model")
        response_model = None
        if isinstance(raw_response_model, str) and raw_response_model.strip():
            response_model = raw_response_model.strip()[:MAX_RESPONSE_MODEL_LENGTH]

        diagnostics: dict[str, object] = {
            "provider": self.provider,
            "request_id": (
                self._response_request_id(response, payload_dict)
                if response is not None
                else None
            ),
            "http_status": (
                response.status_code if response is not None else None
            ),
            "response_model": response_model,
            "choices_count": choices_count,
            "finish_reason": finish_reason,
            "content_present": content_present,
            "content_type": content_type,
            "refusal_present": refusal_present,
            "top_level_error_present": (
                "error" in payload_dict and payload_dict["error"] is not None
            ),
            "usage_completion_tokens": self._usage_completion_tokens(
                payload_dict.get("usage")
            ),
            "response_failure": response_failure,
        }

        finish_reason_category = self._finish_reason_category(finish_reason)
        if finish_reason_category is not None:
            diagnostics["finish_reason_category"] = finish_reason_category

        return diagnostics

    @staticmethod
    def _finish_reason_category(value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.lower()
        if normalized == "length":
            return "length"

        if (
            normalized in FINISH_REASON_REFUSAL_VALUES
            or "refusal" in normalized
            or "safety" in normalized
        ):
            return "refusal"

        if (
            normalized in FINISH_REASON_ERROR_VALUES
            or "error" in normalized
            or "failed" in normalized
        ):
            return "error"

        return None

    @staticmethod
    def _usage_completion_tokens(value: object) -> int | None:
        if not isinstance(value, dict):
            return None

        raw_value = value.get("completion_tokens")
        if isinstance(raw_value, bool):
            return None

        try:
            normalized = int(raw_value)
        except (TypeError, ValueError):
            return None

        return normalized if normalized >= 0 else None

    @staticmethod
    def _normalize_content(value: object) -> str:
        if isinstance(value, str):
            return value.strip()

        if not isinstance(value, list):
            return ""

        text_parts: list[str] = []
        for part in value:
            if isinstance(part, str):
                text_parts.append(part)
                continue

            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])

        return "".join(text_parts).strip()

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

        prompt_tokens = as_non_negative_int("prompt_tokens")
        completion_tokens = as_non_negative_int("completion_tokens")
        total_tokens = as_non_negative_int("total_tokens")

        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None

        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _error_for_status(status_code: int) -> LLMError:
        if status_code in {400, 422}:
            return LLMInputError(
                "OpenRouter rejected the request as invalid."
            )

        if status_code in {401, 403}:
            return LLMAuthenticationError(
                "OpenRouter API credentials are invalid or unauthorized."
            )

        if status_code == 404:
            return LLMConfigurationError(
                "The configured OpenRouter model was not found or is unavailable."
            )

        if status_code == 408:
            return LLMTimeoutError(
                "The AI provider did not respond in time."
            )

        if status_code in {402, 429}:
            return LLMRateLimitError(
                "OpenRouter is rate limited, or its quota or credits are exhausted."
            )

        if status_code >= 500:
            return LLMProviderError(
                "OpenRouter is temporarily unavailable."
            )

        return LLMProviderError(
            "OpenRouter rejected the request."
        )

    @classmethod
    def _error_for_response(cls, response: httpx.Response) -> LLMError:
        if response.status_code in {400, 422}:
            provider_error = cls._safe_provider_error(response)
            model_error_values = {
                str(provider_error.get(key, "")).strip().lower()
                for key in ("code", "type", "status")
            }
            if any(
                value in {
                    "model_not_found",
                    "model_not_available",
                    "model_unavailable",
                }
                or "model_not_found" in value
                or "model_unavailable" in value
                for value in model_error_values
            ):
                return LLMConfigurationError(
                    "The configured OpenRouter model was not found or is unavailable."
                )

        return cls._error_for_status(response.status_code)

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        normalized = content.strip()

        if normalized.startswith("```") and normalized.endswith("```"):
            lines = normalized.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()

        return normalized
