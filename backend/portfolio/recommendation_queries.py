"""Bounded immutable reads; no recomputation or economic/disposition writes."""

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from backend.domain.common import JobV1, PageRequest
from backend.domain.forecast import ForecastV1
from backend.domain.recommendation import RecommendationV1
from backend.domain.recommendation_api import (
    RecommendationDetailV1,
    RecommendationPageV1,
    RecommendationRequest,
    RecommendationSummaryV1,
)
from backend.forecasting.service import read_forecast
from backend.jobs.queue import Queue
from backend.market_data.catalog import verified_snapshot
from backend.persistence.models.job import Job
from backend.persistence.models.ledger import RecommendationReference
from backend.persistence.models.portfolio import PaperPortfolio
from backend.persistence.models.recommendation import RecommendationPublication, RecommendationRun
from backend.persistence.models.snapshot import CurrentSnapshot, DatasetSnapshot
from backend.portfolio.ledger import digest
from backend.portfolio.recommendation_contracts import RecommendationPayload, RecommendationPrepared


class RecommendationQueryError(ValueError):
    pass


class RecommendationPending(ValueError):
    def __init__(self, job: JobV1):
        self.job = job
        super().__init__("Resource has no completed publication")


def history(engine: Engine, owner: UUID, page: PageRequest) -> RecommendationPageV1:
    scope = "recommendation-history-v1:" + str(owner)
    with Session(engine) as session:
        if session.get(PaperPortfolio, owner) is None:
            raise LookupError("Portfolio does not exist")
        # Project only summary inputs, not all frozen holdings or large job payloads.
        statement = (
            select(
                RecommendationRun.id,
                RecommendationRun.job_id,
                RecommendationRun.created_at,
                RecommendationRun.payload["inputs"].label("inputs"),
                RecommendationRun.payload["portfolio_revision"].label("revision"),
                RecommendationRun.payload["strategy_version_id"].label("version"),
                RecommendationRun.payload["snapshot_id"].label("snapshot"),
                RecommendationRun.payload["source_mode"].label("mode"),
                Job.status,
                Job.error,
                RecommendationReference.disposition,
            )
            .join(Job, Job.id == RecommendationRun.job_id)
            .outerjoin(RecommendationReference, RecommendationReference.id == RecommendationRun.id)
            .where(RecommendationRun.portfolio_id == owner, Job.kind == "evaluate_portfolio")
        )
        if page.cursor:
            try:
                value = json.loads(
                    base64.b64decode(
                        page.cursor + "=" * (-len(page.cursor) % 4), altchars=b"-_", validate=True
                    )
                )
                if not isinstance(value, list) or len(value) != 3 or value[0] != scope:
                    raise ValueError
                timestamp, identity = datetime.fromisoformat(value[1]), UUID(value[2])
                if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
                    raise ValueError
            except (ValueError, TypeError, UnicodeError):
                raise RecommendationQueryError("Cursor is invalid for this portfolio") from None
            statement = statement.where(
                or_(
                    RecommendationRun.created_at < timestamp,
                    and_(
                        RecommendationRun.created_at == timestamp, RecommendationRun.id < identity
                    ),
                )
            )
        rows = session.execute(
            statement.order_by(
                RecommendationRun.created_at.desc(), RecommendationRun.id.desc()
            ).limit(page.limit + 1)
        ).all()
        items = []
        for row in rows[: page.limit]:
            request = RecommendationRequest.model_validate(row.inputs)
            items.append(
                RecommendationSummaryV1.model_validate(
                    dict(
                        id=row.id,
                        portfolio_id=owner,
                        job_id=row.job_id,
                        status=row.status,
                        disposition=row.disposition,
                        inputs=request,
                        inputs_canonical_json=request.canonical_bytes().decode(),
                        portfolio_revision=row.revision,
                        strategy_version_id=row.version,
                        snapshot_id=row.snapshot,
                        data_status=row.mode,
                        created_at=row.created_at,
                        error=row.error,
                    )
                )
            )
        cursor = None
        if len(rows) > page.limit:
            last = rows[page.limit - 1]
            cursor = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        [scope, last.created_at.isoformat(), str(last.id)], separators=(",", ":")
                    ).encode()
                )
                .decode()
                .rstrip("=")
            )
        return RecommendationPageV1(items=tuple(items), next_cursor=cursor)


