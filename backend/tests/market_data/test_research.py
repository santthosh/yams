"""SYNTHETIC_DATA_ONLY complete research protocol with authored offline responses."""

import hashlib
import json
from datetime import UTC, datetime, tzinfo
from typing import Self

import pytest

from backend.domain.types import canonical_json
from backend.market_data.research import acquire_research_snapshot
from backend.market_data.research_config import ResearchConfig
from backend.tests.market_data.test_normalization import ROW
from backend.tests.market_data.test_repository import ROOT


def test_complete_acquisition_binds_config_and_preserves_inspection_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.market_data import research

    class TestClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2031, 1, 1, tzinfo=UTC)

    class Download:
        def fetch(self, url: str, *, timeout: float, limit: int) -> bytes:
            return (
                b"Symbol|Security Name|Test Issue|ETF\nAAA|Synthetic ordinary equity|N|N\n"
                b"File Creation Time: 0101203112:00|||\n"
            )

    class History:
        def history(self, symbol: str, **options: object) -> list[dict[str, object]]:
            assert symbol == "AAA"
            return [ROW]

    asset = json.loads((ROOT / "assets.json").read_bytes())[0]
    asset.update(provider="yahoo_yfinance", provider_id="AAA", venue="XNAS")
    context = json.loads((ROOT / "asset_context.json").read_bytes())
    for key in ("aliases", "sectors"):
        context[key] = [row for row in context[key] if row["asset_id"] == asset["asset_id"]]
    context["aliases"][0].update(venue="XNAS", provider="yahoo_yfinance", provider_id="AAA")
    config = ResearchConfig.model_validate(
        {
            "schema_version": 1,
            "rights_verified_local_use": True,
            "rights_reference": "test-only-permission",
            "directory_reference": "test-only-directory",
            "directory_kind": "nasdaqlisted",
            "adapter_version": "yfinance_1.7.0_normalization_1",
            "first_session": "2027-01-04",
            "last_session": "2027-01-04",
            "calendar": json.loads((ROOT / "calendar.json").read_bytes()),
            "assets": [asset],
            "context": context,
            "exchange_codes": ["NASDAQ"],
            "selection_rule_reference": "All non-test listings on the selected source venue",
        }
    )
    monkeypatch.setattr(research, "datetime", TestClock)
    snapshot = acquire_research_snapshot(config, downloader=Download(), client=History())
    provenance = json.loads(snapshot.artifacts["provenance.json"])
    assert (
        provenance["request_hash"]
        == hashlib.sha256(canonical_json(config.model_dump(mode="json"))).hexdigest()
    )
    assert snapshot.manifest.quality == "blocked"
    assert snapshot.manifest.coverage.membership_basis == "current_only"
