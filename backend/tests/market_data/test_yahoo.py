from collections.abc import Mapping, Sequence

import pytest

from backend.market_data.providers.yahoo import (
    ProviderFailure,
    ResearchPermission,
    YahooResearchAdapter,
)


class RecordedClient:
    """Authored provider-shaped responses; SYNTHETIC_DATA_ONLY, never market history."""

    def __init__(self, fail_on: str = ""):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.fail_on = fail_on

    def history(self, symbol: str, **options: object) -> Sequence[Mapping[str, object]]:
        self.calls.append((symbol, options))
        if symbol == self.fail_on:
            raise TimeoutError("private provider response must not escape")
        return [{"label": "SYNTHETIC_DATA_ONLY", "Close": "100"}]


def permission(verified: bool = True) -> ResearchPermission:
    return ResearchPermission(
        "test-only-rights-evidence", "test-only-directory", "test-v1", verified
    )


def test_unverified_rights_prevent_any_request() -> None:
    client = RecordedClient()
    with pytest.raises(ProviderFailure, match="PROVIDER_RIGHTS_UNVERIFIED"):
        YahooResearchAdapter(client, permission(False)).acquire(
            ["AAA"], start="2030-01-01", end="2030-02-01"
        )
    assert client.calls == []


def test_explicit_unrepaired_options_and_no_partial_return() -> None:
    client = RecordedClient(fail_on="BBB")
    with pytest.raises(ProviderFailure, match="^PROVIDER_TIMEOUT$"):
        YahooResearchAdapter(client, permission()).acquire(
            ["AAA", "BBB"], start="2030-01-01", end="2030-02-01"
        )
    options = client.calls[0][1]
    assert options["auto_adjust"] is False and options["repair"] is False
    assert options["keepna"] is True and options["actions"] is True
    assert options["raise_errors"] is True
    assert len(client.calls) == 2


def test_provider_failure_reasons_are_allowlisted_and_retry_classified() -> None:
    assert ProviderFailure("PROVIDER_TIMEOUT").retryable
    assert not ProviderFailure("PROVIDER_RIGHTS_UNVERIFIED").retryable
    assert str(ProviderFailure("secret response body")) == "PROVIDER_REQUEST_FAILED"
