"""Shared API envelopes and lifecycle contracts."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr, StringConstraints, model_validator

from backend.domain.types import Contract, FiniteNumber, Hash256, NonnegativeInt, UTCTimestamp

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "METHOD_NOT_ALLOWED",
    "HTTP_ERROR",
    "STATE_CONFLICT",
    "IDEMPOTENCY_CONFLICT",
    "STALE_DATA",
    "INSUFFICIENT_MARKET_DATA",
    "LIMIT_EXCEEDED",
    "PROVIDER_UNAVAILABLE",
    "FORECAST_UNAVAILABLE",
    "JOB_FAILED",
    "INTERNAL_ERROR",
    "WORKLOAD_LIMIT",
    "RESOURCE_EXHAUSTED",
    "TIME_LIMIT",
]
ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    "VALIDATION_ERROR": 422,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "HTTP_ERROR": 400,
    "STATE_CONFLICT": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "STALE_DATA": 409,
    "INSUFFICIENT_MARKET_DATA": 422,
    "LIMIT_EXCEEDED": 422,
    "PROVIDER_UNAVAILABLE": 503,
    "FORECAST_UNAVAILABLE": 422,
    "JOB_FAILED": 200,
    "INTERNAL_ERROR": 500,
    "WORKLOAD_LIMIT": 422,
    "RESOURCE_EXHAUSTED": 200,
    "TIME_LIMIT": 200,
}


class ErrorDetail(Contract):
    code: ErrorCode
    message: StrictStr
    details: dict[str, StrictStr | StrictInt | StrictBool | tuple[StrictStr, ...]]
    retryable: StrictBool
    correlation_id: UUID


class ErrorEnvelope(Contract):
    error: ErrorDetail


Cursor = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9_-]+$")
]


class PageRequest(Contract):
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 25
    cursor: Cursor | None = None


class Page[T](Contract):
    items: tuple[T, ...]
    next_cursor: Cursor | None


class ArtifactReference(Contract):
    id: UUID
    sha256: Hash256
    schema_version: Annotated[int, Field(strict=True, ge=1)]


JobStatus = Literal["queued", "running", "cancel_requested", "completed", "failed", "cancelled"]


class JobResult(Contract):
    kind: Literal["diagnostic", "resource"]
    resource_id: UUID | None
    message: StrictStr

    @model_validator(mode="after")
    def resource_identity(self) -> Self:
        if (self.kind == "resource") != (self.resource_id is not None):
            raise ValueError("Only resource results have a resource ID")
        return self


class JobV1(Contract):
    id: UUID
    kind: StrictStr
    status: JobStatus
    attempts: NonnegativeInt
    max_attempts: Annotated[int, Field(strict=True, ge=1)]
    progress: Annotated[FiniteNumber, Field(ge=0, le=100)]
    created_at: UTCTimestamp
    updated_at: UTCTimestamp
    result: JobResult | None
    error: ErrorDetail | None

    @model_validator(mode="after")
    def lifecycle(self) -> Self:
        if self.attempts > self.max_attempts or self.updated_at < self.created_at:
            raise ValueError("Invalid attempt count or chronology")
        if (self.status == "completed") != (self.result is not None):
            raise ValueError("Only completed jobs have sealed results")
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Failed jobs require an error; other states have no terminal error")
        if self.status == "completed" and self.progress != 100:
            raise ValueError("Completed jobs report 100 percent progress")
        return self
