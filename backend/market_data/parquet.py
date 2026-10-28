"""Pinned Parquet projection plus exact typed payloads for repository readers."""

import tempfile
from pathlib import Path

import duckdb

from backend.domain.market import MarketBarV1


def encode_bars(bars: tuple[MarketBarV1, ...]) -> bytes:
    with tempfile.TemporaryDirectory(prefix="yams-market-writer-") as directory:
        path = Path(directory) / "bars.parquet"
        with duckdb.connect(config={"threads": 1}) as connection:
            connection.execute(
                "CREATE TABLE bars(asset_id VARCHAR, session_date DATE, "
                "available_at TIMESTAMPTZ, ingested_at TIMESTAMPTZ, payload VARCHAR)"
            )
            if bars:
                connection.executemany(
                    "INSERT INTO bars VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            bar.asset_id,
                            bar.session_date,
                            bar.available_at,
                            bar.ingested_at,
                            bar.model_dump_json(),
                        )
                        for bar in bars
                    ],
                )
            connection.execute(
                "COPY (SELECT * FROM bars ORDER BY asset_id, session_date, payload) "
                "TO ? (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 2048)",
                [str(path)],
            )
        return path.read_bytes()
