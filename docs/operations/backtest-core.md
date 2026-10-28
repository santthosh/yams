# Walk-forward core handoff (#39)

This is an internal Python engine for milestone0.0.3, governed by
[ADR-012](../adr/0012-walk-forward-core.md). It uses synthetic capital only. It is
not the public experiment service or a complete report. The0.0.2 release remains
the published diagnostic installation.

`backend.backtesting.runner.run_backtest(repository, request, config,
engine_version=..., cancelled=...)` consumes one already verified
`MarketRepository`, validated immutable `ExperimentRequest` and `StrategyConfigV1`.
It performs no network or database writes. It returns a `BacktestCoreResult` only
when the full replay succeeds. `BacktestFailure.reason` is a bounded server-owned
reason; cancellation never returns a success-shaped partial result.

The output pins the original request (version/snapshot IDs, policy, capital, date
window, benchmark, seed and split), config/snapshot/calendar hashes, engine build,
source and policy version. It carries ordered daily NAV/cash/positions, shared
candidate/allocation/risk evidence, order plans, original-open execution effects,
corporate actions, holdout boundary and warnings. Existing published strategies
and previous diagnostic results remain immutable. No random strategy optimization
or automatic holdout selection is performed.

The first selected close is an all-cash capital baseline. Decision previews cannot
change that state. Initial and calendar month-end decisions fill at an in-window
next eligible opening under Q17; true calendar lookahead is required. The final
partial month is not forced to rebalance, and the final position is not liquidated
for reporting. Development and holdout share the same continuing portfolio.

Shared `backend.portfolio.valuation.value_close` supplies exact rational
position values and explicit cent NAV to both planning and reporting. It refuses
missing held/required marks. `MarketRepository.accounting_as_of` retains validated
prices/actions outside active membership; its asset list still describes the
eligible universe, and the runner uses ordinary `as_of` for every decision.

Strict replay gaps fail the whole core instead of substituting prices or
retroactively revising already reported closes. Unsupported split/order crossings,
nonrepresentable split shares, late required actions, ambiguous held-asset action
ordering and unknown nonzero dividend payable dates also fail. Known dividend
entitlements survive sale; cash credits once at the validated payable session.
Uncredited entitlements are inspectable and excluded from cash/NAV. Sector-evidence
conflicts remain the shared planner's validation errors, not invented mappings.

Real sources need explicit verified historical raw execution, action, publication
and membership capabilities. `supports_diagnostics` is insufficient. The present
Tiingo observations remain diagnostic-only; this work needs no new token/data
request or redistribution of provider observations. All committed examples are
clearly `SYNTHETIC_DATA_ONLY`.

The independent [cent/event oracle](../../data/fixtures/backtesting/core-case.json)
is authored in `scripts/backtest_oracles/` and copied/indexed by `make fixtures`.
Expected cash, shares, split basis and distributions come from standalone decimal
calculations, never calls to production backtesting/accounting functions.

Verification: `uv run --locked pytest backend/tests/backtesting
backend/tests/portfolio backend/tests/market_data`. Run normal lint/type/fixture
and contract checks as documented in README. Existing fixtures are copied to
private temporary paths before secure reader tests, preserving any user hardlinks.

Remaining #39 work is fenced artifact publication, additive0005_experiments
persistence and supervised worker/restart/cancellation integration. #40 consumes
sealed core series for Q12 metrics/benchmark; #41 exposes completed reports only
with all required metrics and sealed references. Keep #39 open and #40 blocked
until the complete prerequisite artifact, not just this pure phase, is delivered.
