"""Build an inspection-only research snapshot with explicit unsupported capabilities."""

import hashlib
from datetime import date
from types import MappingProxyType

from pydantic import TypeAdapter

from backend.domain.market import AssetV1, SnapshotManifestV1
from backend.domain.types import Hash256, canonical_json
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import AssetContext, Calendar, Universe
from backend.market_data.parquet import encode_bars
from backend.market_data.providers.normalization import NormalizedObservation
from backend.market_data.providers.yahoo import ProviderFailure, ResearchPermission
from backend.market_data.repository import MarketRepository


def build_research_snapshot(
    *,
    assets: tuple[AssetV1, ...],
    context: AssetContext,
    calendar: Calendar,
    universe: Universe,
    observations: tuple[NormalizedObservation, ...],
    permission: ResearchPermission,
    source_payload_hash: str,
    first_session: date,
    last_session: date,
    request_hash: str | None = None,
) -> PinnedSnapshot:
    permission.require_verified()
    source_payload_hash = TypeAdapter(Hash256).validate_python(source_payload_hash)
    if request_hash is not None:
        TypeAdapter(Hash256).validate_python(request_hash)
    TypeAdapter(Hash256).validate_python(universe.source_sha256)
    if not observations or not assets:
        raise ProviderFailure("PROVIDER_INCOMPLETE_COVERAGE")
    if any(row.bar.availability_basis != "observed" for row in observations):
        raise ProviderFailure("RESEARCH_AVAILABILITY_UNSUPPORTED")
    bars = tuple(row.bar for row in observations)
    requested = {
        session.session_date
        for session in calendar.sessions
        if first_session <= session.session_date <= last_session
    }
    expected = {(asset.asset_id, day) for asset in assets for day in requested}
    pairs = [(bar.asset_id, bar.session_date) for bar in bars]
    if not requested or len(pairs) != len(set(pairs)) or set(pairs) != expected:
        raise ProviderFailure("PROVIDER_INCOMPLETE_COVERAGE")
    if any(member.timing_status != "current_only" for member in universe.memberships):
        raise ProviderFailure("RESEARCH_MEMBERSHIP_UNSUPPORTED")
    actions = tuple(action for row in observations for action in row.actions)
    provenance = {
        "request_hash": request_hash,
        "schema_version": 1,
        "provider": "yahoo_yfinance",
        "adapter_version": permission.adapter_version,
        "rights_reference": permission.rights_reference,
        "directory_reference": permission.directory_reference,
        "directory_sha256": universe.source_sha256,
        "source_payload_sha256": source_payload_hash,
        "raw_execution_prices": False,
        "complete_action_accounting": False,
        "historical_membership": False,
        "historical_publication_times": False,
        "parquet_writer": "duckdb_2.0.0_zstd_rowgroup2048_threads1",
    }
    content = {
        "assets.json": canonical_json([asset.model_dump(mode="json") for asset in assets]),
        "asset_context.json": canonical_json(context.model_dump(mode="json")),
        "calendar.json": canonical_json(calendar.model_dump(mode="json")),
        "universe.json": canonical_json(universe.model_dump(mode="json")),
        "actions.json": canonical_json([action.model_dump(mode="json") for action in actions]),
        "provenance.json": canonical_json(provenance),
        "bars.parquet": encode_bars(bars),
    }
    roles = {
        "assets.json": ("assets", 1, len(assets)),
        "asset_context.json": ("assets", 2, len(context.aliases) + len(context.sectors)),
        "calendar.json": ("calendar", 1, len(calendar.sessions)),
        "universe.json": ("universe", 1, len(universe.memberships)),
        "actions.json": ("actions", 1, len(actions)),
        "provenance.json": ("provenance", 1, None),
        "bars.parquet": ("bars", 1, len(bars)),
    }

    def digest(name: str) -> str:
        return hashlib.sha256(content[name]).hexdigest()

    days = sorted({bar.session_date for bar in bars})
    manifest = SnapshotManifestV1.model_validate(
        {
            "schema_version": 1,
            "mode": "research_market_data",
            "source": {
                "provider": "yahoo_yfinance",
                "adapter_version": permission.adapter_version,
                "normalization_version": "1",
                "rights_reference": permission.rights_reference,
                "rights_status": "verified_local_use",
                "capabilities_sha256": digest("provenance.json"),
            },
            "price_basis": {
                "ohlc": "provider_unverified",
                "adjusted_close": "provider_observed",
                "volume": "provider_unverified",
                "currency": "USD",
                "corporate_action_policy": "unverified_no_accounting",
            },
            "calendar": {
                "id": calendar.id,
                "timezone": calendar.timezone,
                "version": digest("calendar.json"),
                "artifact_path": "calendar.json",
            },
            "coverage": {
                "asset_ids": sorted(asset.asset_id for asset in assets),
                "first_session": days[0],
                "last_session": days[-1],
                "latest_completed_session": days[-1],
                "missing_sessions": [],
                "membership_basis": "current_only",
            },
            "quality": "blocked",
            "warnings": sorted(
                [
                    "SURVIVORSHIP_BIAS_RISK",
                    "RAW_PRICE_BASIS_UNVERIFIED",
                    "ACTION_COVERAGE_UNVERIFIED",
                ]
            ),
            "artifacts": [
                {
                    "path": name,
                    "role": roles[name][0],
                    "schema_version": roles[name][1],
                    "row_count": roles[name][2],
                    "format": "parquet" if name.endswith(".parquet") else "json",
                    "sha256": digest(name),
                    "size_bytes": len(data),
                }
                for name, data in sorted(content.items())
            ],
        }
    )
    snapshot = PinnedSnapshot(manifest, MappingProxyType(content))
    with MarketRepository(snapshot):
        pass
    return snapshot
