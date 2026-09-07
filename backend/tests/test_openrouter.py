import asyncio
import logging

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401

from app.ai.embeddings.local import LocalEmbeddingService
from app.ai.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInputError,
    LLMRateLimitError,
    LLMResponseError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.ai.llm.factory import LLMFactory
from app.ai.llm.providers import openrouter
from app.ai.llm.providers.gemini import GeminiLLMAdapter
from app.ai.llm.providers.openrouter import OpenRouterLLMAdapter
from app.ai.llm.types import ChatMessage
from app.core.secrets import encrypt_secret
from app.db.base import Base
from app.models.ai_provider import AIProvider
from app.schemas.agent import ClassificationResult
from app.schemas.ai_provider import AIConnectionTestRequest, AIProviderUpdate
from app.services.ai_provider_service import AIProviderService
from app.services.ai_service import AIService


def run(coroutine):
    return asyncio.run(coroutine)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: object | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class InvalidJSONResponse(FakeResponse):
    def json(self):
        raise ValueError("synthetic non-JSON response")


def patch_http_client(monkeypatch, *, post_handler):
    calls: dict[str, object] = {
        "post": [],
    }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            calls["client_options"] = {
                "args": args,
                "kwargs": kwargs,
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            del args

        async def post(self, url, headers, json):
            post_calls = calls["post"]
            assert isinstance(post_calls, list)
            post_calls.append(
                {
                    "url": url,
                    "headers": headers,
                    "json": json,
                }
            )
            return post_handler(len(post_calls))

    monkeypatch.setattr(openrouter.httpx, "AsyncClient", FakeAsyncClient)
    return calls


def disable_retry_sleep(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(openrouter.asyncio, "sleep", no_sleep)


def successful_openrouter_payload(
    content: str = "Hello from OpenRouter",
    *,
    model: str = "google/gemma-4-26b-a4b-it",
):
    return {
        "id": "gen-synthetic-id",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 5,
            "total_tokens": 12,
        },
    }


def test_llm_factory_resolves_openrouter_and_keeps_gemini_support():
    openrouter_adapter = LLMFactory.create(
        provider="openrouter",
        model="google/gemma-4-26b-a4b-it",
        api_key="synthetic-openrouter-key",
    )
    gemini_adapter = LLMFactory.create(
        provider="gemini",
        model="gemini-2.5-flash",
        api_key="synthetic-gemini-key",
    )

    assert isinstance(openrouter_adapter, OpenRouterLLMAdapter)
    assert openrouter_adapter.provider == "openrouter"
    assert openrouter_adapter.model == "google/gemma-4-26b-a4b-it"
    assert isinstance(gemini_adapter, GeminiLLMAdapter)


def test_openrouter_model_slug_is_normalized_and_validated():
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="  google/gemma-4-26b-a4b-it  ",
    )

    assert adapter.model == "google/gemma-4-26b-a4b-it"

    with pytest.raises(LLMConfigurationError):
        OpenRouterLLMAdapter(
            api_key="synthetic-openrouter-key",
            model="models/google/gemma-4-26b-a4b-it",
        )

    with pytest.raises(LLMConfigurationError) as error:
        OpenRouterLLMAdapter(
            api_key="",
            model="google/gemma-4-26b-a4b-it",
        )

    assert error.value.user_message == "An OpenRouter API key is required."
    assert "synthetic-openrouter-key" not in str(error.value)


def test_openrouter_configuration_schema_and_secret_persistence():
    data = AIProviderUpdate(
        provider=" OpenRouter ",
        model=" google/gemma-4-26b-a4b-it ",
        api_key=SecretStr("synthetic-openrouter-key"),
        embedding_provider="local",
        embedding_model=None,
        enabled=True,
    )
    test_request = AIConnectionTestRequest(
        provider="openrouter",
        model="openrouter/free",
        api_key=SecretStr("synthetic-openrouter-key"),
    )

    assert data.provider == "openrouter"
    assert data.model == "google/gemma-4-26b-a4b-it"
    assert test_request.provider == "openrouter"
    assert test_request.model == "openrouter/free"

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            saved = AIProviderService.update(db, data)

            assert saved.provider == "openrouter"
            assert saved.model == "google/gemma-4-26b-a4b-it"
            assert saved.encrypted_api_key != "synthetic-openrouter-key"

            with pytest.raises(ValueError) as error:
                AIProviderService.update(
                    db,
                    AIProviderUpdate(
                        provider="gemini",
                        model="gemini-2.5-flash",
                        embedding_provider="local",
                        embedding_model=None,
                        enabled=True,
                    ),
                )

            assert error.value.args[0] == "A Gemini API key is required."
    finally:
        engine.dispose()


