from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.core.widget import DEFAULT_WIDGET_PROJECT_ID
from app.db.session import get_db
from app.schemas.widget import (
    WidgetConfigResponse,
    WidgetConfigUpdate,
    WidgetConversationResponse,
    WidgetMessageRequest,
    WidgetPublicConfigResponse,
    WidgetSessionRequest,
)
from app.services.conversation_service import (
    ConversationBusyError,
    ConversationGenerationError,
    ConversationServiceError,
)
from app.services.ticket_service import (
    TicketConflictError,
    TicketNotFoundError,
    TicketServiceError,
    TicketValidationError,
)
from app.services.widget_service import (
    WidgetDisabledError,
    WidgetNotFoundError,
    WidgetOriginError,
    WidgetService,
    WidgetServiceError,
    WidgetValidationError,
)
from app.widget.loader import build_widget_loader_script


admin_router = APIRouter(
    prefix="/settings/widget",
    tags=["Widget settings"],
)

router = APIRouter(
    prefix="/widget",
    tags=["Website widget"],
)

loader_router = APIRouter(tags=["Website widget"])

widget_service = WidgetService()


@admin_router.get(
    "",
    response_model=WidgetConfigResponse | None,
)
def get_widget_settings(
    db: Session = Depends(get_db),
) -> WidgetConfigResponse | None:
    try:
        config = widget_service.get(db, DEFAULT_WIDGET_PROJECT_ID)
    except WidgetValidationError as exc:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.user_message,
        ) from exc
    except WidgetServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc

    return widget_service.to_response(config) if config is not None else None


@admin_router.put(
    "",
    response_model=WidgetConfigResponse,
)
def update_widget_settings(
    data: WidgetConfigUpdate,
    db: Session = Depends(get_db),
) -> WidgetConfigResponse:
    try:
        config = widget_service.update(db, data)
    except WidgetValidationError as exc:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.user_message,
        ) from exc
    except WidgetServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc

    return widget_service.to_response(config)


@router.get(
    "/config/{project_id}",
    response_model=WidgetPublicConfigResponse,
)
def get_public_widget_config(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> WidgetPublicConfigResponse:
    try:
        return widget_service.get_public_config(
            db,
            project_id=project_id,
            origin=request.headers.get("origin"),
        )
    except (
        WidgetNotFoundError,
        WidgetOriginError,
    ) as exc:
        raise _public_error(exc) from exc
    except WidgetValidationError as exc:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.user_message,
        ) from exc
    except WidgetServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc


@router.post(
    "/sessions",
    response_model=WidgetConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_widget_session(
    request: Request,
    data: WidgetSessionRequest | None = Body(default=None),
    project_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
    ),
    db: Session = Depends(get_db),
) -> WidgetConversationResponse:
    resolved_project_id = _resolve_project_id(project_id, data)
    try:
        return widget_service.create_session(
            db,
            project_id=resolved_project_id,
            origin=request.headers.get("origin"),
        )
    except (
        WidgetNotFoundError,
        WidgetOriginError,
        WidgetDisabledError,
    ) as exc:
        raise _public_error(exc) from exc
    except WidgetValidationError as exc:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.user_message,
        ) from exc
    except (ConversationServiceError, TicketServiceError) as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc
    except WidgetServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc


@router.get(
    "/sessions/{session_id}",
    response_model=WidgetConversationResponse,
)
def get_widget_session(
    session_id: str,
    request: Request,
    project_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
    ),
    db: Session = Depends(get_db),
) -> WidgetConversationResponse:
    try:
        return widget_service.get_session(
            db,
            project_id=project_id,
            session_id=session_id,
            origin=request.headers.get("origin"),
        )
    except (WidgetNotFoundError, TicketNotFoundError) as exc:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            exc.user_message,
        ) from exc
    except (WidgetOriginError, WidgetDisabledError) as exc:
        raise _http_error(
            status.HTTP_403_FORBIDDEN,
            exc.user_message,
        ) from exc
    except (WidgetValidationError, TicketValidationError) as exc:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.user_message,
        ) from exc
    except (ConversationServiceError, TicketServiceError) as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc
    except WidgetServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc


@router.post(
    "/sessions/{session_id}/messages",
    response_model=WidgetConversationResponse,
)
async def append_widget_message(
    session_id: str,
    data: WidgetMessageRequest,
    request: Request,
    project_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
    ),
    db: Session = Depends(get_db),
) -> WidgetConversationResponse:
    try:
        return await widget_service.append_message(
            db,
            project_id=project_id,
            session_id=session_id,
            content=data.content,
            origin=request.headers.get("origin"),
        )
    except (WidgetNotFoundError, TicketNotFoundError) as exc:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            exc.user_message,
        ) from exc
    except (WidgetOriginError, WidgetDisabledError) as exc:
        raise _http_error(
            status.HTTP_403_FORBIDDEN,
            exc.user_message,
        ) from exc
    except (ConversationBusyError, TicketConflictError) as exc:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            exc.user_message,
        ) from exc
    except (WidgetValidationError, TicketValidationError) as exc:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.user_message,
        ) from exc
    except ConversationGenerationError:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "We could not complete your message. A support teammate will "
            "review it.",
        ) from None
    except ConversationServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc
    except TicketServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc
    except WidgetServiceError as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            exc.user_message,
        ) from exc


@loader_router.get(
    "/widget.js",
    response_class=Response,
)
def get_widget_loader() -> Response:
    return Response(
        content=build_widget_loader_script(),
        media_type="application/javascript",
    )


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _public_error(exc: WidgetServiceError) -> HTTPException:
    if isinstance(exc, WidgetNotFoundError):
        return _http_error(status.HTTP_404_NOT_FOUND, exc.user_message)

    if isinstance(exc, WidgetOriginError | WidgetDisabledError):
        return _http_error(status.HTTP_403_FORBIDDEN, exc.user_message)

    return _http_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        exc.user_message,
    )


def _resolve_project_id(
    query_project_id: str | None,
    data: WidgetSessionRequest | None,
) -> str:
    body_project_id = data.project_id if data is not None else None
    if query_project_id is not None and body_project_id is not None:
        if query_project_id.strip().lower() != body_project_id.strip().lower():
            raise _http_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "The widget project IDs do not match.",
            )

    resolved = query_project_id or body_project_id
    if resolved is None:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A widget project ID is required.",
        )

    return resolved
