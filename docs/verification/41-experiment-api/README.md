# #41 — Public experiment lifecycle

All results below use committed synthetic inputs labeled `SYNTHETIC_DATA_ONLY`.
The [observed output](observed.json) is runtime evidence, not a golden oracle or
actual investment performance. Independent expected values remain in FIX-07,
`data/fixtures/backtesting/core-case.json` and the separately authored Q12 metrics
extension. [Operational/API handoff](../../operations/experiment-api.md).

## Local verification

- Backend:376 tests pass. Nine new projection/artifact tests cover independent
  NAV/drawdown/SPY/holdout vectors, decimal weights, fixed managed roles,
  hash integrity, symlinks, hardlinks and bounded reads. Contract tests preserve
  the exact uint64 seed ceiling and ensure all generated references resolve.
- Web:57 tests pass, including the closed experiment/cancel proxy paths,
  window query allowlist, same-origin JSON writes and unsupported-path rejection.
- Host and Linux strict mypy:172 source files pass. Python lint/format,
  web lint/format/typecheck, OpenAPI/generated client drift and30-file fixture
  reproduction pass. Pinned wheel/source package build succeeds.
- Isolated PostgreSQL project `yams-it-b1eea7957bf9`:89 integration tests plus4
  actual restart checks pass. Tests cover atomic admission/publication, immutable
  report rows, populated prior-schema upgrade, stable errors, no dropped/duplicate
  pages, exact rerun fingerprints, queued/running/terminal cancel, actual worker
  cancellation, safe failed output, pre/post-publication lease expiry, crash/orphan
  recovery, corrupted artifacts and completion/read/cancel row-lock races.

The earlier full-suite failures were expectations that backtest/cancellation were
still unavailable; those were updated to the newly implemented contract. A first
browser verifier used an incorrect strategy field; it was corrected to the actual
`signals.kind` contract. No financial expected value or application assertion was
weakened to make these checks pass.

## Runtime evidence

The disposable offline full-application project is
`yams-smoke-c395ff94da4a`. Its real browser submits identical inputs twice through
the same-origin proxy and observes different run IDs with matching curve, trade
and reproducibility hashes. It checks complete sealed results, two bounded curve
pages, exact original dates/NAV, trade evidence, invalid cross-role cursors422,
terminal cancel409 and accepted cancellation202 with no report output.

The smoke harness also verifies the existing application/strategy/diagnostic
journeys, offline network isolation, read-only fixtures, persistence after service
restart and rebuild, and migration-failure startup protection. The harness retains
its complete local evidence under `test-results/smoke/<project>/` and removes only
its own random project volumes. No credentials, provider downloads or licensed
market datasets are committed.

This issue adds public transport and final publication over the already reviewed
financial kernel. It does not add the #74 report UI, change Q12 methodology,
activate a real accounting provider, publish a0.0.3 release or post paper fills.
Required exact-head GitHub Actions/MergeWatch and merged-state results are recorded
in the PR and the single #41 shipping tracker; local checks do not substitute for
those gates.
