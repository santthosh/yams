"""Typed recommendation admission/read transport; approval belongs to #50."""

import logging
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import Cursor, ErrorDetail, ErrorEnvelope, PageRequest
from backend.domain.decision_context import ApprovalPreviewV1, DecisionInputsV1
from backend.domain.recommendation_api import (
    RecommendationAccepted,
    RecommendationDetailV1,
    RecommendationPageV1,
    RecommendationRequest,
)
from backend.jobs.queue import IdempotencyConflict
from backend.persistence.database import Settings
from backend.portfolio.accounts import AccountError
from backend.portfolio.decision_context import approval_preview, decision_inputs
from backend.portfolio.recommendation_queries import (
    RecommendationPending,
    RecommendationQueryError,
    detail,
    history,
)
from backend.portfolio.recommendations import RecommendationAdmissionError, admit_recommendation

logger = logging.getLogger(__name__)


def pending_response(error: RecommendationPending) -> JSONResponse:
    job = error.job
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code="STATE_CONFLICT",
            message="Resource has no completed publication; inspect its job status.",
            details={"job_id": str(job.id), "status": job.status, "kind": job.kind},
            retryable=job.status in {"queued", "running", "cancel_requested"},
            correlation_id=uuid4(),
        )
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=409)


def recommendations_router(engine: Engine | None, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)
    }

    def unavailable(error: Exception | None = None) -> JSONResponse:
        if error is not None:
            logger.warning("Recommendation unavailable error_type=%s", type(error).__name__)
        return error_response("NOT_READY", "Recommendation storage or integrity is unavailable.")

    @router.get(
        "/portfolios/{portfolio_id}/decision-inputs",
        response_model=DecisionInputsV1,
        responses=errors,
    )
    def inputs(portfolio_id: UUID) -> DecisionInputsV1 | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            return decision_inputs(engine, settings.artifact_root, portfolio_id)
        except LookupError:
            return error_response("NOT_FOUND", "Portfolio was not found.")
        except Exception as error:
            return unavailable(error)

    @router.get(
        "/recommendations/{recommendation_id}/approval-preview",
        response_model=ApprovalPreviewV1,
        responses=errors,
    )
    def preview(recommendation_id: UUID) -> ApprovalPreviewV1 | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            return approval_preview(engine, settings.artifact_root, recommendation_id)
        except LookupError:
            return error_response("NOT_FOUND", "Recommendation was not found.")
        except RecommendationPending as error:
            return pending_response(error)
        except Exception as error:
            return unavailable(error)

    @router.post(
        "/portfolios/{portfolio_id}/recommendations",
        status_code=202,
        response_model=RecommendationAccepted,
        responses=errors,
    )
    def create(
        portfolio_id: UUID,
        request: RecommendationRequest,
        idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
    ) -> RecommendationAccepted | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            return admit_recommendation(
                engine,
                settings.artifact_root,
                portfolio_id,
                request,
                idempotency_key=idempotency_key,
            )
        except RecommendationAdmissionError as error:
            return error_response(error.code, error.message)
        except AccountError as error:
            return error_response(error.code, error.message)
        except IdempotencyConflict:
            return error_response(
                "IDEMPOTENCY_CONFLICT", "Recommendation key has different inputs."
            )
        except LookupError:
            return error_response("NOT_FOUND", "Portfolio was not found.")
        except Exception as error:
            return unavailable(error)

    @router.get(
        "/portfolios/{portfolio_id}/recommendations",
        response_model=RecommendationPageV1,
        responses=errors,
    )
    def list_recommendations(
        portfolio_id: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: Cursor | None = None,
    ) -> RecommendationPageV1 | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            return history(engine, portfolio_id, PageRequest(limit=limit, cursor=cursor))
        except LookupError:
            return error_response("NOT_FOUND", "Portfolio was not found.")
        except RecommendationQueryError:
            return error_response("VALIDATION_ERROR", "Recommendation history cursor is invalid.")
        except Exception as error:
            return unavailable(error)

    @router.get(
        "/recommendations/{recommendation_id}",
        response_model=RecommendationDetailV1,
        responses=errors,
    )
    def read(recommendation_id: UUID) -> RecommendationDetailV1 | JSONResponse:
        if engine is None:
            return unavailable()
        try:
            result = detail(engine, settings.artifact_root, recommendation_id)
            return (
                result
                if result is not None
                else error_response("NOT_FOUND", "Recommendation was not found.")
            )
        except RecommendationPending as error:
            return pending_response(error)
        except Exception as error:
            return unavailable(error)

    return router