def test_openrouter_chat_uses_exact_endpoint_and_normalizes_response(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_openrouter_payload(
                model="google/gemma-4-26b-a4b-it:free"
            ),
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    response = run(
        adapter.chat(
            [
                ChatMessage(role="system", content="Be concise."),
                ChatMessage(role="user", content="Say hello."),
            ],
            temperature=0.2,
            max_output_tokens=64,
        )
    )

    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    request = post_calls[0]
    assert request["url"] == (
        "https://openrouter.ai/api/v1/chat/completions"
    )
    assert request["headers"] == {
        "Authorization": "Bearer synthetic-openrouter-key",
        "content-type": "application/json",
    }
    assert request["json"] == {
        "model": "google/gemma-4-26b-a4b-it",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say hello."},
        ],
        "temperature": 0.2,
        "max_tokens": 64,
        "stream": False,
    }
    assert response.content == "Hello from OpenRouter"
    assert response.provider == "openrouter"
    assert response.model == "google/gemma-4-26b-a4b-it:free"
    assert response.finish_reason == "stop"
    assert response.usage is not None
    assert response.usage.total_tokens == 12


def test_openrouter_structured_output_sends_openai_json_schema_and_validates(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_openrouter_payload(
                '{"category":"refund","urgency":"normal",'
                '"needs_account_data":true,"confidence":0.98}'
            ),
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    result = run(
        adapter.structured_output(
            [
                ChatMessage(
                    role="system",
                    content="Classify support requests safely.",
                ),
                ChatMessage(
                    role="user",
                    content="Where is my refund right now?",
                ),
            ],
            ClassificationResult,
        )
    )

    assert result.category == "refund"
    assert result.needs_account_data is True
    assert result.confidence == 0.98

    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    payload = post_calls[0]["json"]
    assert isinstance(payload, dict)
    assert payload["messages"][:2] == [
        {
            "role": "system",
            "content": "Classify support requests safely.",
        },
        {
            "role": "user",
            "content": "Where is my refund right now?",
        },
    ]
    assert payload["messages"][-1]["role"] == "user"
    assert payload["response_format"]["type"] == "json_schema"
    json_schema = payload["response_format"]["json_schema"]
    assert json_schema["name"] == "agentdesk_classification"
    assert json_schema["strict"] is True
    assert json_schema["schema"]["type"] == "object"
    assert json_schema["schema"]["required"] == [
        "category",
        "urgency",
        "needs_account_data",
        "confidence",
    ]
    assert json_schema["schema"]["properties"]["category"]["enum"] == [
        "billing",
        "refund",
        "account",
        "technical",
        "shipping",
        "general",
        "other",
    ]
    assert payload["provider"] == {"require_parameters": True}
    assert payload["stream"] is False
    assert "plugins" not in payload


def test_openrouter_connection_test_validates_structured_output(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_openrouter_payload(
                '{"category":"refund","urgency":"normal",'
                '"needs_account_data":false,"confidence":0.95}'
            ),
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    run(adapter.test_connection())

    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    payload = post_calls[0]["json"]
    assert payload["response_format"]["type"] == "json_schema"
    json_schema = payload["response_format"]["json_schema"]
    assert json_schema["name"] == "agentdesk_classification"
    assert json_schema["strict"] is True
    assert payload["provider"] == {"require_parameters": True}
    assert payload["stream"] is False
    assert payload["max_tokens"] == 1_024


def test_openrouter_connection_test_rejects_malformed_classifier_output(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_openrouter_payload(
                '{"category":"refund","urgency":"normal",'
                '"needs_account_data":false,"confidence":0.95'
            ),
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with pytest.raises(LLMConfigurationError) as error:
        run(adapter.test_connection())

    assert error.value.user_message == (
        "The selected OpenRouter model does not support AgentDesk "
        "structured output."
    )
    assert error.value.diagnostics == {
        "structured_output_failure": "invalid_json",
        "json_error_type": "Expecting ',' delimiter",
    }
    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 1


def test_openrouter_classifier_schema_accepts_five_consecutive_requests(
    monkeypatch,
):
    prompts_and_results = [
        (
            "Where is my refund right now?",
            '{"category":"refund","urgency":"normal",'
            '"needs_account_data":true,"confidence":0.97}',
        ),
        (
            "How long do I have to request a refund?",
            '{"category":"refund","urgency":"normal",'
            '"needs_account_data":false,"confidence":0.95}',
        ),
        (
            "I forgot my password",
            '{"category":"account","urgency":"normal",'
            '"needs_account_data":false,"confidence":0.94}',
        ),
        (
            "Do you offer free laptops?",
            '{"category":"general","urgency":"normal",'
            '"needs_account_data":false,"confidence":0.99}',
        ),
        (
            "When will my order arrive?",
            '{"category":"shipping","urgency":"normal",'
            '"needs_account_data":false,"confidence":0.93}',
        ),
    ]

    def post_handler(attempt):
        _prompt, result = prompts_and_results[attempt - 1]
        return FakeResponse(
            200,
            successful_openrouter_payload(result),
        )

    calls = patch_http_client(monkeypatch, post_handler=post_handler)
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="liquid/lfm-2.5-2.6b:free",
    )

    results = [
        run(
            adapter.structured_output(
                [ChatMessage(role="user", content=prompt)],
                ClassificationResult,
                temperature=0.0,
                max_output_tokens=256,
            )
        )
        for prompt, _expected in prompts_and_results
    ]

    assert all(isinstance(result, ClassificationResult) for result in results)
    assert [result.category for result in results] == [
        "refund",
        "refund",
        "account",
        "general",
        "shipping",
    ]
    assert [result.needs_account_data for result in results] == [
        True,
        False,
        False,
        False,
        False,
    ]
    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 5
    for request, (prompt, _expected) in zip(
        post_calls,
        prompts_and_results,
        strict=True,
    ):
        payload = request["json"]
        assert payload["messages"][0]["content"] == prompt
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["provider"] == {"require_parameters": True}
        assert payload["stream"] is False


def test_openrouter_connection_test_rejects_unsupported_structured_output(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            400,
            {
                "error": {
                    "code": 400,
                    "type": "invalid_request_error",
                    "message": "Response format is not supported.",
                }
            },
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with pytest.raises(LLMConfigurationError) as error:
        run(adapter.test_connection())

    assert error.value.user_message == (
        "The selected OpenRouter model does not support AgentDesk "
        "structured output."
    )
    assert error.value.diagnostics == {
        "provider": "openrouter",
        "request_id": None,
        "http_status": 400,
        "response_model": None,
        "choices_count": None,
        "finish_reason": None,
        "content_present": None,
        "content_type": None,
        "refusal_present": None,
        "top_level_error_present": True,
        "usage_completion_tokens": None,
        "response_failure": "http_non_2xx",
        "model": "google/gemma-4-26b-a4b-it",
        "provider_error_code": 400,
        "provider_error_type": "invalid_request_error",
        "provider_error_status": None,
    }
    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 1


def test_openrouter_auth_failure_is_safe_and_not_retried(
    monkeypatch,
    caplog,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            401,
            {
                "error": {
                    "code": 401,
                    "type": "authentication_error",
                    "message": "invalid key",
                }
            },
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with caplog.at_level(
        logging.WARNING,
        logger="app.ai.llm.providers.openrouter",
    ):
        with pytest.raises(LLMAuthenticationError) as error:
            run(
                adapter.chat(
                    [ChatMessage(role="user", content="Hello")]
                )
            )

    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 1
    assert error.value.diagnostics["http_status"] == 401
    assert "synthetic-openrouter-key" not in str(error.value)
    assert "synthetic-openrouter-key" not in caplog.text


def test_openrouter_not_found_preserves_safe_diagnostics(
    monkeypatch,
    caplog,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            404,
            {
                "error": {
                    "code": "MODEL_NOT_FOUND",
                    "type": "invalid_request_error",
                    "status": "NOT_FOUND",
                    "message": "The model is unavailable.",
                }
            },
            headers={"x-openrouter-request-id": "synthetic-request-id"},
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with caplog.at_level(
        logging.WARNING,
        logger="app.ai.llm.providers.openrouter",
    ):
        with pytest.raises(LLMConfigurationError) as error:
            run(
                adapter.chat(
                    [ChatMessage(role="user", content="Hello")]
                )
            )

    assert error.value.user_message == (
        "The configured OpenRouter model was not found or is unavailable."
    )
    assert error.value.diagnostics == {
        "provider": "openrouter",
        "request_id": "synthetic-request-id",
        "http_status": 404,
        "response_model": None,
        "choices_count": None,
        "finish_reason": None,
        "content_present": None,
        "content_type": None,
        "refusal_present": None,
        "top_level_error_present": True,
        "usage_completion_tokens": None,
        "response_failure": "http_non_2xx",
        "model": "google/gemma-4-26b-a4b-it",
        "provider_error_code": "MODEL_NOT_FOUND",
        "provider_error_type": "invalid_request_error",
        "provider_error_status": "NOT_FOUND",
    }
    assert "provider=openrouter" in caplog.text
    assert "model=google/gemma-4-26b-a4b-it" in caplog.text
    assert "http_status=404" in caplog.text
    assert "provider_error_code=MODEL_NOT_FOUND" in caplog.text
    assert "synthetic-request-id" in caplog.text
    assert "synthetic-openrouter-key" not in caplog.text
    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 1


def test_openrouter_rate_limit_retries_then_maps_safely(monkeypatch):
    disable_retry_sleep(monkeypatch)
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            429,
            {
                "error": {
                    "code": 429,
                    "type": "rate_limit_error",
                }
            },
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with pytest.raises(LLMRateLimitError) as error:
        run(
            adapter.chat(
                [ChatMessage(role="user", content="Hello")]
            )
        )

    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 3
    assert error.value.diagnostics["http_status"] == 429


def test_openrouter_timeout_retries_a_bounded_number_of_times(monkeypatch):
    disable_retry_sleep(monkeypatch)

    def timeout_handler(_attempt):
        raise httpx.ReadTimeout("synthetic timeout")

    calls = patch_http_client(
        monkeypatch,
        post_handler=timeout_handler,
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with pytest.raises(LLMTimeoutError) as error:
        run(
            adapter.chat(
                [ChatMessage(role="user", content="Hello")]
            )
        )

    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 3
    assert error.value.diagnostics == {
        "transport_error_type": "ReadTimeout",
    }


def test_openrouter_malformed_structured_response_is_rejected_safely(
    monkeypatch,
):
    patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_openrouter_payload("not valid JSON"),
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with pytest.raises(LLMStructuredOutputError) as error:
        run(
            adapter.structured_output(
                [ChatMessage(role="user", content="Classify this.")],
                ClassificationResult,
            )
        )

    assert error.value.diagnostics == {
        "structured_output_failure": "invalid_json",
        "json_error_type": "Expecting value",
    }
    assert "synthetic-openrouter-key" not in str(error.value)


def synthetic_response_shape_payload(
    *,
    choices: object = None,
    include_choices: bool = True,
    error: object | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "gen-shape-id",
        "model": "dots-studio/dots-3-note-preview:free",
        "usage": {"completion_tokens": 17},
    }
    if include_choices:
        payload["choices"] = choices
    if error is not None:
        payload["error"] = error
    return payload


@pytest.mark.parametrize(
    (
        "payload",
        "expected_failure",
        "expected_finish_reason",
        "expected_content_present",
        "expected_content_type",
        "expected_refusal_present",
        "expected_finish_reason_category",
        "expected_top_level_error",
    ),
    [
        pytest.param(
            synthetic_response_shape_payload(
                include_choices=False,
                error={"code": "UPSTREAM_ERROR"},
            ),
            "top_level_error",
            None,
            None,
            None,
            None,
            None,
            True,
            id="top-level-error",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices={"not": "an array"},
            ),
            "choices_invalid",
            None,
            None,
            None,
            None,
            None,
            False,
            id="choices-invalid",
        ),
        pytest.param(
            synthetic_response_shape_payload(choices=[]),
            "empty_choices",
            None,
            None,
            None,
            None,
            None,
            False,
            id="empty-choices",
        ),
        pytest.param(
            synthetic_response_shape_payload(choices=[None]),
            "first_choice_missing",
            None,
            None,
            None,
            None,
            None,
            False,
            id="first-choice-missing",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[{"finish_reason": "stop"}],
            ),
            "message_missing",
            "stop",
            None,
            None,
            None,
            None,
            False,
            id="message-missing",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "stop",
                        "message": [],
                    }
                ],
            ),
            "message_invalid",
            "stop",
            None,
            None,
            None,
            None,
            False,
            id="message-invalid",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant"},
                    }
                ],
            ),
            "content_missing",
            "stop",
            None,
            None,
            None,
            None,
            False,
            id="content-missing",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "refusal": None,
                        },
                    }
                ],
            ),
            "content_null",
            "stop",
            False,
            "NoneType",
            False,
            None,
            False,
            id="content-null",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "refusal": None,
                        },
                    }
                ],
            ),
            "content_empty",
            "stop",
            True,
            "str",
            False,
            None,
            False,
            id="content-empty",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": {"text": "unexpected"},
                            "refusal": None,
                        },
                    }
                ],
            ),
            "content_type_unexpected",
            "stop",
            True,
            "dict",
            False,
            None,
            False,
            id="content-type-unexpected",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "length",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "refusal": None,
                        },
                    }
                ],
            ),
            "content_null",
            "length",
            False,
            "NoneType",
            False,
            "length",
            False,
            id="finish-reason-length",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "content_filter",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "refusal": "blocked",
                        },
                    }
                ],
            ),
            "content_null",
            "content_filter",
            False,
            "NoneType",
            True,
            "refusal",
            False,
            id="finish-reason-refusal",
        ),
        pytest.param(
            synthetic_response_shape_payload(
                choices=[
                    {
                        "finish_reason": "error",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "refusal": None,
                        },
                    }
                ],
            ),
            "content_null",
            "error",
            False,
            "NoneType",
            False,
            "error",
            False,
            id="finish-reason-error",
        ),
    ],
)
def test_openrouter_successful_response_shapes_have_safe_diagnostics(
    monkeypatch,
    payload,
    expected_failure,
    expected_finish_reason,
    expected_content_present,
    expected_content_type,
    expected_refusal_present,
    expected_finish_reason_category,
    expected_top_level_error,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            payload,
            headers={"x-request-id": "shape-request-id"},
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="dots-studio/dots-3-note-preview:free",
    )

    with pytest.raises(LLMResponseError) as error:
        run(adapter.chat([ChatMessage(role="user", content="Hello")]))

    diagnostics = error.value.diagnostics
    raw_choices = payload.get("choices")
    expected_choices_count = (
        len(raw_choices) if isinstance(raw_choices, list) else None
    )
    assert diagnostics == {
        "provider": "openrouter",
        "request_id": "shape-request-id",
        "http_status": 200,
        "response_model": "dots-studio/dots-3-note-preview:free",
        "choices_count": expected_choices_count,
        "finish_reason": expected_finish_reason,
        "content_present": expected_content_present,
        "content_type": expected_content_type,
        "refusal_present": expected_refusal_present,
        "top_level_error_present": expected_top_level_error,
        "usage_completion_tokens": 17,
        "response_failure": expected_failure,
        **(
            {"finish_reason_category": expected_finish_reason_category}
            if expected_finish_reason_category is not None
            else {}
        ),
    }
    assert "synthetic-openrouter-key" not in str(error.value)
    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert len(post_calls) == 1


