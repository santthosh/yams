# ADR-015: Public paper controls and explicit synthetic replay

Status: Proposed under #50. Acceptance requires the owning reviewed PR and its
required checks. This draft activates no endpoint or provider capability.

## Context and authority

ADR-001 owns the cutoff, strict next opening, pricing and costs. ADR-004 owns
approval, reservation, idempotency, cancellation and ledger transactions.
ADR-014 retains separate original decision and later execution evidence.
ADR-008 assigns concrete approval/dismiss/cancel/recovery contracts to #50.

The delivered recommendation API distinguishes explicit synthetic replay from
actual computation time. Authored fixture sessions can be future-dated relative
to the local computer. Public paper controls therefore need a durable, visible
replay clock and an explicit operator step before fixture execution. Real-market
approval uses actual server UTC. Existing real providers remain diagnostic-only
for accounting; this decision grants no additional source capability.

## Public lifecycle

| Method and path | Request | Result |
|---|---|---|
| `POST /recommendations/{id}/apply` | Required UUID `Idempotency-Key`; expected portfolio revision | HTTP202 immutable approval/resource identity |
| `GET /recommendations/{id}/apply-result` | Required original UUID key header | HTTP200 original approval identity; no new approval |
| `GET /order-batches/{id}` | No mutation fields | Current typed batch/orders and source/clock provenance |
| `POST /recommendations/{id}/dismiss` | Closed empty JSON object | Disposition only; original content retained |
| `POST /order-batches/{id}/cancel` | Closed empty JSON object | Actual durable batch state after cancellation race |
| `POST /order-batches/{id}/advance-fixture` | Closed empty JSON object; required UUID key | HTTP202 original job/observation identity for one explicit replay step |

Paths above are under `/api/v1`. All new request/result models and generated
client definitions are coordinated with the implementation. No HTTP body accepts
prices, amounts, quantities, `approved_at`, `cancelled_at`, observation timestamps
or arbitrary clock changes. Same-origin JSON rules remain enforced by the web
proxy, with only scoped methods, query parameters and validated keys forwarded.

Approval results retain immutable batch identity, original key, revision,
approval instant and eligible opening. GET provides subsequently changing order
states. Exact retry recovers original approval before current data/version/time
checks, including after a lost response or source-file failure. Different inputs
under a known key conflict. A HOLD result without executable orders has no batch
to authorize; report that explicitly rather than manufacturing an order.

Dismissal serializes with approval on the recommendation row. Ready or expired
analysis can become dismissed; dismissal retry retains that disposition. An
already applied decision cannot be dismissed to reverse its authorization.
Cancellation delegates to the existing controller and closes only outstanding
intent. Fill-first retains committed effects and returns the actual filled or
partial state; cancel-first prevents remaining posting. Terminal retries create
no extra financial event.

## Server-owned clock and audit

The public controller selects its clock under the same portfolio lock as the
operation. For synthetic replay, the durable clock floor includes original
approval/decision timing, posted ledger chronology and accepted fixture-fill
observation clocks. [ADR-016](0016-portfolio-review-scheduler.md) adds explicitly
requested manual synthetic review cutoffs as durable clock observations so cash-only
portfolios can progress without inventing a batch. Scheduled reviews must already
be due and cannot advance the clock themselves. Accepted failed/cancelled step jobs still document an
operator-issued clock advance. Their original immutable payloads prevent a later
request from rewinding time merely because no fill posted.

New synthetic approval uses the later of that floor and the selected original
decision cutoff/creation time. Cancellation uses the current durable floor.
Original approval instants never change during retry, cancellation, worker
recovery or later data publication. The first eligible opening remains strictly
after both approval and cutoff under ADR-001. Late approval cannot claim a past
opening.

The actual UTC operator request time is retained separately in immutable ledger
event details. Existing private fixture callers can retain their explicit trusted
clock seam; omitted new audit metadata preserves their original serialized
content. Public requests supply neither timestamp. Unknown audit metadata in
older private records remains unknown rather than being reconstructed.

Clock computation and current-state validation occur while holding the portfolio
lock. Source files are verified before that lock and their registered references
are rechecked within it. This prevents an advance/cancel/approval interleaving
from silently choosing an earlier clock. A stale or changed original state
requires reevaluation instead of changing the original recommendation.

## Explicit fixture advancement

An operator may advance an already approved synthetic batch to the next completed
session in a verified pinned calendar. A daily bar can become available at close;
the step therefore uses a completed session rather than pretending the opening
quote was available earlier. It does not change the original eligible opening or
select a different day's execution price when that opening is missing.

The controller persists the chosen observation time in the existing closed
`ScheduledFillPayload.fixture_observed_at` and queues bounded work through the
existing fill service. It derives time on the server; it does not add a general
clock service or accept a caller timestamp. Unknown calendar coverage, unsafe or
incompatible sources and missing required evidence retain explicit error/pending
states. No weekday, price or corporate action is invented.

Step retry resolves the original key before deriving another session, returning
the original job and observation instant. A new key represents another explicit
operator step. An active fill attempt prevents overlapping new steps; its current
job remains inspectable. A terminal batch accepts no new work, while retry of an
earlier accepted key still recovers that original operation.

The worker may continue remaining authorized orders at the same persisted
observation instant, subject to existing cash/chronology/lease checks. Restart
resumes original work and clocks; it does not advance a fixture to tomorrow.
Portfolio schedules belong to #51. Monitoring remains paused while Docker is off.
The future #52 screen must label synthetic time and show an explicit advancement
action rather than silently simulating future sessions after approval.

## Errors and proofs

Use structured domain conflicts: changed keyed inputs map to409
`IDEMPOTENCY_CONFLICT`; changed revision/version/disposition or terminal action
maps to409 `STATE_CONFLICT`; stale/incompatible decision data maps to409
`STALE_DATA`. Invalid/no-order requests return422, unknown resources404 and
unavailable storage503. Error messages do not expose provider payloads or tokens.

Implementation must prove FIX-04/06/09 through HTTP, actual PostgreSQL and the
bounded worker: duplicate concurrent approvals, response-loss/key lookup,
changed-body conflict, strict late-opening choice, no approval-time holding/cash
change, monotonic replay clocks, advance/cancel/fill races, already filled effects,
source/calendar failure, immutable audit metadata and exact retry after restart.
Existing canonical financial payloads, arithmetic and private replay proofs must
remain compatible. An actual offline Docker journey must obtain a real
recommendation, approve pending intent, explicitly step to supported evidence,
observe durable synthetic fills and retain the original result after restart.
