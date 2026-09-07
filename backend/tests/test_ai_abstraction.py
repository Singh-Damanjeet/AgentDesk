import asyncio

import httpx
import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401

from app.ai.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingInputError,
    EmbeddingProviderError,
)
from app.ai.embeddings.factory import EmbeddingFactory
from app.ai.embeddings.local import LocalEmbeddingService
from app.ai.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.ai.llm.factory import LLMFactory
from app.ai.llm.providers import gemini
from app.ai.llm.providers.gemini import GeminiLLMAdapter
from app.ai.llm.types import ChatMessage
from app.core.secrets import encrypt_secret
from app.db.base import Base
from app.models.ai_provider import AIProvider
from app.schemas.agent import ClassificationResult as AgentClassificationResult
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


def patch_http_client(monkeypatch, *, get_handler=None, post_handler=None):
    calls = {
        "get": [],
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

        async def get(self, url, headers):
            calls["get"].append(
                {
                    "url": url,
                    "headers": headers,
                }
            )
            if get_handler is None:
                raise AssertionError("Unexpected GET request")

            return get_handler(len(calls["get"]))

        async def post(self, url, headers, json):
            calls["post"].append(
                {
                    "url": url,
                    "headers": headers,
                    "json": json,
                }
            )
            if post_handler is None:
                raise AssertionError("Unexpected POST request")

            return post_handler(len(calls["post"]))

    monkeypatch.setattr(gemini.httpx, "AsyncClient", FakeAsyncClient)
    return calls


def disable_retry_sleep(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(gemini.asyncio, "sleep", no_sleep)


def successful_gemini_payload(content: str = "Hello from Gemini"):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": content}],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 4,
            "candidatesTokenCount": 6,
            "totalTokenCount": 10,
        },
    }


def test_gemini_chat_normalizes_response_and_metadata(monkeypatch):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_gemini_payload(),
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    response = run(
        adapter.chat(
            [
                ChatMessage(role="system", content="Be concise."),
                ChatMessage(role="user", content="Say hello."),
            ],
            temperature=0.2,
        )
    )

    assert response.content == "Hello from Gemini"
    assert response.provider == "gemini"
    assert response.model == "gemini-2.5-flash"
    assert response.finish_reason == "STOP"
    assert response.usage is not None
    assert response.usage.total_tokens == 10
    assert len(calls["post"]) == 1
    assert calls["post"][0]["json"]["systemInstruction"] == {
        "parts": [{"text": "Be concise."}],
    }
    assert calls["post"][0]["url"] == (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert "synthetic-gemini-key" not in response.model_dump_json()


def test_gemini_connection_test_uses_generation_endpoint_and_payload(monkeypatch):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_gemini_payload("OK"),
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="models/gemini-3.6-flash",
    )

    run(adapter.test_connection())

    assert calls["get"] == []
    assert calls["post"][0]["url"] == (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.6-flash:generateContent"
    )
    assert calls["post"][0]["json"] == {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "Reply with exactly OK."}],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 256,
        },
    }


def test_gemini_authentication_failure_is_safe_and_not_retried(monkeypatch):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(401, {}),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    with pytest.raises(LLMAuthenticationError) as error:
        run(
            adapter.chat(
                [ChatMessage(role="user", content="Hello")]
            )
        )

    assert len(calls["post"]) == 1
    assert "synthetic-gemini-key" not in str(error.value)


