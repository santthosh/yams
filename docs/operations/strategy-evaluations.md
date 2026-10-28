# Snapshot-to-target diagnostics

**Draft implementation under #34.** The independent transport, persistence and UI
work is implemented on its feature branch. Q15 (staggered closing-bar cutoff) is
pending user input. No default cutoff or supervised evaluation handler is ratified
by this draft, and no real worker-to-browser completion is claimed yet.

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

The worker implementation must compare the pinned build/config/snapshot/calendar
identities before evaluating and use the resolved Q15 timing policy. This pending
work must not be replaced with a guessed cutoff or an unsupported job handler.

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

## Current verification scope

Independent FIX-01 momentum values are checked at an **explicit fixture cutoff**
(`2028-07-17T20:00:01Z`), not a chosen default arrival policy. PostgreSQL tests
cover admission/reads, direct fenced sealing, repeat-result hashes, immutability,
cancel/expiry, injected rollback and actual container restart. These tests do not
prove the still-pending supervised evaluation handler.

Browser transport fixtures are labeled `SYNTHETIC_DATA_ONLY`, generated from
explicit-cutoff engine runs, and are **not independent financial oracles**. Four
desktop/mobile tests verify polling/rerun display, recovery, cash-only/failure/
unknown/stale/research-empty states, keyboard tables, width and Axe accessibility.
The real worker/API/browser and fresh-Docker demonstration remain required after
the cutoff decision, before #34 or milestone0.0.2 can be completed.
