"""Bounded fixed-host Tiingo reads; only successful source bytes enter local evidence."""

import base64
import csv
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol

from backend.market_data.providers.yahoo import ProviderFailure

DIRECTORY_URL = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
API_ORIGIN = "https://api.tiingo.com"
RULE = "tiingo_us_stock_hash20_v1"
SYMBOL = re.compile(r"^[A-Z]{1,5}$")
VENUES = {"NASDAQ": "XNAS", "NYSE": "XNYS"}
MAX_RESPONSE = 8 * 1024 * 1024


class TiingoClient(Protocol):
    evidence: list[dict[str, Any]]

    def directory(self) -> tuple[bytes, datetime]: ...
    def metadata(self, symbols: tuple[str, ...]) -> tuple[list[dict[str, Any]], datetime]: ...
    def identity(self, symbol: str) -> tuple[dict[str, Any], datetime]: ...
    def history(
        self, symbol: str, first: str, last: str
    ) -> tuple[list[dict[str, Any]], datetime]: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED")


def reject_constant(value: str) -> None:
    raise ValueError("Nonfinite source value")


class HTTPTiingoClient:
    def __init__(self) -> None:
        token = os.environ.get("TIINGO_API_TOKEN", "")
        if not token:
            raise ProviderFailure("PROVIDER_NOT_CONFIGURED")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", token):
            raise ProviderFailure("PROVIDER_CREDENTIAL_INVALID")
        self._token = token
        self._opener = urllib.request.build_opener(NoRedirect())
        self.evidence: list[dict[str, Any]] = []
        self._requests = 0
        self._raw_bytes = 0

    def _read(self, path: str, *, directory: bool = False) -> tuple[bytes, datetime]:
        if self._requests >= 45:
            raise ProviderFailure("PROVIDER_BUDGET_EXHAUSTED")
        if not directory and not path.startswith("/tiingo/"):
            raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED")
        url = DIRECTORY_URL if directory else API_ORIGIN + path
        headers = {"Accept-Encoding": "identity", "User-Agent": "YAMS/0.0.2 personal-research"}
        if not directory:
            headers.update(Authorization="Token " + self._token, Accept="application/json")
        self._requests += 1
        try:
            request = urllib.request.Request(url, headers=headers)
            with self._opener.open(request, timeout=10) as response:
                if (
                    response.status != 200
                    or response.headers.get("Content-Encoding", "identity") != "identity"
                ):
                    raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED")
                content = response.read(MAX_RESPONSE + 1)
            if len(content) > MAX_RESPONSE or self._token.encode() in content:
                raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED")
            self._raw_bytes += len(content)
            if self._raw_bytes > 32 * 1024 * 1024:
                raise ProviderFailure("PROVIDER_BUDGET_EXHAUSTED")
        except urllib.error.HTTPError as error:
            code = {
                401: "PROVIDER_CREDENTIAL_INVALID",
                403: "PROVIDER_CAPABILITY_UNAVAILABLE",
                404: "PROVIDER_SYMBOL_UNAVAILABLE",
                429: "PROVIDER_RATE_LIMITED",
            }.get(
                error.code,
                "PROVIDER_UNAVAILABLE" if error.code >= 500 else "PROVIDER_REQUEST_FAILED",
            )
            raise ProviderFailure(code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderFailure("PROVIDER_TIMEOUT") from None
        observed = datetime.now(UTC)
        self.evidence.append(
            {
                "url": url,
                "observed_at": observed.isoformat().replace("+00:00", "Z"),
                "sha256": hashlib.sha256(content).hexdigest(),
                "body_base64": base64.b64encode(content).decode(),
            }
        )
        return content, observed

    def _json(self, path: str) -> tuple[Any, datetime]:
        content, observed = self._read(path)
        try:
            return json.loads(
                content, parse_float=Decimal, parse_constant=reject_constant
            ), observed
        except (ValueError, UnicodeError):
            raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED") from None

    def directory(self) -> tuple[bytes, datetime]:
        return self._read("", directory=True)

    def metadata(self, symbols: tuple[str, ...]) -> tuple[list[dict[str, Any]], datetime]:
        if not symbols or len(symbols) > 100 or any(not SYMBOL.fullmatch(s) for s in symbols):
            raise ProviderFailure("INVALID_RESEARCH_UNIVERSE")
        data, observed = self._json(
            "/tiingo/fundamentals/meta?" + urllib.parse.urlencode({"tickers": ",".join(symbols)})
        )
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED")
        return data, observed

    def identity(self, symbol: str) -> tuple[dict[str, Any], datetime]:
        if not SYMBOL.fullmatch(symbol):
            raise ProviderFailure("INVALID_RESEARCH_UNIVERSE")
        data, observed = self._json("/tiingo/daily/" + symbol.lower())
        if not isinstance(data, dict):
            raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED")
        return data, observed

    def history(self, symbol: str, first: str, last: str) -> tuple[list[dict[str, Any]], datetime]:
        if not SYMBOL.fullmatch(symbol):
            raise ProviderFailure("INVALID_RESEARCH_UNIVERSE")
        data, observed = self._json(
            "/tiingo/daily/"
            + symbol.lower()
            + "/prices?"
            + urllib.parse.urlencode({"startDate": first, "endDate": last, "resampleFreq": "daily"})
        )
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ProviderFailure("PROVIDER_RESPONSE_UNSUPPORTED")
        return data, observed


def directory_candidates(content: bytes, first: str, last: str) -> tuple[dict[str, str], ...]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].file_size > 32 * 1024 * 1024:
                raise ValueError("Unsupported directory archive")
            with archive.open(entries[0]) as stream:
                expanded = stream.read(32 * 1024 * 1024 + 1)
            if len(expanded) > 32 * 1024 * 1024:
                raise ValueError("Directory expansion exceeds budget")
        reader = csv.DictReader(io.StringIO(expanded.decode("utf-8-sig")))
        expected = {"ticker", "exchange", "assetType", "priceCurrency", "startDate", "endDate"}
        if reader.fieldnames is None or set(reader.fieldnames) != expected:
            raise ValueError("Unsupported directory fields")
        rows: dict[tuple[str, str], dict[str, str]] = {}
        for number, raw in enumerate(reader):
            if number >= 250000 or None in raw or any(v is None for v in raw.values()):
                raise ValueError("Invalid directory row")
            row = {str(k): str(v).strip() for k, v in raw.items()}
            if (
                row["assetType"] != "Stock"
                or row["priceCurrency"] != "USD"
                or row["exchange"] not in VENUES
                or not SYMBOL.fullmatch(row["ticker"])
                or not row["startDate"]
                or not row["endDate"]
            ):
                continue
            if any(
                date.fromisoformat(row[key]).isoformat() != row[key]
                for key in ("startDate", "endDate")
            ):
                raise ValueError("Invalid source coverage dates")
            if row["startDate"] > first or row["endDate"] < last:
                continue
            key = VENUES[row["exchange"]], row["ticker"]
            if key in rows:
                raise ValueError("Duplicate source identity")
            rows[key] = row
        if len({key[1] for key in rows}) != len(rows):
            raise ValueError("Ambiguous cross-venue source ticker")
        return tuple(
            rows[key]
            for key in sorted(
                rows,
                key=lambda key: (
                    hashlib.sha256(f"{RULE}:{key[0]}:{key[1]}".encode()).hexdigest(),
                    key,
                ),
            )[:100]
        )
    except (
        ValueError,
        OSError,
        UnicodeError,
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
    ):
        raise ProviderFailure("DIRECTORY_SCHEMA_INVALID") from None


def metadata_by_symbol(
    rows: list[dict[str, Any]], candidates: tuple[dict[str, str], ...]
) -> tuple[Mapping[str, dict[str, Any]], frozenset[str]]:
    """Exclude every occurrence of ambiguous tickers; never choose the first alias."""
    allowed = {row["ticker"] for row in candidates}
    indexed: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for row in rows:
        symbol = row.get("ticker")
        if not isinstance(symbol, str) or symbol.upper() not in allowed:
            raise ProviderFailure("PROVIDER_ALIAS_AMBIGUOUS")
        normalized = symbol.upper()
        if normalized in indexed or normalized in ambiguous:
            indexed.pop(normalized, None)
            ambiguous.add(normalized)
        else:
            indexed[normalized] = row
    return indexed, frozenset(ambiguous)
