from enum import Enum


class TicketStatus(str, Enum):
    OPEN = "open"
    AI_PROCESSING = "ai_processing"
    WAITING_CUSTOMER = "waiting_customer"
    HUMAN_REVIEW = "human_review"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageSenderType(str, Enum):
    CUSTOMER = "customer"
    AI = "ai"
    HUMAN = "human"
    SYSTEM = "system"


ACTIVE_TICKET_STATUSES = frozenset(
    {
        TicketStatus.OPEN,
        TicketStatus.AI_PROCESSING,
        TicketStatus.WAITING_CUSTOMER,
        TicketStatus.HUMAN_REVIEW,
    }
)


TICKET_STATUS_TRANSITIONS = {
    TicketStatus.OPEN: frozenset(
        {
            TicketStatus.AI_PROCESSING,
            TicketStatus.HUMAN_REVIEW,
            TicketStatus.RESOLVED,
        }
    ),
    TicketStatus.AI_PROCESSING: frozenset(
        {
            TicketStatus.WAITING_CUSTOMER,
            TicketStatus.HUMAN_REVIEW,
            TicketStatus.OPEN,
        }
    ),
    TicketStatus.WAITING_CUSTOMER: frozenset(
        {
            TicketStatus.OPEN,
            TicketStatus.AI_PROCESSING,
            TicketStatus.RESOLVED,
        }
    ),
    TicketStatus.HUMAN_REVIEW: frozenset(
        {
            TicketStatus.OPEN,
            TicketStatus.RESOLVED,
        }
    ),
    TicketStatus.RESOLVED: frozenset(
        {
            TicketStatus.CLOSED,
            TicketStatus.OPEN,
        }
    ),
    TicketStatus.CLOSED: frozenset({TicketStatus.OPEN}),
}


DEFAULT_CONVERSATION_CHANNEL = "web"
MAX_CHANNEL_LENGTH = 50
MAX_MESSAGE_LENGTH = 10_000
MAX_SESSION_ID_LENGTH = 100
