# Snapshot-to-target diagnostics

The diagnostic slice combines immutable transport/persistence, the supervised
shared quant engine and a responsive inspection UI. Approved Q15 fixes the cutoff
at scheduled close plus15 minutes, including early-close days. Only validated
evidence available by that instant is usable; late bars retain exclusion reasons.
This is a paper-only research diagnostic, not an approval or order operation.

## Contract and identity

`POST /api/v1/strategy-evaluations` accepts exactly `strategy_version_id`,
`snapshot_id` and exchange-local `as_of_session`. It returns202 with `job_id` and
`evaluation_id`. Diagnostic requests are research operations; they do not mutate
paper accounts. Repeated submissions may create different resource/job IDs while
identical pinned inputs reproduce the completed financial evidence.

`GET /api/v1/strategy-evaluations/{evaluation_id}` returns:

- Resource/job IDs and persisted job status; immutable request inputs and source
  mode/provider, config/snapshot hashes, engine fingerprint, canonical strategy
  rules and creation time.
- Nullable `result`, `result_sha256` and `error`. Only completed jobs expose a
  sealed result/hash; only failed jobs expose a terminal error. Pending, failed
  and cancelled jobs cannot masquerade as completed target allocations.
- A completed result contains as-of session, explicit UTC decision cutoff,
  source mode/warnings, all candidates with features/contributions/ranks/reasons,
  selected IDs, complete targets/cash, independently checked constraint evidence,
  allocation/data diagnostics and strategy/snapshot/config/calendar/build identity.

The result reuses shared momentum/allocation evidence, not frontend-owned math.
Weights are full decimal strings; statistical values are finite numbers or have
the engine's explicit unavailable/exclusion evidence. Cash-only and empty eligible
universes are legitimate completed results. The canonical result hash excludes
job/resource IDs and creation time, so it can establish financial rerun equality.

## Admission and storage

Admission verifies registered snapshot artifacts and published strategy rules,
rejects unknown references404, uncovered/non-calendar sessions422, and blocked or
incomplete requested coverage409 STALE_DATA. Retrospective covered sessions remain
inspectable. Real research sessions cannot be in the future. Authored synthetic
fixture calendars may contain future fictional dates and remain visibly labeled;
this is not evidence of future securities-market prices.

Existing hard workload ceilings apply: at most1000 assets,2520 scheduled sessions
and2,520,000 declared bars. These are admission ceilings, not performance promises;
supervised runtime budgets still govern execution. Result transport is bounded at
8MiB. No credential or provider acquisition is part of diagnostic evaluation.

Migration `0004a_evaluations` follows `0004_strategies` without consuming the
reserved experiment migration. `strategy_evaluation` stores immutable input/job
references, source/config/calendar/build hashes and session. Admission inserts its
job and input row in one transaction. `strategy_evaluation_result` stores the
separately sealed JSON evidence/hash, completion time and attempt token. PostgreSQL
rejects updates/deletes of either evidence table. Portfolio/order/ledger/forecast
tables are not introduced by this flow.

Sealing holds the owning job row lock and verifies the active lease token,
attempt, deadline, non-cancelled state, complete lineage and target risk policy.
Result insertion and completed job state commit together. Failed/cancelled/expired
attempts cannot publish evidence. A fault before commit leaves neither a result
nor a completed job. Reads validate canonical hashes, config identity, resource
linkage and target constraints before returning completed evidence.

## Build reproducibility

`engine_fingerprint()` hashes production backend source files, actual declared
core dependency versions, Python patch version and normalized CPU architecture.
Tests and optional acquisition extras do not change the quant runtime identity.
Checkout/images use the project manifest; installed wheels use distribution
metadata. Native and Linux worker fingerprints must agree for equivalent source,
dependencies and architecture. Different architecture/runtime fingerprints remain
distinguishable. Stored results retain their original fingerprint across updates.

The supervised worker compares pinned build/config/snapshot/calendar identities
before evaluating and enforces Q15's scheduled-close-plus15-minute cutoff. Admission
pins this instant in the immutable job payload; the child independently derives it
from the verified calendar, and publication/reads reject a different result cutoff.
Bar arrival order cannot change it. Real-market admission and execution of the
handler reject a cutoff that has not elapsed. All current diagnostics are
historical as-of views, so they filter by availability; a future live-like caller
must additionally enforce local ingestion as ADR-002 requires. The child performs
no database writes. Only the supervisor may seal its bounded result under the
active lease. Validation/stale failures expose sanitized typed codes.

## Inspection UI

`/lab/candidates` selects source, snapshot, published default version and as-of
session. It links to Settings & data to prepare snapshots, keeps research-empty
states explicit and never substitutes synthetic values for missing research data.
Saved evaluation IDs recover through the URL or optional browser storage. Polling
uses persisted evaluation status, bounded retry/backoff and aborts on unmount;
auxiliary job-read failures cannot invalidate independently read evidence.

The page displays complete target/cash and concentration evidence, searchable
candidates (50 visible at a time, disclosed without altering stored results), raw
features/contributions, exclusions and reproducibility. Tables scroll horizontally
and accept keyboard focus; details expose exact stored values. There is no paper
approval action in this diagnostic slice. Public cancellation is staged to #41.

## Verification and limitations

FIX-01 momentum values are checked against independently authored expectations at
the approved cutoff `2028-07-17T20:15:00Z`; authored target weights are20% each for
SYN:AAA/BBB/CCC and40% cash. The insufficient-history session2027-01-04 completes
with100% cash and exclusions. Boundary tests cover availability exactly at the
cutoff and ±1 microsecond, separate late ingestion, DST and early closes.

PostgreSQL tests cover admission/reads, fenced sealing, repeat-result hashes,
immutability, wrong cutoff/lineage, cancel/expiry, injected rollback and actual
container restart. A real supervised-child test verifies two identical financial
results through the queue. The Compose browser journey refreshes fixtures, selects
pinned inputs and evaluates/reruns both populated and cash-only results through
the actual API/worker at desktop/mobile widths. Its saved envelopes are checked
after restart/recreate. Native packaged-install verification uses the same browser
journey and checks retained evaluation evidence after restart; per-platform release
runs remain necessary before a release is declared supported.

Separate browser transport fixtures are labeled `SYNTHETIC_DATA_ONLY`, generated
from explicit-cutoff engine runs, and are **not independent financial oracles**.
They retain their original historical build/cutoff values. Four desktop/mobile
tests cover polling/rerun display, recovery, cash-only/failure/unknown/stale/
research-empty states, keyboard tables, width and Axe accessibility. A reproduced
polling regression ensures completion of an older run cannot erase a failed new
submission's admission error.

Optional external research remains subject to provider permission/capability and
chronology restrictions. No real provider-derived universe, calibrated prediction,
portfolio deployment, order execution or completed0.0.2 release is established by
this synthetic diagnostic journey. The milestone epic owns its integrated gate.
