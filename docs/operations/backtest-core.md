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

## Internal persisted cores

`backend.backtesting.service.admit_core(engine, artifact_root, request)` atomically
pins the published strategy, verified snapshot and current build into an immutable
experiment row and a closed `backtest_core` queue entry. This is an internal Python
service for #40/#41 integration, not a public submission endpoint. The full input
request is stored as bounded canonical JSON text so the allowed statistical split
fraction never relaxes exact queue hashing or Decimal cash requirements.

The supervised child validates the pinned build/config/calendar/source again,
computes the core and stages `core.json` plus its hash manifest under
`experiment-staging/<job-id>-<attempt-token>`. The64MiB core limit is a hard bound,
not a truncated result. The handler does not open a DB connection or register artifacts; the
supervisor owns registration. Progress messages report completed sessions, stay monotone within an attempt and below100,
and are persisted by supervisor heartbeats.100 means the core seal committed.

Only the supervisor's `seal_core` may register a result. It verifies the full
input/window/phase lineage, acquires a digest lock, checks the live uncancelled
lease, fsyncs/no-replace publishes under `experiments/<manifest-sha256>`, rechecks
ownership/deadline and commits the core reference plus job completion together.
Inputs and core seals reject updates/deletes. Files reject tampering, symlinks,
hardlinks, path traversal, missing data and excess read budgets. A failed database
commit after rename leaves an unregistered orphan; recovery must recompute and
verify fresh staged bytes before reusing it. Never manually adopt or delete it as
a completed report. User data is preserved through additive0005_experiments.

`read_core_run(engine, artifact_root, experiment_id)` verifies persisted linkage,
status, content hash and complete input/window before returning an internal core.
Failed/cancelled/pending runs expose no completed core. Expired workers cannot
publish; bounded recovery uses the original inputs with a new attempt token.
Old queued engine hashes fail explicitly; completed older cores stay readable.
Provider credentials and market datasets are not included in committed evidence.

#40 consumes `CoreRun.result` for approved Q12 metrics/benchmark. #41 owns the
complete `backtest` job/API/report lifecycle: it must not project an internal
`backtest_core` success as completed `ExperimentRunV1`. All required metrics and
three sealed report references remain mandatory. Reuse this experiment aggregate,
core functions and publication checks; add a distinct revision for report storage
if needed. Public experiments/report/chart UI remain staged until their owners
land. No changed protection, broker route, new provider read or paid service is
required.
