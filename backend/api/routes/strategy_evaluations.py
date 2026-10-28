"""Pinned asynchronous research diagnostics; never creates trading state."""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope
from backend.domain.evaluation import (
    StrategyEvaluationAccepted,
    StrategyEvaluationRequest,
    StrategyEvaluationV1,
)
from backend.persistence.database import Settings
from backend.strategies.evaluations import (
    EvaluationAdmissionError,
    admit_evaluation,
    read_evaluation,
)

logger = logging.getLogger(__name__)


def evaluations_router(engine: Engine | None, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/strategy-evaluations", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)
    }

    @router.post("", status_code=202, response_model=StrategyEvaluationAccepted, responses=errors)
    def create(request: StrategyEvaluationRequest) -> StrategyEvaluationAccepted | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Diagnostic storage is not ready.")
        try:
            return admit_evaluation(engine, settings.artifact_root, request)
        except EvaluationAdmissionError as error:
            return error_response(error.code, error.message)
        except Exception as error:
            logger.warning("Diagnostic admission unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Diagnostic storage or integrity is unavailable.")

    @router.get("/{evaluation_id}", response_model=StrategyEvaluationV1, responses=errors)
    def read(evaluation_id: UUID) -> StrategyEvaluationV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Diagnostic storage is not ready.")
        try:
            result = read_evaluation(engine, evaluation_id)
            if result is None:
                return error_response("NOT_FOUND", "Diagnostic evaluation was not found.")
            return result
        except Exception as error:
            logger.warning("Diagnostic read unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Diagnostic storage or integrity is unavailable.")

    return router
