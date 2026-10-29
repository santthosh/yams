"""Read only published recommendation forecasts, retaining genuine job failures."""

import logging
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routes.recommendations import pending_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope
from backend.domain.forecast import ForecastV1
from backend.persistence.database import Settings
from backend.portfolio.recommendation_queries import RecommendationPending, public_forecast

logger = logging.getLogger(__name__)


def forecasts_router(engine: Engine | None, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/forecasts", route_class=ContractRoute)

    @router.get(
        "/{forecast_id}",
        response_model=ForecastV1,
        responses={status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)},
    )
    def read(forecast_id: UUID) -> ForecastV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Forecast storage is not ready.")
        try:
            result = public_forecast(engine, settings.artifact_root, forecast_id)
            return (
                result
                if result is not None
                else error_response("NOT_FOUND", "Forecast was not found.")
            )
        except RecommendationPending as error:
            return pending_response(error)
        except Exception as error:
            logger.warning("Forecast unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Forecast storage or integrity is unavailable.")

    return router
