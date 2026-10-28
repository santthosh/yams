# Installing and upgrading YAMS releases

YAMS 0.0.2 is a **candidate diagnostics prerelease**, preceding the complete 0.0.5
core product. It adds immutable market snapshots, source discovery/refresh,
published strategy versions, shared momentum ranking and feasible target-weight
diagnostics. The offline fixture journey is clearly labeled synthetic. Optional
personal-use Tiingo acquisition requires the operator's own token and terms;
source data remains local. Complete corporate-action accounting, backtests,
forecasts and durable paper accounts/orders/fills remain unavailable. No real
money or brokerage is involved. See `RESEARCH.md` for the optional source workflow.

The existing 0.0.1 release remains an immutable foundation with its original
installation assets and capabilities; its filename compatibility note appears below.
A milestone name alone does not establish that a release has been published.

## Fresh installation

Use Docker with Linux containers, Compose 2.38.2 or newer, and enough resources
for the 4 CPU / 4.5 GiB application allocation plus Docker overhead (at least
6 GiB allocated to Docker). Published installations support native linux/amd64
and linux/arm64, verified separately. Docker Desktop supplies Linux on macOS.

Download **all assets** from the same GitHub prerelease into a new directory:
`compose.yaml`, `compose.research.yaml`, `env.example`, `INSTALL.md`, `RESEARCH.md`,
`provenance.json`, both platform
evidence JSON files and `SHA256SUMS`. Verify before startup:

```bash
sha256sum --check SHA256SUMS
# macOS alternative: shasum -a 256 -c SHA256SUMS
cp env.example .env
docker compose pull
docker compose up -d --wait --pull never
```

Open http://127.0.0.1:3000. The manifest contains literal immutable image digests;
PostgreSQL is also pinned. API/PostgreSQL are private and only web binds loopback.
`YAMS_WEB_PORT` in `.env` changes the local web port. Keep the private networking
and resource controls unless you deliberately accept different exposure/behavior.
Do not add credentials to release files or Git.

The first pull requires internet, but uses public GHCR images without a login.
After images are cached, `docker compose up -d --wait --pull never` needs no market
provider or registry access. Startup migrates/seeds without resetting data.
`docker compose down` stops services and preserves database/artifact volumes.
Do not use `down --volumes` for normal operation or upgrades.

## Backup before upgrading

Keep the existing Compose manifest, `.env`, exact image digests and backups
together outside Git. Stop writers, leave PostgreSQL running, and back up both
durable stores. Use private backup paths; artifacts may contain operator data in
later releases.

```bash
docker compose stop web api worker
docker compose exec -T postgres pg_dump -U yams -d yams -Fc > workspace.dump
docker compose run --rm --no-deps --entrypoint tar worker -C /artifacts -czf - . > artifacts.tgz
docker compose up -d --wait --pull never
```

Verify that backup files are nonempty and test restoration into a separate project
before relying on them. A successful dump command alone is not restoration proof.

## Upgrade and restore-aware rollback

The 0.0.1 → 0.0.2 upgrade adds snapshot publication, immutable strategy versions and
diagnostic-evaluation tables. Startup applies Alembic migrations in order and
preserves the workspace and existing artifacts; it never resets either store.
The default strategy is seeded immutably. Back up both durable stores first.
Older images must not be run against a newer schema as an assumed rollback.

Read the new release's migration notes. Download/verify its assets separately,
back up the old installation, stop old services with `docker compose down`, then
use the new manifest with the **same project name and volume definitions** to
retain data. Pull new digests and start with `up -d --wait --pull never`. Inspect
`docker compose ps` and logs if migration/readiness fails. Never reset volumes to
hide a failed upgrade. Upgrades are operator initiated; CD publishes artifacts and
does not update your machine or deploy a hosted service.

Changing images back does not reverse a database migration. Rollback may require
the prior manifest/images plus the matching pre-upgrade database and artifact
backup. Restore into a **new project with empty volumes**, preserving the original
installation. For example, use the previous release manifest and consistently
pass `-p yams-restored`:

```bash
docker compose -p yams-restored up -d --wait postgres
docker compose -p yams-restored exec -T postgres pg_restore --no-owner --exit-on-error -U yams -d yams < workspace.dump
docker compose -p yams-restored run --rm --no-deps --entrypoint tar worker -C /artifacts -xzf - < artifacts.tgz
docker compose -p yams-restored up -d --wait --pull never
```

Use only your own verified backups. Confirm the new database is empty before
restore; do not apply this example over live data. Stop the original web service
or choose another loopback port before starting the restored web service.

## Publication and recovery

The release workflow accepts a main-branch dispatch with a semver version or a
version-tag push. It verifies exact source ancestry and passing main CI, builds
native candidates with provenance/SBOM, assembles immutable indexes and checks
anonymous packaged installation on both architectures. A main dispatch verifies candidates without publishing a final release. After
that succeeds, a repository administrator creates the immutable version tag on
that exact source SHA; the tag-triggered run repeats verification and publishes
version aliases and a GitHub prerelease. The built-in Actions integration cannot
be granted the tag-creation exception in this repository, so creation is limited
to administrators. Update/deletion protection has no exceptions.

Packages must be public under approved Q06. Repository visibility does not imply
package visibility. If the initial anonymous pull fails because a new package is
private, set the two YAMS packages public in GitHub package settings and rerun
**failed jobs** on the same run. Successful build outputs and candidate digests
are retained for 30 days. Do not rebuild/overwrite a published version to repair
it; use a new version for changed content.

Partial publication remains a draft or failed workflow. Identical draft assets
can resume, but conflicting digests/assets and existing published versions are
rejected. Downloaded assets are byte-checked before the draft becomes public.
`provenance.json` links the source/run and immutable images; platform evidence
records actual native architecture, fixture hash, browser/job and restart checks.
The release's `SHA256SUMS` covers all installation and evidence assets.

## Recovering the first release upload

GitHub renamed the original 0.0.1 `.env.example` upload to `default.env.example`.
The immutable 0.0.1 bundle retains its original bytes and checksums: follow the
release note and copy `default.env.example` to `.env.example` before checking
checksums and following that bundle's INSTALL.md. Future bundles use `env.example`
to avoid this filename normalization.

The manual Release recovery workflow accepts only a failed tag run whose native
build/package/installation gates all passed and whose identical draft still exists.
Both the recovery implementation and original source must have passed main CI.
It reuses retained artifacts and image digests, verifies downloaded asset bytes and
checksums, and never rebuilds images, moves tags or replaces conflicting assets.
