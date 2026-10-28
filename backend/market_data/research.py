"""Complete conditional acquisition into an immutable inspection snapshot."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from backend.domain.types import canonical_json
from backend.jobs.registry import validate_workload
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Membership, Universe
from backend.market_data.providers.directory_transport import DirectoryDownloader, acquire_directory
from backend.market_data.providers.normalization import normalize_observation
from backend.market_data.providers.yahoo import (
    HistoryClient,
    ProviderFailure,
    YahooResearchAdapter,
    YFinanceClient,
)
from backend.market_data.research_config import ResearchConfig
from backend.market_data.research_snapshot import build_research_snapshot
from backend.market_data.tiingo_config import TiingoResearchConfigV1
from backend.market_data.tiingo_research import acquire_tiingo_snapshot

# Source-documented exchange identities; unsupported codes require explicit evidence.
VENUES = {"NASDAQ": "XNAS", "N": "XNYS", "A": "XASE", "P": "ARCX"}


def acquire_research_snapshot(
    config: ResearchConfig | TiingoResearchConfigV1,
    *,
    downloader: DirectoryDownloader | None = None,
    client: HistoryClient | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> PinnedSnapshot:
    if isinstance(config, TiingoResearchConfigV1):
        return acquire_tiingo_snapshot(config, cancelled=cancelled)
    permission = config.permission()
    permission.require_verified()
    directory = acquire_directory(config.directory_kind, permission, downloader)
    selected = [
        row for row in directory.snapshot.listings if row.exchange_code in config.exchange_codes
    ]
    if any(row.exchange_code not in VENUES for row in selected):
        raise ProviderFailure("DIRECTORY_VENUE_UNSUPPORTED")
    selected_keys = {(VENUES[row.exchange_code], row.symbol) for row in selected}
    configured_keys = {(asset.venue, asset.symbol) for asset in config.assets}
    if not selected_keys or selected_keys != configured_keys:
        raise ProviderFailure("DIRECTORY_IDENTITY_COVERAGE_MISMATCH")
    sessions = [
        row
        for row in config.calendar.sessions
        if config.first_session <= row.session_date <= config.last_session
    ]
    validate_workload(assets=len(selected), sessions=len(sessions))
    if len({asset.provider_id for asset in config.assets}) != len(config.assets):
        raise ProviderFailure("PROVIDER_ALIAS_AMBIGUOUS")
    # All inputs must finish before building any snapshot; no partial refresh escapes.
    acquired = YahooResearchAdapter(client or YFinanceClient(permission), permission).acquire(
        [asset.provider_id for asset in config.assets],
        start=config.first_session.isoformat(),
        end=(config.last_session + timedelta(days=1)).isoformat(),
        cancelled=cancelled,
    )
    observed = datetime.now(UTC)
    by_provider = {asset.provider_id: asset.asset_id for asset in config.assets}
    observations = tuple(
        normalize_observation(by_provider[item.symbol], row, observed, config.calendar)
        for item in acquired
        for row in item.rows
    )
    universe = Universe.model_validate(
        {
            "schema_version": 1,
            "label": "Current provider directory selection",
            "rule": config.selection_rule_reference,
            "source_sha256": directory.snapshot.source_sha256,
            "memberships": [
                Membership.model_validate(
                    {
                        "asset_id": asset.asset_id,
                        "effective_from": config.first_session,
                        "effective_to_exclusive": None,
                        "available_at": directory.observed_at,
                        "ingested_at": directory.observed_at,
                        "timing_status": "current_only",
                    }
                ).model_dump(mode="json")
                for asset in config.assets
            ],
        }
    )
    payload_hash = hashlib.sha256(
        canonical_json([{"symbol": item.symbol, "rows": list(item.rows)} for item in acquired])
    ).hexdigest()
    return build_research_snapshot(
        assets=config.assets,
        context=config.context,
        calendar=config.calendar,
        universe=universe,
        observations=observations,
        permission=permission,
        source_payload_hash=payload_hash,
        first_session=config.first_session,
        last_session=config.last_session,
        request_hash=hashlib.sha256(canonical_json(config.model_dump(mode="json"))).hexdigest(),
    )
