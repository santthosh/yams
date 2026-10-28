"""Strategy identity and append-only, validated configuration publication."""

import logging
from collections.abc import Callable
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope, Page
from backend.domain.registry import StrategyCreateRequest, StrategyV1, StrategyVersionV1
from backend.domain.strategy import StrategyConfigV1
from backend.strategies.registry import (
    StrategyNameConflict,
    StrategyNotFound,
    create_strategy,
    get_strategy,
    list_strategies,
    list_versions,
    publish_version,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


def strategies_router(engine: Engine | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/strategies", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)
    }

    def stored(operation: Callable[[Engine], T]) -> T | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Strategy storage is not ready.")
        try:
            return operation(engine)
        except StrategyNotFound:
            return error_response("NOT_FOUND", "Strategy was not found.")
        except StrategyNameConflict:
            return error_response("STATE_CONFLICT", "Strategy name already exists.")
        except LookupError:
            return error_response("VALIDATION_ERROR", "Strategy cursor is invalid.")
        except Exception as error:
            logger.warning("Strategy registry unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Strategy storage or integrity is unavailable.")

    @router.get("", response_model=Page[StrategyV1], responses=errors)
    def strategies(
        limit: Annotated[int, Query(ge=1, le=100)] = 25, cursor: UUID | None = None
    ) -> Page[StrategyV1] | JSONResponse:
        return stored(lambda db: list_strategies(db, limit, cursor))

    @router.post("", status_code=201, response_model=StrategyV1, responses=errors)
    def create(request: StrategyCreateRequest) -> StrategyV1 | JSONResponse:
        return stored(lambda db: create_strategy(db, request))

    @router.get("/{strategy_id}", response_model=StrategyV1, responses=errors)
    def detail(strategy_id: UUID) -> StrategyV1 | JSONResponse:
        return stored(lambda db: get_strategy(db, strategy_id))

    @router.get("/{strategy_id}/versions", response_model=Page[StrategyVersionV1], responses=errors)
    def versions(
        strategy_id: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: UUID | None = None,
    ) -> Page[StrategyVersionV1] | JSONResponse:
        return stored(lambda db: list_versions(db, strategy_id, limit, cursor))

    @router.post(
        "/{strategy_id}/versions",
        status_code=201,
        response_model=StrategyVersionV1,
        responses=errors,
    )
    def publish(strategy_id: UUID, config: StrategyConfigV1) -> StrategyVersionV1 | JSONResponse:
        return stored(lambda db: publish_version(db, strategy_id, config))

    return router
