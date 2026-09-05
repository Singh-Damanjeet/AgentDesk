from fastapi import FastAPI

from app.api.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentDesk API",
        description="Backend API for the AgentDesk customer support platform.",
        version="0.1.0",
    )

    app.include_router(
        health_router,
        prefix="/api",
    )

    return app


app = create_app()