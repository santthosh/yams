# 0.0.4 release verification

The [v0.0.4 Paper Portfolios prerelease](https://github.com/santthosh/yams/releases/tag/v0.0.4) was published at
`2026-10-29T04:22:18Z` from immutable source `14e8dc021c4826d2a512783ee2d31ac223232f58`.
It adds independent cash accounts, backend holdings/valuation, immutable ledger
inspection and private authorization/fenced synthetic fill processing. Public
recommendation/apply/cancel controls and numerical scenarios remain staged for
0.0.5. All financial demonstrations are `SYNTHETIC_DATA_ONLY`; real feeds remain
diagnostic-only. No real money or brokerage is involved.

## Reviewed source and integrated verification

Ledger [PR #129](https://github.com/santthosh/yams/pull/129), account API
[PR #130](https://github.com/santthosh/yams/pull/130), authorization/worker
[PR #132](https://github.com/santthosh/yams/pull/132), account screens
[PR #133](https://github.com/santthosh/yams/pull/133) and release preparation
[PR #134](https://github.com/santthosh/yams/pull/134) passed actual current-head
MergeWatch review and required CI. Reviewed and merged trees match. The
[exact release-source main CI](https://github.com/santthosh/yams/actions/runs/40814643573)
passed all gates; 137 targeted release/account/contract checks and package/API
0.0.4 agreement also pass on the clean release source.

Release preparation passes 406 backend/66 web tests, lint/format/separate strict
types, production web/Python builds, generated-contract checks, 30 canonical
fixtures and 70 Markdown checks. The actual source Docker smoke
`yams-smoke-7caf3252d6d0` passes 21 checks, including account creation, keyed retry,
real worker fill, browser inspection after restart/rebuild and migration-failure
recovery. Required CI repeats applicable PostgreSQL/actual-restart and full
container/browser gates. No private user volumes or credentials were accessed.

The [account screen evidence](../47-portfolios/README.md) contains actual Docker
screenshots, responsive/keyboard/Axe proofs and the independent fixture oracle.
The [ledger handoff](../../operations/paper-ledger.md) covers exact cents/6dp,
concurrency, actual process crash/lost acknowledgment, replay and populated
migration/backup restoration. The [batch handoff](../../operations/paper-batches.md)
covers immutable approval/execution provenance, chronological action blockers,
sale-funded separate commits and atomic queue fences. No public approval UI or
real-data accounting support is claimed by those private services.

## Native packaged installations and publication

[Candidate run 40815824371](https://github.com/santthosh/yams/actions/runs/40815824371)
passed four native image builds, digest packaging and anonymous amd64/arm64
installations before the protected immutable tag was created on the exact source.
[Tag run 40816506275](https://github.com/santthosh/yams/actions/runs/40816506275)
repeated every build/package/native installation gate before publication.
Actual hosts are `x86_64` and `aarch64`; neither installation uses emulation.

Both installations create two independent $1,000 cash accounts through the real
browser at 360px/1280px, retry original keys without duplicate funding and inspect
an explicitly service-seeded private authorization processed by the actual worker.
The posted account has cash $859.76, 2.000000 shares, basis $140.24, NAV $1,063.36,
raw open 70.05, executed price 70.12005, zero commission and $0.14 slippage.
Only funding, approval and fill events exist. Cached restart preserves account
identity/key/history, posted state and all prior Strategy Lab reports/challenges.
The actual UI passes keyboard/Axe/overflow/no-external-request checks.

The first publication attempt created the correct empty draft but its immediate
lookup did not see it. After inspecting that exact-source draft and proving every
build/native gate had passed, one **publication-only** retry reused all original
artifacts/digests and completed. No images were rebuilt and no immutable tag or
published asset was changed. The accompanying publisher regression reproduces
that failure against the unchanged source; a bounded exact-draft visibility wait
addresses future publication while retaining timeout/conflict/permission guards.
This follow-up does not alter the published 0.0.4 source or assets.

## Independent public verification

All nine release assets were downloaded **without authentication** and every
checksum passed: Compose manifests, safe example configuration, INSTALL/RESEARCH
guides, provenance, both complete native evidence records and SHA256SUMS.
The exact version/tag/source/run/native image identity, fixture provenance and safe
configuration checks pass. Both final indexes contain linux/amd64 and linux/arm64;
BuildKit provenance/SBOM accompanies the manifests.

Final digest-pinned images:

- Backend/API/worker: `ghcr.io/santthosh/yams-backend@sha256:640f1eb32de841493501c58c2ecafde0cf06286b622363ca919219a40d5087ec`.
- Web: `ghcr.io/santthosh/yams-web@sha256:bb20b7c9c5293d424963cbc1dd434586b409784821945fe7e6ed9e7b735a4518`.

The public [amd64 evidence](https://github.com/santthosh/yams/releases/download/v0.0.4/evidence-amd64.json)
and [arm64 evidence](https://github.com/santthosh/yams/releases/download/v0.0.4/evidence-arm64.json)
retain the complete source/image/account/worker/report/restart records. Only web
binds loopback; API/PostgreSQL remain private, resources are bounded and normal
restart preserves volumes. Follow the release INSTALL.md for fresh installation,
backup, the forward 0006 migration and restore-aware rollback. Startup/migration
creates no accounts or recommendations. Earlier releases remain immutable.
