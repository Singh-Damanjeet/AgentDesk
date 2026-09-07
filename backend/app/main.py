import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.config import router as config_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.agent_runs import router as agent_runs_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.rag import router as rag_router
from app.api.routes.settings import router as settings_router
from app.api.routes.tickets import router as tickets_router
from app.api.routes.widget import (
    admin_router as widget_admin_router,
    loader_router as widget_loader_router,
    router as widget_router,
)
from app.core.logging import RequestLoggingMiddleware
from app.core.widget_cors import WidgetCORSMiddleware


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

ADMIN_CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
ADMIN_CORS_HEADERS = ["Accept", "Content-Type"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentDesk API",
        description="Backend API for the AgentDesk customer support platform.",
        version="0.1.0",
    )

    app.add_middleware(RequestLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=ADMIN_CORS_METHODS,
        allow_headers=ADMIN_CORS_HEADERS,
    )

    # Widget origins are persisted configuration, so their CORS response
    # headers are handled separately while route services enforce access.
    app.add_middleware(WidgetCORSMiddleware)

    app.include_router(
        health_router,
        prefix="/api",
    )

    app.include_router(
        config_router,
        prefix="/api",
    )

    app.include_router(
        dashboard_router,
        prefix="/api",
    )

    app.include_router(
        agent_runs_router,
        prefix="/api",
    )

    app.include_router(
        settings_router,
        prefix="/api",
    )

    app.include_router(
        knowledge_router,
        prefix="/api",
    )

    app.include_router(
        rag_router,
        prefix="/api",
    )

    app.include_router(
        tickets_router,
        prefix="/api",
    )

    app.include_router(
        conversations_router,
        prefix="/api",
    )

    app.include_router(
        widget_admin_router,
        prefix="/api",
    )

    app.include_router(
        widget_router,
        prefix="/api",
    )

    app.include_router(widget_loader_router)

    return app


app = create_app()
