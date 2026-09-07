from enum import Enum
import re


DEFAULT_WIDGET_PROJECT_ID = "local-default"
DEFAULT_WIDGET_DISPLAY_NAME = "AgentDesk Support"
DEFAULT_WIDGET_WELCOME_MESSAGE = "Hi! How can we help?"
WIDGET_CHANNEL = "widget"

MAX_WIDGET_PROJECT_ID_LENGTH = 64
MAX_WIDGET_DISPLAY_NAME_LENGTH = 255
MAX_WIDGET_WELCOME_MESSAGE_LENGTH = 2_000
MAX_WIDGET_ALLOWED_DOMAINS = 25
MAX_WIDGET_ORIGIN_LENGTH = 2_048

WIDGET_PROJECT_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_-]{0,63}$"
)


class WidgetPosition(str, Enum):
    BOTTOM_RIGHT = "bottom-right"
    BOTTOM_LEFT = "bottom-left"


def normalize_widget_project_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Widget project ID must be a string.")

    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > MAX_WIDGET_PROJECT_ID_LENGTH
        or WIDGET_PROJECT_ID_PATTERN.fullmatch(normalized) is None
    ):
        raise ValueError("The widget project ID is invalid.")

    return normalized
