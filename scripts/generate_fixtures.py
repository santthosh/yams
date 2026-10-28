"""Deterministic fixture inputs; deliberately imports no production calculations."""

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEED = 42
ASSETS = ("SYN:AAA", "SYN:BBB", "SYN:CCC", "SYN:SPY", "SYN:ZERO")


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def schedule() -> list[dict[str, str]]:
    """Synthetic weekdays minus Jan 1/Dec 25; explicit post-2007 US DST rule."""
    result = []
    day = date(2027, 1, 1)
    while day <= date(2030, 12, 31):
        if day.weekday() < 5 and (day.month, day.day) not in {(1, 1), (12, 25)}:
            march = date(day.year, 3, 1)
            november = date(day.year, 11, 1)
            dst_start = march + timedelta(days=(6 - march.weekday()) % 7 + 7)
            dst_end = november + timedelta(days=(6 - november.weekday()) % 7)
            dst = dst_start <= day < dst_end
            result.append(
                {
                    "session_date": day.isoformat(),
                    "open_at": f"{day}T{13 if dst else 14}:30:00Z",
                    "close_at": f"{day}T{20 if dst else 21}:00:00Z",
                }
            )
        day += timedelta(days=1)
    return result


def price(asset: str, index: int) -> str:
    # Exact cent/mill values, no stochastic library or financial engine required.
    if asset in {"SYN:AAA", "SYN:BBB"}:
        value = Decimal(50) + Decimal(index) / 20
    elif asset == "SYN:CCC":
        value = Decimal(50) + Decimal(index) / 25 + Decimal((-1) ** index)
    elif asset == "SYN:SPY":
        value = Decimal(100) + Decimal(index) / 40
    else:
        value = Decimal(50)
    return format(value, ".3f")


def parquet_bars(rows: list[dict[str, object]]) -> bytes:
    """Pinned writer over authored rows; does not derive any expected financial value."""
    with tempfile.TemporaryDirectory(prefix="yams-fixture-parquet-") as directory:
        path = Path(directory) / "bars.parquet"
        with duckdb.connect(config={"threads": 1}) as connection:
            connection.execute(
                "CREATE TABLE bars(asset_id VARCHAR, session_date DATE, "
                "available_at TIMESTAMPTZ, ingested_at TIMESTAMPTZ, payload VARCHAR)"
            )
            connection.executemany(
                "INSERT INTO bars VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        row["asset_id"],
                        row["session_date"],
                        row["available_at"],
                        row["ingested_at"],
                        encoded(row).decode(),
                    )
                    for row in rows
                ],
            )
            connection.execute(
                "COPY (SELECT * FROM bars ORDER BY asset_id, session_date) TO ? "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 2048)",
                [str(path)],
            )
        return path.read_bytes()


