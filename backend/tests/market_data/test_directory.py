"""Authored SYNTHETIC_DATA_ONLY directory responses, not redistributed listing files."""

import hashlib

import pytest

from backend.market_data.providers.directory import parse_directory
from backend.market_data.providers.yahoo import ProviderFailure

HEADER = "Symbol|Security Name|Test Issue|ETF\n"
FOOTER = "File Creation Time: 0102203017:03|||\n"


def test_full_non_test_inventory_hash_and_membership_warning() -> None:
    data = (
        HEADER
        + "CCC|Synthetic ETF|N|Y\nAAA|Synthetic Equity|N|N\n"
        + "TEST|Synthetic test issue|Y|N\n"
        + FOOTER
    ).encode()
    snapshot = parse_directory(data, "nasdaqlisted")
    assert [row.symbol for row in snapshot.listings] == ["AAA", "CCC"]
    assert snapshot.listings[1].is_etf
    assert snapshot.source_sha256 == hashlib.sha256(data).hexdigest()
    assert "SURVIVORSHIP_BIAS_RISK" in snapshot.warnings


@pytest.mark.parametrize(
    "data",
    [
        HEADER + "AAA|Synthetic Equity|N|N\n",
        HEADER + "AAA|Synthetic Equity|N|N\nAAA|Duplicate|N|N\n" + FOOTER,
        HEADER + "AAA|Synthetic Equity|?|N\n" + FOOTER,
        HEADER + "AAA|Synthetic Equity|N\n" + FOOTER,
    ],
)
def test_invalid_or_partial_directory_never_becomes_membership(data: str) -> None:
    with pytest.raises(ProviderFailure):
        parse_directory(data.encode(), "nasdaqlisted")


def test_directory_network_gate_and_observation_lineage() -> None:
    from datetime import UTC, datetime

    from backend.market_data.providers.directory_transport import acquire_directory
    from backend.market_data.providers.yahoo import ResearchPermission

    class RecordedDownload:
        calls = 0

        def fetch(self, url: str, *, timeout: float, limit: int) -> bytes:
            self.calls += 1
            assert url.endswith("nasdaqlisted.txt") and timeout == 10 and limit == 8 * 1024 * 1024
            return (HEADER + "AAA|Synthetic Equity|N|N\n" + FOOTER).encode()

    downloader = RecordedDownload()
    with pytest.raises(ProviderFailure, match="RIGHTS_UNVERIFIED"):
        acquire_directory("nasdaqlisted", ResearchPermission("", "", ""), downloader)
    assert downloader.calls == 0
    before = datetime.now(UTC)
    result = acquire_directory(
        "nasdaqlisted", ResearchPermission("test", "test", "test", True), downloader
    )
    assert result.observed_at >= before
    assert result.snapshot.source_sha256 == hashlib.sha256(result.content).hexdigest()
    assert downloader.calls == 1
