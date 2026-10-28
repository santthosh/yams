"""SYNTHETIC_DATA_ONLY provider contract inputs; never real-access evidence."""

import io
import json
import urllib.error
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from email.message import Message

import pytest
from pydantic import ValidationError

from backend.jobs.registry import RefreshPayload
from backend.market_data.calendar import real_calendar
from backend.market_data.models import Calendar
from backend.market_data.providers.tiingo import (
    HTTPTiingoClient,
    directory_candidates,
    metadata_by_symbol,
)
from backend.market_data.providers.tiingo_normalization import normalize_tiingo
from backend.market_data.providers.yahoo import ProviderFailure
from backend.market_data.tiingo_config import TiingoResearchConfigV1
from backend.market_data.tiingo_research import acquire_tiingo_snapshot


def archive(rows: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr(
            "supported_tickers.csv",
            "ticker,exchange,assetType,priceCurrency,startDate,endDate\n" + rows,
        )
    return stream.getvalue()


def test_config_is_closed_and_does_not_accept_credentials() -> None:
    config = dict(schema_version=1, provider="tiingo_eod", rights_verified_local_use=True)
    payload = RefreshPayload.model_validate(
        {"schema_version": 1, "source_mode": "research_market_data", "research_config": config}
    )
    assert isinstance(payload.research_config, TiingoResearchConfigV1)
    assert payload.research_config.history_sessions == 400
    for changed in (
        {"TIINGO_API_TOKEN": "SYNTHETIC_DATA_ONLY"},
        {"max_assets": 21},
        {"history_sessions": 251},
        {"rights_verified_local_use": "true"},
        {"provider": "arbitrary_module"},
    ):
        with pytest.raises(ValidationError):
            TiingoResearchConfigV1.model_validate(config | changed)


def test_calendar_is_independent_of_bars_and_covers_next_open() -> None:
    calendar, day = real_calendar(400, now=datetime(2026, 10, 28, 9, 30, tzinfo=UTC))
    assert day == date(2026, 10, 27) and len(calendar.sessions) == 401
    assert calendar.sessions[-1].session_date == date(2026, 10, 28)
    assert calendar.sessions[-1].open_at == datetime(2026, 10, 28, 13, 30, tzinfo=UTC)
    assert calendar.generator_version == "exchange_calendars_4.13.2"
    assert "sha256_" in calendar.timezone_rules_version
    # Independent NYSE published holiday/early-close/DST expectations.
    fall, day = real_calendar(252, date(2026, 11, 27), now=datetime(2026, 11, 30, 12, tzinfo=UTC))
    assert fall.sessions[-2].close_at == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert date(2026, 11, 26) not in {row.session_date for row in fall.sessions}
    assert date(2026, 7, 3) not in {row.session_date for row in fall.sessions}
    indexed = {row.session_date: row for row in fall.sessions}
    assert indexed[date(2026, 3, 6)].open_at.hour == 14
    assert indexed[date(2026, 3, 9)].open_at.hour == 13
    for requested in (date(2026, 7, 3), date(2027, 1, 1)):
        with pytest.raises(ValueError):
            real_calendar(252, requested, now=datetime(2026, 10, 28, 9, tzinfo=UTC))


def test_directory_rule_is_order_independent_and_never_uses_favorites() -> None:
    rows = [f"SYN{letter},NASDAQ,Stock,USD,2020-01-01,2026-10-27\n" for letter in "ABCDE"]
    extra = "SYNF,NASDAQ,ETF,USD,2020-01-01,2026-10-27\n"
    first = directory_candidates(archive("".join(rows) + extra), "2025-01-01", "2026-10-27")
    second = directory_candidates(archive("".join(reversed(rows))), "2025-01-01", "2026-10-27")
    assert first == second and len(first) == 5
    assert all(row["assetType"] == "Stock" for row in first)
    with pytest.raises(ProviderFailure):
        directory_candidates(archive(rows[0] + rows[0]), "2025-01-01", "2026-10-27")


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_http_errors_are_typed_and_never_echo_token(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "synthetic_test_token_only"
    monkeypatch.setenv("TIINGO_API_TOKEN", secret)
    client = HTTPTiingoClient()

    def denied(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("https://api.tiingo.com", status, secret, Message(), None)

    monkeypatch.setattr(client._opener, "open", denied)
    with pytest.raises(ProviderFailure) as caught:
        client.identity("SYNA")
    assert secret not in str(caught.value) and not client.evidence
    assert caught.value.retryable == (status in {429, 503})


def test_missing_token_and_nonfinite_source_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIINGO_API_TOKEN", raising=False)
    with pytest.raises(ProviderFailure, match="PROVIDER_NOT_CONFIGURED"):
        HTTPTiingoClient()
    from backend.market_data.providers.tiingo import reject_constant

    with pytest.raises(ValueError):
        json.loads('{"close": NaN}', parse_constant=reject_constant)


def test_normalization_preserves_raw_volume_and_does_not_backdate_or_invent_paydate() -> None:
    from pathlib import Path

    calendar = Calendar.model_validate_json(
        (Path(__file__).resolve().parents[3] / "data/fixtures/snapshot/calendar.json").read_bytes()
    )
    observed = datetime(2027, 1, 5, 12, tzinfo=UTC)
    row = {
        "date": "2027-01-04T00:00:00.000Z",
        "open": Decimal("100.00"),
        "high": 105,
        "low": 99,
        "close": 103,
        "volume": 1000,
        "adjClose": Decimal("51.50"),
        "adjVolume": 2000,
        "divCash": Decimal("1.250"),
        "splitFactor": Decimal("2"),
    }
    result = normalize_tiingo("SYN:TEST", row, observed, calendar)
    assert result.bar.open == "100.00" and result.bar.close == "103"
    assert result.bar.adjusted_close == "51.50" and result.bar.volume == 1000
    assert result.bar.published_at is None
    assert result.bar.available_at == result.bar.ingested_at == observed
    assert result.bar.price_basis == "raw_as_traded" and result.bar.volume_basis == "raw_shares_v1"
    split, dividend = result.actions
    assert (split.ratio_numerator, split.ratio_denominator) == ("2", "1")
    assert dividend.per_share == "1.25" and dividend.payable_session is None
    assert (
        normalize_tiingo("SYN:TEST", row | {"divCash": Decimal("1.25")}, observed, calendar).actions
        == result.actions
    )
    for changed in (
        {"volume": Decimal("1.5")},
        {"low": 104},
        {"adjClose": Decimal("NaN")},
        {"date": "2027-01-04T12:00:00Z"},
        {"divCash": -1},
    ):
        with pytest.raises(ProviderFailure):
            normalize_tiingo("SYN:TEST", row | changed, observed, calendar)


def test_complete_synthetic_provider_cohort_has_diagnostic_only_capabilities() -> None:
    from typing import Any

    observed = datetime(2026, 10, 28, 9, 30, tzinfo=UTC)
    calendar, day = real_calendar(252, now=observed)

    class SyntheticClient:
        evidence: list[dict[str, Any]] = [{"label": "SYNTHETIC_DATA_ONLY"}]

        def directory(self) -> tuple[bytes, datetime]:
            return archive(
                "".join(
                    f"SYN{letter},NASDAQ,Stock,USD,2020-01-01,2026-10-27\n" for letter in "ABCDE"
                )
            ), observed

        def metadata(self, symbols: tuple[str, ...]) -> tuple[list[dict[str, Any]], datetime]:
            return [
                {
                    "ticker": s,
                    "permaTicker": "PERM-" + s,
                    "isActive": True,
                    "isADR": False,
                    "name": "Synthetic Common Stock",
                    "sector": "Technology",
                }
                for s in symbols
            ], observed

        def identity(self, symbol: str) -> tuple[dict[str, Any], datetime]:
            return {
                "ticker": symbol,
                "exchangeCode": "NASDAQ",
                "startDate": "2020-01-01",
                "endDate": "2026-10-27",
            }, observed

        def history(
            self, symbol: str, first: str, last: str
        ) -> tuple[list[dict[str, Any]], datetime]:
            return [
                {
                    "date": session.session_date.isoformat() + "T00:00:00.000Z",
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 100000,
                    "adjClose": 100,
                    "adjVolume": 100000,
                    "divCash": 0,
                    "splitFactor": 1,
                }
                for session in calendar.sessions
                if session.session_date <= day
            ], observed

    config = TiingoResearchConfigV1(
        schema_version=1,
        provider="tiingo_eod",
        rights_verified_local_use=True,
        history_sessions=252,
        max_assets=3,
    )
    pinned = acquire_tiingo_snapshot(config, client=SyntheticClient(), now=observed)
    assert pinned.manifest.quality == "usable_with_warnings"
    assert len(pinned.manifest.coverage.asset_ids) == 3
    assert "BUDGET_SAMPLED_UNIVERSE" in pinned.manifest.warnings
    capabilities = json.loads(pinned.artifacts["provenance.json"])
    assert capabilities["supports_diagnostics"] is True
    assert capabilities["supports_complete_action_accounting"] is False
    assert capabilities["raw_execution_prices"] is False
    assert (
        json.loads(pinned.artifacts["source_evidence.json"])["requests"][0]["label"]
        == "SYNTHETIC_DATA_ONLY"
    )
    with pytest.raises(ProviderFailure, match="REFRESH_CANCELLED"):
        acquire_tiingo_snapshot(
            config, client=SyntheticClient(), now=observed, cancelled=lambda: True
        )


def test_ambiguous_metadata_is_excluded_independently_of_response_order() -> None:
    candidates = ({"ticker": "SYNA"}, {"ticker": "SYNB"})
    rows = [
        {"ticker": "syna", "permaTicker": "old"},
        {"ticker": "synb", "permaTicker": "unique"},
        {"ticker": "syna", "permaTicker": "new"},
        {"ticker": "SYNA", "permaTicker": "third"},
    ]
    expected = ({"SYNB": rows[1]}, frozenset({"SYNA"}))
    assert metadata_by_symbol(rows, candidates) == expected
    assert metadata_by_symbol(list(reversed(rows)), candidates) == expected
    with pytest.raises(ProviderFailure, match="PROVIDER_ALIAS_AMBIGUOUS"):
        metadata_by_symbol(rows + [{"ticker": "OUTSIDE"}], candidates)
