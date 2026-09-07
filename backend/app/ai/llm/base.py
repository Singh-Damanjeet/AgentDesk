from collections.abc import Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.ai.llm.types import ChatMessage, LLMResponse


SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class LLMService(Protocol):
    @property
    def provider(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        ...

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaModel],
        *,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
    ) -> SchemaModel:
        ...

    async def test_connection(self) -> None:
        ...
