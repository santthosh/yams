# Complete core release gate — 0.0.5

The [published release verification](verification/0.0.5-release/README.md) records
the completed native/publication gates and exact immutable source/image evidence.
The source-preparation checkpoint below is retained as historical evidence.

Owner: [#53](https://github.com/santthosh/yams/issues/53), under
[epic #6](https://github.com/santthosh/yams/issues/6) and the recorded decisions in
[#72](https://github.com/santthosh/yams/issues/72). This document defines reproducible
verification and its limits. A source version, merged PR or this checklist alone is
not a published release. The exact source, immutable image digests, checksums and
native results belong to the corresponding GitHub Release's `provenance.json` and
`evidence-amd64.json` / `evidence-arm64.json`.

## Integrated scope

A fresh local installation, without provider credentials, must explicitly load
`SYNTHETIC_DATA_ONLY` fixtures and demonstrate dynamic candidate evidence, an audited
shared-engine backtest/benchmark comparison, an independent $1,000 paper account,
constrained targets, explanations and common-shock 90-calendar-day numerical scenarios.
The real Decision Center must confirm the original portfolio/revision/version/as-of,
estimated quantities/costs and indicative future opening before public paper approval.
Approval leaves holdings/cash unchanged. Explicit fixture observations expose original
opening evidence; the actual bounded worker posts durable fills. Later review can
produce a genuine HOLD that can be dismissed without a ledger change.

Restart inspection restores the original browser operation key at the harness's
current ephemeral loopback origin, recovers the existing approval through GET and
inspects original scenarios, exact quantities/cash/ledger, HOLD/dismissal and logical
clock state. Inspection makes zero POSTs. Current snapshot applicability, valuation
marks and supervisor observations can change; original financial artifacts and
posted ledger facts cannot. Both 360px and 1280px views must pass keyboard/focus,
accessible tables, Axe and viewport bounds.

Negative cases are genuine worker outputs: an early pinned session with insufficient
feature history yields an empty eligible universe and all cash; a late session without
90-day calendar lookahead yields an unavailable forecast with null outcomes, not zero
security returns. Cash-only zero-yield scenarios may legitimately return zero and
$1,000. An injected browser connection failure must show a recoverable error without
invented account state or admitting new work. No production API response is mocked.

## Fixture and independent-proof trace

| Fixture | Required invariant | Existing independent/runtime proof |
| --- | --- | --- |
| FIX-01 | Deterministic features/ranks/ties and feasible targets | [Strategy contracts](../backend/tests/strategies/test_evaluation_contracts.py), [allocation](../backend/tests/portfolio/test_allocation.py), actual candidate/Decision Center worker journeys |
| FIX-02 | Future information cannot change a historical decision | [Temporal boundaries](../backend/tests/strategies/test_boundaries.py), [backtest lineage](../backend/tests/backtesting/test_lineage.py), [forecast timing](../backend/tests/forecasting/test_temporal.py) |
| FIX-03 | Cents cash, six-place shares, adverse costs and constraints | [Execution](../backend/tests/portfolio/test_execution.py), [authored recommendation expectations](../backend/tests/recommendations/expected_cases.json), [independent reference ledger](verification/52-decision-center/README.md) |
| FIX-04 | Retry/duplicate approval or fill creates one durable effect | [Actual public controls](../backend/tests/integration/test_paper_controls.py), real double-click and response-loss/reload browser proof |
| FIX-05 | Raw/adjusted prices and corporate actions never double count | [Execution provenance](../backend/tests/portfolio/test_execution_provenance.py), [paper ledger integration](../backend/tests/integration/test_paper_ledger.py), pending-action/fill guards |
| FIX-06 | Holiday/missing/stale quote stays pending or blocked | [Execution sources](../backend/tests/portfolio/test_execution_sources.py), original pinned opening after explicit fixture observations; stale/unavailable UI cases |
| FIX-07 | Drawdown, CAGR, turnover and benchmark alignment are independently checkable | [Metrics](../backend/tests/backtesting/test_metrics.py), [benchmark](../backend/tests/backtesting/test_benchmark.py), original report/challenge/comparison browser proofs |
| FIX-08 | Fixed-seed correlated vectors and honest 90-calendar-day scenarios | [Bootstrap](../backend/tests/forecasting/test_bootstrap.py), [horizon](../backend/tests/forecasting/test_horizon.py), [scenario invariants](../backend/tests/forecasting/test_scenarios.py), actual numerical and unavailable UI results |
| FIX-09 | Restart preserves original jobs/orders/keys/artifacts without duplicate financial effects | [Recommendation recovery](../backend/tests/integration/test_recommendation_recovery.py), [review restart](../backend/tests/integration/test_review_restart.py), source/native readonly browser inspection |

Browser/application output is retained as
`RECORDED_APPLICATION_OUTPUT_NOT_INDEPENDENT_ORACLE`. It proves integration and
persistence, while the independently authored fixture arithmetic and tests above
establish financial correctness. No golden expectation is generated by the production
function being tested. The reference three buys debit 200.34 + 200.34 + 194.34 = 595.02,
leaving 404.98 from 1000; the derivation uses committed synthetic openings and Decimal
round-half-even accounting. It is not a market performance claim.

## Required automation and review

| Layer | Gate and retained evidence |
| --- | --- |
| Unit/contracts | `make lint`, `make typecheck`, `make test`, `make contracts-check`, `make fixtures-check`; generated client drift and all prior schemas remain checked |
| Actual database | `make test-integration` owns isolated Compose volumes and verifies migration, queue/lease/ledger/snapshot invariants, then actual PostgreSQL restart |
| Production Docker | `make smoke` builds the current source, exercises all prior diagnostics/Strategy Lab/backtest/portfolio/forecast/scheduling proofs plus core positive/negative/readonly restart/rebuild browsers |
| Browser cases | `decision-browser.mjs`, `core-negative-browser.mjs`, `decision-inspection.mjs`, alongside prior editor/report/challenge/portfolio browser helpers; screenshots and failure logs retained |
| PR/default branch | Existing `.github/workflows/ci.yml` requires quality, contracts, production-build browser checks, actual PostgreSQL and full offline Compose smoke through `CI / required`; runtime work never receives a docs-only skip |
| Review | Trusted current-head MergeWatch review, findings addressed and conversations resolved before a normal authorized merge; a separate human approval is not required under recorded Q05 |
| Packaged release | Existing `.github/workflows/release.yml` builds exact-source native amd64/arm64 candidates, creates immutable multi-platform indexes, packages digest-pinned Compose and verifies anonymous native installations through `scripts/release_smoke.py` before publication |

The source/native harnesses reuse the same real browser helpers. They keep older
published-release capability proofs and require the new public core workflow and
negative states to pass. The release publisher verifies both platform/source/image
records, checksums/provenance and existing-tag/release immutability. A publication-only
retry may reuse verified artifacts after a demonstrated transient draft-visibility
failure; it must not rebuild or replace published images/tags/assets.

## Status and operational limits

The owning issue's maintained ship tracker records actual source/PR/CI/candidate/
publication results as they complete. Pending native checks or publication must stay
open; do not infer them from passing local source tests. The final public release and
epic evidence identify exactly what shipped. See [installation/upgrade](releases.md)
and [Decision Center operations](operations/decision-center.md).

Real Tiingo acquisition was independently verified in 0.0.2; it remains optional,
user-token/local-data and diagnostic-only for accounting. No licensed downloaded data
or credentials enter public assets. Underlying synthetic fixtures are clearly marked;
forecast intervals are historical scenarios, not calibrated predictions or guarantees.
Only web binds loopback; API/PostgreSQL remain private. Monitoring runs only while
Docker is active. Arena, outcome Journal and assisted authoring are later milestones,
not prerequisites or delivered claims for 0.0.5.


## Source-preparation checkpoint — 2026-10-29

[Safe recorded source evidence](verification/53-core-source/evidence.json) records
472 backend unit/contract and 84 web checks,188 actual PostgreSQL cases plus 11 actual
restart checks and 32 fresh production Docker checks, with lint/format, strict types,
contracts/30fixtures/docs and wheel/source package builds passing. All 158 production
Python files match both tested Linux images. The API change is version metadata only;
prior paths/shared schemas and canonical fixtures are unchanged.

The real 360/1280 browser runs cover original-key recovery, exact complete fills,
genuine HOLD/dismissal and all negative states described above. Readonly initial,
restart and rebuild inspections make zero POSTs and retain identical hashes of
original financial artifacts, exact cash/ledger and both negative outcomes, with
stable logical clocks, zero Axe findings and bounded viewports. Populated 0.0.4
schema migration, queued work and original artifacts remain covered by the actual
PostgreSQL upgrade/recovery suite.

Screenshots: [cash-only mobile](verification/53-core-source/core-empty-360.png),
[unavailable forecast desktop](verification/53-core-source/core-unavailable-1280.png),
[readonly restart mobile](verification/53-core-source/core-retained-restart-360.png).
At this source-preparation checkpoint, required PR/main CI, native packaged candidates
and public publication remain separate gates recorded by the owning issue and release
assets. The local source results do not substitute for either native installation.
