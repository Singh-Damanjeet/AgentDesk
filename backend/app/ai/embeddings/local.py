import asyncio
import math
from collections.abc import Callable, Sequence
from numbers import Real
from typing import Any

from app.ai.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingInputError,
    EmbeddingProviderError,
)


DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

ModelLoader = Callable[[str], object]


class LocalEmbeddingService:
    """Lazy, cached Sentence Transformer embedding service."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        model_loader: ModelLoader | None = None,
    ):
        normalized_model_name = model_name.strip()

        if not normalized_model_name:
            raise EmbeddingConfigurationError(
                "A local embedding model is required."
            )

        self.model_name = normalized_model_name
        self._model_loader = model_loader or self._load_sentence_transformer
        self._model: object | None = None
        self._model_lock = asyncio.Lock()
        self._dimension: int | None = None

    @property
    def dimension(self) -> int | None:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        normalized_texts = self._validate_texts(texts)

        if not normalized_texts:
            return []

        model = await self._get_model()

        try:
            encode = getattr(model, "encode")
            raw_vectors = await asyncio.to_thread(
                encode,
                normalized_texts,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(
                "The local embedding model failed to create an embedding."
            ) from exc

        vectors = self._normalize_vectors(
            raw_vectors,
            expected_count=len(normalized_texts),
        )

        return vectors

    async def _get_model(self) -> object:
        if self._model is not None:
            return self._model

        async with self._model_lock:
            if self._model is not None:
                return self._model

            try:
                self._model = await asyncio.to_thread(
                    self._model_loader,
                    self.model_name,
                )
            except EmbeddingError:
                raise
            except Exception as exc:
                raise EmbeddingConfigurationError(
                    "The local embedding model could not be loaded."
                ) from exc

        if self._model is None:
            raise EmbeddingConfigurationError(
                "The local embedding model could not be loaded."
            )

        return self._model

    @staticmethod
    def _load_sentence_transformer(model_name: str) -> object:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingConfigurationError(
                "The sentence-transformers dependency is not installed."
            ) from exc

        return SentenceTransformer(model_name)

    @staticmethod
    def _validate_texts(texts: Sequence[str]) -> list[str]:
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise EmbeddingInputError(
                "Embedding input must be a sequence of strings."
            )

        normalized_texts = list(texts)

        for text in normalized_texts:
            if not isinstance(text, str) or not text.strip():
                raise EmbeddingInputError(
                    "Embedding text must not be empty."
                )

        return normalized_texts

    def _normalize_vectors(
        self,
        raw_vectors: Any,
        *,
        expected_count: int,
    ) -> list[list[float]]:
        raw_vectors = self._to_python_value(raw_vectors)

        if self._looks_like_single_vector(raw_vectors):
            vectors_data = [raw_vectors]
        elif isinstance(raw_vectors, (list, tuple)):
            vectors_data = list(raw_vectors)
        else:
            raise EmbeddingProviderError(
                "The local embedding model returned an invalid result."
            )

        if len(vectors_data) != expected_count:
            raise EmbeddingProviderError(
                "The local embedding model returned an unexpected number of vectors."
            )

        vectors: list[list[float]] = []

        for vector_data in vectors_data:
            vector_data = self._to_python_value(vector_data)

            if not isinstance(vector_data, (list, tuple)) or not vector_data:
                raise EmbeddingProviderError(
                    "The local embedding model returned an invalid vector."
                )

            vector: list[float] = []
            for value in vector_data:
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise EmbeddingProviderError(
                        "The local embedding model returned a non-numeric vector."
                    )

                normalized_value = float(value)
                if not math.isfinite(normalized_value):
                    raise EmbeddingProviderError(
                        "The local embedding model returned an invalid vector."
                    )

                vector.append(normalized_value)

            vectors.append(vector)

        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise EmbeddingProviderError(
                "The local embedding model returned inconsistent dimensions."
            )

        dimension = dimensions.pop()
        if self._dimension is None:
            self._dimension = dimension
        elif self._dimension != dimension:
            raise EmbeddingProviderError(
                "The local embedding model returned inconsistent dimensions."
            )

        return vectors

    @staticmethod
    def _to_python_value(value: Any) -> Any:
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            return tolist()

        return value

    @staticmethod
    def _looks_like_single_vector(value: Any) -> bool:
        if not isinstance(value, (list, tuple)) or not value:
            return False

        return all(
            isinstance(item, Real) and not isinstance(item, bool)
            for item in value
        )
