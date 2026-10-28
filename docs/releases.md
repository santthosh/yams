# Installing and upgrading YAMS releases

YAMS 0.0.1 is a **prerelease foundation**, not the complete 0.0.5 financial product.
It provides a clearly labeled synthetic Dashboard/Settings shell, durable local
workspace, bounded diagnostic worker and offline fixtures. Recommendations,
backtests, forecasts and paper trading remain unavailable. No real money, broker,
provider account or API key is used.

## Fresh installation

Use Docker with Linux containers, Compose 2.38.2 or newer, and enough resources
for the 4 CPU / 4.5 GiB application allocation plus Docker overhead (at least
6 GiB allocated to Docker). Published installations support native linux/amd64
and linux/arm64, verified separately. Docker Desktop supplies Linux on macOS.

Download **all assets** from the same GitHub prerelease into a new directory:
`compose.yaml`, `.env.example`, `INSTALL.md`, `provenance.json`, both platform
evidence JSON files and `SHA256SUMS`. Verify before startup:

```bash
sha256sum --check SHA256SUMS
# macOS alternative: shasum -a 256 -c SHA256SUMS
cp .env.example .env
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
