# 0.0.1 release verification

The [v0.0.1 foundation prerelease](https://github.com/santthosh/yams/releases/tag/v0.0.1)
ships source `9878dbb2dd562f1b19667189c07dd33376c9ac0d`. It provides the local
synthetic workspace, Dashboard/Settings, versioned contracts, fixtures, PostgreSQL
persistence and bounded diagnostic worker. Financial engines and live providers
remain unavailable; the first complete core product is scheduled for 0.0.5.

## Reviewed source and runtime gates

- [Implementation PR #97](https://github.com/santthosh/yams/pull/97): current-head
  MergeWatch approved after the checksum finding was resolved. All checks passed in
  [PR CI](https://github.com/santthosh/yams/actions/runs/40610108391) and
  [exact-source main CI](https://github.com/santthosh/yams/actions/runs/40610865794).
- Local merged-state `make smoke` passed in isolated project
  `yams-smoke-3f00b0c100c0`: fresh boot, browser at 360/1280px, persisted diagnostic,
  concurrent reads, external-routing rejection, restart/rebuild retention, resource
  caps, private ports and failed-migration recovery. Only its own volumes were removed.
- [Candidate dispatch](https://github.com/santthosh/yams/actions/runs/40611483562)
  passed native amd64/arm64 builds and anonymous packaged installations before tag creation.
- [Final tag run](https://github.com/santthosh/yams/actions/runs/40611902167) passed
  all four native builds, digest packaging and both native installation checks.
  Each installation checked anonymous pulls, actual architecture/source labels,
  bundled fixture bytes, real browser/API/worker behavior and cached restart with
  retained workspace, job and artifact. No emulation was used.

Final image indexes (the manifest pins these literal digests):

- Backend/API/worker: `sha256:273d16d9dba1d098117eab80e37e6091ab7e815ecf9012ada47fc42cf62cca6e`
- Web: `sha256:78de8b216f32a6046847874bb271359d0d569dd2407edbdd496b01b35f1c0a90`

BuildKit provenance/SBOM accompanies the image manifests. Release assets retain
source/run/fixture provenance and the actual native verification records. Workflow
artifacts also contain browser screenshots and Compose logs, retained for 30 days.

## Publication failure and verified recovery

GitHub normalized `.env.example` to `default.env.example`. The final tag run's
publication job rejected the unexpected asset and left the release as a draft;
there was no premature successful release. An asset rename API request returned the
same normalized name. Neither the tag, image digests nor asset bytes were changed.

[Recovery PR #98](https://github.com/santthosh/yams/pull/98) adds exact handling for
this legacy alias and uses `env.example` for future bundles. MergeWatch approved;
161 Python tests, 42 web tests, types, contracts and full CI passed. The recovery
workflow requires passing main CI for its implementation and original release
source, a failed tag publication with every native gate successful, and the same
unpublished draft. It reuses original artifacts without rebuilding.

The first recovery attempt stopped in its read-only validation job because private
GitHub drafts require write-scoped listing access. [PR #99](https://github.com/santthosh/yams/pull/99)
moved the draft check to the publication job before any mutation and added the
162nd Python test; MergeWatch and
[PR CI](https://github.com/santthosh/yams/actions/runs/40614445106) passed.
[Recovery implementation main CI](https://github.com/santthosh/yams/actions/runs/40615050110)
and [final recovery publication](https://github.com/santthosh/yams/actions/runs/40615528520)
passed. Public assets were independently downloaded without authentication, every
checksum passed, and every byte matched the original draft. Both published native
evidence records match the final image digests and original source. The release is
public and explicitly marked prerelease; its protected tag remains unchanged.

For this first release, download all assets and run
`cp default.env.example .env.example` **before** the checksum/install commands in
its INSTALL.md. This is also stated prominently in the release notes. Both the
recovery job and independent downloads verify the complete original checksum set
after this filename-only copy. Future bundles avoid the workaround.

## Negative cases and release controls

- [Non-main dispatch](https://github.com/santthosh/yams/actions/runs/40610896008)
  failed validation; build, package, verify and publish were all skipped.
- [Duplicate-version dispatch](https://github.com/santthosh/yams/actions/runs/40615605387)
  rejected the published version before all build/package/verify/publish jobs.
- Local tests exercise actual Git ancestry rejection, wrong/failed main-CI records,
  missing/failed native evidence, immutable image references, conflicting draft
  assets, interrupted upload recovery and invalid recovery-run gates. These are
  local tests, not claims of hosted destructive tag probes.
- Active tag ruleset readbacks are recorded as [creation](tag-creation.json) and
  [immutability](tag-immutability.json). Creation is administrator-only; updates and
  deletion have no bypass actors. Main requires current-base CI, current-head
  MergeWatch and resolved conversations, including administrators.

Installation requires an initial public image download; cached runtime is offline.
Docker uses Linux containers, native amd64/arm64, Compose 2.38.2+ and the documented
resource allocation. There is no automatic upgrade or hosted deployment. Backup,
restore-aware rollback and migration limits are in the release's INSTALL.md and
[current release operations](../../releases.md). No credentials or licensed market
datasets are included. The milestone is a foundation, not a financial-performance demo.
