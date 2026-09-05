import logging

from fastapi import FastAPI

from app.api.routes.config import router as config_router
from app.api.routes.health import router as health_router
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

    app.include_router(
        health_router,
        prefix="/api",
    )

    app.include_router(
        config_router,
        prefix="/api",
    )

    app.include_router(
        settings_router,
        prefix="/api",
    )

    return app


app = create_app()