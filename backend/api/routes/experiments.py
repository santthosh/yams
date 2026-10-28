"""Public asynchronous experiments; bounded reads never execute a backtest."""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.backtesting.errors import BacktestFailure
from backend.backtesting.queries import (
    ExperimentQueryError,
    ExperimentStateConflict,
    artifact_page,
    detail,
    history,
)
from backend.backtesting.service import admit_experiment
from backend.domain.common import Cursor, ErrorEnvelope, PageRequest
from backend.domain.experiment import ExperimentRequest
from backend.domain.experiment_api import (
    ExperimentAccepted,
    ExperimentDetailV1,
    ExperimentPageV1,
    ExperimentSeriesPageV1,
    ExperimentTradesPageV1,
)
from backend.domain.types import SessionDate
from backend.market_data.files import SnapshotIntegrityError
from backend.persistence.database import Settings

logger = logging.getLogger(__name__)


def experiments_router(engine: Engine | None, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/experiments", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)
    }

    def unavailable(error: Exception | None = None) -> JSONResponse:
        if error is not None:
            logger.warning("Experiment unavailable error_type=%s", type(error).__name__)
        return error_response("NOT_READY", "Experiment storage or integrity is unavailable.")

    @router.post("", status_code=202, response_model=ExperimentAccepted, responses=errors)
    def create(request: ExperimentRequest) -> ExperimentAccepted | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            accepted = admit_experiment(engine, settings.artifact_root, request)
            return ExperimentAccepted(experiment_id=accepted.experiment_id, job_id=accepted.job_id)
        except BacktestFailure as error:
            return error_response(
                "VALIDATION_ERROR",
                "Snapshot cannot support this backtest.",
                field_paths=(error.reason,),
            )
        except SnapshotIntegrityError as error:
            return unavailable(error)
        except ValueError as error:
            if str(error) == "NOT_FOUND":
                return error_response("NOT_FOUND", "Strategy version or snapshot was not found.")
            if str(error) == "WORKLOAD_LIMIT":
                return error_response("WORKLOAD_LIMIT", "Backtest exceeds workload limits.")
            if str(error) == "INVALID_EXPERIMENT_WINDOW":
                return error_response(
                    "VALIDATION_ERROR", "Window has no usable pinned sessions or cutoff."
                )
            if str(error) == "DECISION_CUTOFF_NOT_ELAPSED":
                return error_response("VALIDATION_ERROR", "Market decision cutoff has not elapsed.")
            return unavailable(error)
        except Exception as error:
            return unavailable(error)

    @router.get("", response_model=ExperimentPageV1, responses=errors)
    def list_experiments(
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: Cursor | None = None,
    ) -> ExperimentPageV1 | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            return history(engine, PageRequest(limit=limit, cursor=cursor))
        except ExperimentQueryError:
            return error_response("VALIDATION_ERROR", "Experiment history cursor is invalid.")
        except Exception as error:
            return unavailable(error)

    @router.get("/{experiment_id}", response_model=ExperimentDetailV1, responses=errors)
    def read(experiment_id: UUID) -> ExperimentDetailV1 | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            result = detail(engine, settings.artifact_root, experiment_id)
            return (
                result
                if result is not None
                else error_response("NOT_FOUND", "Experiment not found.")
            )
        except Exception as error:
            return unavailable(error)

    def samples(
        experiment_id: UUID,
        role: str,
        limit: int,
        cursor: str | None,
        start_session: SessionDate | None,
        end_session_exclusive: SessionDate | None,
    ) -> ExperimentSeriesPageV1 | ExperimentTradesPageV1 | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            result = artifact_page(
                engine,
                settings.artifact_root,
                experiment_id,
                "series" if role == "series" else "trades",
                PageRequest(limit=limit, cursor=cursor),
                start_session,
                end_session_exclusive,
            )
            return (
                result
                if result is not None
                else error_response("NOT_FOUND", "Experiment not found.")
            )
        except ExperimentQueryError:
            return error_response("VALIDATION_ERROR", "Experiment window or cursor is invalid.")
        except ExperimentStateConflict:
            return error_response("STATE_CONFLICT", "Experiment has no completed report.")
        except Exception as error:
            return unavailable(error)

    @router.get("/{experiment_id}/series", response_model=ExperimentSeriesPageV1, responses=errors)
    def series(
        experiment_id: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: Cursor | None = None,
        start_session: SessionDate | None = None,
        end_session_exclusive: SessionDate | None = None,
    ) -> ExperimentSeriesPageV1 | ExperimentTradesPageV1 | JSONResponse:
        return samples(experiment_id, "series", limit, cursor, start_session, end_session_exclusive)

    @router.get("/{experiment_id}/trades", response_model=ExperimentTradesPageV1, responses=errors)
    def trades(
        experiment_id: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: Cursor | None = None,
        start_session: SessionDate | None = None,
        end_session_exclusive: SessionDate | None = None,
    ) -> ExperimentSeriesPageV1 | ExperimentTradesPageV1 | JSONResponse:
        return samples(experiment_id, "trades", limit, cursor, start_session, end_session_exclusive)

    return router
