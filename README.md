# YAMS

Yet Another Market Simulator is a local, single-user paper research workspace. It never connects to a brokerage or trades real money.

## Current state

The `0.0.1` foundation provides an importable FastAPI package, an accessible Next.js Dashboard/Settings shell, versioned contracts, synthetic fixtures, PostgreSQL workspace/job migrations, a bounded diagnostic worker and working quality commands. `/livez` checks only that the API process responds; `/api/v1/health` checks database/migration/workspace/fixture readiness. Local Compose, isolated smoke checks and protected GitHub Actions CI are implemented. The release workflow builds and verifies native amd64/arm64 candidates before publication; see [release installation and recovery](docs/releases.md). Publication is complete only when the corresponding verified GitHub Release exists. No portfolio values or investment results are seeded by this foundation.

## Local Docker startup

With Docker Compose 2.38.2 or newer, run `docker compose up --build -d --wait`, then open `http://127.0.0.1:3000`. Initial builds download pinned images and locked dependencies; cached runtime needs no external provider. Migrations and workspace seeding run before the API and worker. Named database/artifact volumes survive restart and rebuild.

See [local operations](docs/operations/local-compose.md) for offline startup, resource caps, diagnostics and the separate destructive `make reset` command. [Compose verification](docs/verification/25-compose/README.md) records browser, job, failure/recovery and resource evidence. `make smoke` requires the development dependencies and Playwright Chromium described below. `make dev` runs native web/API with hot reload and a separate Docker PostgreSQL/worker project, as approved in Q14. Full-container mode remains authoritative.

## Development setup

Use Python **3.13.12**, uv **0.8.0**, Node **22.17.0** and pnpm **10.23.0**. `.python-version`, `.nvmrc`, `pyproject.toml` and `package.json` record these versions. Install the pinned Python via your runtime manager if an older uv distribution does not provide that patch release. The runtime must be available before `make install`.

```sh
nvm install
nvm use
npm install --global pnpm@10.23.0
make install
```

Install uv 0.8.0 with your preferred tool installer. `make install` uses `uv sync --locked` and `pnpm install --frozen-lockfile`; neither is allowed to resolve a different dependency graph. Both installs need registry access initially. Python dependencies are shared by the API and worker through the `backend` package. The web workspace is `apps/web`. Exact direct dependencies and transitive resolutions are committed in the manifests/lockfiles.

In separate terminals:

```sh
uv run --locked uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
API_INTERNAL_ORIGIN=http://127.0.0.1:8000 pnpm --filter @yams/web dev
```

Open `http://127.0.0.1:3000`; inspect process liveness at `http://127.0.0.1:8000/livez`. Without a configured database, the shell shows unavailable workspace/readiness states; it does not invent balances. Provider credentials are not needed. Native development binds to loopback; Compose publishes only the web port. `.env.example` documents available settings; `.env` and downloaded/cached market data are ignored. The UI uses system fonts so builds do not fetch remote fonts.

## Verification

```sh
make lint
make typecheck
make test
make contracts-check
make build
```

`lint-backend` runs Ruff checks and formatting; `lint-web` runs ESLint and Prettier. `typecheck-backend` runs strict mypy separately from frontend `next typegen`/TypeScript. `test-backend` exercises liveness and unavailable routes without a DB; `test-web` verifies formatting, provenance/job/error states and proxy boundaries with Vitest. `build-backend` creates a wheel/sdist and `build-web` creates a production Next.js build. These targets propagate failures and contain no empty success stubs.

Playwright is pinned. Install its Chromium once with `pnpm --filter @yams/web exec playwright install chromium`, then run `make test-e2e` for production-build browser checks at 360px and 1280px against a labeled synthetic transport. `make test-integration` verifies PostgreSQL in an isolated Docker project; `make smoke` verifies the full container application with isolated volumes; `make dev` starts the approved native web/API plus Docker worker/database workflow. Tailwind and locally owned shadcn-style primitives are implemented; charts remain with their feature owners.

Read [AGENTS.md](AGENTS.md), the [implementation blueprint](docs/IMPLEMENTATION_BLUEPRINT.md), and the scoped GitHub issue before changing financial semantics. Milestone `0.0.1` is not released merely because the scaffold builds.

## Versioned contracts

`backend/domain` implements closed Pydantic contracts for strategies, market bars and snapshot manifests, recommendations, forecasts, paper orders, experiments, jobs, errors and pagination. Money, quantities, prices and allocation weights remain decimal strings; statistical numbers must be finite. Cross-field validators enforce complete allocations and lifecycle-dependent results. These validators do not implement financial calculations, storage, calendar verification or artifact-byte verification.

Run `make contracts` after changing a model or route. It regenerates `contracts/openapi.json`, input/output JSON schema goldens and `apps/web/src/api/generated/` using pinned tools. Commit these artifacts together. `make contracts-check` compares them byte-for-byte without rewriting; Python and frontend tests deliberately introduce isolated schema drift and require failure before regeneration. The generated `createApiClient` accepts a base URL and optional fetch implementation. Implemented typed paths are `/livez`, `/api/v1/health`, `/api/v1/workspace` and `/api/v1/jobs/{job_id}`; future domain components do not activate financial endpoints.

New API routers must use `APIRouter(route_class=ContractRoute)` from `backend.api.routing` to preserve exact JSON score numbers and reject duplicate keys/NaN before Pydantic validation. Direct routes on `create_app()` already use this class. For raw offline strategy documents, use `StrategyConfigV1.from_json`; parsing with ordinary float-based `json.loads` first loses precision. Serialize validated models with `model_dump(mode="json")` or FastAPI response models. Use the shared typed error envelope and `error_response` for documented feature failures; validation errors expose field paths without submitted values.