def generate() -> dict[str, bytes]:
    output: dict[str, bytes] = {}
    sessions = schedule()
    calendar = {
        "schema_version": 1,
        "label": "SYNTHETIC_DATA_ONLY",
        "id": "SYNTHETIC_XNYS_LIKE_V1",
        "timezone": "America/New_York",
        "generator_version": "weekday_minus_jan1_dec25_v1",
        "timezone_rules_version": "synthetic_us_post2007_v1",
        "limitations": [
            "Not a validated exchange schedule; other holidays are intentionally absent."
        ],
        "sessions": sessions,
    }
    bars: list[dict[str, object]] = []
    for asset in ASSETS:
        for index, session in enumerate(sessions):
            close = price(asset, index)
            available = (
                (datetime.fromisoformat(session["close_at"]) + timedelta(seconds=1))
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )
            bars.append(
                {
                    "schema_version": 1,
                    "asset_id": asset,
                    "session_date": session["session_date"],
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adjusted_close": close,
                    "volume": 1000000,
                    "currency": "USD",
                    "provider": "yams_synthetic_v1",
                    "published_at": available,
                    "available_at": available,
                    "ingested_at": available,
                    "availability_basis": "synthetic",
                    "price_basis": "raw_as_traded",
                    "volume_basis": "raw_shares_v1",
                    "quality_flags": ["SYNTHETIC_DATA_ONLY"],
                }
            )
    assets = [
        {
            "asset_id": asset,
            "venue": "XNYS",
            "symbol": asset.split(":")[1],
            "currency": "USD",
            "instrument": "etf" if asset == "SYN:SPY" else "ordinary_equity",
            "sector": "Technology" if asset in {"SYN:AAA", "SYN:BBB"} else "Unknown",
            "provider": "yams_synthetic_v1",
            "provider_id": asset,
        }
        for asset in ASSETS
    ]
    provenance = {
        "schema_version": 1,
        "label": "SYNTHETIC_DATA_ONLY",
        "seed": SEED,
        "generator": "scripts/generate_fixtures.py",
        "generator_version": "2",
        "parquet_writer": "duckdb_2.0.0_zstd_rowgroup2048_threads1",
        "randomness": "bars use exact Decimal formulas; forecast probe uses pinned PCG64 seed42",
        "rights": "Repository-authored synthetic data; no downloaded market data.",
        "price_formula": {
            "AAA_BBB": "50 + session_index/20",
            "CCC": "50 + session_index/25 + (-1)^index",
            "SPY": "100 + session_index/40",
            "ZERO": "50",
        },
        "capabilities": ["synthetic_raw_ohlc", "explicit_availability", "synthetic_membership"],
    }
    universe = {
        "schema_version": 1,
        "label": "SYNTHETIC_DATA_ONLY",
        "rule": "authored_five_assets_v1",
        "source_sha256": digest(encoded(provenance)),
        "memberships": [
            {
                "asset_id": asset,
                "effective_from": sessions[0]["session_date"],
                "effective_to_exclusive": "2031-01-01",
                "available_at": "2026-12-31T00:00:00Z",
                "ingested_at": "2026-12-31T00:00:00Z",
                "timing_status": "synthetic_known",
            }
            for asset in ASSETS
        ],
    }
    temporal = {
        "effective_from": sessions[0]["session_date"],
        "effective_to_exclusive": "2031-01-01",
        "available_at": "2026-12-31T00:00:00Z",
        "ingested_at": "2026-12-31T00:00:00Z",
    }
    context = {
        "schema_version": 2,
        "aliases": [
            {
                **temporal,
                **{
                    key: asset[key]
                    for key in ("asset_id", "venue", "symbol", "provider", "provider_id")
                },
            }
            for asset in assets
        ],
        "sectors": [
            {**temporal, **{key: asset[key] for key in ("asset_id", "sector", "provider")}}
            for asset in assets
        ],
        "fundamentals": [],
    }
    artifacts: list[dict[str, object]] = []
    for name, role, value, count in (
        ("assets", "assets", assets, len(assets)),
        ("bars", "bars", bars, len(bars)),
        ("asset_context", "assets", context, len(assets) * 2),
        ("calendar", "calendar", calendar, len(sessions)),
        ("provenance", "provenance", provenance, None),
        ("universe", "universe", universe, len(assets)),
        ("actions", "actions", [], 0),
    ):
        content = encoded(value)
        output[f"snapshot/{name}.json"] = content
        filename = f"{name}.json"
        if name == "bars":
            # JSON remains an independently inspectable fixture input; the runtime
            # manifest pins only the exact Parquet representation of those rows.
            content = parquet_bars(bars)
            filename = "bars.parquet"
            output[f"snapshot/{filename}"] = content
        artifacts.append(
            {
                "path": filename,
                "role": role,
                "format": "parquet" if name == "bars" else "json",
                "schema_version": 2 if name == "asset_context" else 1,
                "sha256": digest(content),
                "size_bytes": len(content),
                "row_count": count,
            }
        )
    manifest = {
        "schema_version": 1,
        "mode": "synthetic_fixture",
        "source": {
            "provider": "yams_synthetic_v1",
            "adapter_version": "1",
            "normalization_version": "1",
            "rights_reference": "provenance.json",
            "rights_status": "synthetic_owned",
            "capabilities_sha256": digest(output["snapshot/provenance.json"]),
        },
        "price_basis": {
            "ohlc": "raw_as_traded",
            "adjusted_close": "identity_no_actions_v1",
            "volume": "raw_shares_v1",
            "currency": "USD",
            "corporate_action_policy": "synthetic_no_actions_v1",
        },
        "calendar": {
            "id": calendar["id"],
            "timezone": calendar["timezone"],
            "version": digest(output["snapshot/calendar.json"]),
            "artifact_path": "calendar.json",
        },
        "coverage": {
            "asset_ids": list(ASSETS),
            "first_session": sessions[0]["session_date"],
            "last_session": sessions[-1]["session_date"],
            "latest_completed_session": sessions[-1]["session_date"],
            "missing_sessions": [],
            "membership_basis": "synthetic",
        },
        "quality": "usable_with_warnings",
        "warnings": ["SYNTHETIC_DATA_ONLY"],
        "artifacts": sorted(artifacts, key=lambda artifact: str(artifact["path"])),
    }
    output["snapshot/manifest.json"] = encoded(manifest)
    snapshot_hash = digest(output["snapshot/manifest.json"])
    for case in json.loads((ROOT / "scripts/fixture_cases.json").read_text()):
        output[f"{case['id'].lower()}/case.json"] = encoded(case)
    # Canonical config oracle is authored separately, not emitted by production hashing code.
    config = (ROOT / "scripts/fixture_strategy.canonical.json").read_bytes().rstrip(b"\n")
    output["fix-01/strategy.canonical.json"] = config
    output["fix-01/strategy.sha256"] = digest(config).encode() + b"\n"
    rng = np.random.Generator(np.random.PCG64(SEED))
    initial_state = rng.bit_generator.state
    starts = rng.integers(0, 248, size=(5000, 13), dtype=np.int64, endpoint=False)
    output["fix-08/starts.i64le"] = starts.astype("<i8").tobytes(order="C")
    vectors = np.array([[0.01, -0.01]] * 252, dtype="<f8")
    output["fix-08/constant-vectors.f64le"] = vectors.tobytes(order="C")
    sampling = {
        "schema_version": 1,
        "label": "SYNTHETIC_DATA_ONLY",
        "seed": SEED,
        "generator": "PCG64",
        "numpy_version": np.__version__,
        "initial_state": initial_state,
        "sampling_version": "noncircular_c_order_v1",
        "shape": [5000, 13],
        "horizon_sessions": 63,
        "block_length": 5,
        "history_rows": 252,
        "indices_sha256": digest(output["fix-08/starts.i64le"]),
        "array_sha256": digest(output["fix-08/constant-vectors.f64le"]),
        "asset_order": ["SYN:AAA", "SYN:BBB"],
        "byte_order": "little",
        "fingerprint_scope": "sampling probe only; not a production forecast fingerprint",
    }
    output["fix-08/sampling.json"] = encoded(sampling)
    output["manifest.json"] = encoded(
        {
            "schema_version": 1,
            "label": "SYNTHETIC_DATA_ONLY",
            "seed": SEED,
            "generator_version": "2",
            "parquet_writer": "duckdb_2.0.0_zstd_rowgroup2048_threads1",
            "snapshot_sha256": snapshot_hash,
            "snapshot_id": str(uuid5(NAMESPACE_URL, "urn:yams:dataset:sha256:" + snapshot_hash)),
            "files": {
                name: {"sha256": digest(content), "size_bytes": len(content)}
                for name, content in sorted(output.items())
            },
        }
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/fixtures")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = generate()
    for name, content in outputs.items():
        target = args.output_root / name
        if args.check:
            if not target.is_file() or target.read_bytes() != content:
                raise SystemExit(f"Fixture drift: {name}; run make fixtures")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print(f"{'Verified' if args.check else 'Generated'} {len(outputs)} synthetic fixture files")


if __name__ == "__main__":
    main()