def test_gemini_timeout_retries_a_bounded_number_of_times(monkeypatch):
    disable_retry_sleep(monkeypatch)

    def timeout_handler(_attempt):
        raise httpx.ReadTimeout("synthetic timeout")

    calls = patch_http_client(
        monkeypatch,
        post_handler=timeout_handler,
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    with pytest.raises(LLMTimeoutError):
        run(
            adapter.chat(
                [ChatMessage(role="user", content="Hello")]
            )
        )

    assert len(calls["post"]) == 3


def test_gemini_transient_failure_retries_then_succeeds(monkeypatch):
    disable_retry_sleep(monkeypatch)

    def transient_handler(attempt):
        if attempt == 1:
            return FakeResponse(503, {})

        return FakeResponse(200, successful_gemini_payload("Recovered"))

    calls = patch_http_client(
        monkeypatch,
        post_handler=transient_handler,
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    response = run(
        adapter.chat(
            [ChatMessage(role="user", content="Retry this")]
        )
    )

    assert response.content == "Recovered"
    assert len(calls["post"]) == 2


def test_gemini_rate_limit_is_retried_then_mapped(monkeypatch):
    disable_retry_sleep(monkeypatch)
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(429, {}),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    with pytest.raises(LLMRateLimitError) as error:
        run(
            adapter.chat(
                [ChatMessage(role="user", content="Hello")]
            )
        )

    assert len(calls["post"]) == 3
    assert "synthetic-gemini-key" not in str(error.value)


def test_gemini_invalid_request_is_not_retried(monkeypatch):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            400,
            {
                "error": {
                    "code": 400,
                    "status": "INVALID_ARGUMENT",
                    "message": "Invalid structured response schema.",
                }
            },
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    with pytest.raises(LLMInputError) as error:
        run(
            adapter.chat(
                [ChatMessage(role="user", content="Hello")]
            )
        )

    assert len(calls["post"]) == 1
    assert error.value.user_message == "Gemini rejected the request as invalid."
    assert error.value.diagnostics == {
        "http_status": 400,
        "google_error_status": "INVALID_ARGUMENT",
        "google_error_code": 400,
        "request_id": None,
    }


def test_gemini_not_found_preserves_safe_provider_diagnostics(
    monkeypatch,
    caplog,
):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            404,
            {
                "error": {
                    "code": 404,
                    "status": "NOT_FOUND",
                    "message": "Model is unavailable to this account.",
                }
            },
            headers={"x-request-id": "synthetic-request-id"},
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    with caplog.at_level("WARNING", logger="app.ai.llm.providers.gemini"):
        with pytest.raises(LLMConfigurationError) as error:
            run(
                adapter.chat(
                    [ChatMessage(role="user", content="Hello")]
                )
            )

    assert len(calls["post"]) == 1
    assert error.value.user_message == (
        "The configured Gemini model or endpoint was not found."
    )
    assert error.value.diagnostics == {
        "http_status": 404,
        "google_error_status": "NOT_FOUND",
        "google_error_code": 404,
        "request_id": "synthetic-request-id",
    }
    assert "provider=gemini" in caplog.text
    assert "model=gemini-2.5-flash" in caplog.text
    assert "http_status=404" in caplog.text
    assert "google_error_status=NOT_FOUND" in caplog.text
    assert "google_error_code=404" in caplog.text
    assert "request_id=synthetic-request-id" in caplog.text
    assert "synthetic-gemini-key" not in caplog.text


def test_llm_factory_resolves_gemini_and_rejects_unsupported_provider():
    adapter = LLMFactory.create(
        provider="gemini",
        model="models/gemini-2.5-flash",
        api_key="synthetic-gemini-key",
    )

    assert isinstance(adapter, GeminiLLMAdapter)
    assert adapter.model == "gemini-2.5-flash"

    with pytest.raises(LLMConfigurationError) as error:
        LLMFactory.create(
            provider="openai",
            model="gpt-test",
            api_key="synthetic-gemini-key",
        )

    assert "synthetic-gemini-key" not in str(error.value)


class ClassificationResult(BaseModel):
    category: str
    urgency: str
    needs_account_data: bool
    confidence: float


def test_structured_output_validates_and_returns_typed_model(monkeypatch):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_gemini_payload(
                '{"category":"billing","urgency":"high",'
                '"needs_account_data":true,"confidence":0.92}'
            ),
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    result = run(
        adapter.structured_output(
            [ChatMessage(role="user", content="Classify this request.")],
            ClassificationResult,
        )
    )

    assert isinstance(result, ClassificationResult)
    assert result.category == "billing"
    assert result.confidence == 0.92
    generation_config = calls["post"][0]["json"]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert "responseSchema" not in generation_config
    assert generation_config["responseJsonSchema"] == (
        ClassificationResult.model_json_schema()
    )


def test_structured_output_sends_production_classifier_schema(monkeypatch):
    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_gemini_payload(
                '{"category":"refund","urgency":"normal",'
                '"needs_account_data":true,"confidence":0.98}'
            ),
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-3.6-flash",
    )

    result = run(
        adapter.structured_output(
            [ChatMessage(role="user", content="Classify this request.")],
            AgentClassificationResult,
        )
    )

    assert result.category == "refund"
    assert result.needs_account_data is True
    generation_config = calls["post"][0]["json"]["generationConfig"]
    schema = generation_config["responseJsonSchema"]
    assert generation_config["responseMimeType"] == "application/json"
    assert "responseSchema" not in generation_config
    assert schema["type"] == "object"
    assert schema["required"] == [
        "category",
        "urgency",
        "needs_account_data",
        "confidence",
    ]
    assert schema["properties"]["category"]["enum"] == [
        "billing",
        "refund",
        "account",
        "technical",
        "shipping",
        "general",
        "other",
    ]
    assert schema["properties"]["urgency"]["enum"] == [
        "low",
        "normal",
        "high",
        "urgent",
    ]
    assert schema["properties"]["confidence"]["minimum"] == 0.0
    assert schema["properties"]["confidence"]["maximum"] == 1.0


def test_structured_output_sanitizes_unsupported_json_schema_keywords(
    monkeypatch,
):
    class SchemaWithUnsupportedKeywords(BaseModel):
        model_config = {
            "json_schema_extra": {
                "examples": ["remove this"],
                "x-provider-only": "remove this",
            }
        }

        value: str = Field(
            json_schema_extra={
                "default": "remove this",
                "x-field-only": "remove this",
            }
        )

    calls = patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_gemini_payload('{"value":"kept"}'),
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    result = run(
        adapter.structured_output(
            [ChatMessage(role="user", content="Return a value.")],
            SchemaWithUnsupportedKeywords,
        )
    )

    assert result.value == "kept"
    generation_config = calls["post"][0]["json"]["generationConfig"]
    schema = generation_config["responseJsonSchema"]
    assert "responseSchema" not in generation_config
    assert "examples" not in schema
    assert "x-provider-only" not in schema
    assert "default" not in schema["properties"]["value"]
    assert "x-field-only" not in schema["properties"]["value"]


def test_structured_output_rejects_invalid_schema_result(monkeypatch):
    patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_gemini_payload('{"category":"billing"}'),
        ),
    )
    adapter = GeminiLLMAdapter(
        api_key="synthetic-gemini-key",
        model="gemini-2.5-flash",
    )

    with pytest.raises(LLMStructuredOutputError) as error:
        run(
            adapter.structured_output(
                [ChatMessage(role="user", content="Classify this request.")],
                ClassificationResult,
            )
        )

    assert "synthetic-gemini-key" not in str(error.value)
    assert error.value.diagnostics == {
        "structured_output_failure": "schema_validation",
        "validation_fields": [
            "confidence",
            "needs_account_data",
            "urgency",
        ],
        "validation_error_types": ["missing"],
    }


