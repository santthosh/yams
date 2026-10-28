# #40 reporting verification (0.0.3)

All committed examples are **SYNTHETIC_DATA_ONLY**, descriptive statistics rather
than actual market performance or calibrated predictions. ADR-013 was committed,
actually reviewed5/5 and merged in PR #122 before financial implementation.

- 366 backend tests pass, including19 new metric/benchmark cases. FIX-07 independently
  verifies8% cumulative return,25% maximum drawdown,3-return geometric annualization,
  sample volatility, zero-risk-free Sharpe and gross turnover/mean daily NAV.
- New vectors in `scripts/metrics_oracles/` were authored before production math
  using standalone Fraction/Decimal arithmetic over the independent core trace.
  They are copied/indexed reproducibly. Original FIX-01–FIX-10 cases and snapshot artifacts remain
  unchanged; fixture reproduction now verifies30 files.
- Cases cover empty/one-point/flat/constant-nonzero returns, zero denominators,
  unrepresentable annualizations, costs counted once, owned holdout denominator,
  full2520-observation deterministic statistics, SPY gaps/late/flagged evidence,
  adjusted-versus-raw split treatment, unsupported benchmark identities, shared
  raw-mark exposure and explicit incompatible controls across both engine versions.
- Host and Linux strict typing pass163 source files. Lint/format, OpenAPI/generated
  client drift, fixture reproduction, package build and documentation links/content
  checks pass. This change adds no migration, dependency or public endpoint.
- Real PostgreSQL integration passes78 tests plus3 actual-restart tests in
  `yams-it-2ffad9eacc69`. Actual supervised core output is read/verified, composed
  into a deterministic serializable report, and remains unchanged after reporting.
  Partial cores are rejected. The calculator also composes complete evidence inside
  a still-running future report job, before final public completion/sealing.
- Full offline Compose/browser/report/restart/rebuild smoke passed in
  `yams-smoke-c511c2c326ef`. It computes a real report in the bounded worker
  container from a persisted core, checks independent metrics, aligned SPY/cash,
  holdout observations and identical reports through actual restart/rebuild.
  Existing10 candidate evaluations, immutable strategy publication, offline routing,
  internal ports, read-only fixtures, resource caps and migration recovery remain.

[Observed output](observed.json) is sanitized Docker evidence, not a golden oracle.
It retains separate core/reporting provenance and the independent expected values
remain in FIX-07 and its extension case. Test-owned projects/volumes were cleaned
by their harnesses; user credentials, downloaded data and private volumes were not
modified. Current-head GitHub Actions/review and merged verification are recorded
in the maintained #40 tracker and runtime PR.

#41 still owns final report persistence/job completion/API and #74 report UI.
Internal calculations do not satisfy completed `ExperimentRunV1` by themselves.
See the [reporting handoff](../../operations/backtest-reporting.md). #68 reuses
Q12 methodology; later milestones remain gated by the sequential delivery goal.
