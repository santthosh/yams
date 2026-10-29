"""Readonly portfolio schedule diagnostics; mutation remains in the bounded supervisor."""

import logging
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope
from backend.domain.review import PortfolioScheduleV1
from backend.jobs.review_queries import schedule_status

logger = logging.getLogger(__name__)


def reviews_router(engine: Engine | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/portfolios", route_class=ContractRoute)

    @router.get(
        "/{portfolio_id}/schedule",
        response_model=PortfolioScheduleV1,
        responses={status: {"model": ErrorEnvelope} for status in (404, 422, 503)},
    )
    def read(portfolio_id: UUID) -> PortfolioScheduleV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Scheduling storage is unavailable.")
        try:
            return schedule_status(engine, portfolio_id)
        except LookupError:
            return error_response("NOT_FOUND", "Portfolio was not found.")
        except Exception as error:
            logger.warning("schedule_status_unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Scheduling storage or integrity is unavailable.")

    return router