class FakeEmbeddingModel:
    def __init__(self):
        self.calls: list[list[str]] = []

    def encode(self, texts, **kwargs):
        del kwargs
        self.calls.append(list(texts))
        return [
            [0.1, 0.2, 0.3]
            for _text in texts
        ]


def test_local_embeddings_support_single_batch_and_cache_model():
    model = FakeEmbeddingModel()
    service = LocalEmbeddingService(
        model_name="test-local-model",
        model_loader=lambda _model_name: model,
    )

    single = run(service.embed_text("How do I reset my password?"))
    batch = run(
        service.embed_batch(
            [
                "How do I reset my password?",
                "Where can I update billing details?",
            ]
        )
    )

    assert len(single) == 3
    assert len(batch) == 2
    assert all(len(vector) == 3 for vector in batch)
    assert service.dimension == 3
    assert len(model.calls) == 2


def test_local_embeddings_handle_empty_and_inconsistent_input():
    service = LocalEmbeddingService(
        model_loader=lambda _model_name: FakeEmbeddingModel(),
    )

    assert run(service.embed_batch([])) == []

    with pytest.raises(EmbeddingInputError):
        run(service.embed_text("   "))

    with pytest.raises(EmbeddingInputError):
        run(service.embed_batch("not a batch"))

    class InconsistentModel:
        def encode(self, texts, **kwargs):
            del kwargs
            return [[0.1, 0.2], [0.3]]

    inconsistent_service = LocalEmbeddingService(
        model_loader=lambda _model_name: InconsistentModel(),
    )

    with pytest.raises(EmbeddingProviderError):
        run(inconsistent_service.embed_batch(["one", "two"]))


def test_embedding_factory_rejects_unsupported_provider():
    with pytest.raises(EmbeddingConfigurationError) as error:
        EmbeddingFactory.create(provider="remote")

    assert "remote" in str(error.value)


def test_embedding_factory_reuses_lazy_local_service_per_model():
    first = EmbeddingFactory.create(model="test-cached-model")
    second = EmbeddingFactory.create(model="test-cached-model")

    assert first is second


def test_ai_service_resolves_persisted_configuration_and_keeps_key_server_side(
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    secret = "synthetic-persisted-gemini-key"

    patch_http_client(
        monkeypatch,
        post_handler=lambda _attempt: FakeResponse(
            200,
            successful_gemini_payload("Configured response"),
        ),
    )

    try:
        with Session(engine) as db:
            db.add(
                AIProvider(
                    provider="gemini",
                    model="gemini-2.5-flash",
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

        assert response.content == "Configured response"
        assert secret not in repr(service)
        assert secret not in response.model_dump_json()
    finally:
        engine.dispose()
