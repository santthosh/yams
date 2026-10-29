# Seeded scenario comparisons

The source implementation for 0.0.5 adds a private numerical engine, immutable
forecast jobs and durable artifact inspection. Public recommendation/forecast
transport belongs to #49 and the Decision Center to #52. Their presence in the
versioned domain schema does not activate an HTTP endpoint. The published 0.0.4
bundle retains its original capabilities.

These are historical scenarios, **not calibrated predictions**. Fixture examples
are `SYNTHETIC_DATA_ONLY`. They neither approve orders nor change cash or shares.

## Fixed method

[ADR-006](../adr/0006-forecast-baseline.md) owns the method. Use the same last 253
scheduled adjusted closes ending at the decision session for every positive-weight
asset in either case. They yield 252 common return vectors. No forward filling,
older-window substitution, missing-position removal or future observation is
allowed. Current holdings outside the eligible strategy universe still need their
complete history. Adjusted returns do not receive dividends a second time.

NumPy 2.5.4/PCG64 draws a C-order `(5000, ceil(H/5))` int64 array of starts 0–247.
Each noncircular five-session block contains the **whole cross-asset vector**;
only the last tail is truncated. Both cases use the same vectors. Asset columns
are sorted canonical IDs. Zero-weight entries require no history. An asset union
larger than 16 gives an explicit unavailable result; it never reduces path count.

The horizon is 90 calendar days in New York local time from the pinned decision
cutoff, retaining local wall time across DST. Count the pinned future session
closes strictly after cutoff and at or before that endpoint. Do not assume 63 or 90
trading sessions. Real timezone rules must match the pinned byte identity;
synthetic fixtures use their explicitly declared US post-2007 rules.

Each case maintains its original constant weights; cash earns zero. This is a
frictionless constant-mix approximation, without subsequent order costs or taxes.
Archive unrounded float64 **gross growth factors**, starting at 1, for both cases.
They are not dollar-valued ledger paths. Current ending value is `V * G`; proposed
ending value is `(V-C) * G`, with the estimated initial slippage/commission cost
charged once. Trade notional is exchanged value, not a cost. Original decimal
capital/cost is retained through final money presentation so a known cent is not
lost at large NAV. Return calculations use stable equivalent equations, with the
same original V denominator. No cent rounding occurs between scenario steps.

P10/P50/P90 use sorted linear interpolation at `(N-1)*q`; exactly zero is not a
loss. The reported delta is proposed median return minus current median return,
not probability of outperformance. Money is rounded once with HALF_EVEN; all
statistics must be finite. Both all-cash cases need no history/RNG, but still need
known valuation, costs and a covered calendar. Zero gross return does not erase
a known upfront cost.

## Server-owned input and lifecycle

The private entry points are:

- `backend.forecasting.service.admit_forecast(engine, artifact_root, inputs)`
  returns forecast/job identities.
- `read_forecast(engine, artifact_root, forecast_id)` returns job status, pinned
  payload, optional immutable `ForecastV1` and registered manifest digest.
- `compare_scenarios(repository, inputs, forecast_id=..., engine_version=...)`
  is the shared calculation used by the supervised handler; it performs no
  financial or database writes.

`ForecastInputs` pins portfolio/revision, strategy/config identity, snapshot and
calendar hashes, source mode, as-of/canonical cutoff, valuation session, original
NAV, complete current/proposed weights and costs, and uint64 seed (default 42).
The recommendation owner must derive a coherent valuation and preview cost from
backend evidence before calling admission. This is **not** permission to expose
arbitrary user-supplied NAV, prices or trade-cost overrides as a public API.

Admission verifies immutable source/config files before locking the portfolio,
then checks current revision/version/mode and inserts forecast/job together.
The child opens the exact registered snapshot, verifies the engine build and
stages bounded output read-only with respect to PostgreSQL. The parent verifies
artifacts, original inputs, calendar, exact RNG stream and numerical results.
Only a current running lease within its deadline may rename/publish and register
the result; cancellation/lease/deadline are checked again after filesystem work.
Artifact identity, job completion and attempt completion commit atomically.
Progress reaches 100 only on that commit. Failed/cancelled work exposes no partial
scenario. An older queued build fails closed rather than being reinterpreted.

