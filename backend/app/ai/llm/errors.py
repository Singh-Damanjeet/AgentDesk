class LLMError(Exception):
    """Base class for safe, provider-independent LLM errors."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class LLMConfigurationError(LLMError):
    """Raised when the provider or model configuration is invalid."""


class LLMInputError(LLMError):
    """Raised when an LLM request cannot be sent as provided."""


class LLMAuthenticationError(LLMError):
    """Raised when provider credentials are rejected."""


class LLMTimeoutError(LLMError):
    """Raised when a provider does not respond within the deadline."""


class LLMRateLimitError(LLMError):
    """Raised when the provider continues rate limiting after retries."""


class LLMProviderError(LLMError):
    """Raised for temporary or otherwise safe provider failures."""


class LLMResponseError(LLMError):
    """Raised when a provider response cannot be normalized."""


class LLMStructuredOutputError(LLMError):
    """Raised when structured output is not valid for the requested schema."""
