from urllib.parse import urlsplit

from app.core.widget import (
    MAX_WIDGET_ALLOWED_DOMAINS,
    MAX_WIDGET_ORIGIN_LENGTH,
)


class OriginValidationError(ValueError):
    """Raised when a configured website origin is not safe to use."""


def normalize_origin(value: str) -> str:
    if not isinstance(value, str):
        raise OriginValidationError(
            "Allowed domains must be full HTTP or HTTPS origins."
        )

    candidate = value.strip()
    if not candidate or len(candidate) > MAX_WIDGET_ORIGIN_LENGTH:
        raise OriginValidationError(
            "Allowed domains must be full HTTP or HTTPS origins."
        )

    try:
        parsed = urlsplit(candidate)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise OriginValidationError(
            "Allowed domains must be full HTTP or HTTPS origins."
        ) from exc

    if (
        scheme not in {"http", "https"}
        or hostname is None
        or parsed.netloc.endswith(":")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise OriginValidationError(
            "Allowed domains must be full HTTP or HTTPS origins."
        )

    normalized_hostname = hostname.lower()
    if ":" in normalized_hostname:
        normalized_hostname = f"[{normalized_hostname}]"

    default_port = 80 if scheme == "http" else 443
    port_suffix = "" if port in {None, default_port} else f":{port}"
    return f"{scheme}://{normalized_hostname}{port_suffix}"


def normalize_allowed_origins(values: list[str]) -> list[str]:
    if len(values) > MAX_WIDGET_ALLOWED_DOMAINS:
        raise OriginValidationError(
            f"At most {MAX_WIDGET_ALLOWED_DOMAINS} allowed domains are supported."
        )

    normalized_values: list[str] = []
    for value in values:
        normalized = normalize_origin(value)
        if normalized not in normalized_values:
            normalized_values.append(normalized)

    return normalized_values


def origin_is_allowed(origin: str | None, allowed_origins: list[str]) -> bool:
    if origin is None:
        return False

    try:
        normalized_origin = normalize_origin(origin)
    except OriginValidationError:
        return False

    return normalized_origin in set(allowed_origins)
