"""Strict current-directory parsing; never infer issuer identity or historical membership."""

import csv
import hashlib
import io
from dataclasses import dataclass
from typing import Literal

from backend.market_data.providers.yahoo import ProviderFailure


@dataclass(frozen=True)
class DirectoryListing:
    symbol: str
    exchange_code: str
    security_name: str
    is_etf: bool


@dataclass(frozen=True)
class DirectorySnapshot:
    source_sha256: str
    file_creation_text: str
    listings: tuple[DirectoryListing, ...]
    warnings: tuple[str, ...] = ("SURVIVORSHIP_BIAS_RISK", "CURRENT_MEMBERSHIP_ONLY")


def parse_directory(
    content: bytes, kind: Literal["nasdaqlisted", "otherlisted"]
) -> DirectorySnapshot:
    """Keep every non-test listing; ordinary-equity eligibility needs other evidence.

    The file-generation marker is retained verbatim, never treated as first public
    availability. Callers retain original ingestion time, rights and source URL.
    Exchange codes are provider codes, not guessed permanent asset IDs or MICs.
    """
    if len(content) > 8 * 1024 * 1024:
        raise ProviderFailure("DIRECTORY_SIZE_LIMIT")
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        raise ProviderFailure("DIRECTORY_ENCODING_INVALID") from None
    if len(lines) < 3 or not lines[-1].startswith("File Creation Time:"):
        raise ProviderFailure("DIRECTORY_INCOMPLETE")
    reader = csv.DictReader(io.StringIO("\n".join(lines[:-1])), delimiter="|")
    symbol_field = "Symbol" if kind == "nasdaqlisted" else "ACT Symbol"
    required = {symbol_field, "Security Name", "Test Issue", "ETF"}
    if kind == "otherlisted":
        required.add("Exchange")
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ProviderFailure("DIRECTORY_SCHEMA_INVALID")
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ProviderFailure("DIRECTORY_SCHEMA_INVALID")
    listings = []
    seen = set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ProviderFailure("DIRECTORY_ROW_INVALID")
        if row["Test Issue"] not in {"Y", "N"} or row["ETF"] not in {"Y", "N"}:
            raise ProviderFailure("DIRECTORY_ROW_INVALID")
        if row["Test Issue"] == "Y":
            continue
        symbol = row[symbol_field]
        exchange = "NASDAQ" if kind == "nasdaqlisted" else row["Exchange"]
        if not symbol or len(symbol) > 32 or not exchange or not row["Security Name"]:
            raise ProviderFailure("DIRECTORY_ROW_INVALID")
        key = (exchange, symbol)
        if key in seen:
            raise ProviderFailure("DIRECTORY_DUPLICATE_IDENTITY")
        seen.add(key)
        listings.append(DirectoryListing(symbol, exchange, row["Security Name"], row["ETF"] == "Y"))
    if not listings:
        raise ProviderFailure("DIRECTORY_EMPTY")
    return DirectorySnapshot(
        hashlib.sha256(content).hexdigest(),
        lines[-1].split("|")[0],
        tuple(sorted(listings, key=lambda row: (row.exchange_code, row.symbol))),
    )
