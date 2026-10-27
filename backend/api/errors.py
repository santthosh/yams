"""Consistent safe error responses; request payloads are never echoed."""

import logging
from collections.abc import Mapping
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.domain.common import ERROR_HTTP_STATUS, ErrorCode, ErrorDetail, ErrorEnvelope

logger = logging.getLogger(__name__)


def error_response(
    code: ErrorCode,
    message: str,
    status: int | None = None,
    field_paths: tuple[str, ...] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            details={"field_paths": field_paths} if field_paths else {},
            retryable=code == "PROVIDER_UNAVAILABLE",
            correlation_id=uuid4(),
        )
    )
    response_status = status or ERROR_HTTP_STATUS[code]
    if response_status >= 500:
        logger.error(
            "API failure code=%s status=%s correlation_id=%s",
            code,
            response_status,
            envelope.error.correlation_id,
        )
    return JSONResponse(
        envelope.model_dump(mode="json"),
        status_code=response_status,
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        paths = tuple(dict.fromkeys(".".join(map(str, item["loc"])) for item in error.errors()))
        return error_response(
            "VALIDATION_ERROR", "Request does not match the contract.", field_paths=paths
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == 404:
            return error_response("NOT_FOUND", "Resource not found.")
        if error.status_code == 405:
            return error_response(
                "METHOD_NOT_ALLOWED", "Method not allowed.", headers=error.headers
            )
        if error.status_code == 429:
            return error_response(
                "LIMIT_EXCEEDED", "Request limit exceeded.", 429, headers=error.headers
            )
        if 400 <= error.status_code < 500:
            client_codes: dict[int, ErrorCode] = {
                400: "VALIDATION_ERROR",
                409: "STATE_CONFLICT",
                422: "VALIDATION_ERROR",
            }
            code = client_codes.get(error.status_code, "HTTP_ERROR")
            return error_response(
                code, "Request could not be completed.", error.status_code, headers=error.headers
            )
        code = "PROVIDER_UNAVAILABLE" if error.status_code == 503 else "INTERNAL_ERROR"
        return error_response(
            code, "Request could not be completed.", error.status_code, headers=error.headers
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception) -> JSONResponse:
        return error_response("INTERNAL_ERROR", "An internal error occurred.")
