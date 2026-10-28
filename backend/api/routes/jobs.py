import logging
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope, JobV1
from backend.domain.experiment_api import JobCancelRequest
from backend.jobs.queue import Queue, TerminalJobConflict

logger = logging.getLogger(__name__)


def jobs_router(engine: Engine | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/jobs", route_class=ContractRoute)

    @router.get(
        "/{job_id}",
        response_model=JobV1,
        responses={
            404: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
    )
    def get_job(job_id: UUID) -> JobV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Job storage is not ready.")
        try:
            job = Queue(engine).get(job_id)
        except Exception as error:
            logger.warning("Job read failed error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Job storage is not ready.")
        if job is None:
            return error_response("NOT_FOUND", "Job not found.")
        return job

    @router.post(
        "/{job_id}/cancel",
        status_code=202,
        response_model=JobV1,
        responses={status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)},
    )
    def cancel_job(job_id: UUID, request: JobCancelRequest) -> JobV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Job storage is not ready.")
        try:
            job = Queue(engine).cancel(job_id, reject_terminal=True)
        except TerminalJobConflict:
            return error_response("STATE_CONFLICT", "Job is already terminal.")
        except Exception as error:
            logger.warning("Job cancel failed error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Job storage is not ready.")
        if job is None:
            return error_response("NOT_FOUND", "Job not found.")
        return job

    return router
