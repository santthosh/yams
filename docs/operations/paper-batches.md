# Private paper authorization and eligible-fill worker

Issue #46 supplies backend orchestration for 0.0.4. All capital, orders and fills
are synthetic. Public recommendation production/apply/batch HTTP transport belongs
to #49/#50 in 0.0.5; this service does not expose an approval shortcut. Production
startup creates no recommendations or portfolios. Portfolio screens belong to #47.

## Producer and approval handoff

`backend.portfolio.batches.ExecutionIntentV1` is the closed internal execution
content stored under `recommendation.content.execution_intent`. It contains
`schema_version: 1`, the original engine version and positive six-decimal order
intents (`key`, canonical `asset_id`, `sector`, `side`, `requested_quantity`).
Keys and assets are unique; at most 1,000 intents are accepted. This is separate
from the full public recommendation/forecast view owned by #49. A producer must
store its real, immutable, hash-verified content alongside the linked portfolio,
strategy version, snapshot, revision, decision session/cutoff and source mode.
Tests insert explicitly labeled `SYNTHETIC_DATA_ONLY` envelopes; they do not claim
the 0.0.5 evaluator or forecast exists.

`approve_batch(engine, portfolio_id, recommendation_id, expected_revision=...,
idempotency_key=..., pinned=...)` consumes that stored intent. The caller must
load `pinned` through `verified_snapshot` outside any financial transaction.
The service checks its registered manifest, current mode-specific publication,
calendar, account/version/revision, immutable recommendation hash and disposition.
Exact retries return the original batch before freshness/revision checks; changing
the recommendation or expected revision under the same key conflicts. Another
key cannot reauthorize the same recommendation. A new approval cannot precede
posted history. Research approvals use the server UTC clock; only explicit fixture
replay can supply the trusted internal `approved_at` seam. It is not an HTTP field.

The portfolio lock serializes competing approvals. One nonterminal batch reserves
exclusive use of cash and holdings. Approval inserts the batch/orders, marks the
recommendation applied and appends one revision event atomically. **Cash and
holdings do not change.** Sells precede buys, ordered by asset and stable ordinal.
`read_batch` returns the typed private batch lifecycle without posting events.

`cancel_batch` locks the same portfolio and closes remaining quantities once.
Posted fills remain intact; a batch containing fills remains terminal partial
rather than hiding them behind a cancelled state. Repeated cancellation returns
its durable outcome. Fixture callers supply a coherent `cancelled_at` replay clock.
Cancellation cannot backdate a new event before posted history.

## Separate decision and execution evidence

[ADR-014](../adr/0014-decision-and-execution-snapshots.md) retains the original
recommendation/batch snapshot, cutoff, approval time, policy and calendar. A later
immutable publication may supply the opening for the **original eligible session**.
The shared kernel's paired optional `execution_snapshot_id` and
`execution_snapshot_sha256` identify this source. They are omitted when absent,
so existing same-source execution/core artifacts retain their canonical bytes.
Generated OpenAPI/TypeScript definitions include these additive optional fields.

Both sources must be registered and hash-verified. Source mode, provider,
normalization, price/action basis and canonical asset/currency identity must agree.
A later calendar may extend coverage but must retain the original selected
session's identity/timezone/open/close. Wrong calendar/source/asset, blocked data,
future availability or missing original opening cannot create a fill. Fill events
link the actual execution snapshot; the original batch reference never changes.
Worker events and attempt diagnostics also retain the actual execution engine
fingerprint; the original decision build remains in the frozen context. The
fingerprint is computed before financial locks and checked again at publication.
The event identity remains order/policy/original session/logical ordinal, not job
attempt, publication or observation time. A changed explicit posted payload
conflicts; a completed job retains its original result after lost acknowledgment.

**Delivered real providers remain diagnostic-only.** This orchestration currently
rejects research accounting sources. Interface additions do not establish missing
raw-price/action/publication rights or capabilities. No fallback silently replaces
real evidence with fixtures.

## Admission, scheduling and publication

`enqueue_batch_attempt(queue, batch_id, fixture_observed_at=...)` is a trusted
private admission boundary. A fixture attempt requires an explicit replay clock;
research uses wall time. Before the eligible opening no job is enqueued. The
closed `apply_scheduled_fills` payload carries IDs/hashes and session identity,
not prices, credentials, arbitrary code or a new approval. Snapshot workload
metadata and persisted ADR-005 resource limits bound admission and execution.

The supervised child opens verified source files and prepares bounded evidence.
It never writes financial database state. The supervisor acquires the portfolio
lock, checks current queue token/lease/deadline/cancellation under the job lock,
revalidates immutable approval/source linkage, and recalculates using the shared
kernel against current posted balances. One action **or** one order effect and
the corresponding job result commit in one transaction. Failure before commit
rolls back both. The authority/deadline is checked again before completion.

Each sell therefore commits before a subsequent job may reuse its proceeds for a
buy. Corporate actions retain entitlement/payment chronology. Unsupported pending
split adjustments and revised economic evidence require reevaluation/correction.
Ex-date capture and payable recognition are separate chronological commits. A
positive entitlement without reliable payable evidence keeps the whole affected
batch pending, including trades in another asset; a later compatible publication
may supply that evidence without reapproval. Ambiguous same-session actions block
for reevaluation. Later-session fills, actions or correction credits cannot fund an earlier pending
order. No catch-up path rewrites financial history or approval time.

The worker's normal scheduler scans at most the configured catch-up batch in
original eligible-open order. Semantic keys include order, execution source and
posted revision; repeated polls of unchanged state/evidence return the same job,
including terminal failures/cancellations. Missing opening evidence leaves the
order pending with a reason. A newer compatible publication permits another
attempt for that same session. Explicit fixture attempts persist their replay
clock in the job; after restart the scheduler may continue remaining orders at
that **same** instant, never invent tomorrow's fixture clock. An approval alone
does not start automatic fixture time travel. Advancing a fixture replay is an
explicit backend/test operation.

Job cancellation stops that job's remaining publication authority. Batch
cancellation revokes all remaining approved intent. Neither reverses an already
committed fill. Cancelling one job is not an implicit cancellation of the entire
standing batch. The scheduler can consider new evidence for still-approved intent.
Monitoring/catch-up runs only while Docker is active; no always-on claim is made.

## Verification and inspectable examples

Run `make test-integration` in its disposable Docker project. The focused suite is
`backend/tests/integration/test_paper_batches.py`; it includes actual supervised
worker execution and separate `restart_verify` cases run after PostgreSQL restarts.
Never point these tests at user volumes. Existing ledger tests retain independent
FIX-03/04/05/09 accounting, concurrency, fault, crash and replay coverage.

An authored fixture trace buys two SYN:AAA shares at raw 70.050 with 0.001
slippage: executed 70.120050, debit 140.24, remaining cash 859.76 and basis 140.24.
This exact expected result is independent of the production accounting functions.
The two-publication case first publishes a decision source whose bars end at T,
then publishes the immutable source containing T+1. It verifies unchanged decision
bytes/approval, the original eligible opening, and the execution event's distinct
source reference. Missing-open recovery uses the same approval, not a replacement.

Tests also cover concurrent same/different-key approvals, stale revisions,
reservation, late approval, no balance mutation at approval, cancellation-first,
completion-write fault rollback/retry, and completed/pending jobs across a real
PostgreSQL restart. Pure kernel tests retain fixed pre-change serialization hashes
and reject mismatched/partial execution references and future/missing prices.
These proofs are synthetic accounting evidence, not investment results.
