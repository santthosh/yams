# Backtest reporting handoff (#40)

[ADR-013](../adr/0013-backtest-reporting-methodology.md) ratifies Q12 before this
implementation. These are internal worker-side calculations over the shared
[core](backtest-core.md), not a public completed experiment endpoint. All committed
examples are `SYNTHETIC_DATA_ONLY`; statistics are descriptive historical measures,
not investment forecasts or calibrated predictions.

## Calculations and intervals

`backend.backtesting.metrics.calculate_metrics` consumes decimal-string daily NAV
and projected posted-fill costs. Its optional preceding close supplies returns
without becoming another owned daily NAV in turnover. `metrics_periods` composes
total/development/holdout from the same unchanged core cash/positions. The first
holdout return is included; no capital reset or additional trade is created.

Returns/drawdown/turnover use exact rational money inputs. Sample-return statistics
use80-digit Decimal arithmetic and finite numeric transport; bounded precision
avoids accumulating enormous unrelated rational denominators over long histories.
Volatility uses sample simple daily net returns and252-session annualization.
Zero variance makes Sharpe unavailable. Fees/slippage are summed once from actual
fill effects; NAV is already net and is never charged those costs again.

Every undefined ratio is `MetricValue(value=null, unavailable_reason=...)`, including
short/empty histories, zero denominators and unrepresentable annualizations. Known
zero trade costs, cash yield or observed volatility are distinct from undefined
ratios. Existing FIX-07 is normative; [extension vectors](../../data/fixtures/metrics_extensions/case.json)
were independently authored with standalone Fraction/Decimal arithmetic before
production reporting code. Original FIX-01–FIX-10 cases and snapshot artifacts remain unchanged; the suite index adds the extension.

## References, exposure and comparison

`benchmark_curve` retains every original pinned session and uses SPY adjusted-price
ratios at each Q17 cutoff. It requires the verified source, supported ETF identity
and usable evidence; it never drops rows, forward-fills or substitutes another
instrument. Gaps make benchmark statistics unavailable while preserving visible
missing points and portfolio statistics. SPY is a benchmark-only fully invested,
friction-free total-return approximation; flags disclose cash, initial-close
execution and dividend-recognition differences. No separate dividends are credited
to an adjusted-price benchmark. The explicit cash baseline earns zero.

`exposure_series` calls the shared close valuation over posted state and the pinned
accounting view, retaining evidence after universe exit. Ratios use that shared
unrounded exact valuation; reported NAV remains cents. Missing/incoherent marks or
zero NAV produce unavailable exposure. Positive-NAV all-cash has cash weight1 and
maximum position weight0. No portfolio/strategy/order math is moved to the frontend.

`ComparisonTerms` pins actual sessions/window, capital, source/snapshot, universe,
calendar, both core/reporting engines, execution policy/costs, benchmark and split.
Its canonical fingerprint and explicit `INCOMPARABLE_*` differences let #43 show
incompatible controls without declaring a fair winner. Different strategy families
or portfolio/scoring parameters can share terms; changed universe assumptions are
flagged. Repeated holdout selection and synthetic/short-sample caveats remain visible.

## Composition and ownership

`benchmark.calculate_report(payload, complete_core, verified_core_manifest_sha256,
repository)` composes validated complete evidence inside a still-running future
#41 report job. It checks nested input/window/decision/fill lineage and the pinned
source before calculation. It does not publish artifacts or complete a job. This
lets #41 compute core plus metrics, then atomically seal the final report without
pretending the public job completed before metrics existed.

`build_report(CoreRun, repository)` is a readonly wrapper for an already persisted
complete internal core. It rejects pending/failed/cancelled cores. Outputs contain
period counts/metrics, aligned SPY/cash, exposures, warnings, comparison terms and
separate core/reporting provenance. They serialize without NaN/Infinity and leave
all input/core artifacts unchanged. Reporting does not retune or rerun decisions.

#41 owns final report/artifact persistence, job lifecycle, cancellation and public
paginated API/generated types. It must require all domain completion fields before
exposing `ExperimentRunV1` as completed. #74 owns the honest report UI; #43 owns
comparison/challenge. Display the existing pinned execution-policy costs; do not
invent request-level fee overrides or a publishable SPY strategy. #68 reuses Q12
formulas with its separately owned cohort/overlap rules. Any changed financial
methodology needs a new version, coordinated ADR/spec/fixture changes and preserved
historical evidence.

Run `make lint-backend`, host and Linux strict typing, `make test-backend`, contract/
fixture checks, real PostgreSQL integration and full offline Compose smoke. The
smoke computes a real report in the bounded worker container from a persisted core
and checks independent metrics, SPY/cash, holdout and identical outputs through
restart/rebuild. It is not a public endpoint or UI-report demonstration. Run Docker
harnesses sequentially on constrained hosts; no resource/time guards are relaxed.
