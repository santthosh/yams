from pathlib import Path

from fastapi import APIRouter, Response
from sqlalchemy import Engine

from backend.api.routing import ContractRoute
from backend.domain.workspace import HealthV1
from backend.persistence.readiness import readiness


def health_router(
    engine: Engine | None, fixture_root: Path, database_reason: str = "DATABASE_UNAVAILABLE"
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", route_class=ContractRoute)

    @router.get("/health", response_model=HealthV1, responses={503: {"model": HealthV1}})
    def health(response: Response) -> HealthV1:
        result = readiness(engine, fixture_root, database_reason)
        response.status_code = 200 if result.status == "ready" else 503
        return result

    return router
