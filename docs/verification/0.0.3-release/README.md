# 0.0.3 release verification

The [v0.0.3 Strategy Lab prerelease](https://github.com/santthosh/yams/releases/tag/v0.0.3)
ships immutable source `86ac61397b8a11db62017e99d5cf3f7821d191ea`.
It adds strategy publication/templates, bounded walk-forward experiments,
full/development/holdout reports, SPY/cash references, fair comparison and a
controlled maximum-position-weight challenge. Historical accounting examples are
explicitly `SYNTHETIC_DATA_ONLY`; real feeds remain diagnostic-only. Durable paper
accounts/orders/fills and forecasts are later increments.

## Reviewed source and installation gates

[Feature PR #126](https://github.com/santthosh/yams/pull/126) and
[release preparation PR #127](https://github.com/santthosh/yams/pull/127) passed
actual current-head MergeWatch 5/5 without findings or unresolved threads and their
required CI. Reviewed and merged source trees match. Exact release-source
[main CI](https://github.com/santthosh/yams/actions/runs/40774123146) passed; 29
release/API guards and package/API 0.0.3 agreement also passed on clean main.

The source Docker smoke `yams-smoke-7083e50e3155` passes 16 checks: actual
editor→version→experiment→report→challenge→comparison, mismatched-capital and
common-setting reruns, exact 42/MAX uint64 seeds, cancellation, original preservation,
restart/rebuild and migration-failure recovery. No private user volumes or provider
credentials were accessed. Feature proofs remain in
[the comparison evidence](../43-comparison/README.md).

[Candidate dispatch 40775442456](https://github.com/santthosh/yams/actions/runs/40775442456)
passed four native builds, digest packaging and anonymous native amd64/arm64
installations before tag creation. The protected immutable `v0.0.3` tag was then
created at the exact verified source. [Tag run 40776462863](https://github.com/santthosh/yams/actions/runs/40776462863)
repeated all builds/package/native installations before publishing the prerelease.
No emulation or tag/protection bypass was used.

Both actual native installations run the full editor/report/challenge/fair-rerun
journey with keyboard/Axe/exact tables at 360px and desktop. They verify source and
fixture bytes, exact canonical inputs/full uint64 seeds, managed artifact hashes,
unchanged originals, newly published challenge versions and cached-restart
persistence. Original and challenge cash/returns are derived by the shared backend;
no frontend financial calculation or new financial default was added.

## Publication and independent public verification

The first publication attempt created the correct draft but its immediate lookup
could not see it. After confirming the same empty draft/source, a single failed-
publication-job retry reused every passing build/native artifact and identical
image digest. No tag or image was rebuilt, moved or overwritten. Attempt 2 published
successfully at 2026-10-28T22:07:51Z.

All nine public release assets were independently downloaded **without authentication**.
Every checksum, exact tag/source/version, native evidence/image identity and
safe configuration check passed; both final image indexes contain native
linux/amd64 and linux/arm64. [Verification summary](public-verification.json)
records the actual source/run/digests/platforms. The public release retains both
complete native evidence records, checksums and source/run/fixture provenance.
BuildKit provenance/SBOM accompanies image manifests.

Final digest-pinned images:

- Backend/API/worker: `sha256:9bbd5e558c678d905e0802af3f2a0ebb25ead1af827d8a7293f925ee4a6aa06c`.
- Web: `sha256:b62a9d76745f111b2e13093b03aa103a4ecfc54cc7c73f33302c4b59f4247c5e`.

Only web binds loopback; API/PostgreSQL remain private, resources are bounded and
normal restart/upgrade preserves volumes. Follow the release's INSTALL.md for
fresh installation, backup and forward-migration/restore-aware rollback guidance.
The first image pull needs registry access; cached operation is offline. Earlier
0.0.1/0.0.2 releases retain their original immutable assets and capabilities.
