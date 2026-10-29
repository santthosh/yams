# #50 public paper controls verification

All prices, funds and fills in [evidence.json](evidence.json) are
`SYNTHETIC_DATA_ONLY`. These are recorded application outputs, not an independently
derived financial oracle or investment claim. Existing independently authored
FIX-04/06/09 arithmetic/ledger/execution fixtures remain unchanged and pass.

Fresh isolated Docker project `yams-smoke-0bcdff018b0c` passed26 checks. It creates
an independent account, computes a genuine #49 recommendation, approves through
the same-origin proxy with its original key, and verifies unchanged cash/holdings.
The first explicit completed-session step remains pending because fixture bars
arrive one second after close. A later keyed step exposes the original eligible
opening; the actual supervised worker fills three orders through the shared
ledger service. Posted cash404.98 and quantities are measured application output.
Exact approval/step retry, read-only recovery, original decision, immutable ledger,
source labels and clock survive actual restart and rebuild. Existing Strategy Lab,
forecast, account, private-worker and infrastructure proofs remain intact. Only
owned disposable project resources were removed; no user volumes were reset.

Complete PostgreSQL project `yams-it-795427f0c3b7` passes168 cases and10 real-restart
checks; an additional genuine cash-only computed-decision case passes independently.
Final production Python source hashes match that tested Linux image. Public
fixtures cover concurrent duplicate approval, changed body/key, recovery without
source files, stale revision/source/disposition, pending publication, dismissal
without financial mutation, cancellation after partial fills and cancellation
winning against prepared output. Existing late-approval, independent execution
publication, corporate actions, crash/replay, lease and exact-ledger proofs pass.

465 backend and73 web tests,127 targeted API/contracts,31 proxy cases, lint,
formatting, strict Python/TS types, generated contracts,30 fixture files and Python
wheel/sdist pass. Prior standalone schemas and route definitions are unchanged;
new expected-revision int64 bounds remain exact. Documentation links/whitespace
are checked. Local native Turbopack build is unavailable because its subprocess
port bind is denied in this environment. The production Docker web build and
actual application journey pass; required CI repeats build/runtime verification.

An initial worker test incorrectly expected a quote at close; it was corrected to
assert truthful pending availability before the later explicit step. Testing
found public forced job identities could create duplicate scheduler work; public
recovery now uses immutable namespaced correlation while existing semantic job
keys remain unchanged. A stale-source test needed to drain its queued forecast
before invoking a single-job publication helper. Full verification above is after
those corrections. Review, CI and merge evidence are recorded in the PR and single
owning issue tracker; this source evidence does not claim a0.0.5 release.
