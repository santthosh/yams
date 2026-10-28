"""Explicit source-mode snapshot discovery and durable refresh admission."""

import base64
import binascii
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from backend.api.errors import error_response
from backend.api.routing import ContractRoute
from backend.domain.common import Cursor, ErrorEnvelope, JobV1, Page
from backend.domain.data import AssetPageV1, DataHealthV1, SnapshotV1
from backend.domain.types import SourceMode
from backend.jobs.queue import IdempotencyConflict, Queue
from backend.jobs.registry import RefreshPayload
from backend.market_data.catalog import discover_assets, snapshot_envelope
from backend.persistence.database import Settings
from backend.persistence.models.job import Job
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot

logger = logging.getLogger(__name__)


def data_router(engine: Engine | None, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/data", route_class=ContractRoute)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (404, 409, 422, 503)
    }

    @router.get("/snapshots", response_model=Page[SnapshotV1], responses=errors)
    def snapshots(
        mode: SourceMode,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: UUID | None = None,
    ) -> Page[SnapshotV1] | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Snapshot storage is not ready.")
        try:
            with Session(engine) as session:
                statement = select(DatasetSnapshot).where(DatasetSnapshot.source_mode == mode)
                if cursor is not None:
                    previous = session.get(DatasetSnapshot, cursor)
                    if previous is None or previous.source_mode != mode:
                        raise HTTPException(422)
                    statement = statement.where(
                        or_(
                            DatasetSnapshot.registered_at < previous.registered_at,
                            (DatasetSnapshot.registered_at == previous.registered_at)
                            & (DatasetSnapshot.id < previous.id),
                        )
                    )
                rows = session.scalars(
                    statement.order_by(
                        DatasetSnapshot.registered_at.desc(), DatasetSnapshot.id.desc()
                    ).limit(limit + 1)
                ).all()
                return Page[SnapshotV1](
                    items=tuple(
                        snapshot_envelope(row, settings.artifact_root) for row in rows[:limit]
                    ),
                    next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
                )
        except HTTPException:
            raise
        except Exception as error:
            logger.warning("Snapshot catalog unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Snapshot storage or integrity is unavailable.")

    @router.post("/refresh", status_code=202, response_model=JobV1, responses=errors)
    def refresh(
        request: RefreshPayload,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> JobV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Refresh storage is not ready.")
        try:
            queue = Queue(engine)
            identity = queue.enqueue(
                "refresh_market_data", request.model_dump(mode="json"), idempotency_key
            )
            job = queue.get(identity)
            assert job is not None
            return job
        except IdempotencyConflict:
            return error_response("IDEMPOTENCY_CONFLICT", "Refresh key has different inputs.")
        except Exception as error:
            logger.warning("Refresh admission unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Refresh storage is not ready.")

    @router.get("/assets", response_model=AssetPageV1, responses=errors)
    def assets(
        mode: SourceMode,
        snapshot_id: UUID,
        query: Annotated[str, Query(max_length=120)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: Cursor | None = None,
    ) -> AssetPageV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Asset storage is not ready.")
        query = query.strip().casefold()
        scope = f"{snapshot_id}\n{mode}\n{query}\n"
        after = ""
        if cursor is not None:
            try:
                decoded = base64.b64decode(
                    cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
                ).decode()
                if not decoded.startswith(scope):
                    raise ValueError("Cursor scope mismatch")
                after = decoded[len(scope) :]
                if not after:
                    raise ValueError("Empty cursor")
            except (ValueError, UnicodeError, binascii.Error):
                return error_response(
                    "VALIDATION_ERROR", "Asset cursor is invalid for this search."
                )
        try:
            inventory = discover_assets(engine, settings.artifact_root, snapshot_id, mode)
            found = [
                asset
                for asset in inventory
                if asset.asset_id > after
                and (
                    not query
                    or query in asset.symbol.casefold()
                    or query in asset.asset_id.casefold()
                )
            ]
            next_cursor = None
            if len(found) > limit:
                next_cursor = (
                    base64.urlsafe_b64encode((scope + found[limit - 1].asset_id).encode())
                    .decode()
                    .rstrip("=")
                )
            return AssetPageV1(
                snapshot_id=snapshot_id,
                mode=mode,
                items=tuple(found[:limit]),
                next_cursor=next_cursor,
            )
        except LookupError:
            return error_response("NOT_FOUND", "Snapshot not found in the selected source mode.")
        except Exception as error:
            logger.warning("Asset inventory unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Asset storage or integrity is unavailable.")

    @router.get("/health", response_model=DataHealthV1, responses=errors)
    def health(mode: SourceMode) -> DataHealthV1 | JSONResponse:
        if engine is None:
            return error_response("NOT_READY", "Data storage is not ready.")
        try:
            with Session(engine) as session:
                pointer = session.get(CurrentSnapshot, mode)
                current = None
                if pointer is not None:
                    row = session.get(DatasetSnapshot, pointer.snapshot_id)
                    if row is None or row.source_mode != mode:
                        raise ValueError("Current snapshot identity mismatch")
                    current = snapshot_envelope(row, settings.artifact_root)
                    if current.quality == "blocked":
                        raise ValueError("Blocked snapshot cannot be current")
                latest = session.scalar(
                    select(Job)
                    .where(Job.kind == "refresh_market_data", Job.source_mode == mode)
                    .order_by(Job.created_at.desc(), Job.id.desc())
                    .limit(1)
                )
                job = Queue.view(latest) if latest is not None else None
                pending = job is not None and job.status in {
                    "queued",
                    "running",
                    "cancel_requested",
                }
                failed = job is not None and job.status == "failed"
                return DataHealthV1(
                    mode=mode,
                    checked_at=datetime.now(UTC),
                    status="refreshing"
                    if pending
                    else "failed"
                    if failed
                    else "ready"
                    if current
                    else "empty",
                    current_snapshot=current,
                    latest_job=job,
                    warnings=("LAST_REFRESH_FAILED",) if failed else (),
                    freshness="refresh_failed"
                    if failed
                    else "synthetic"
                    if mode == "synthetic_fixture"
                    else "unknown",
                )
        except Exception as error:
            logger.warning("Data health unavailable error_type=%s", type(error).__name__)
            return error_response("NOT_READY", "Data storage or integrity is unavailable.")

    return router
