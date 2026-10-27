"""Database-independent API bootstrap; readiness belongs to the persistence layer."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from backend.api.errors import register_error_handlers
from backend.api.openapi import ContractAPI
from backend.api.routes.health import health_router
from backend.api.routes.workspace import workspace_router
from backend.api.routing import ContractRoute
from backend.persistence.database import Settings, database_engine


class Liveness(BaseModel):
    status: Literal["alive"] = "alive"
    paper_only: Literal[True] = True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    engine = None
    if settings.database_url:
        try:
            engine = database_engine(settings.database_url)
        except ValueError:
            pass

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    app = ContractAPI(title="YAMS", version="0.0.1", lifespan=lifespan)
    app.router.route_class = ContractRoute
    register_error_handlers(app)
    app.include_router(health_router(engine, settings.fixture_root))
    app.include_router(workspace_router(engine, settings.fixture_root))

    @app.get("/livez", response_model=Liveness, tags=["operations"])
    def liveness() -> Liveness:
        """Process liveness only: not database, fixture or worker readiness."""
        return Liveness()

    return app


app = create_app()
