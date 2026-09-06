import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.config import router as config_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.rag import router as rag_router
from app.api.routes.settings import router as settings_router
from app.core.logging import RequestLoggingMiddleware


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


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
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    return app


app = create_app()