def test_openrouter_successful_non_json_response_has_safe_diagnostics(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: InvalidJSONResponse(
            200,
            headers={"x-openrouter-request-id": "non-json-request-id"},
        ),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="dots-studio/dots-3-note-preview:free",
    )

    with pytest.raises(LLMResponseError) as error:
        run(adapter.chat([ChatMessage(role="user", content="Hello")]))

    assert error.value.diagnostics == {
        "provider": "openrouter",
        "request_id": "non-json-request-id",
        "http_status": 200,
        "response_model": None,
        "choices_count": None,
        "finish_reason": None,
        "content_present": None,
        "content_type": None,
        "refusal_present": None,
        "top_level_error_present": False,
        "usage_completion_tokens": None,
        "response_failure": "invalid_response_json",
    }
    assert "synthetic-openrouter-key" not in str(error.value)


def test_openrouter_malformed_provider_response_is_rejected():
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with pytest.raises(LLMResponseError):
        run(
            adapter._normalize_response(
                {"choices": []},
                latency_ms=1,
            )
        )


def test_openrouter_configuration_uses_local_embeddings_without_gemini(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_openrouter_payload("Configured response"),
        ),
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    secret = "synthetic-openrouter-key"

    try:
        with Session(engine) as db:
            db.add(
                AIProvider(
                    provider="openrouter",
                    model="google/gemma-4-26b-a4b-it",
                    encrypted_api_key=encrypt_secret(secret),
                    embedding_provider="local",
                    embedding_model=None,
                    enabled=True,
                )
            )
            db.commit()

            service = AIService.from_configuration(db)
            response = run(
                service.chat(
                    [ChatMessage(role="user", content="Say hello")]
                )
            )

        assert response.provider == "openrouter"
        assert response.content == "Configured response"
        assert isinstance(service._embeddings, LocalEmbeddingService)
        assert secret not in repr(service)
        assert secret not in response.model_dump_json()
        post_calls = calls["post"]
        assert isinstance(post_calls, list)
        assert len(post_calls) == 1
    finally:
        engine.dispose()


def test_openrouter_invalid_generation_options_are_rejected_before_http(
    monkeypatch,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: pytest.fail("HTTP must not be called"),
    )
    adapter = OpenRouterLLMAdapter(
        api_key="synthetic-openrouter-key",
        model="google/gemma-4-26b-a4b-it",
    )

    with pytest.raises(LLMInputError):
        run(
            adapter.chat(
                [ChatMessage(role="user", content="Hello")],
                temperature=2.1,
            )
        )

    post_calls = calls["post"]
    assert isinstance(post_calls, list)
    assert post_calls == []
