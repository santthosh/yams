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
Issue #25 is delivered in PR #92. Release images
and installation artifacts are owned by #28, not by these local image tags.

## Development with hot reload

After `make install`, run `make dev`. Web and API run natively on loopback ports
3000 and 8000, with Next Fast Refresh and Uvicorn source reload. PostgreSQL and the
worker run in the separate `yams-dev` Compose project; the worker retains Linux
cgroup/process enforcement. This is the Q14 workflow, including on macOS. Worker
source is mounted read-only; use `docker compose -p yams-dev -f compose.dev.yaml restart worker`
after handler changes. Dependency changes require rebuilding/restarting the launcher.

The development database publishes an ephemeral loopback port which the launcher
discovers. `YAMS_DEV_DB_PORT` selects a fixed port if needed. This is an explicit
development exception: the default full-container application still publishes only
web. `YAMS_DEV_API_PORT` and `YAMS_DEV_WEB_PORT` select native ports. The launcher
rejects occupied ports and duplicate launchers and stops both native processes if
either exits. Ctrl-C/SIGTERM stops the development containers while preserving
their separate named volumes. It does not reset application or development data.

`YAMS_DEV_PROJECT=yams-dev-<suffix>` creates a separate development namespace for
verification. Avoid running multiple Next dev processes in the same checkout.
The launcher does not load `.env` into native processes; export optional settings
in the shell. Database/fixture/proxy addresses are supplied by the launcher.
