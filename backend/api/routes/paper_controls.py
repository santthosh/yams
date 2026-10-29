"""Paper-only authorization transport; prices and timestamps are never client inputs."""

import logging
from collections.abc import Callable
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routes.recommendations import pending_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope
from backend.domain.paper_api import (
    ApplyRecommendationRequest,
    FixtureAdvanceAccepted,
    PaperActionRequest,
    PaperApprovalAccepted,
    PaperBatchDetailV1,
    RecommendationDispositionV1,
)
from backend.jobs.queue import Queue
from backend.persistence.database import Settings
from backend.portfolio.batches import (
    ApprovalIdempotencyConflict,
    ApprovalIntegrityConflict,
    NoExecutableOrders,
    StaleApprovalData,
    cancel_batch,
)
from backend.portfolio.ledger import LedgerConflict
from backend.portfolio.paper_controls import (
    advance_fixture,
    apply_recommendation,
    approval_result,
    batch_detail,
    dismiss_recommendation,
)
from backend.portfolio.recommendation_queries import RecommendationPending

logger = logging.getLogger(__name__)
T = TypeVar("T")


def paper_controls_router(engine: Engine | None, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)
    }

    def run(operation: Callable[[Engine], T]) -> T | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Paper control storage is unavailable.")
        try:
            return operation(engine)
        except RecommendationPending as error:
            return pending_response(error)
        except ApprovalIdempotencyConflict:
            return error_response("IDEMPOTENCY_CONFLICT", "Approval key has different inputs.")
        except ApprovalIntegrityConflict:
            return error_response("NOT_READY", "Immutable approval evidence is unavailable.")
        except StaleApprovalData:
            return error_response("STALE_DATA", "Pinned market evidence is stale or unavailable.")
        except NoExecutableOrders:
            return error_response("VALIDATION_ERROR", "Recommendation has no executable orders.")
        except LedgerConflict:
            return error_response("STATE_CONFLICT", "Paper state changed; refresh before retrying.")
        except LookupError:
            return error_response("NOT_FOUND", "Paper resource was not found.")
        except Exception as error:
            logger.warning("paper_control_unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Paper control storage or integrity is unavailable.")

    @router.post(
        "/recommendations/{recommendation_id}/apply",
        status_code=202,
        response_model=PaperApprovalAccepted,
        responses=errors,
    )
    def apply(
        recommendation_id: UUID,
        request: ApplyRecommendationRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> PaperApprovalAccepted | JSONResponse:
        return run(
            lambda db: apply_recommendation(
                db,
                settings.artifact_root,
                recommendation_id,
                request.expected_revision,
                idempotency_key,
            )
        )

    @router.get(
        "/recommendations/{recommendation_id}/apply-result",
        response_model=PaperApprovalAccepted,
        responses=errors,
    )
    def recover(
        recommendation_id: UUID, idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")]
    ) -> PaperApprovalAccepted | JSONResponse:
        return run(lambda db: approval_result(db, recommendation_id, idempotency_key))

    @router.get("/order-batches/{batch_id}", response_model=PaperBatchDetailV1, responses=errors)
    def read(batch_id: UUID) -> PaperBatchDetailV1 | JSONResponse:
        return run(lambda db: batch_detail(db, batch_id))

    @router.post(
        "/recommendations/{recommendation_id}/dismiss",
        response_model=RecommendationDispositionV1,
        responses=errors,
    )
    def dismiss(
        recommendation_id: UUID, request: PaperActionRequest
    ) -> RecommendationDispositionV1 | JSONResponse:
        return run(lambda db: dismiss_recommendation(db, recommendation_id))

    @router.post(
        "/order-batches/{batch_id}/cancel", response_model=PaperBatchDetailV1, responses=errors
    )
    def cancel(batch_id: UUID, request: PaperActionRequest) -> PaperBatchDetailV1 | JSONResponse:
        def operation(db: Engine) -> PaperBatchDetailV1:
            # Public identity check occurs before invoking the private controller.
            batch_detail(db, batch_id)
            cancel_batch(db, batch_id, server_clock=True)
            return batch_detail(db, batch_id)

        return run(operation)

    @router.post(
        "/order-batches/{batch_id}/advance-fixture",
        status_code=202,
        response_model=FixtureAdvanceAccepted,
        responses=errors,
    )
    def advance(
        batch_id: UUID,
        request: PaperActionRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> FixtureAdvanceAccepted | JSONResponse:
        return run(
            lambda db: advance_fixture(Queue(db), settings.artifact_root, batch_id, idempotency_key)
        )

    return router
