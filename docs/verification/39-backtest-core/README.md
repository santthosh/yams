# #39 pure core verification (0.0.3, phase2a)

All financial examples are **SYNTHETIC_DATA_ONLY** and are not market-performance
claims. No provider token, downloaded dataset or private workspace is used.

- 16 new core tests pass: independent exact-cents next-open trace, untouched initial
  cash baseline, deterministic reruns/serialization, pinned month ends/weekend
  cutoff, half-open dates, chronological carry/rounding, future evidence injection,
  missing/late openings and held closes, universe exit, dividend and split effects,
  unsupported actions/source capabilities, coverage and cooperative cancellation.
- Shared close valuation replaces the planner's identical inline arithmetic;
  existing portfolio tests remain green. The strict source guard refuses a
  diagnostics-only capability even when raw-price metadata is present.
- Linux offline run:122 backtest/portfolio/market tests passed under2CPU,2GiB,
  zero swap,64PIDs, read-only filesystem and `--network none`. The subsequently
  added16th core test checks the same pinned weekend/month-end trace locally;
  it is included in normal CI, not claimed as part of that earlier122-test run.
- Final full backend regression passed333 tests, including all16 core tests;
  lint/format, strict typing, OpenAPI and generated client drift,29-file fixture
  reproduction, package build and53-document links/content checks passed.
- Real PostgreSQL regression:65 tests plus2 actual-restart tests passed in isolated
  project `yams-it-c1e6c9f9859a`. This validates existing storage/worker compatibility;
  it does not claim new experiment persistence, which remains the next #39 phase.
- Full Compose/browser/offline smoke passed in `yams-smoke-463daba6c789`: real
  keyboard strategy forks/appends,10 supervised candidate/evaluation runs,
  immutable histories, restart/rebuild, internal API/database ports, loopback web,
  image/resource budgets and migration-failure/recovery. Existing diagnostics
  exercised the shared code; this is not a public backtest endpoint demonstration.

Both disposable projects were cleaned up by their owning harnesses. The user's
separate Tiingo project/volumes, root `.env` and source fixture hardlinks were not
modified. Current-head GitHub Actions/MergeWatch and merge verification are
recorded in the maintained #39 tracker and PR after publication.

Follow [ADR-012](../../adr/0012-walk-forward-core.md) and the
[handoff](../../operations/backtest-core.md). #39 stays open: fenced artifact
publication,0005_experiments and supervised experiment crash/cancellation/restart
proofs are outstanding. #40 remains blocked until that full artifact lands.
