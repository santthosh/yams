# Immutable portfolio recommendations

The source implementation for 0.0.5 adds recommendation production and forecast
read APIs. Public approval/dismissal/batch transport remains #50, scheduling #51,
and Decision Center screens #52. This source work does not publish 0.0.5 or change
the immutable 0.0.4 bundle.

Capital, orders and holdings are synthetic. Current real providers remain
diagnostic-only for accounting. These APIs never approve an order or post cash,
shares or fills. Startup creates no recommendations or accounts.

## Explicit inputs and clocks

Create an account through the existing portfolio API, then submit:

```http
POST /api/v1/portfolios/{portfolio_id}/recommendations
Content-Type: application/json
Idempotency-Key: <optional UUID retained for retries>

{"as_of_session":"2028-07-17","clock_mode":"synthetic_replay","seed":42}
```

An optional `snapshot_id` selects registered evidence in the account's own source
mode; otherwise admission freezes its current valuation snapshot. The server
freezes posted cash/positions, revision/ledger sequence, strategy/config, source
and calendar hashes, canonical cutoff, engine build and uint64 seed. Prices,
NAV, costs and operator approval timestamps are not public overrides. Unsupported
real accounting inputs fail honestly; they never switch into fixture values.

`clock_mode` is required. A synthetic account requires `synthetic_replay`, making
the authored fixture clock explicit. The decision cutoff remains the next pinned
session opening minus one hour. Posted state observed after that cutoff cannot
be used for an earlier decision. Real decisions cannot precede their cutoff;
no supported real provider is promoted to accounting by this interface.

Fixtures contain explicitly authored future-dated sessions. For those replay
results, `created_at` is the later of request admission and the logical cutoff;
`computed_at` retains the actual UTC publication time. History's `created_at` is
actual admission time. `clock_mode` and `data_status` distinguish this replay from
an observed market decision; a future fixture date is not knowledge of real prices.
No public request accepts `approved_at`, and evaluation does not advance time or
authorize an execution.

With a key, exact request retries return the original recommendation/job before
reconsidering current state or data. Different inputs under the same portfolio/key
conflict. Without a key, a new request creates a new immutable evaluation identity.
Retain canonical JSON fields for exact full-range seeds; parsing a uint64 into a
browser Number and serializing it again can change its value.

## Asynchronous lifecycle and reads

Admission returns HTTP202 with `recommendation_id` and `job_id`. The supervised
`evaluate_portfolio` worker uses the shared strategy, capped allocation, valuation
and order planner. It performs no database/economic writes. Its fenced publisher
registers original recommendation evidence and enqueues the existing `forecast`
job in one transaction. Recommendation completion does not claim forecast completion.

| Read | Behavior |
|---|---|
| `GET /jobs/{job_id}` | Existing job status/progress/error contract |
| `GET /portfolios/{id}/recommendations` | Bounded history including queued/failed/cancelled runs; `limit`1–100 and portfolio-scoped cursor |
| `GET /recommendations/{id}` | Immutable original analysis plus current disposition/applicability and separate forecast job/result |
| `GET /forecasts/{id}` | Completed `ForecastV1`, including explicit completed-unavailable results |

A known unpublished recommendation or incomplete forecast returns HTTP409
`STATE_CONFLICT` with safe `details.job_id`, `details.status` and `details.kind`.
Poll the identified job. Failed/cancelled jobs retain those states and their job
errors; they are not fabricated `available` or model-unavailable forecasts.
Only forecasts linked to an actual published recommendation are public. Unknown
IDs return404, invalid inputs422 and missing/corrupt storage503. The local web
proxy allows only these scoped routes and preserves exact successful JSON bytes;
it strips private upstream messages and unrelated error details.

Reads release their initial DB connection before opening artifacts/forecast
storage, preserving the bounded pool under concurrent requests. History projects
small summary fields rather than loading every frozen holding/job payload.
GET never changes financial state or recommendation disposition.

## Evidence, preview and scenarios

Every published result retains complete targets and cash, every selected/rejected
candidate, original feature/score contributions, constraint evidence and measured
BUY/SELL/HOLD explanations. `strategy_evidence` retains typed indicator prices and
data diagnostics in addition to the summary candidate fields. Empty eligibility
produces cash targets with reasons. Under-band changes can remain HOLD; mandatory
risk corrections still use the shared minimum, quantity and cash rules.

Action `estimated_notional_usd` is quantity times raw decision-close price, rounded
for display; adverse slippage/commission is reported separately in total cost.
Requested intent remains distinct from the preview's executable quantity. The
stored execution intent is not an approval, reservation or posted fill.

Forecast inputs use complete current weights and feasible post-preview weights,
including cash and quantity/minimum/cash constraints. This keeps an all-HOLD
comparison unchanged rather than pretending an under-band target was traded.
The estimated upfront slippage/commission is charged once under ADR-006. Target
weights remain inspectable separately from feasible preview weights; no frontend
performs financial calculations. Scenarios remain the historical constant-weight
approximation described in [forecast operations](scenario-forecasts.md), not
calibrated predictions or promises of next-open prices.

Required missing marks or unposted/conflicting corporate-action state fail
evaluation with a safe reason. A preview cannot repair the ledger or assume a
missing split, entitlement or dividend has posted. An already captured entitlement
waiting for its reliable future payable session does not become spendable cash.
Missing forecast history/calendar instead yields the existing explicit unavailable
model result while preserving the truthful recommendation analysis.

## Immutability, stale evidence and recovery

Migration `0008_recommendations` adds immutable computation/publication linkage to
the existing recommendation identity/content table. It creates no fake economic
rows and preserves earlier versions, jobs, forecasts and ledger history.
Canonical JSON strings preserve original statistical tokens inside the existing
float-free ledger content digest; the approval service can verify that same digest.
Reads expose original evidence rather than recalculating explanations/forecasts
under a newer build. The original source files/hashes remain required.

Publication checks portfolio/job authority under the same lock order as posting.
Cancellation or an expired/replaced lease cannot publish. Recommendation content,
forecast admission/job, publication record and evaluation-job completion commit
together. A failed transaction leaves no partially published recommendation or
forecast job. Retry does not post economic effects.

A revision/version/source change during computation preserves original analysis
with `expired` disposition. Later changes are reported through `is_current`,
`current_portfolio_revision` and `stale_reasons` without changing original content.
The eventual approval controller still verifies current state atomically; a GET
response is not authorization. Normal restart/upgrade never resets volumes.
