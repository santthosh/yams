"""Read-only, parameterized analytical views over one verified snapshot."""

import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

import duckdb
from pydantic import TypeAdapter

from backend.domain.market import AssetV1, MarketBarV1
from backend.domain.types import SessionDate, SourceMode, UTCTimestamp
from backend.market_data.files import PinnedSnapshot, SnapshotIntegrityError
from backend.market_data.models import (
    Alias,
    AssetContext,
    Calendar,
    CorporateAction,
    Fundamental,
    Sector,
    Universe,
)
from backend.market_data.quality import extreme_adjusted_move


@dataclass(frozen=True)
class Diagnostic:
    reason: str
    asset_id: str | None = None
    session_date: date | None = None
    count: int = 1


@dataclass(frozen=True)
class AsOfAsset:
    asset_id: str
    currency: Literal["USD"]
    instrument: Literal["ordinary_equity", "etf"]
    alias: Alias | None
    sector: Sector | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MarketView:
    snapshot_id: UUID
    manifest_hash: str
    mode: SourceMode
    cutoff: datetime
    session_date: date
    assets: tuple[AsOfAsset, ...]
    bars: tuple[MarketBarV1, ...]
    actions: tuple[CorporateAction, ...]
    fundamentals: tuple[Fundamental, ...]
    diagnostics: tuple[Diagnostic, ...]
    warnings: tuple[str, ...]


