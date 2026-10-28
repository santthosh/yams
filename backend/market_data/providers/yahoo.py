"""Conditional research acquisition; observations do not prove raw execution prices."""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

SAFE_PROVIDER_REASONS = frozenset(
    {
        "DIRECTORY_DUPLICATE_IDENTITY",
        "DIRECTORY_EMPTY",
        "DIRECTORY_ENCODING_INVALID",
        "DIRECTORY_ENDPOINT_UNSUPPORTED",
        "DIRECTORY_IDENTITY_COVERAGE_MISMATCH",
        "DIRECTORY_INCOMPLETE",
        "DIRECTORY_RATE_LIMITED",
        "DIRECTORY_REDIRECT_UNSUPPORTED",
        "DIRECTORY_REQUEST_FAILED",
        "DIRECTORY_RESPONSE_UNSUPPORTED",
        "DIRECTORY_ROW_INVALID",
        "DIRECTORY_SCHEMA_INVALID",
        "DIRECTORY_SIZE_LIMIT",
        "DIRECTORY_UNAVAILABLE",
        "DIRECTORY_VENUE_UNSUPPORTED",
        "INVALID_RESEARCH_UNIVERSE",
        "PROVIDER_ACTION_INVALID",
        "PROVIDER_NOT_CONFIGURED",
        "PROVIDER_RESPONSE_UNSUPPORTED",
        "PROVIDER_CREDENTIAL_INVALID",
        "PROVIDER_CAPABILITY_UNAVAILABLE",
        "PROVIDER_SYMBOL_UNAVAILABLE",
        "PROVIDER_UNAVAILABLE",
        "PROVIDER_ADAPTER_VERSION_UNSUPPORTED",
        "PROVIDER_ALIAS_AMBIGUOUS",
        "PROVIDER_BUDGET_EXHAUSTED",
        "PROVIDER_EXTRA_NOT_INSTALLED",
        "PROVIDER_INCOMPLETE_COVERAGE",
        "PROVIDER_NUMERIC_VALUE_INVALID",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_REQUEST_FAILED",
        "PROVIDER_RIGHTS_UNVERIFIED",
        "PROVIDER_ROW_INVALID",
        "PROVIDER_SESSION_INCOMPLETE",
        "PROVIDER_TIMEOUT",
        "PROVIDER_VOLUME_INVALID",
        "REFRESH_CANCELLED",
        "RESEARCH_AVAILABILITY_UNSUPPORTED",
        "RESEARCH_CALENDAR_UNSUPPORTED",
        "RESEARCH_MEMBERSHIP_UNSUPPORTED",
    }
)
TRANSIENT_PROVIDER_REASONS = frozenset(
    {
        "DIRECTORY_RATE_LIMITED",
        "DIRECTORY_UNAVAILABLE",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_UNAVAILABLE",
    }
)


class ProviderFailure(ValueError):
    """Stable, secret-free failure reason; no partial result may be published."""

    def __init__(self, reason: str):
        self.reason = reason if reason in SAFE_PROVIDER_REASONS else "PROVIDER_REQUEST_FAILED"
        self.retryable = self.reason in TRANSIENT_PROVIDER_REASONS
        super().__init__(self.reason)


@dataclass(frozen=True)
class ResearchPermission:
    """Operator-reviewed evidence, never inferred from library/network availability."""

    rights_reference: str
    directory_reference: str
    adapter_version: str
    verified_local_use: bool = False

    def require_verified(self) -> None:
        if not self.verified_local_use or not all(
            value.strip()
            for value in (self.rights_reference, self.directory_reference, self.adapter_version)
        ):
            raise ProviderFailure("PROVIDER_RIGHTS_UNVERIFIED")


class HistoryClient(Protocol):
    def history(self, symbol: str, **options: object) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True)
class AcquiredHistory:
    symbol: str
    rows: tuple[Mapping[str, object], ...]


class YahooResearchAdapter:
    """Acquire a complete bounded directory selection or fail without a result.

    Client injection keeps recorded contract tests offline. The caller owns validated
    venue/identity mappings and broad directory selection; ticker strings alone never
    become internal asset IDs. These observations still require ADR-002 normalization,
    hashing, chronology and capability checks before immutable snapshot publication.
    """

    def __init__(
        self,
        client: HistoryClient,
        permission: ResearchPermission,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.client = client
        self.permission = permission
        self.clock = clock

    def acquire(
        self,
        symbols: Sequence[str],
        *,
        start: str,
        end: str,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> tuple[AcquiredHistory, ...]:
        self.permission.require_verified()
        if not symbols or len(symbols) > 1000 or len(set(symbols)) != len(symbols):
            raise ProviderFailure("INVALID_RESEARCH_UNIVERSE")
        deadline = self.clock() + 300
        result = []
        for symbol in symbols:
            if cancelled():
                raise ProviderFailure("REFRESH_CANCELLED")
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise ProviderFailure("PROVIDER_BUDGET_EXHAUSTED")
            try:
                rows = self.client.history(
                    symbol,
                    start=start,
                    end=end,
                    interval="1d",
                    auto_adjust=False,
                    back_adjust=False,
                    repair=False,
                    keepna=True,
                    rounding=False,
                    actions=True,
                    raise_errors=True,
                    timeout=min(10.0, remaining),
                )
            except (TimeoutError, ConnectionError):
                raise ProviderFailure("PROVIDER_TIMEOUT") from None
            except Exception as error:
                if type(error).__name__ == "YFRateLimitError":
                    raise ProviderFailure("PROVIDER_RATE_LIMITED") from None
                # Never log response bodies, URLs with secrets or provider exceptions.
                raise ProviderFailure("PROVIDER_REQUEST_FAILED") from None
            if not rows or len(rows) > 2520:
                raise ProviderFailure("PROVIDER_INCOMPLETE_COVERAGE")
            if self.clock() > deadline:
                raise ProviderFailure("PROVIDER_BUDGET_EXHAUSTED")
            result.append(AcquiredHistory(symbol, tuple(rows)))
        return tuple(result)


class YFinanceClient:
    """Lazy optional transport. Construction verifies permission before library access.

    Rows preserve provider fields and the session label for later normalization;
    no synthetic price, publication timestamp or action date is introduced here.
    """

    def __init__(self, permission: ResearchPermission):
        import importlib
        from importlib.metadata import PackageNotFoundError, version

        permission.require_verified()
        try:
            if version("yfinance") != "1.7.0":
                raise ProviderFailure("PROVIDER_ADAPTER_VERSION_UNSUPPORTED")
            self._library = importlib.import_module("yfinance")
        except (PackageNotFoundError, ImportError):
            raise ProviderFailure("PROVIDER_EXTRA_NOT_INSTALLED") from None

    def history(self, symbol: str, **options: object) -> Sequence[Mapping[str, object]]:
        frame = self._library.Ticker(symbol).history(**options)
        rows: list[Mapping[str, object]] = []
        for session, values in frame.iterrows():
            row: dict[str, object] = dict(values.to_dict())
            row["session_date"] = session.date().isoformat()
            rows.append(row)
        return rows
