# Historical experiment builder and report (planned 0.0.3, #74)

Open `/lab/experiments`, or use **Run selected version** in the Strategy Lab.
The latter carries the selected immutable strategy/version into the builder;
publishing another version does not change that selection or an earlier report.
The [experiment API](experiment-api.md) owns admission, financial calculations,
artifacts and cancellation. Comparison/challenge remains #43.

## Create an experiment

Choose a saved strategy and published version, then a synthetic snapshot, SPY
benchmark, half-open dates, positive USD capital, chronological holdout fraction
and unsigned 64-bit seed. Default capital is $1,000, holdout fraction 0.25 and seed 42.
The initial window starts at coverage start and uses the last covered session as
the exclusive end, reserving a covered session for the next-open decision cutoff.
Narrow it as needed; the builder keeps that lookahead boundary. Coverage estimates
do not establish adequate warmup or a usable exchange session.
The backend checks the actual pinned calendar, source and workload before queuing.

Known invalid ranges, missing inputs, blocked quality, invalid money/seeds and
invalid split disable submission. Storage failure is distinct from no inputs;
history failure is distinct from an empty history. Reload controls preserve
stored backend resources. Published versions, snapshots, version history and saved
experiments have explicit bounded pagination rather than unbounded loading.

Execution costs are readonly evidence of `us_eod_next_open_v1`: 10 bps adverse
slippage per side, zero commission, next eligible open. The public request does
not offer fee/slippage overrides. Current Tiingo/Yahoo snapshots remain diagnostic
sources without the historical accounting evidence required by the backtester;
the UI explains that limitation and stages historical creation to synthetic data.
No provider key or downloaded market dataset is required for this path.

## Inspect a durable report

Submission navigates to `/lab/experiments/{id}`. Queued/running jobs show progress
and cooperative cancellation. Cancellation requested, cancelled, failed, storage
unavailable and completed results are separate states. A late cancel conflict
refreshes status; it cannot relabel a completed result as cancelled. Failed or
cancelled runs expose no partial financial report and can be rerun explicitly.

Completed reports show:

- Source/provider, exact observed session, Paper only and synthetic-data labels.
- Full/development/holdout net metrics, observation counts, fees/slippage and
  holdout start. SPY/cash period statistics are available separately.
- Lazy-loaded Plotly equity/SPY/cash, backend drawdown and exposure charts, with
  exact keyboard-accessible tables and explicit partial-page/window labels.
- Stored holdings quantities and cost basis, cash, and bounded simulated execution
  pages with decision/approval/next-open timing, partial/skipped quantities and
  complete execution evidence. These records do not post durable paper fills.
- Immutable rules, source/config/calendar/core/report hashes, policies, seed and
  managed artifact identities. Financial calculations stay in the shared backend.

SPY is an adjusted-close, fully invested, friction-free approximation, with
initial-close and dividend conventions different from raw-price strategy
execution. Missing benchmark points remain gaps with explicit reasons; no
forward-fill or fabricated zero is inserted. Chart axes are numeric, and exact
money/quantity/exposure strings remain in the tables. Chart rendering failure
retains the table alternative.

Sample windows must be contained in the original half-open interval. Genuine
nontrading windows can be empty; artifact errors do not appear as empty results.
Load more controls retain the same window and page size for the returned cursor.
Charts show only loaded rows, with a partial-data notice until the window is fully
loaded. Summary metrics continue to describe the immutable original experiment.

Annualized values extrapolate the observed period under Q12's 252-session rule;
very short histories can produce extreme figures. Holdout is separately labeled,
never reset or automatically tuned. Repeated selection after inspecting holdout
results weakens independence. Backtest results are not forecasts.

## Exact reruns and compatibility

**Rerun with same inputs** creates another durable identity and keeps the original
result intact. Public detail projects `inputs_canonical_json` from the existing
immutable payload. It is validated against typed inputs and transported unchanged
through the generated client's body serializer, preserving seeds beyond
JavaScript's exact-number range. The web proxy validates/sanitizes response
envelopes while forwarding successful JSON text unchanged, so it cannot round an
upstream uint64 literal by re-encoding it. The builder also serializes validated seed text
as a numeric JSON literal without rounding it through a JS number.

This is a coordinated response/client addition; the financial request schema,
execution method, stored report bytes and existing artifact hashes are unchanged.
It needs no migration or report rewrite. Earlier completed reports can expose the
new projection from their retained canonical payload. Raw max-uint64 API reruns
and unchanged sealed files are covered by PostgreSQL tests.

The selected chart bundle is pinned in the workspace lockfile and loaded locally
only for completed charts; no CDN, cloud chart service or external telemetry is
required. Implementation references: [Plotly distributions](https://github.com/plotly/plotly.js/blob/main/dist/README.md)
and [function lifecycle](https://plotly.com/javascript/plotlyjs-function-reference/).

Verification uses unit/contract/type/lint/build checks, Playwright at 360px and
desktop with keyboard/Axe/tables and negative states, real PostgreSQL/restart tests,
and the full offline Docker form→worker→report→rerun/cancel journey. Committed
transport examples are labeled `SYNTHETIC_DATA_ONLY`; independent financial
expectations remain the pre-authored FIX-07 and Q12 fixture vectors.