def detail(engine: Engine, root: Path, identity: UUID) -> RecommendationDetailV1 | None:
    with Session(engine) as session:
        run = session.get(RecommendationRun, identity)
        if run is None:
            return None
        job = session.execute(
            select(Job).where(Job.id == run.job_id).with_for_update(read=True)
        ).scalar_one_or_none()
        if job is None or job.kind != "evaluate_portfolio" or job.payload != run.payload:
            raise ValueError("Recommendation job linkage is unavailable")
        payload = RecommendationPayload.model_validate(run.payload)
        view = Queue.view(job)
        publication = session.get(RecommendationPublication, identity)
        if (view.status == "completed") != (publication is not None):
            raise ValueError("Recommendation completion differs from publication")
        if publication is None:
            raise RecommendationPending(view)
        row = session.get(RecommendationReference, identity)
        if (
            row is None
            or view.result is None
            or view.result.resource_id != identity
            or payload.recommendation_id != identity
            or row.portfolio_id != payload.portfolio_id
            or run.portfolio_id != payload.portfolio_id
            or row.strategy_version_id != payload.strategy_version_id
            or row.portfolio_revision != payload.portfolio_revision
            or row.snapshot_id != payload.snapshot_id
            or row.source_mode != payload.source_mode
            or row.decision_cutoff != payload.decision_cutoff_utc
            or row.as_of_session != payload.inputs.as_of_session
            or digest(row.content) != row.content_sha256
        ):
            raise ValueError("Recommendation immutable evidence is unavailable")
        content = dict(row.content)
        original = RecommendationV1.model_validate_json(content["recommendation_canonical_json"])
        prepared = RecommendationPrepared.model_validate_json(content["prepared_canonical_json"])
        if (
            original.id != identity
            or original.portfolio_id != payload.portfolio_id
            or original.portfolio_revision != payload.portfolio_revision
            or original.strategy_version_id != payload.strategy_version_id
            or original.snapshot_id != payload.snapshot_id
            or original.snapshot_sha256 != payload.snapshot_sha256
            or original.engine_version != payload.engine_version
            or original.forecast_id != publication.forecast_id
            or original.forecast_id != payload.forecast_id
            or original.created_at != row.created_at
            or content["request_canonical_json"] != payload.inputs.canonical_bytes().decode()
            or content["clock_mode"] != payload.inputs.clock_mode
        ):
            raise ValueError("Recommendation context differs from original admission")
        source = session.get(DatasetSnapshot, payload.snapshot_id)
        if source is None:
            raise ValueError("Recommendation source is unavailable")
        portfolio = session.get(PaperPortfolio, payload.portfolio_id)
        if portfolio is None:
            raise ValueError("Recommendation account is unavailable")
        current = session.get(CurrentSnapshot, payload.source_mode)
        stale = []
        if (
            portfolio.revision != payload.portfolio_revision
            or portfolio.last_sequence != payload.last_sequence
        ):
            stale.append("PORTFOLIO_REVISION_CHANGED")
        if portfolio.strategy_version_id != payload.strategy_version_id:
            stale.append("STRATEGY_VERSION_CHANGED")
        if portfolio.source_mode != payload.source_mode:
            stale.append("SOURCE_MODE_CHANGED")
        if portfolio.status != "active" or portfolio.reconciliation_failed:
            stale.append("PORTFOLIO_NOT_ACTIVE")
        if current is None or current.snapshot_id != payload.snapshot_id:
            stale.append("SNAPSHOT_SUPERSEDED")
        revision, disposition = portfolio.revision, row.disposition
    # Release the connection before artifact/forecast reads. Concurrent detail
    # requests must not each hold one slot while waiting on the two-slot pool.
    pinned = verified_snapshot(source, root)
    if pinned.manifest.manifest_hash() != payload.snapshot_sha256:
        raise ValueError("Recommendation source fingerprint differs")
    forecast = read_forecast(engine, root, payload.forecast_id)
    if (
        forecast is None
        or forecast.payload.inputs_canonical_json != content["forecast_inputs_canonical_json"]
    ):
        raise ValueError("Recommendation forecast linkage differs")
    return RecommendationDetailV1.model_validate(
        original.model_dump()
        | dict(
            status=disposition,
            job_id=view.id,
            inputs=payload.inputs,
            inputs_canonical_json=payload.inputs.canonical_bytes().decode(),
            clock_mode=payload.inputs.clock_mode,
            computed_at=content["computed_at"],
            config_sha256=payload.config_sha256,
            calendar_sha256=payload.calendar_sha256,
            strategy_config=payload.config,
            strategy_evidence=prepared.evaluation,
            forecast_inputs_canonical_json=content["forecast_inputs_canonical_json"],
            forecast_job=forecast.job,
            forecast=forecast.result,
            is_current=not stale and disposition == "ready",
            current_portfolio_revision=revision,
            stale_reasons=tuple(stale),
        )
    )


def public_forecast(engine: Engine, root: Path, identity: UUID) -> ForecastV1 | None:
    with Session(engine) as session:
        publication = session.scalar(
            select(RecommendationPublication.recommendation_id).where(
                RecommendationPublication.forecast_id == identity
            )
        )
    if publication is None:
        return None
    result = read_forecast(engine, root, identity)
    if result is None:
        raise ValueError("Published recommendation forecast is unavailable")
    if result.result is None:
        raise RecommendationPending(result.job)
    return result.result
