# 0.0.5 release verification

The [v0.0.5 complete-core prerelease](https://github.com/santthosh/yams/releases/tag/v0.0.5) was published at
`2026-10-29T14:24:34Z` from immutable source `38f0dcc96d640567c53c3f0837358e32030e3624`.
It completes the assigned 0.0.2–0.0.5 sequence. Arena, outcome Journal and assisted
authoring remain later increments. All financial demonstrations are
`SYNTHETIC_DATA_ONLY`; real provider feeds remain diagnostic-only for accounting.
Scenarios are historical resampling under disclosed assumptions, not calibrated
future predictions. No brokerage or real money is involved.

## Reviewed source and required verification

Forecast [PR #136](https://github.com/santthosh/yams/pull/136), recommendation
[PR #137](https://github.com/santthosh/yams/pull/137), public paper controls
[PR #138](https://github.com/santthosh/yams/pull/138), monthly reviews
[PR #139](https://github.com/santthosh/yams/pull/139), Decision Center
[PR #140](https://github.com/santthosh/yams/pull/140) and integrated release gates
[PR #141](https://github.com/santthosh/yams/pull/141) passed actual current-head
MergeWatch review, required CI and normal merges. Documentation-only
[PR #142](https://github.com/santthosh/yams/pull/142) corrected the public platform
evidence filenames. Its reviewed merge is the exact release source; executable
code is identical to the preceding complete-core merge.

[Full-code main CI](https://github.com/santthosh/yams/actions/runs/40884610510)
passes all quality/PostgreSQL/offline production Docker gates.
[Exact release-source main CI](https://github.com/santthosh/yams/actions/runs/40886421968)
passes applicable documentation gates; runtime checks are correctly skipped for
that one-line Markdown change. Clean-main 158 targeted backend/84 web tests,
generated contracts, 30 fixture checks, 84 Markdown checks and version agreement
pass. Source preparation passes 472 backend/84 web tests, 188 actual PostgreSQL
cases plus 11 real restart checks, lint/format/separate strict types and Python
wheel/source packaging. The fresh production Docker smoke passes 32 checks,
including restart/rebuild and failure recovery. The actual PostgreSQL suite also
verifies populated 0.0.4 account/job migration through the latest schema.

Local native macOS Turbopack subprocess binding is unavailable in this environment;
that check is not claimed passed. Actual production Docker and Linux CI verify the
production build and browser journeys independently. No assertions or gates were
weakened. See [source fixture trace](../../core-release-evidence.md),
[source restart screenshot](../53-core-source/core-retained-restart-360.png) and
[Decision Center evidence](../52-decision-center/README.md).

## Native packaged core journey

[Candidate run 40888251004](https://github.com/santthosh/yams/actions/runs/40888251004)
passes four native image builds, digest packaging and anonymous fresh amd64/arm64
installations before tag creation. [Tag run 40889643624](https://github.com/santthosh/yams/actions/runs/40889643624)
repeats all builds/package/native installation gates before publication. Actual
hosts are x86_64 and aarch64. Final public image digests and provenance come from
the tag run; preliminary candidate images are not substituted.

Both 360px/1280px browser journeys create a synthetic $1,000 portfolio and inspect
dynamic candidates, three constrained 20% targets plus 40% cash, original strategy/
snapshot/as-of/cost evidence and numerical common-shock 90-calendar-day scenarios
with 5,000 paths. Explicit approval changes no balances. Response-loss recovery
retains the original approval key and body; retries do not duplicate economic
effects. Pending orders retain their original eligible opening; explicit fixture
observations allow the real bounded worker to post complete quantities.

Independent arithmetic, documented with the source evidence, gives quantities
2.857142 / 2.857142 / 2.985074 and cent-rounded debits $200.34 / $200.34 / $194.34,
leaving cash **$404.98**. No pending or cancelled shortfall remains. A subsequent
genuine HOLD recommendation is inspected and dismissed without changing the ledger.

Negative cases exercise a genuinely empty eligible universe/cash-only portfolio,
insufficient pinned calendar coverage with unavailable/null scenarios and a real
aborted account request followed by recovery. Cash-only portfolios retain $1,000,
no holdings and only original funding. Accessible labels, keyboard/modal focus,
Axe and viewport bounds pass. Readonly initial/restart inspections send zero POSTs
and retain identical original approval/order/ledger/scenario/clock records, along
with negative-case results. Prior Strategy Lab/backtest/challenge/fair comparison,
maximum-uint64 seed, private fill and artifact persistence proofs remain required.

## Public assets and installation

All nine public assets were independently downloaded without authentication and
every checksum passed. Version/source/tag-run/fixture provenance, both native
records, final image indexes and safe configuration pass. Both indexes contain
linux/amd64 and linux/arm64 images with BuildKit provenance/SBOM attestations.

- Backend/API/worker: `ghcr.io/santthosh/yams-backend@sha256:ae1215a12f0f44acde0b5f3528a71b4bbac1bb876b0950d0512e69d818a33f16`.
- Web: `ghcr.io/santthosh/yams-web@sha256:b2d1c528d423e1b1723d9e7ae0221a856ddf0891c934c59f7121b6f0154c8ce1`.

Public [amd64 evidence](https://github.com/santthosh/yams/releases/download/v0.0.5/evidence-amd64.json)
and [arm64 evidence](https://github.com/santthosh/yams/releases/download/v0.0.5/evidence-arm64.json)
retain complete native source/image/report/account/worker/restart records.
The release INSTALL.md covers fresh installation, backup, forward migrations
0007–0009 and restore-aware rollback. Only web binds loopback; API/PostgreSQL remain
private and resource limits remain bounded. Provider tokens and licensed market
downloads are excluded. Startup creates no accounts, recommendations or orders;
normal startup/restart preserves volumes. No private user credentials or volumes
were changed. Earlier releases remain immutable.

This documentation follows publication and does not modify the immutable release
source, images, tag or assets. The assigned goal stops before 0.0.6.
