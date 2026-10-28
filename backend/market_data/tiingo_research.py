"""ADR-010 source-derived diagnostics; complete selected cohort or no publication."""

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from backend.domain.market import AssetV1
from backend.domain.types import canonical_json
from backend.market_data.calendar import real_calendar
from backend.market_data.files import PinnedSnapshot
from backend.market_data.models import Alias, AssetContext, Membership, Sector, Universe
from backend.market_data.providers.normalization import NormalizedObservation
from backend.market_data.providers.tiingo import (
    DIRECTORY_URL,
    RULE,
    VENUES,
    HTTPTiingoClient,
    TiingoClient,
    directory_candidates,
    metadata_by_symbol,
)
from backend.market_data.providers.tiingo_normalization import normalize_tiingo
from backend.market_data.providers.yahoo import ProviderFailure, ResearchPermission
from backend.market_data.research_snapshot import build_research_snapshot
from backend.market_data.tiingo_config import TiingoResearchConfigV1

UNSUPPORTED_NAME = re.compile(
    r"\b(preferred|warrants?|units?|depositary|limited partnership|L\.?P\.?)\b", re.I
)


def covers(identity: dict[str, Any], first: date, last: date) -> bool:
    try:
        start, end = identity["startDate"], identity["endDate"]
        return (
            isinstance(start, str)
            and isinstance(end, str)
            and date.fromisoformat(start).isoformat() == start
            and date.fromisoformat(end).isoformat() == end
            and start <= first.isoformat()
            and end >= last.isoformat()
        )
    except (ValueError, KeyError):
        return False


