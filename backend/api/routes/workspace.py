from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope
from backend.domain.workspace import WorkspaceV1
from backend.persistence.readiness import read_workspace, readiness


def workspace_router(engine: Engine | None, fixture_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1", route_class=ContractRoute)

    @router.get("/workspace", response_model=WorkspaceV1, responses={503: {"model": ErrorEnvelope}})
    def workspace() -> WorkspaceV1 | JSONResponse:
        health = readiness(engine, fixture_root)
        if engine is None or any(
            check.status != "ready"
            for check in (
                health.database,
                health.migration,
                health.workspace,
            )
        ):
            return error_response("NOT_READY", "Workspace is not ready.")
        try:
            return read_workspace(engine)
        except Exception:
            return error_response("NOT_READY", "Workspace is not ready.")

    return router
