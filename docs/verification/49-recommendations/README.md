# Recommendation and forecast API verification

Source work for #49 produces immutable recommendations from the shared strategy,
allocation, valuation and order planner, then enqueues the existing bounded
forecast job. Public approval/dismissal remains #50, scheduling #51 and screens
#52. This record does not claim a published 0.0.5 release.

All financial inputs and results here are **SYNTHETIC_DATA_ONLY**. The
[recorded application evidence](evidence.json) demonstrates reproducibility and
persistence; it is explicitly not an independently derived financial oracle or
market performance. The committed test oracles independently derive quantities
and costs from authored inputs under ADR-001/FIX-03.

## Numerical, temporal and transport proofs

The 11 focused recommendation tests pass: complete selected/rejected evidence,
known six-decimal quantities and raw notional/costs, all-cash targets, under-band
HOLD, mandatory risk reduction, missing held marks, cancellation, exact uint64
inputs, posted-state chronology, held sectors outside eligibility and unposted
split/dividend guards. An already captured entitlement waiting for its reliable
future payable session does not create spendable cash. Shared forecast and
market repository tests remain passing.

The full backend suite passes **453 tests** and the full web suite **72 tests**.
Proxy tests cover only permitted methods/paths, same-origin/key rules, exact
request/response seed tokens and sanitized pending/failed job details. Request
and response schema seed bounds remain exact integers. OpenAPI generation
reproduced FastAPI's uint64-bound float coercion; the existing narrow normalization
now covers the new request and forecast field, while conflicting definitions
still fail. Every previous standalone contract and every previous route definition
is semantically unchanged.

`make lint typecheck`, `make contracts-check fixtures-check`, `make build`, local
Markdown/link review and whitespace checks pass. All 30 canonical fixtures verify;
no fixture snapshot bars, calendar or manifest changed. Python package and native
production web builds pass. No UI screen source changed; the actual existing
browser journeys are retained in the Docker proof below.

## PostgreSQL and durable worker proofs

Full `make test-integration` passes **158 cases plus 9 actual restart checks** in
disposable project `yams-it-c364a593ca80`. A focused predecessor passes 10 cases
plus 1 actual restart check in `yams-it49-881598d65e9d`. The full tested Linux
image's production Python source hashes exactly match the implementation.

Actual services prove frozen admission, concurrent keyed retries, pagination,
real Linux recommendation and forecast workers, completed numerical and explicit
calendar-unavailable results, no recommendation-time financial effects,
cancel/expiry fencing and immutable records. The existing private approval
controller consumes the new canonical content digest and real stored intent;
a revision change between computation and publication preserves expired original
evidence and prevents it being presented as current. A completion-write failure
rolls back the recommendation, publication and forecast/job graph, then one
current-lease retry publishes exactly once.

Final publication review reproduced a late lease/deadline expiry after graph
insertion: the prototype could complete without a second check. The regression
failed before correction. The publisher now flushes all graph writes and checks
current authority again immediately before completion; expiry rolls back every
insert. The new regression passes along with the refreshed full PostgreSQL and
24-check Docker proofs. Final strict types/static checks and 60 affected
recommendation/forecast/queue unit tests pass; the exact final backend package
also builds successfully.

Populated 0007→0008 upgrade retains original accounts, funding, snapshots,
strategies, completed forecasts and queued jobs without creating recommendations.
Completed recommendation/forecast content survives actual database restart;
queued original inputs resume through both workers. Two concurrent detail reads
retain original results with the bounded connection pool. Existing ledger
concurrency/crash/replay and prior backtest/forecast restart checks pass.

Two prototype test issues were corrected without loosening contracts: raw JSON
requests needed the required content type, and actual publication timestamps
needed RFC3339 UTC `Z`. A TypeScript error-detail narrowing was also corrected.
Their corrected paths pass the actual worker/API and static checks.

## Actual offline application journey

Full `make smoke` passes **24 checks** in disposable project
`yams-smoke-9cb9ed5d4204`. The browser-facing same-origin API creates a real
recommendation on the cash account, retries its original key, waits for both
supervised jobs and reads a numerical forecast with seed 18446744073709551615.
The default authored snapshot yields three 20% targets plus 40% cash, independently
checked preview quantities and estimated upfront cost 0.60. Current cash remains
1000.00 with no holdings, one funding event and no fills.

Original request, analysis, candidates, targets, costs, timestamps and forecast
survive actual restart and rebuild. A later owned execution publication may
change current applicability; it does not change original evidence. The API's
current-state envelope is deliberately checked separately from immutable content.
Existing desktop/mobile/keyboard/Axe Strategy Lab, reports, fair comparisons,
account/ledger, private fill/forecast, offline networking and migration-failure
recovery checks pass. Startup seeds no recommendations or accounts. No user
credentials, licensed provider data or private volumes were accessed or changed.