def acquire_tiingo_snapshot(
    config: TiingoResearchConfigV1,
    *,
    client: TiingoClient | None = None,
    now: datetime | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> PinnedSnapshot:
    permission = ResearchPermission(
        config.rights_reference,
        DIRECTORY_URL,
        "tiingo_eod_normalization_1",
        config.rights_verified_local_use,
    )
    permission.require_verified()
    observed = now or datetime.now(UTC)
    try:
        calendar, day = real_calendar(config.history_sessions, config.as_of_session, now=observed)
    except ValueError:
        raise ProviderFailure("RESEARCH_CALENDAR_UNSUPPORTED") from None
    first = calendar.sessions[0].session_date
    transport = client or HTTPTiingoClient()
    if cancelled():
        raise ProviderFailure("REFRESH_CANCELLED")
    directory, directory_at = transport.directory()
    candidates = directory_candidates(directory, first.isoformat(), day.isoformat())
    if not candidates:
        raise ProviderFailure("PROVIDER_INCOMPLETE_COVERAGE")
    metadata, metadata_at = transport.metadata(tuple(row["ticker"] for row in candidates))
    indexed, ambiguous = metadata_by_symbol(metadata, candidates)
    selected: list[tuple[AssetV1, datetime]] = []
    rejections: list[dict[str, str]] = []
    permanent_ids: set[str] = set()
    for row in candidates:
        if cancelled():
            raise ProviderFailure("REFRESH_CANCELLED")
        symbol = row["ticker"]
        meta = indexed.get(symbol)
        reason = ""
        if symbol in ambiguous:
            reason = "AMBIGUOUS_SOURCE_IDENTITY"
        elif meta is None:
            reason = "UNSUPPORTED_PRIMARY_STOCK_METADATA"
        elif meta.get("isActive") is not True or meta.get("isADR") is not False:
            reason = "INACTIVE_OR_ADR_OR_UNKNOWN_TYPE"
        elif (
            not isinstance(meta.get("permaTicker"), str)
            or not meta["permaTicker"]
            or len(meta["permaTicker"]) > 128
        ):
            reason = "MISSING_PERMANENT_IDENTITY"
        elif (
            not isinstance(meta.get("sector"), str)
            or not meta["sector"].strip()
            or len(meta["sector"].strip()) > 120
            or any(ord(character) < 32 for character in meta["sector"])
            or meta["sector"].strip().casefold() in {"n/a", "none", "null"}
        ):
            reason = "MISSING_SECTOR"
        elif (
            not isinstance(meta.get("name"), str)
            or not meta["name"].strip()
            or UNSUPPORTED_NAME.search(meta["name"])
        ):
            reason = "UNSUPPORTED_SECURITY_CLASS"
        if reason:
            rejections.append({"symbol": symbol, "reason": reason})
            continue
        assert meta is not None
        try:
            identity, identity_at = transport.identity(symbol)
        except ProviderFailure as error:
            if error.reason != "PROVIDER_SYMBOL_UNAVAILABLE":
                raise
            rejections.append({"symbol": symbol, "reason": "SOURCE_SYMBOL_UNAVAILABLE"})
            continue
        venue = VENUES[row["exchange"]]
        if (
            not isinstance(identity.get("ticker"), str)
            or identity["ticker"].upper() != symbol
            or not isinstance(identity.get("exchangeCode"), str)
            or VENUES.get(identity["exchangeCode"]) != venue
            or not covers(identity, first, day)
        ):
            rejections.append(
                {"symbol": symbol, "reason": "CURRENT_IDENTITY_OR_COVERAGE_UNSUPPORTED"}
            )
            continue
        if meta["permaTicker"] in permanent_ids:
            raise ProviderFailure("PROVIDER_ALIAS_AMBIGUOUS")
        permanent_ids.add(meta["permaTicker"])
        asset = AssetV1(
            asset_id="TIINGO:" + meta["permaTicker"],
            venue=venue,
            symbol=symbol,
            currency="USD",
            instrument="ordinary_equity",
            sector=meta["sector"].strip(),
            provider="tiingo_eod",
            provider_id=symbol,
        )
        selected.append((asset, max(directory_at, metadata_at, identity_at)))
        if len(selected) == config.max_assets:
            break
    if len(selected) != config.max_assets:
        raise ProviderFailure("PROVIDER_INCOMPLETE_COVERAGE")
    aliases: list[Alias] = []
    sectors: list[Sector] = []
    memberships: list[Membership] = []
    observations: list[NormalizedObservation] = []
    for asset, available in selected:
        if cancelled():
            raise ProviderFailure("REFRESH_CANCELLED")
        temporal: dict[str, Any] = {
            "asset_id": asset.asset_id,
            "effective_from": day,
            "effective_to_exclusive": None,
            "available_at": available,
            "ingested_at": available,
        }
        aliases.append(
            Alias.model_validate(
                temporal
                | {
                    "venue": asset.venue,
                    "symbol": asset.symbol,
                    "provider": asset.provider,
                    "provider_id": asset.provider_id,
                }
            )
        )
        sectors.append(
            Sector.model_validate(
                temporal
                | {
                    "sector": asset.sector,
                    "provider": "tiingo_fundamentals_meta",
                }
            )
        )
        memberships.append(Membership.model_validate(temporal | {"timing_status": "current_only"}))
        rows, acquired_at = transport.history(asset.symbol, first.isoformat(), day.isoformat())
        if not rows:
            raise ProviderFailure("PROVIDER_INCOMPLETE_COVERAGE")
        observations.extend(
            normalize_tiingo(asset.asset_id, row, acquired_at, calendar) for row in rows
        )
    source_evidence = canonical_json(
        {
            "schema_version": 1,
            "provider": "tiingo_eod",
            "selection_rule": RULE,
            "requests": transport.evidence,
        }
    )
    assets = tuple(asset for asset, _ in selected)
    return build_research_snapshot(
        assets=assets,
        context=AssetContext(
            schema_version=2,
            aliases=tuple(aliases),
            sectors=tuple(sectors),
            fundamentals=(),
        ),
        calendar=calendar,
        universe=Universe(
            schema_version=1,
            label="Budget-sampled current Tiingo USD primary stocks",
            rule=RULE,
            source_sha256=hashlib.sha256(directory).hexdigest(),
            memberships=tuple(memberships),
        ),
        observations=tuple(observations),
        permission=permission,
        source_payload_hash=hashlib.sha256(source_evidence).hexdigest(),
        first_session=first,
        last_session=day,
        request_hash=hashlib.sha256(canonical_json(config.model_dump(mode="json"))).hexdigest(),
        provider="tiingo_eod",
        diagnostic_supported=True,
        source_evidence=source_evidence,
        provider_evidence={
            "selection_rule": RULE,
            "candidate_bound": 100,
            "selected_count": len(assets),
            "rejections": rejections,
            "calendar_lookahead_required": True,
            "ordinary_stock_basis": "SOURCE_STOCK_PLUS_ACTIVE_NON_ADR_PRIMARY_METADATA",
            "source_metadata_available_at": metadata_at.isoformat().replace("+00:00", "Z"),
        },
    )
