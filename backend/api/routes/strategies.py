"""Read-only strategy discovery; mutation APIs belong to 0.0.3."""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope, Page
from backend.domain.registry import StrategyV1
from backend.strategies.registry import list_strategies

logger = logging.getLogger(__name__)


def strategies_router(engine: Engine | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/strategies", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (422, 503)
    }

    @router.get("", response_model=Page[StrategyV1], responses=errors)
    def strategies(
        limit: Annotated[int, Query(ge=1, le=100)] = 25, cursor: UUID | None = None
    ) -> Page[StrategyV1] | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Strategy storage is not ready.")
        try:
            return list_strategies(engine, limit, cursor)
        except LookupError:
            return error_response("VALIDATION_ERROR", "Strategy cursor is invalid.")
        except Exception as error:
            logger.warning("Strategy registry unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Strategy storage or integrity is unavailable.")

    return router