Payload examples in `backend/tests/contracts/examples/` are **SYNTHETIC_DATA_ONLY**, illustrative contract shapes, not market evidence or engine outputs. IDs and hashes are placeholders; the forecast uses an abbreviated synthetic calendar and a zero-return all-cash case. Actual snapshot bytes, exchange calendars, forecast arithmetic, transactions and financial job behavior remain with their owning feature issues. The schema and client checks require no database, Docker or provider network.

## Offline synthetic fixtures

`data/fixtures/` contains a complete four-year synthetic snapshot and FIX-01–FIX-10 independent input/oracle cases. `make fixtures` regenerates the committed artifacts; `make fixtures-check` detects byte drift. Fixture generation and tests use locked NumPy 2.5.4 for the pinned PCG64 sampling inputs. The snapshot is deliberately synthetic, including its versioned weekday calendar; it is not real exchange data or evidence of implemented financial engines. See the [fixture handoff](backend/tests/fixtures/README.md) for checksums, formulas, tolerances, limitations and later test owners. Compose readiness validates this snapshot and displays its labeled metadata; this does not execute financial simulations.

## PostgreSQL workspace

Set `DATABASE_URL` to a private PostgreSQL16 service using the `postgresql+psycopg://` driver. `.env.example` shows the format; the application reads environment variables rather than loading `.env` implicitly. Keep the database port unpublished. Set `YAMS_FIXTURE_ROOT` only to the trusted, committed fixture root when it differs from the repository default.

`make db-bootstrap` upgrades the single linear Alembic head and seeds one local workspace in the same transaction, serialized by a PostgreSQL advisory lock. Repeating it preserves the workspace UUID, locale and preferences. Run it before starting API/worker services; importing or starting the API never silently migrates a database. A failed migration exits nonzero with a sanitized message and rolls back. Connection, statement, lock and pool waits are bounded. Restore from a verified backup for rollback; destructive downgrade is intentionally unsupported.

Migration `0001_workspace` owns only `local_workspace` and Alembic metadata. Defaults are `en-US`, benchmark `SPY`, and theme `system`; a unique singleton marker and check constraint prevent a second workspace. There are no users, tenants, authentication or financial tables. Subsequent owners add linear revisions according to ADR-004 and must not rewrite this revision or reseed existing preferences. Workspace settings mutation remains with its later contract owner.

`GET /api/v1/health` returns200 only when database, schema, workspace and all synthetic snapshot artifact checks pass; otherwise503 with safe reason codes and no connection strings. Invalid database configuration is distinguished as `DATABASE_MISCONFIGURED`. Server logs identify failed probe components and exception classes without messages, SQL, values or tracebacks; bootstrap failures likewise expose only the exception class. `GET /api/v1/workspace` returns persisted configuration, or retryable `503 NOT_READY` when its database/schema/workspace is unavailable. Fixture metadata is explicitly synthetic. These read-only checks do not register snapshots, execute jobs or prove financial calculations.

`make test-integration` builds a hash-locked test image and starts a unique disposable Compose project, publishes no host ports, and tests empty/concurrent/repeated bootstrap, singleton enforcement, preferences, unavailable DB, mismatched schema, failed-migration rollback and missing fixtures. It restarts the actual PostgreSQL container and verifies identity/preferences afterward, then removes only its own containers/network/volumes. Existing user volumes are never reset. Docker and initial registry access are required; cached tests use no provider service. Unit tests exclude the `integration` marker explicitly; integration is a separate required command. After dependency changes, regenerate the test image's requirements with `uv export --locked --format requirements-txt --no-emit-project --output-file infra/docker/integration-requirements.txt`.

## Durable diagnostic jobs

Migration `0002_jobs` adds immutable job envelopes, attempt history, fixed-interval
schedules and one idempotent diagnostic effect per job. The PostgreSQL queue uses
fenced leases and bounded recovery; a Linux supervisor renews heartbeats while a
separate resource-limited process executes the diagnostic. No financial handlers
are registered. `GET /api/v1/jobs/{job_id}` is read-only; public cancellation is
owned by #41, not this foundation endpoint.

See [worker operations](docs/operations/durable-jobs.md) for configuration,
enqueue/schedule/cancel service examples, guarantees and deployment limitations.
`make test-integration` also exercises queue contention, cancellation, bounded
retries, scheduler catch-up, actual process crashes and resource failures. It
retains measurements in ignored `test-results/integration/<project>/worker.json`.
The [verification report](docs/verification/23-durable-jobs/README.md) records the
measured environment and committed evidence; these are not financial benchmarks.

## Web shell and same-origin transport

Dashboard and Settings are implemented in `apps/web/src/app`. Unavailable Lab,
Portfolios, Arena and Journal routes are hidden. Global paper scope, source/as-of
metadata and last-checked job status stay visible. Settings exposes persisted
workspace preferences read-only and a job-ID lookup; it does not enqueue or cancel
work. Missing monetary values display `Unavailable`, never a substituted zero.

Set `API_INTERNAL_ORIGIN` only in the web server environment. Its default is
`http://api:8000` for the private Compose network; native development uses
`http://127.0.0.1:8000`. It is not a `NEXT_PUBLIC_` setting and is not sent to the
browser. The browser uses same-origin `/api/v1` routes. The proxy allows only GET
health/workspace and GET jobs with UUIDs, rejects other paths/methods/query strings,
does not forward cookies/authorization, rejects redirects, and bounds upstream
requests at three seconds. Failures carry safe correlation IDs.

[Web-shell handoff and verification](docs/verification/24-web-shell/README.md)
describes components, fixtures, browser evidence and the boundary between these
transport tests and #25's integrated Docker/persistence journey.
