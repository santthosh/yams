# Forecast engine verification

Source work for #48 implements the private ADR-006 comparison and worker.
Public recommendation/forecast APIs and screens remain #49/#52. All observations
and allocation/cost probes here are `SYNTHETIC_DATA_ONLY`; no provider dataset or
credential is included.

## Independent numerical and temporal proofs

31 focused tests pass: committed FIX-08 whole-vector/index/matrix hashes,
noncircular tail, shared shocks/identical cases, linear quantiles, fixed seed,
zero cash yield/one-time costs, explicit unavailable cases, method fingerprints,
DST/local-calendar conversion, actual Parquet future changes and late required
observations, byte/shape/RNG/symlink guards and immutable archive reads.
The full backend suite passes 442 tests; strict Python formatting/lint/types pass.
The 30 canonical fixture check passes. Only the authored FIX-08 precision case
and top fixture manifest changed; underlying snapshot bars/calendar/hash remain
unchanged.

A prototype one-cent cost at NAV 1e21 could disappear through float cancellation,
producing unchanged capital and loss probability 0. The focused test reproduces
that failure before correction. Unrounded gross growth factors plus exact initial
capital/cost and stable return equations now preserve the known cent, negative
return and loss probability 1. The independent literal oracle is committed in
FIX-08. Nearly complete costs and the original-NAV denominator also pass.

## Durable worker and migration proofs

Focused actual PostgreSQL verification passes 9 cases plus 1 actual restart check
in disposable project `yams-it48-400940415b69`. Actual Linux worker computation,
immutable reruns, no cash/fill changes, cancellation/expiry fencing, completed
unavailable results, old-build rejection, post-rename completion-write rollback
and verified-orphan retry, stale context, populated 0006→0007 upgrade and both
completed/queued jobs after restart pass. Production source hashes in the tested
image exactly match the current implementation.

Full PostgreSQL verification passes 148 cases plus 8 actual restart checks in
`yams-it-2fccb0ec049f`, preserving all existing ledger/backtest/queue proofs. Two
older table-presence assertions were updated for the intentionally delivered
forecast tables; diagnostics now additionally assert no forecast or economic
rows were created. A broad pytest collection collision was corrected by giving
the new tests their own package. Neither change weakened financial assertions.

The full actual application Docker smoke passes **22 checks** in disposable
project `yams-smoke-0ae2f0238910`. It creates an explicitly authored private
scenario probe, runs the real worker, verifies numeric current/proposed results
and original artifact/payload identity after actual restart and rebuild. The
probe account retains $1,000 cash, revision 1, one funding event and no holdings or
fills. It performs no recommendation, approval or invented public API request.
[The recorded application evidence](evidence.json) is reproducibility/persistence
proof, not an independently derived financial oracle. Existing Strategy Lab,
comparison, account browser, keyboard/Axe and migration-recovery checks pass.
No user volumes or credentials were touched. Public interfaces remain staged for
#49/#52; this source work is not a published 0.0.5 release.

## Numerical resource probe

[The measurement](benchmark.json) records an actual native aarch64 Linux process
with read-only filesystem, no network, two CPUs, 2GiB container/address-space cap
and 10 CPU-second limit. A neutral authored 252×16 matrix, 5000 paths and 90 sessions
produced the expected 2×5000×91 gross-factor shape in about 0.029s, with process peak
RSS 64,504 KiB. These are arithmetic-process measurements; imports/dataset validation,
queue/DB/publication latency and investment performance are separate concerns.
The [operations guide](../../operations/scenario-forecasts.md) gives the
reproducible command and documents method, caller responsibilities, unavailable
states, artifact format, immutable reads and recovery limitations.
