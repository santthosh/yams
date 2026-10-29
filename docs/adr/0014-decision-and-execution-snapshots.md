# ADR-014: Separate decision and execution snapshot provenance

Status: Accepted by PR #131 on 2026-10-29 under #46. Coordinated implementation
and worker proofs belong to #46. This decision itself activates no endpoint,
handler or provider capability.

## Problem and authority

ADR-007 makes published snapshots immutable. ADR-001 requires an order to use the
first opening strictly after its original decision cutoff and operator approval.
That opening is normally absent from the decision-time snapshot and arrives in a
later publication. The current shared kernel requires `ExecutionContext` and
`MarketEvidence` to name the same snapshot. Full historical fixtures can satisfy
that condition, but a prospective worker cannot add tomorrow's bar to yesterday's
immutable snapshot or truthfully label a later snapshot's bar with the older hash.

Resolve this interface gap while preserving ADR-001 prices/timing, ADR-002 action
accounting, ADR-004 immutable intent/idempotency and ADR-005 publication fencing.
The same Python execution implementation remains shared by backtests, paper
accounts and Arena. No financial default, new broker integration, new approval
route or forecast assumption changes.

## Decision provenance remains frozen

The recommendation and batch retain their original `snapshot_id`/hash, strategy
version/configuration, decision session/cutoff, original approval instant, calendar
hash, policy, requested intent and request hash. Later price publications cannot
recompute an old ranking, change its original universe, backdate approval or
silently replace that decision snapshot. Approval retry returns the existing
batch before reconsidering today's data.

These references identify what supported the decision. They need not contain a
future opening price. Backtest execution may continue using one complete pinned
historical snapshot, subject to the existing as-of filters.

## Execution provenance is explicit

An execution attempt may use a separately registered, hash-verified execution
snapshot. Add a paired optional `execution_snapshot_id` and
`execution_snapshot_sha256` to the shared execution context. The existing
`snapshot_id`/`snapshot_sha256` continue to identify decision evidence.

For the existing same-snapshot path, the optional pair defaults to null and is
omitted from serialized output. Old stored execution/core artifacts must validate
and serialize to their original canonical bytes/hashes. Do not rewrite published
experiments, comparisons, snapshots or ledger entries. The implementation must
prove this compatibility before activating the new path.

When the optional pair is present, `MarketEvidence` must match that execution
reference. Its bars must still satisfy raw-as-traded basis, quality, original
eligible session, source availability and live ingestion checks. A different
snapshot does not permit a later execution session or a different price rule.

The controller/ledger must verify both registered references and preloaded files
before posting. Require matching source mode, canonical asset identity, currency,
provider/normalization and accounting basis, plus usable quality, applicable local
rights and complete accounting support. Unsupported sources remain unavailable;
this ADR does not turn diagnostic-only provider flags into accounting support.
The execution snapshot is not an input to strategy eligibility or features.

Persist the actual execution snapshot on the fill's ledger event and in its
execution result. The original recommendation/batch still links the decision
snapshot. `PortfolioTransactionV1` source references identify the data used
for that event; same-source historical records retain their original meaning.
Keep the original decision build/clock and actual execution build/observation
metadata inspectable rather than relabeling a later computation as the original.

## Calendar and action compatibility

The original pinned calendar continues to determine the eligible opening from
cutoff and approval. A later execution calendar may extend coverage; its whole
file hash need not equal the older calendar's hash. Both must agree on the
calendar identity/timezone and the selected session's date, UTC opening and close.
Record both snapshot/calendar references. Missing or inconsistent session facts
block execution for reevaluation; do not guess a weekday or move an approved
order to a convenient later open.

Use execution-source action evidence chronologically under ADR-002/004. Preserve
ex-date entitlements before affected trading and reliable payable recognition;
revised economic evidence requires an explicit correction. Pending-order action
adjustments unsupported by v1 block for reevaluation. Do not spend a later
session's dividend/correction proceeds to reconstruct an earlier pending fill.
If posted state has advanced incompatibly with that original chronology, block
and require explicit reconciliation/reevaluation instead of rewriting history.

## Idempotency, cancellation and worker publication

The financial event identity remains immutable order ID, policy version, original
eligible session and logical fill ordinal. Neither the worker attempt nor a new
snapshot creates another economic fill. The accepted quote/source payload is
sealed once; a changed explicit payload under an already posted event identity
conflicts. Lost acknowledgment returns the original durable posting and its
original execution reference.

Queue ownership remains separate from that financial uniqueness. A worker must
prove current lease/cancellation authority before each side effect or fenced
publication, and check the batch under its portfolio lock. The job result cannot
claim completion before its relevant ledger effects commit. Each fill tuple and
status/revision transition stays atomic; posted sale proceeds may finance a
subsequent buy only after durable posting, as Q01 and the shared kernel require.
Cancel-first prevents remaining work; fill-first retains the committed effects.
Cancellation never edits a fill, resets approval time or resurrects intent.

Missing eligible opening evidence stays pending with a reason. It may be supplied
by a later compatible immutable publication for the original eligible session.
Do not silently substitute today's opening or treat a failed refresh as a fill.
Scheduling/catch-up preserves original business chronology, bounded work and
explicit fixture replay clocks; no monitoring is promised while Docker is off.

## Required implementation and independent proofs

The implementation PR must update shared typed models/serialization, kernel,
ledger/controller/worker, affected API/generated types, operational documentation
and fixtures together. It must not claim provider support from schema changes.

- Original decision snapshot ends at T; a second immutable snapshot supplies the
  T+1 opening. No T+1 price is visible in the decision inputs. Original snapshot
  bytes/hash and approval fields remain unchanged after the fill.
- Missing/newly available bars, late approval, holidays and compatible calendar
  extension preserve the original eligible opening. Conflicting calendar/source,
  wrong mode/provider, unsafe prices/actions, future availability or live
  ingestion cannot produce a fill.
- Independent FIX-03/04/05/09 cent/6dp expectations remain exact. Duplicate
  deliveries, lost acknowledgment, concurrent approvals/fills and cancel races
  produce one truthful outcome; later credits cannot finance a past order.
- Existing stored same-snapshot artifacts round-trip without hash drift. Existing
  generated clients remain compatible; any additive schema fields are coordinated.
- Real PostgreSQL transactions, supervised worker/resource limits, actual restart
  and integrated offline installation prove the path. No mock or document-only
  check counts as those runtime proofs.

The decision PR requires content/link/consistency review only. The implementation
remains incomplete until these tests and normal CI/MergeWatch gates pass.