A model result with insufficient evidence completes as `status="unavailable"`,
a reason and null current/proposed outcomes. Missing values are never zero.
Malformed weights/capital/costs/seeds are validation errors. Reasons include
`VALUATION_UNAVAILABLE`, `COST_UNAVAILABLE`, `INSUFFICIENT_ALIGNED_HISTORY`,
`ASSET_UNAVAILABLE`, `UNSAFE_PRICE_BASIS`, `CALENDAR_UNAVAILABLE`,
`ZERO_SESSION_HORIZON`, `WORKLOAD_LIMIT` and `NONFINITE_RESULT` (including an
unrepresentable money scalar). This differs from a crashed/resource-limited job.

Current real research publications retain only one future calendar session;
they cannot support this 90-day model and return `CALENDAR_UNAVAILABLE`.
Do not invent additional exchange dates or fabricate a forecast. The committed
synthetic calendar covers 2027–2030; a covered fixture decision such as 2028-07-17
can demonstrate numeric scenarios, while a late 2030 decision cannot. Real feeds
remain diagnostic-only for accounting under the existing provider policy.

## Evidence, persistence and recovery

Additive migration `0007_forecasts` creates immutable forecast admission and
sealed-artifact records linked to the original job, account, strategy and snapshot.
It preserves existing balances, history, versions, snapshots and jobs and seeds
no accounts, recommendations or forecasts. Normal restart does not reset volumes.
Use the documented database/artifact backup procedure before upgrading.

The registered SHA-256 manifest bounds six fixed file names: `forecast.json`,
`reproducibility.json`, `returns.f64`, `indices.i64`, `rng-state.json`, `paths.f64`.
Unavailable/cash-only cases omit inapplicable files. Arrays are raw little-endian
C-order bytes with explicit shapes, row dates, asset order and units. The RNG
state is a separate hashed artifact, keeping 128-bit state out of JS numbers.
Paths are gross growth factors; original monetary inputs are separate. Keep
uint64 seeds exact through future public transport, following the experiment
canonical/raw JSON pattern rather than a lossy browser Number conversion.

The fingerprint normalizes decimal values and positive-weight ordering and binds
all immutable context, method/software/build versions, horizon/session list and
array/index/state hashes. Generated forecast UUID and publication wall time are
excluded. Separate UUIDs may legitimately share a numerical fingerprint.

Files are contained, hashed, private, fsynced and renamed without replacement.
An interrupted registration may leave an unreferenced directory; it is not a
public result. A retry may register only byte-verified identical evidence under a
current lease. Corrupt existing bytes are rejected, never overwritten to hide a
failure. Treat missing/corrupt registered evidence as an integrity problem.

Reads obtain the digest from the immutable database record and verify bytes,
shape and original context. They retain the recorded UTC endpoint/session list
and statistics; they do not rerun original results using another host timezone
or numerical build. This supports native API/Docker worker development and
restoration across hosts. Publication still performs full pinned-rule and
numerical verification; an archived read is not a publication bypass.

## Verification and numerical budget

`make test-integration` uses an isolated PostgreSQL project, including an actual
Linux worker, cancellation/expiry fences, post-rename rollback/retry, immutable
rows, populated 0.0.4 upgrade and completed/queued jobs after a real DB restart.
`make smoke` adds an explicitly authored private allocation/cost probe to the real
application and checks original results and unchanged cash after restart/rebuild.
It is not a recommendation producer or a fabricated public forecast route.

To repeat the bounded arithmetic diagnostic without provider data or credentials:

```bash
docker build -f infra/docker/integration.Dockerfile -t yams-forecast-benchmark .
docker run --rm --read-only --network none --cpus 2 --memory 2g --memory-swap 2g \
  --pids-limit 64 --entrypoint python -i yams-forecast-benchmark - < scripts/benchmark_forecast.py
```

The script applies its own 2GiB address-space/10 CPU-second limit and two-CPU
affinity before importing NumPy. Its neutral authored 16-column array exercises
5,000 paths/90 sessions, not market performance or predictive accuracy. The
[recorded measurement](../verification/48-forecasts/benchmark.json) reports only
that arithmetic process; it is not the full dataset/worker end-to-end latency.
See the [verification record](../verification/48-forecasts/README.md) for actual
checks and remaining staged work.
