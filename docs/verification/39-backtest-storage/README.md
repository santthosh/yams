# #39 persisted core verification (0.0.3, phase2b)

All financial examples are **SYNTHETIC_DATA_ONLY**. These are execution and
persistence proofs, not actual market returns. The independent financial oracle
remains [core-case.json](../../../data/fixtures/backtesting/core-case.json); any
observed proof recorded here is not substituted for that oracle.

The implementation adds bounded canonical request/config envelopes, additive
`0005_experiments`, immutable experiment/core rows, private hash-sealed artifacts
and a closed internal `backtest_core` worker. Completion is fenced by current
attempt ownership, cancellation state and deadline before and after filesystem
publication. A status/artifact reader shares the job lock with completion so it
cannot assemble a response from different transaction states.

Verification includes exact nested decision/config/calendar/source lineage,
initial cash, complete execution cardinality, strict original-open/approval/fill
chronology, complete session/phase windows, duplicate orders, valid risk evidence
and readable persisted input fingerprints. File tests reject tampering, missing
bytes, symlinks, hardlinks, path traversal and excess budgets. A fresh validated
recomputation can reuse an identical post-rename orphan; an arbitrary orphan
cannot establish completion. Partial output never becomes a completed core.

Financial/queue coverage includes real supervised reruns, cancellation while a
core job is running, cancelled/expired publication fences, abandoned-lease
recovery/new token, stale-token rejection, old queued build rejection, post-rename
DB rollback/recovery, concurrent reader/completion serialization, populated prior
schema upgrade and actual PostgreSQL restart. Canonical split-statistic hashing
has a dedicated regression; no binary-float cash policy was relaxed.

Local final checks passed:347 backend tests;77 real PostgreSQL integration tests
plus3 actual-restart tests in `yams-it-8197adca36b0`; full offline/browser/core/
restart/rebuild smoke in `yams-smoke-350867fcadf1`; lint/format, strict typing,
OpenAPI/generated-client drift,29-file fixture reproduction, package build and
54-document content/link checks. The [observed core proof](observed.json) retains
sanitized source/build identities and exact synthetic points/fills.

One earlier parallel Docker run passed all77 tests but hit the existing5-second
disposable-database teardown timeout; the unchanged integration harness passed
when rerun once alone. No timeout, assertion or resource guard was weakened.
Current-head CI/review evidence is recorded in the maintained #39 tracker and
storage PR. No credential, downloaded data, private volume
or user source hardlink is part of these proofs.

The full Compose harness now uses internal admission in the isolated API container,
lets the actual supervised worker compute the authored next-open trace, polls its
existing job resource and verifies the sealed core/NAV/provenance through actual
restart and rebuild. Existing browser publication and10 candidate evaluations,
offline routing, internal ports, read-only fixtures, resource caps and migration
failure/recovery remain required. This is not a public experiment endpoint/UI.

#40 owns report metrics/benchmark over the verified persisted core. #41 owns the
complete `backtest` report/API lifecycle. An internal `backtest_core` completion
must never be projected as completed `ExperimentRunV1` without required report
metrics and sealed references. Preserve historical input/core identities; future
report schema changes use a distinct additive revision.
