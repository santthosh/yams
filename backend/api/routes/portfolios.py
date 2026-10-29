"""Paper account creation and read-only posted state/history transport."""

import logging
from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import ErrorEnvelope, Page
from backend.domain.portfolio import (
    PaperPortfolioV1,
    PortfolioCreateRequest,
    PortfolioTransactionPageV1,
)
from backend.domain.types import SourceMode
from backend.persistence.database import Settings
from backend.portfolio.accounts import (
    AccountError,
    PriceCache,
    account_record,
    account_transactions,
    create_account,
    list_accounts,
    render_account,
)
from backend.portfolio.ledger import ReconciliationFailure

logger = logging.getLogger(__name__)


def portfolios_router(engine: Engine | None, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/portfolios", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)
    }

    def stored[T](operation: Callable[[Engine], T]) -> T | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Paper account storage is not ready.")
        try:
            return operation(engine)
        except AccountError as error:
            return error_response(error.code, error.message)
        except LookupError:
            return error_response("NOT_FOUND", "Paper account was not found.")
        except ReconciliationFailure:
            return error_response("STATE_CONFLICT", "Paper account requires reconciliation.")
        except Exception as error:
            logger.warning(
                "Paper account operation unavailable error_type=%s", type(error).__name__
            )
            return error_response("NOT_READY", "Paper account storage or integrity is unavailable.")

    @router.post("", status_code=201, response_model=PaperPortfolioV1, responses=errors)
    def create(
        request: PortfolioCreateRequest,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> PaperPortfolioV1 | JSONResponse:
        return stored(
            lambda db: render_account(
                db,
                settings.artifact_root,
                create_account(db, settings.artifact_root, request, idempotency_key),
            )
        )

    @router.get("", response_model=Page[PaperPortfolioV1], responses=errors)
    def accounts(
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: UUID | None = None,
        mode: SourceMode | None = None,
    ) -> Page[PaperPortfolioV1] | JSONResponse:
        def read(db: Engine) -> Page[PaperPortfolioV1]:
            records, next_cursor = list_accounts(db, limit=limit, cursor=cursor, mode=mode)
            prices: PriceCache = {}
            return Page[PaperPortfolioV1](
                items=tuple(
                    render_account(db, settings.artifact_root, record, price_cache=prices)
                    for record in records
                ),
                next_cursor=next_cursor,
            )

        return stored(read)

    @router.get("/{portfolio_id}", response_model=PaperPortfolioV1, responses=errors)
    def detail(portfolio_id: UUID) -> PaperPortfolioV1 | JSONResponse:
        return stored(
            lambda db: render_account(db, settings.artifact_root, account_record(db, portfolio_id))
        )

    @router.get(
        "/{portfolio_id}/transactions", response_model=PortfolioTransactionPageV1, responses=errors
    )
    def transactions(
        portfolio_id: UUID,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: UUID | None = None,
    ) -> PortfolioTransactionPageV1 | JSONResponse:
        return stored(lambda db: account_transactions(db, portfolio_id, limit=limit, cursor=cursor))

    return router
