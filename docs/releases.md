# Installing and upgrading YAMS releases

YAMS 0.0.4 is a **Paper Portfolios prerelease**, preceding the complete 0.0.5
core product. It adds independent cash accounts, exact-cent posted holdings,
backend valuations and immutable ledger inspection to the existing Strategy Lab,
historical experiments and candidate diagnostics. At `/portfolios`, create a
$1,000 synthetic cash account, select a published strategy version and inspect
its source, cash and history. Creation retries preserve the original account.

Private authorization and the supervised worker can post explicitly authorized
synthetic fills and corporate-action effects with revision/idempotency/lease
fences. Native installation verification uses clearly labeled, service-seeded
synthetic intent to exercise those internals and inspect posted state in the
real browser after restart. **The public recommendation/apply/cancel controls
remain staged until 0.0.5**; this release does not expose an operator approval UI.
Starting or migrating an installation creates no paper accounts or orders.

Missing or stale holding marks retain known cash/shares and show unavailable
value with reasons. No frontend financial calculation or assumed fill is used.
Historical Strategy Lab accounting proofs use `SYNTHETIC_DATA_ONLY`; they are
research evidence, not investment performance or a forecast. Forecasts are not
included in this increment.

Optional Tiingo acquisition requires the operator's own token and terms; source
data remains local. Current real feeds lack historical raw/action/publication/
membership evidence for accounting and remain diagnostic-only. They cannot execute research-mode paper orders. No real money or brokerage is involved.
See `RESEARCH.md` for the optional source workflow.

Existing 0.0.1–0.0.3 releases remain immutable with their original capabilities
and assets. A milestone name or candidate workflow alone does not establish
publication; use the exact release's tag, source SHA, immutable image digests
and native evidence.

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

## First Strategy Lab journey

Open `/lab/strategies`, inspect a template and publish a named fork or new immutable
version. **Run selected version** opens `/lab/experiments` with that version pinned.
Choose the synthetic snapshot, a covered half-open window, positive synthetic USD
capital, SPY and chronological holdout split. The default window reserves a covered
session for next-open lookahead; the backend validates actual calendar/workload.
Current costs are readonly 10bps adverse slippage per side and zero commission.

Follow the queued job into its report. Inspect full/development/holdout metrics,
original-date charts/exact tables, trade evidence and source/method limits. Reruns
create new identities and preserve the exact canonical request, including full-range
uint64 seeds. Cancellation is cooperative and publishes no partial financial report.

At `/lab/compare`, select 2–4 completed experiments. Exact incompatible settings
block metric ranking and curves. **Rerun all with reference settings** creates
explicit comparable requests; different universe rules or older engines can still
require compatible versions/new runs. Only matching completed backend comparison
fingerprints establish alignment. **Change one rule** publishes a maximum-position-
weight copy before submitting its run. Source and target remain inspectable through
the shareable comparison link and stored configurations; no parent-version database
relation is claimed. Other edits belong in the full editor.

Repeated parameter tuning or holdout selection weakens independent validation.
SPY is an adjusted-close, fully invested friction-free approximation; strategy raw
execution and dividend timing differ. Missing benchmark points stay unavailable.
Scheduled work runs only while Docker is active. Backtests do not post durable
paper holdings/fills, and neither backtests nor later scenario models guarantee
future outcomes.

## First paper account journey

Open `/portfolios`, give the account a name, keep or edit the positive starting
capital and select an actual published strategy version. Choose the source mode
explicitly; fixture and research accounts stay independent. A confirmed default
account has $1,000 cash, 100% cash weight and no posted holdings. View its funding
event, original strategy version, risk assumptions and current reconciliation
status. Inspect an account with posted holdings to see exact quantity/basis,
mark/session, cash, total value and immutable transaction lineage/fees.

If creation loses its response, use **Retry same account creation** with the frozen
request rather than starting another account. Definitive validation errors allow
editing. Missing marks leave value unavailable, never zero; known cash and shares
remain visible. Refresh if account and separately paginated history show different
sequences. Pending/partial/cancelled presentation is implemented, while live batch
inspection and approval remain honestly staged for 0.0.5. No UI action in this
increment previews or approves a recommendation.

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

The 0.0.2→0.0.3 upgrade adds immutable experiment/core/report tables and reviewed
alternative-family seeds. Existing workspace, snapshots, strategy versions,
diagnostic results and artifacts are preserved. The original momentum template
remains unchanged. No paper portfolio or trade is created by migration or boot.
Back up both stores before upgrading; new images may write schemas older images
cannot read. Existing results pin their original engine; use explicit common-setting
reruns rather than treating different engine builds as directly comparable.
Older images must not be run against a newer schema as an assumed rollback.

The 0.0.3→0.0.4 upgrade adds the `0006_paper_ledger` migration: linked account,
recommendation, batch, order, immutable event/fill/entry/action and projection
records with deferred accounting safeguards. Existing workspace, preferences,
strategies, snapshots, jobs, experiments and artifacts are retained. Migration
creates no accounts, recommendations or fills. Durable account keys, histories
and pending private-worker jobs survive normal restart; work runs only while
Docker is active. Real research data remains unsuitable for accounting. Back up
both stores before applying this forward migration; use the prior matching
backup and images for restore-aware rollback.

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
