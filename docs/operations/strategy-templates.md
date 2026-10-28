# Stock templates and diagnostic evidence (#38)

The development source for0.0.3 implements [ADR-011](../adr/0011-strategy-templates.md)
through the existing registry, supervised evaluator and shared allocation policy.
Published0.0.2 bundles retain their documented momentum-only capabilities; use the
current source or a later verified release for these additions.

| Template | Inspectable hypothesis | Important limit | Canonical config SHA-256 |
|---|---|---|---|
| Mean Reversion | Higher z-score of `1-close/SMA20` favors prices below their short moving average, subject to the strict positive SMA200 trend filter | Weakness can continue; a high score is not an expected return | `10904787385cca66062bcb1b27d264799b3cc954ee7fed62a91d11339295d81b` |
| Low Volatility | Higher `-z(VOL60)` favors lower historical sample log volatility | Historical stability does not guarantee smaller future losses | `133492a4ad378dff7e0ef2b96e3d6efe9f5a55fc3c286b440a32cb6a4c76fdcf` |

Momentum's original parameters, stable IDs and canonical hash remain unchanged.
SPY is a separately labeled benchmark; there is no passive/SPY publishable kind.
All stock families retain ordinary-equity eligibility, as-of history, inverse
volatility, zero-volatility exclusion before top-N, position/sector/cash caps,
monthly rebalance and existing execution policy. No score is a profitability claim.

## Inspect, fork and evaluate

1. Start the normal local Compose application. Serialized bootstrap validates and
   reuses three immutable template roots/initial versions; no schema migration or
   market acquisition is required. `GET /api/v1/strategies` exposes complete rules.
2. In `/lab/candidates`, select a published Strategy version, snapshot/source and
   a covered completed session with next-session lookahead. In the committed
   synthetic snapshot,2028-07-18 exercises the independent alternative-family case.
   Run `Evaluate pinned inputs`; wait for the durable worker's completed result.
3. Inspect the actual family explanation, ranks, exclusions, constraints, full
   config/hash and stored feature/score evidence. Mean reversion shows distance
   below its moving average; low volatility shows volatility without invented
   momentum columns. Both preserve `Paper only` and synthetic/source labels.
4. Follow the [publication workflow](strategy-registry.md) to copy a complete
   config into a named identity or append a version. The full version editor is
   owned by #73; the candidate page is an existing diagnostic surface.

Mean-reversion features carry `kind`, `mean_reversion_distance`,
`mean_reversion_sma` and `volatility`; scores carry `kind`, `mean_reversion_z` and
`score`. Low-volatility features carry `kind` and `volatility`; scores carry
`kind`, `volatility_z` and `score`. Existing momentum evidence keeps its original
shape. Config/evidence family mismatches fail validation rather than reinterpret
stored values. Each complete result pins its version/config, snapshot, calendar,
cutoff and engine build; repeat equal inputs on an equal build for equal hashes.

Closed signal variants reject unknown/cross-family fields, unsupported kinds,
missing values, invalid windows and executable expressions. Config publication
validates syntax separately from data availability. Missing scheduled history is
an explicit exclusion/cash-only result; no history is invented. Source membership,
availability and action-accounting limitations apply unchanged to every family.

## Seed upgrades and durable identities

Template roots use the ADR-011 stable UUIDv5 identities and keys
`mean_reversion_v1` / `low_volatility_v1`; version1 is UUIDv5(root,"1"). Metadata
names prefer `Mean Reversion` / `Low Volatility`. If a user already owns a casefold
matching name, bootstrap preserves it and reserves the first free
`<name> (template N)` name instead. Repeated/concurrent startup reuses that stored
metadata name and never renames the user or rewrites a published config.

Bootstrap validates every packaged config against independent canonical/hash
vectors before publication, in the existing atomic bootstrap transaction. Failure
rolls back; conflicting stable identities fail visibly. Appended versions and
pinned diagnostic references survive repeat startup/restart. Old stored momentum
results remain readable. A binary predating alternative kinds rejects them;
restore a compatible backup for a downgrade, rather than reset or reinterpret data.

## Independent verification

`data/fixtures/template_extensions/` extends FIX-01/02 without changing existing
snapshot or case bytes. `scripts/template_oracles/` contains separately authored
canonical config bytes and60-digit Decimal feature/score literals. The fixture
generator copies/indexes them and imports no production calculation. At session
index401 (2028-07-18), the full252-session snapshot case ranks C,A,B for mean
reversion and A,B,C for low volatility. Default caps produce0.20 per selected
stock and0.40 cash. A separate top2 parameter probe produces distinct selected
pairs, each0.20, and0.60 cash. These are **SYNTHETIC_DATA_ONLY** arithmetic examples.

Tests exercise signs/windows/sample denominator, population ties, all-zero and
positive-zero-dispersion differences, no future bars, missing/empty history,
canonical bytes, unsupported fields and shared capped targets. Real PostgreSQL
proofs cover an upgrade with user-name collisions, concurrent bootstrap,
immutable original/appended versions, actual restart and both real supervised
worker reruns. Offline Docker/browser smoke exercises each family at mobile and
desktop widths and checks equal result hashes and persistence after restart/rebuild.
Native release verification uses the same journey when the release owner runs it;
source tests alone do not claim a published0.0.3 release or platform evidence.
