from datetime import datetime, timezone
from typing import Iterable
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.tickets import (
    ACTIVE_TICKET_STATUSES,
    MAX_CHANNEL_LENGTH,
    MAX_SESSION_ID_LENGTH,
    TICKET_STATUS_TRANSITIONS,
    TicketPriority,
    TicketStatus,
)
from app.models.customer import Customer
from app.models.message import Message
from app.models.ticket import Ticket
from app.schemas.tickets import (
    TicketCustomerResponse,
    TicketListResponse,
    TicketSummaryResponse,
)


class TicketServiceError(RuntimeError):
    """Base class for safe ticket service errors."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class TicketNotFoundError(TicketServiceError):
    """Raised when a ticket or conversation session does not exist."""


class TicketValidationError(TicketServiceError):
    """Raised when ticket input is invalid."""


class TicketConflictError(TicketServiceError):
    """Raised when a ticket operation conflicts with current state."""


class InvalidTicketStatusTransitionError(TicketConflictError):
    """Raised when a requested status transition is not allowed."""


class TicketService:
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100

    @staticmethod
    def create(
        db: Session,
        *,
        channel: str,
        session_id: str | None = None,
        customer_id: str | None = None,
        subject: str | None = None,
        category: str | None = None,
        priority: TicketPriority | str = TicketPriority.NORMAL,
    ) -> Ticket:
        normalized_channel = TicketService._normalize_channel(channel)
        normalized_session_id = (
            TicketService._normalize_identifier(
                session_id,
                field_name="session ID",
                required=False,
            )
            if session_id is not None
            else str(uuid.uuid4())
        )
        normalized_customer_id = (
            TicketService._normalize_identifier(
                customer_id,
                field_name="customer ID",
                required=False,
            )
            if customer_id is not None
            else None
        )
        normalized_priority = TicketService._normalize_priority(priority)

        ticket = Ticket(
            session_id=normalized_session_id,
            customer_id=normalized_customer_id,
            channel=normalized_channel,
            subject=TicketService._normalize_optional_text(subject, 500),
            category=TicketService._normalize_optional_text(category, 100),
            status=TicketStatus.OPEN.value,
            priority=normalized_priority.value,
        )
        db.add(ticket)

        try:
            db.commit()
            db.refresh(ticket)
        except IntegrityError as exc:
            db.rollback()
            raise TicketConflictError(
                "A ticket already exists for this conversation session."
            ) from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise TicketServiceError(
                "The ticket could not be created."
            ) from exc

        return ticket

    @staticmethod
    def get(db: Session, ticket_id: str) -> Ticket:
        normalized_id = TicketService._normalize_identifier(
            ticket_id,
            field_name="ticket ID",
        )
        ticket = db.get(Ticket, normalized_id)

        if ticket is None:
            raise TicketNotFoundError("Ticket not found.")

        return ticket

    @staticmethod
    def get_by_session(db: Session, session_id: str) -> Ticket:
        normalized_session_id = TicketService._normalize_identifier(
            session_id,
            field_name="session ID",
        )
        ticket = db.scalar(
            select(Ticket).where(Ticket.session_id == normalized_session_id)
        )

        if ticket is None:
            raise TicketNotFoundError("Conversation session not found.")

        return ticket

    @staticmethod
    def list_tickets(
        db: Session,
        *,
        status: TicketStatus | str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> TicketListResponse:
        normalized_limit = TicketService._normalize_limit(limit)
        normalized_offset = TicketService._normalize_offset(offset)
        normalized_status = (
            TicketService._normalize_status(status)
            if status is not None
            else None
        )
        filters = []

        if normalized_status is not None:
            filters.append(Ticket.status == normalized_status.value)

        try:
            total = int(
                db.scalar(
                    select(func.count(Ticket.id)).where(*filters)
                )
                or 0
            )
            message_count = (
                select(func.count(Message.id))
                .where(Message.ticket_id == Ticket.id)
                .correlate(Ticket)
                .scalar_subquery()
            )
            last_message_preview = (
                select(Message.content)
                .where(Message.ticket_id == Ticket.id)
                .order_by(
                    Message.sequence_number.desc(),
                    Message.created_at.desc(),
                    Message.id.desc(),
                )
                .limit(1)
                .correlate(Ticket)
                .scalar_subquery()
            )
            rows = db.execute(
                select(
                    Ticket,
                    Customer,
                    message_count.label("message_count"),
                    last_message_preview.label("last_message_preview"),
                )
                .outerjoin(Customer, Customer.id == Ticket.customer_id)
                .where(*filters)
                .order_by(Ticket.updated_at.desc(), Ticket.id.desc())
                .offset(normalized_offset)
                .limit(normalized_limit)
            ).all()
        except SQLAlchemyError as exc:
            db.rollback()
            raise TicketServiceError(
                "Tickets are currently unavailable."
            ) from exc

        items = [
            TicketService._to_summary(
                ticket=ticket,
                customer=customer,
                message_count=message_count_value,
                last_message_preview=last_message_preview_value,
            )
            for (
                ticket,
                customer,
                message_count_value,
                last_message_preview_value,
            ) in rows
        ]

        return TicketListResponse(
            items=items,
            total=total,
            limit=normalized_limit,
            offset=normalized_offset,
        )

    @staticmethod
    def count(
        db: Session,
        *,
        statuses: Iterable[TicketStatus | str] | None = None,
    ) -> int:
        filters = []
        if statuses is not None:
            status_values = [
                TicketService._normalize_status(status).value
                for status in statuses
            ]
            filters.append(Ticket.status.in_(status_values))

        try:
            return max(
                int(
                    db.scalar(
                        select(func.count(Ticket.id)).where(*filters)
                    )
                    or 0
                ),
                0,
            )
        except SQLAlchemyError as exc:
            db.rollback()
            raise TicketServiceError(
                "Ticket counts are currently unavailable."
            ) from exc

    @staticmethod
    def update_status(
        db: Session,
        ticket_id: str,
        status: TicketStatus | str,
    ) -> Ticket:
        ticket = TicketService.get(db, ticket_id)
        target_status = TicketService._normalize_status(status)

        try:
            current_status = TicketStatus(ticket.status)
        except ValueError as exc:
            raise TicketValidationError(
                "The ticket has an unsupported current status."
            ) from exc

        if current_status == target_status:
            return ticket

        if target_status not in TICKET_STATUS_TRANSITIONS[current_status]:
            raise InvalidTicketStatusTransitionError(
                f"Cannot move a {current_status.value} ticket to "
                f"{target_status.value}."
            )

        ticket.status = target_status.value
        ticket.updated_at = datetime.now(timezone.utc)

        try:
            db.commit()
            db.refresh(ticket)
        except SQLAlchemyError as exc:
            db.rollback()
            raise TicketServiceError(
                "The ticket status could not be updated."
            ) from exc

        return ticket

    @staticmethod
    def reopen(db: Session, ticket_id: str) -> Ticket:
        return TicketService.update_status(
            db,
            ticket_id,
            TicketStatus.OPEN,
        )

    @staticmethod
    def resolve(db: Session, ticket_id: str) -> Ticket:
        return TicketService.update_status(
            db,
            ticket_id,
            TicketStatus.RESOLVED,
        )

    @staticmethod
    def close(db: Session, ticket_id: str) -> Ticket:
        return TicketService.update_status(
            db,
            ticket_id,
            TicketStatus.CLOSED,
        )

    @staticmethod
    def _to_summary(
        *,
        ticket: Ticket,
        customer: Customer | None,
        message_count: int,
        last_message_preview: str | None,
    ) -> TicketSummaryResponse:
        return TicketSummaryResponse(
            id=ticket.id,
            session_id=ticket.session_id,
            subject=ticket.subject,
            status=TicketStatus(ticket.status),
            priority=TicketPriority(ticket.priority),
            channel=ticket.channel,
            customer=TicketService._to_customer_response(customer),
            last_message_preview=last_message_preview,
            message_count=max(int(message_count or 0), 0),
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )

    @staticmethod
    def _to_customer_response(
        customer: Customer | None,
    ) -> TicketCustomerResponse | None:
        if customer is None:
            return None

        return TicketCustomerResponse(
            id=customer.id,
            name=customer.name,
            email=customer.email,
            external_customer_id=customer.external_customer_id,
        )

    @staticmethod
    def _normalize_identifier(
        value: str | None,
        *,
        field_name: str,
        required: bool = True,
    ) -> str:
        if value is None:
            if required:
                raise TicketValidationError(
                    f"A {field_name} is required."
                )

            raise TicketValidationError(
                f"A {field_name} cannot be empty."
            )

        normalized = value.strip()
        if not normalized or len(normalized) > MAX_SESSION_ID_LENGTH:
            raise TicketValidationError(
                f"The {field_name} is invalid."
            )

        try:
            return str(uuid.UUID(normalized))
        except ValueError as exc:
            raise TicketValidationError(
                f"The {field_name} is invalid."
            ) from exc

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        if not isinstance(channel, str):
            raise TicketValidationError("Channel must be a string.")

        normalized = channel.strip()
        if not normalized or len(normalized) > MAX_CHANNEL_LENGTH:
            raise TicketValidationError("The channel is invalid.")

        return normalized

    @staticmethod
    def _normalize_optional_text(
        value: str | None,
        max_length: int,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        if len(normalized) > max_length:
            raise TicketValidationError("Ticket text exceeds its limit.")

        return normalized

    @staticmethod
    def _normalize_priority(
        priority: TicketPriority | str,
    ) -> TicketPriority:
        try:
            return TicketPriority(priority)
        except ValueError as exc:
            raise TicketValidationError("The ticket priority is invalid.") from exc

    @staticmethod
    def _normalize_status(status: TicketStatus | str) -> TicketStatus:
        try:
            return TicketStatus(status)
        except ValueError as exc:
            raise TicketValidationError("The ticket status is invalid.") from exc

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        if not 1 <= limit <= TicketService.MAX_PAGE_SIZE:
            raise TicketValidationError(
                f"Ticket limit must be between 1 and "
                f"{TicketService.MAX_PAGE_SIZE}."
            )

        return limit

    @staticmethod
    def _normalize_offset(offset: int) -> int:
        if offset < 0:
            raise TicketValidationError("Ticket offset cannot be negative.")

        return offset