class MarketRepository:
    """Owns a private copy of hash-verified Parquet, with no user SQL interface.

    Close explicitly or use a context manager. External/extension access is disabled
    except the enumerated private Parquet copy. Queries never rediscover a path or
    latest snapshot. Prices remain exact strings in the validated row payload.
    """

    def __init__(self, snapshot: PinnedSnapshot):
        self.snapshot = snapshot
        self._temporary = tempfile.TemporaryDirectory(prefix="yams-market-reader-")
        self._connection: duckdb.DuckDBPyConnection | None = None
        try:
            manifest = snapshot.manifest

            def artifact(role: str, version: int, format_name: str = "json") -> bytes:
                matches = [
                    item
                    for item in manifest.artifacts
                    if item.role == role
                    and item.schema_version == version
                    and item.format == format_name
                ]
                if len(matches) != 1:
                    raise SnapshotIntegrityError("Expected one artifact for the supported schema")
                return snapshot.artifacts[matches[0].path]

            self._assets = TypeAdapter(tuple[AssetV1, ...]).validate_json(artifact("assets", 1))
            self._context = AssetContext.model_validate_json(artifact("assets", 2))
            self.calendar = Calendar.model_validate_json(artifact("calendar", 1))
            self._universe = Universe.model_validate_json(artifact("universe", 1))
            self._actions = TypeAdapter(tuple[CorporateAction, ...]).validate_json(
                artifact("actions", 1)
            )
            ids = [asset.asset_id for asset in self._assets]
            if len(ids) != len(set(ids)) or set(ids) != set(manifest.coverage.asset_ids):
                raise SnapshotIntegrityError("Asset inventory does not match manifest coverage")
            if self.calendar.id != manifest.calendar.id:
                raise SnapshotIntegrityError("Calendar identity mismatch")
            for row in (
                *self._context.aliases,
                *self._context.sectors,
                *self._context.fundamentals,
                *self._universe.memberships,
                *self._actions,
            ):
                if row.asset_id not in ids:
                    raise SnapshotIntegrityError("Unknown asset cross-reference")
            if len({row.event_id for row in self._actions}) != len(self._actions):
                raise SnapshotIntegrityError("Duplicate corporate action event identity")
            self._path = Path(self._temporary.name) / "bars.parquet"
            self._path.write_bytes(artifact("bars", 1, "parquet"))
            self._path.chmod(0o400)
            self._connection = duckdb.connect(
                config={
                    "threads": 1,
                    "memory_limit": "256MB",
                    "max_temp_directory_size": "0B",
                    "autoinstall_known_extensions": False,
                    "autoload_known_extensions": False,
                    "allow_community_extensions": False,
                }
            )
            self._connection.execute("SET allowed_paths = ?", [[str(self._path)]])
            self._connection.execute("SET enable_external_access = false")
            self._connection.execute("SET lock_configuration = true")
            raw = self._connection.execute(
                "SELECT asset_id, session_date, available_at, ingested_at, payload "
                "FROM read_parquet(?)",
                [str(self._path)],
            ).fetchall()
            bar_artifact = next(
                item
                for item in manifest.artifacts
                if item.role == "bars" and item.format == "parquet"
            )
            if len(raw) != bar_artifact.row_count:
                raise SnapshotIntegrityError("Parquet row count mismatch")
            self._rows: dict[str, MarketBarV1] = {}
            sessions = {row.session_date: row for row in self.calendar.sessions}
            for asset_id, session_date, available_at, ingested_at, payload in raw:
                bar = MarketBarV1.model_validate_json(payload)
                if (asset_id, session_date, available_at, ingested_at) != (
                    bar.asset_id,
                    bar.session_date,
                    bar.available_at,
                    bar.ingested_at,
                ):
                    raise SnapshotIntegrityError(
                        "Parquet projection differs from validated payload"
                    )
                if bar.asset_id not in ids or bar.session_date not in sessions:
                    raise SnapshotIntegrityError("Bar references unknown asset or session")
                if bar.available_at < sessions[bar.session_date].close_at:
                    raise SnapshotIntegrityError("Daily closing bar cannot precede session close")
                if (
                    bar.provider != manifest.source.provider
                    or bar.price_basis != manifest.price_basis.ohlc
                    or bar.volume_basis != manifest.price_basis.volume
                ):
                    raise SnapshotIntegrityError("Bar provenance/basis differs from manifest")
                if manifest.mode == "synthetic_fixture" and (
                    bar.availability_basis != "synthetic"
                    or "SYNTHETIC_DATA_ONLY" not in bar.quality_flags
                ):
                    raise SnapshotIntegrityError("Fixture row lacks synthetic provenance")
                if (
                    manifest.mode == "research_market_data"
                    and bar.availability_basis == "synthetic"
                ):
                    raise SnapshotIntegrityError("Research snapshot contains synthetic evidence")
                self._rows[payload] = bar
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._temporary.cleanup()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fixture_observation_at(self, session_date: date) -> datetime:
        """Explicit synthetic clock after that session's pinned bar observations.

        Fixtures may be dated beyond wall time. Derive their read-only display
        clock from actual row evidence rather than inventing a publication lag.
        Real-market consumers must always supply their actual observation time.
        """
        if self.snapshot.manifest.mode != "synthetic_fixture":
            raise ValueError("Synthetic observation clock requires fixture mode")
        session_date = TypeAdapter(SessionDate).validate_python(session_date)
        scheduled = next(
            (s for s in self.calendar.sessions if s.session_date == session_date), None
        )
        if scheduled is None:
            raise ValueError("Session is outside the pinned calendar")
        observations = [scheduled.close_at]
        for bar in self._rows.values():
            if bar.session_date == session_date:
                observations.extend((bar.available_at, bar.ingested_at))
        return max(observations)

    def as_of(
        self,
        cutoff: datetime,
        session_date: date,
        *,
        start_session: date | None = None,
        live: bool = False,
    ) -> MarketView:
        return self._view(cutoff, session_date, start_session=start_session, live=live)

    def accounting_as_of(self, cutoff: datetime, session_date: date) -> MarketView:
        """Validated bars/actions remain usable for holdings after universe exit.

        Assets still describe the eligible decision universe. Accounting consumers
        use bars/actions only; this view must never enlarge strategy eligibility.
        """
        return self._view(cutoff, session_date, include_inactive=True)

    def _sector_at(
        self, asset_id: str, cutoff: datetime, session_date: date, live: bool
    ) -> Sector | None:
        rows = [
            row
            for row in self._context.sectors
            if row.asset_id == asset_id and row.covers(session_date) and row.visible(cutoff, live)
        ]
        return (
            max(rows, key=lambda row: row.available_at)
            if len({row.sector for row in rows}) == 1
            else None
        )

    def accounting_sectors(
        self, asset_ids: tuple[str, ...], cutoff: datetime, session_date: date
    ) -> dict[str, str]:
        """As-of risk classifications for held assets, including universe exits.

        This lookup does not change eligibility or the account's posted projection.
        Ambiguous/missing classifications retain the shared Unknown risk bucket.
        """
        cutoff = TypeAdapter(UTCTimestamp).validate_python(cutoff)
        session_date = TypeAdapter(SessionDate).validate_python(session_date)
        live = self.snapshot.manifest.mode != "synthetic_fixture"
        return {
            identity: row.sector
            if (row := self._sector_at(identity, cutoff, session_date, live))
            else "Unknown"
            for identity in asset_ids
        }

    def _view(
        self,
        cutoff: datetime,
        session_date: date,
        *,
        start_session: date | None = None,
        live: bool = False,
        include_inactive: bool = False,
    ) -> MarketView:
        cutoff = TypeAdapter(UTCTimestamp).validate_python(cutoff)
        session_date = TypeAdapter(SessionDate).validate_python(session_date)
        if self._connection is None:
            raise RuntimeError("Repository is closed")
        if session_date not in {
            row.session_date for row in self.calendar.sessions if row.close_at <= cutoff
        }:
            raise ValueError("As-of session must be a completed pinned calendar session")
        start = TypeAdapter(SessionDate).validate_python(
            start_session or self.calendar.sessions[0].session_date
        )
        if start > session_date:
            raise ValueError("Start session must not follow as-of session")
        diagnostics: list[Diagnostic] = []
        memberships = [
            row
            for row in self._universe.memberships
            if row.covers(session_date) and row.visible(cutoff, live)
        ]
        active = {row.asset_id for row in memberships if row.timing_status != "unknown"}
        for membership in memberships:
            if membership.timing_status == "unknown":
                diagnostics.append(Diagnostic("UNKNOWN_MEMBERSHIP_TIMING", membership.asset_id))
        aliases = [
            row
            for row in self._context.aliases
            if row.covers(session_date) and row.visible(cutoff, live)
        ]
        collisions: dict[tuple[str, str], set[str]] = defaultdict(set)
        for alias_row in aliases:
            collisions[alias_row.venue, alias_row.symbol].add(alias_row.asset_id)
        assets = []
        for asset in sorted(self._assets, key=lambda row: row.asset_id):
            if asset.asset_id not in active:
                continue
            reasons = []
            matches = [row for row in aliases if row.asset_id == asset.asset_id]
            keys = {(row.venue, row.symbol) for row in matches}
            alias = max(matches, key=lambda row: row.available_at) if matches else None
            if len(keys) != 1 or (
                alias is not None and len(collisions[alias.venue, alias.symbol]) != 1
            ):
                alias = None
                reasons.append("AMBIGUOUS_OR_MISSING_ALIAS")
            sector = self._sector_at(asset.asset_id, cutoff, session_date, live)
            if sector is None:
                reasons.append("AMBIGUOUS_OR_MISSING_SECTOR")
            assets.append(
                AsOfAsset(
                    asset.asset_id, asset.currency, asset.instrument, alias, sector, tuple(reasons)
                )
            )
            diagnostics.extend(Diagnostic(reason, asset.asset_id) for reason in reasons)
        rows = self._connection.execute(
            "SELECT payload FROM read_parquet(?) WHERE available_at <= ? "
            "AND (? = false OR ingested_at <= ?) AND session_date >= ? "
            "AND session_date <= ? ORDER BY asset_id, session_date, available_at, payload",
            [
                str(self._path),
                cutoff,
                live,
                cutoff,
                self.calendar.sessions[0].session_date,
                session_date,
            ],
        ).fetchall()
        grouped: dict[tuple[str, date], list[MarketBarV1]] = defaultdict(list)
        for (payload,) in rows:
            bar = self._rows[payload]
            if include_inactive or bar.asset_id in active:
                grouped[bar.asset_id, bar.session_date].append(bar)
        bars = []
        for (asset_id, day), candidates in sorted(grouped.items()):
            distinct = {row.model_dump_json() for row in candidates}
            if len(distinct) != 1:
                diagnostics.append(Diagnostic("CONFLICTING_BAR", asset_id, day, len(candidates)))
                continue
            if len(candidates) > 1:
                diagnostics.append(Diagnostic("DUPLICATE_BAR", asset_id, day, len(candidates) - 1))
            bars.append(candidates[0])
        # Compare original valid observations, never bridge missing/conflicting sessions.
        # Include the previous session even when the caller requests a narrow window.
        observed = {(bar.asset_id, bar.session_date): bar for bar in bars}
        previous_session = {
            current.session_date: previous.session_date
            for previous, current in zip(
                self.calendar.sessions[:-1], self.calendar.sessions[1:], strict=True
            )
        }
        retained = []
        for bar in bars:
            prior_day = previous_session.get(bar.session_date)
            previous = observed.get((bar.asset_id, prior_day)) if prior_day else None
            if previous is not None and extreme_adjusted_move(
                previous.adjusted_close, bar.adjusted_close
            ):
                diagnostics.append(
                    Diagnostic("EXTREME_ADJUSTED_MOVE", bar.asset_id, bar.session_date)
                )
            else:
                retained.append(bar)
        bars = [bar for bar in retained if bar.session_date >= start]
        for calendar_session in self.calendar.sessions:
            if (
                start <= calendar_session.session_date <= session_date
                and calendar_session.close_at <= cutoff
            ):
                for asset_id in sorted(active):
                    if (asset_id, calendar_session.session_date) not in grouped and any(
                        row.asset_id == asset_id and row.covers(calendar_session.session_date)
                        for row in memberships
                    ):
                        diagnostics.append(
                            Diagnostic("MISSING_SESSION", asset_id, calendar_session.session_date)
                        )
        fundamentals = tuple(
            row
            for row in self._context.fundamentals
            if row.asset_id in active
            and row.period_end <= session_date
            and row.visible(cutoff, live)
        )
        actions = tuple(
            row
            for row in self._actions
            if (include_inactive or row.asset_id in active) and row.visible(cutoff, live)
        )
        for action in actions:
            if action.kind == "dividend" and action.payable_session is None:
                diagnostics.append(
                    Diagnostic(
                        "UNRESOLVED_DIVIDEND_PAYABLE", action.asset_id, action.effective_session
                    )
                )
        manifest = self.snapshot.manifest
        if manifest.quality == "blocked":
            diagnostics.append(Diagnostic("SNAPSHOT_BLOCKED"))
        return MarketView(
            manifest.snapshot_id(),
            manifest.manifest_hash(),
            manifest.mode,
            cutoff,
            session_date,
            tuple(assets),
            tuple(bars),
            actions,
            fundamentals,
            tuple(diagnostics),
            manifest.warnings,
        )
