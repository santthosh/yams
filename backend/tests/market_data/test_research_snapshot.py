"""SYNTHETIC_DATA_ONLY provider-shaped inputs exercise the research protocol offline."""

import json
from datetime import UTC, date, datetime

import pytest

from backend.domain.market import AssetV1
from backend.market_data.models import AssetContext, Calendar, Universe
from backend.market_data.providers.normalization import normalize_observation
from backend.market_data.providers.yahoo import ProviderFailure, ResearchPermission
from backend.market_data.research_snapshot import build_research_snapshot
from backend.tests.market_data.test_normalization import ROW
from backend.tests.market_data.test_repository import ROOT


def build(*, last: date = date(2027, 1, 4)) -> object:
    assets = tuple(
        AssetV1.model_validate(item) for item in json.loads((ROOT / "assets.json").read_bytes())[:1]
    )
    context = AssetContext.model_validate_json((ROOT / "asset_context.json").read_bytes())
    context = context.model_copy(
        update={
            "aliases": tuple(row for row in context.aliases if row.asset_id == assets[0].asset_id),
            "sectors": tuple(row for row in context.sectors if row.asset_id == assets[0].asset_id),
        }
    )
    universe = Universe.model_validate_json((ROOT / "universe.json").read_bytes())
    observed = datetime(2031, 1, 1, tzinfo=UTC)
    universe = universe.model_copy(
        update={
            "memberships": tuple(
                row.model_copy(
                    update={
                        "timing_status": "current_only",
                        "available_at": observed,
                        "ingested_at": observed,
                    }
                )
                for row in universe.memberships
                if row.asset_id == assets[0].asset_id
            )
        }
    )
    calendar = Calendar.model_validate_json((ROOT / "calendar.json").read_bytes())
    observation = normalize_observation(assets[0].asset_id, ROW, observed, calendar)
    return build_research_snapshot(
        assets=assets,
        context=context,
        universe=universe,
        calendar=calendar,
        observations=(observation,),
        permission=ResearchPermission("test-rights", "test-directory", "test-v1", True),
        source_payload_hash="a" * 64,
        first_session=date(2027, 1, 4),
        last_session=last,
    )


def test_deterministic_inspection_snapshot_preserves_capability_limits() -> None:
    from backend.market_data.files import PinnedSnapshot

    first, second = build(), build()
    assert isinstance(first, PinnedSnapshot) and isinstance(second, PinnedSnapshot)
    assert first.manifest.manifest_hash() == second.manifest.manifest_hash()
    assert first.manifest.mode == "research_market_data" and first.manifest.quality == "blocked"
    assert first.manifest.coverage.membership_basis == "current_only"
    assert "SURVIVORSHIP_BIAS_RISK" in first.manifest.warnings
    assert first.manifest.price_basis.ohlc == "provider_unverified"
    assert json.loads(first.artifacts["provenance.json"])["source_payload_sha256"] == "a" * 64


def test_partial_requested_refresh_is_rejected() -> None:
    with pytest.raises(ProviderFailure, match="PROVIDER_INCOMPLETE_COVERAGE"):
        build(last=date(2027, 1, 5))
