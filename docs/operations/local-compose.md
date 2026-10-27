# Local foundation runtime

The application has four long-running services: web, API, worker and PostgreSQL.
The migration service runs once before API/worker startup. It upgrades the schema
and idempotently creates the singleton workspace; it never clears stored data.
The web service waits for API readiness, including schema, workspace and fixtures.

## Build and start

From the repository root, with Docker Compose 2.38.2 or newer available:

```sh
docker compose up --build -d --wait
docker compose ps
```

Open `http://127.0.0.1:3000`. Dashboard and Settings show a local paper-only
workspace and labeled synthetic fixture metadata. No API key or account is needed.
There are no portfolio computations or investment results in this increment.

The first build downloads pinned base images and locked dependencies. Once those
images are available, `docker compose up -d --wait --pull never --no-build` uses
them without downloading dependencies. Offline runtime does not mean an uncached
first build works without internet.

Only the web port is published, on loopback. Set `YAMS_WEB_PORT` to change its port.
API, PostgreSQL and worker use an internal Docker network without external routing.
Web additionally joins an ingress network with explicit gateway priority for the published port. The application
does not call external providers; the synthetic fixture set is baked into the
read-only backend filesystem. Web requests stay on the browser's origin.

The fixed `yams_local_only` PostgreSQL password is a public local default for this
private network, not an external-service credential. Do not expose PostgreSQL or
reuse this value elsewhere. Operator-specific tokens and `.env` are excluded from
the image build context. Backend and web run as non-root users with read-only root
filesystems; the PostgreSQL image performs its own initialization.

## Retain and inspect data

```sh
docker compose logs --tail 100 api worker migrate
docker compose restart
docker compose down
docker compose up -d --wait
```

`down` preserves the project-scoped `database` and `artifacts` named volumes.
Rebuilds and container replacement preserve those volumes too. `/artifacts` is
the shared writable artifact mount; repository fixtures are separate and immutable.
Do not use `down --volumes` during normal startup, restart or upgrade.

`make reset` is a separate, destructive operation. It lists the resolved project
and volume names and requires typing `delete <project>` before deletion. Back up
valuable data first. It is never invoked by startup, migration or smoke commands.

API readiness fails when migrations, fixtures or storage are unavailable. If a
migration fails, inspect its logs and correct the cause before restarting. Never
manually change a production migration revision to hide a failed migration.
The smoke test deliberately corrupts only its disposable test database.

## Verification and limits

`make smoke` creates a unique project and ephemeral loopback web port. It verifies
real API/browser/job behavior, immutable fixtures, restart/rebuild persistence,
resource/port configuration and migration-failure gating. Its cleanup removes only
that randomly named test project's containers, networks and volumes. Evidence and
screenshots are retained under ignored `test-results/smoke/<project>/`.

Runtime caps total four CPU cores and 4.5 GiB: worker 2 CPU/2 GiB, web 1 CPU/1 GiB,
API 0.5 CPU/512 MiB and PostgreSQL 0.5 CPU/1 GiB. Migration runs before application
services and has a 0.5 CPU/512 MiB cap. Swap is disabled for these containers.
These are enforced ceilings, not performance guarantees. Builds need additional
temporary resources. The worker requires Linux cgroup v2, including on Docker
Desktop's Linux VM; native macOS execution does not supply that enforcement.

The [verification report](../verification/25-compose/README.md) records measured
startup and diagnostic load, browser and failure/recovery evidence.
Issue #25 is still in implementation. Native development,
the complete operational handoff and review gates remain pending. Release images
and installation artifacts are owned by #28, not by these local image tags.
