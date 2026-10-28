# Pinned market repository (issue #29)

`backend.market_data.providers.fixture.fixture_repository(root, expected_manifest_hash)`
opens an explicitly identified **SYNTHETIC_DATA_ONLY** snapshot. Use it as a context
manager. It has no provider/network fallback. Research snapshots require the generic
`MarketRepository` and their own verified source artifacts; the fixture adapter rejects
research mode.

```python
from datetime import UTC, date, datetime
from pathlib import Path
from backend.market_data.providers.fixture import fixture_repository

# Obtain the trusted hash from the committed fixture suite manifest or persisted job.
with fixture_repository(Path("/absolute/private/snapshot"), expected_hash) as market:
    view = market.as_of(
        datetime(2027, 1, 5, 21, 0, 1, tzinfo=UTC), date(2027, 1, 5)
    )
```

The reader rejects symlinks, hard links, nonregular files, excessive sizes, hash drift
and unknown cross-references. Copy a hard-linked development checkout into a private
regular-file staging directory before opening it. Once opened, immutable verified bytes
and a private Parquet copy pin the view even if the original files change. DuckDB has
extension installation/loading and external access disabled except for that copy;
callers supply typed clocks, never SQL or arbitrary artifact paths.

Runtime artifacts are assets schema 1, temporal asset context schema 2, universe schema 1,
calendar schema 1, actions schema 1 and bars Parquet schema 1. Parquet includes asset,
session, availability and ingestion projections plus the exact MarketBarV1 JSON payload;
every projection must equal its validated payload. `bars.json` remains an inspectable
fixture-generation input, not a runtime manifest artifact. The pinned DuckDB writer
version and settings are recorded in provenance; fixture regeneration must match bytes.

Queries include evidence available **at or before** the cutoff. Live queries additionally
require original ingestion at or before it. Requested session must be a completed pinned
calendar session. Output dates run from inclusive `start_session` to inclusive requested
session. The quality guard still inspects the immediately preceding calendar session
when the output window is narrow. No missing bar is forward-filled. Future evidence
cannot alter an earlier result. Effective aliases and sectors use half-open date intervals;
missing or ambiguous context has explicit reasons, never an inferred `Unknown` sector.

Exact duplicates yield one row and an audit count. Conflicting duplicates are excluded.
Unexplained adjacent-session adjusted-close moves strictly greater than 50% are excluded
with `EXTREME_ADJUSTED_MOVE`; exactly ±50% is allowed. No action-based price repair is
inferred. Corporate actions remain evidence: unresolved dividend payable dates are flagged
and this repository never posts cash, mutates holdings or computes action-adjusted prices.

Consumers must inspect diagnostics, asset reasons, manifest quality, source mode and
warnings before declaring eligibility or execution readiness. A blocked snapshot is
inspectable with `SNAPSHOT_BLOCKED`, not approved for trading. Missing sessions are
reported per asset. Historical research claims must honor the manifest membership basis
and ADR-002 survivorship limitations; an available current-only membership is not proof
of historical point-in-time membership. Strategy eligibility belongs to #32.

`publish_sealed(stage, store, hash)` validates and fsyncs a sealed private staging tree,
then uses Linux `renameat2(RENAME_NOREPLACE)` or macOS `renamex_np(RENAME_EXCL)`.
There is no overwrite/cross-filesystem copy fallback. Existing destinations are fully
hash-verified before reuse; mismatches fail. The caller must exclude writers, hold the
digest lock and valid lease, and own both parent directories. #30 owns that coordination,
PostgreSQL registration, current-pointer update and crash/recovery integration. A failure
after rename may leave a valid orphan; this primitive never adopts or deletes it.

Verification: `uv run --locked pytest backend/tests/market_data -q`, `make fixtures-check`,
`make lint`, `make typecheck`, `make contracts-check`. PostgreSQL and end-to-end delivery
remain separate gates; this library alone does not deliver milestone 0.0.2.
