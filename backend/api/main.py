"""Database-independent API bootstrap; readiness belongs to the persistence layer."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from backend.api.errors import register_error_handlers
from backend.api.openapi import ContractAPI
from backend.api.routes.data import data_router
from backend.api.routes.health import health_router
from backend.api.routes.jobs import jobs_router
from backend.api.routes.strategies import strategies_router
from backend.api.routes.strategy_evaluations import evaluations_router
from backend.api.routes.workspace import workspace_router
from backend.api.routing import ContractRoute
from backend.persistence.database import Settings, database_engine

logger = logging.getLogger(__name__)


class Liveness(BaseModel):
    status: Literal["alive"] = "alive"
    paper_only: Literal[True] = True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    engine = None
    database_reason = "DATABASE_UNAVAILABLE"
    if settings.database_url:
        try:
            engine = database_engine(settings.database_url)
        except ValueError:
            database_reason = "DATABASE_MISCONFIGURED"
            logger.warning("DATABASE_URL is set but invalid; database features disabled")

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
    app.include_router(health_router(engine, settings.fixture_root, database_reason))
    app.include_router(workspace_router(engine, settings.fixture_root, database_reason))
    app.include_router(jobs_router(engine))
    app.include_router(data_router(engine, settings))
    app.include_router(strategies_router(engine))
    app.include_router(evaluations_router(engine, settings))

    @app.get("/livez", response_model=Liveness, tags=["operations"])
    def liveness() -> Liveness:
        """Process liveness only: not database, fixture or worker readiness."""
        return Liveness()

    return app


app = create_app()
