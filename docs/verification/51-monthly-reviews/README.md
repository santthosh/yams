# #51 monthly review verification

[evidence.json](evidence.json) contains recorded application output from an owned
fresh Docker project, not an independent financial oracle. Every dataset, cash
balance, order and fill is `SYNTHETIC_DATA_ONLY`. Existing independently authored
FIX-06/09 chronology/idempotency and financial golden fixtures remain unchanged.
The new missed-month list and clock-boundary expectations are independently
specified in tests; no production scoring function generates an expected value.

Final Docker project `yams-smoke-c1127a7e39bb` passes29 checks. An explicit manual
July31 synthetic review on an independent cash-only account advances the durable
observation to August1's canonical cutoff. The real supervisor records18 missed
monthly opportunities without backdating a decision and reuses the manual run
for the current monthly opportunity. One numerical forecast is produced through
the actual worker; cash remains1000.00, revision1 and only original funding exists.

The harness then stops only its own worker. A later explicit August31 review
moves current replay time to September1 while last-supervisor observation remains
August1. Readonly status immediately shows backlog before any new scan. Restart
reuses that next manual/monthly job, preserving20 original occurrence records:
18 missed and2 admitted, with real completed jobs/forecasts. Original keys,
logical clocks, immutable decisions, forecasts and readonly financial state
survive normal application restart and image rebuild. The other26 established
application/browser/infrastructure proofs remain intact. No user volumes or
private provider credentials were used; owned disposable projects were cleaned.

Final full PostgreSQL project `yams-it-6a8e15a513bf` passes185 cases and11 actual
restart checks. It proves manual-first/scheduled-first/concurrent deduplication,
original per-key input binding and recovery without source files, atomic
job/run/checkpoint and explicit-observation rollback, missing source recovery,
bounded chronological catch-up, monotonic clock/checkpoint guards, immutable
handled history, observed gaps and populated0008->0009 upgrade retaining original
analysis/forecast/key/payload bytes. Actual restart retains queued work and two
concurrent readonly status calls; the original job then completes through the
worker without duplicate evaluation or any fill. Existing financial crash/replay,
cancellation/lease, next-open, source/action and exact-ledger proofs pass.

A prototype status read used the previous scan's clock after a new explicit
manual selection. The actual PostgreSQL regression failed (`False` instead of
`True` backlog) before correction and passes afterward using the current durable
clock while retaining the distinct last-observed clock. An initial full run also
identified an outdated bootstrap table-list expectation; it was updated for the
four additive tables. Final results above are after both corrections.

470 backend and74 web tests,32 proxy cases,123 targeted API/contracts, Ruff/format,
strict Python/TS types, generated contracts,30 fixture files, documentation links
and Python wheel/sdist pass. All prior standalone schema and route definitions
are unchanged. Final production Python source hashes match both the complete
integration image and the actual production API image. Local native macOS
Turbopack cannot bind its subprocess port in this managed environment; production
Docker build/runtime/rebuild pass and required CI repeats build/runtime gates.
Review/CI/merge evidence belongs to the PR and single #51 tracker. This source
verification does not claim a0.0.5 release or an implemented Decision Center UI.
