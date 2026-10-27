# YAMS

Yet Another Market Simulator is a local, single-user paper research workspace. It never connects to a brokerage or trades real money.

## Current state

The `0.0.1` foundation provides an importable FastAPI package, a labeled Next.js shell, versioned contracts, synthetic fixtures, PostgreSQL workspace migrations and working quality commands. `/livez` checks only that the API process responds; `/api/v1/health` checks database/migration/workspace/fixture readiness. Durable jobs, application Compose, CI and release packaging remain tracked foundation work. No portfolio values or investment results are seeded by this foundation.

## Development setup

Use Python **3.13.12**, uv **0.8.0**, Node **22.17.0** and pnpm **10.23.0**. `.python-version`, `.nvmrc`, `pyproject.toml` and `package.json` record these versions. Install the pinned Python via your runtime manager if an older uv distribution does not provide that patch release. The runtime must be available before `make install`.

```sh
nvm install
nvm use
npm install --global pnpm@10.23.0
make install
```

Install uv 0.8.0 with your preferred tool installer. `make install` uses `uv sync --locked` and `pnpm install --frozen-lockfile`; neither is allowed to resolve a different dependency graph. Both installs need registry access initially. Python dependencies are shared by the API and future worker through the `backend` package. The web workspace is `apps/web`. Exact direct dependencies and transitive resolutions are committed in the manifests/lockfiles.

In separate terminals:

```sh
uv run --locked uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
pnpm --filter @yams/web dev
```

Open `http://127.0.0.1:3000`; inspect process liveness at `http://127.0.0.1:8000/livez`. No database or provider credentials are needed. Native development binds to loopback; final Compose networking is owned by #25. `.env.example` documents available settings; `.env` and downloaded/cached market data are ignored. The UI uses system fonts so builds do not fetch remote fonts.

## Verification

```sh
make lint
make typecheck
make test
make contracts-check
make build
```

`lint-backend` runs Ruff checks and formatting; `lint-web` runs ESLint and Prettier. `typecheck-backend` runs strict mypy separately from frontend `next typegen`/TypeScript. `test-backend` exercises liveness and unavailable routes without a DB; `test-web` renders the paper-only/empty shell with Vitest. `build-backend` creates a wheel/sdist and `build-web` creates a production Next.js build. These targets propagate failures and contain no empty success stubs.

Playwright is pinned and its CLI is available through `pnpm --filter @yams/web playwright`; browser journeys and `make test-e2e` arrive with #24. `make test-integration` verifies the PostgreSQL foundation in an isolated Docker project; `make dev`/`make smoke` arrive with #25. Do not interpret these planned commands as existing checks. Tailwind/shadcn components and chart dependencies arrive with their UI owners when used.

Read [AGENTS.md](AGENTS.md), the [implementation blueprint](docs/IMPLEMENTATION_BLUEPRINT.md), and the scoped GitHub issue before changing financial semantics. Milestone `0.0.1` is not released merely because the scaffold builds.

## Versioned contracts

`backend/domain` implements closed Pydantic contracts for strategies, market bars and snapshot manifests, recommendations, forecasts, paper orders, experiments, jobs, errors and pagination. Money, quantities, prices and allocation weights remain decimal strings; statistical numbers must be finite. Cross-field validators enforce complete allocations and lifecycle-dependent results. These validators do not implement financial calculations, storage, calendar verification or artifact-byte verification.

Run `make contracts` after changing a model or route. It regenerates `contracts/openapi.json`, input/output JSON schema goldens and `apps/web/src/api/generated/` using pinned tools. Commit these artifacts together. `make contracts-check` compares them byte-for-byte without rewriting; Python and frontend tests deliberately introduce isolated schema drift and require failure before regeneration. The generated `createApiClient` accepts a base URL and optional fetch implementation. Implemented typed paths are `/livez`, `/api/v1/health` and `/api/v1/workspace`; future domain components do not activate financial endpoints.

New API routers must use `APIRouter(route_class=ContractRoute)` from `backend.api.routing` to preserve exact JSON score numbers and reject duplicate keys/NaN before Pydantic validation. Direct routes on `create_app()` already use this class. For raw offline strategy documents, use `StrategyConfigV1.from_json`; parsing with ordinary float-based `json.loads` first loses precision. Serialize validated models with `model_dump(mode="json")` or FastAPI response models. Use the shared typed error envelope and `error_response` for documented feature failures; validation errors expose field paths without submitted values.

Payload examples in `backend/tests/contracts/examples/` are **SYNTHETIC_DATA_ONLY**, illustrative contract shapes, not market evidence or engine outputs. IDs and hashes are placeholders; the forecast uses an abbreviated synthetic calendar and a zero-return all-cash case. Actual snapshot bytes, exchange calendars, forecast arithmetic, transactions and durable job behavior remain with their owning feature issues. The schema and client checks require no database, Docker or provider network.

## Offline synthetic fixtures

`data/fixtures/` contains a complete four-year synthetic snapshot and FIX-01–FIX-10 independent input/oracle cases. `make fixtures` regenerates the committed artifacts; `make fixtures-check` detects byte drift. Fixture generation and tests use locked NumPy 2.5.4 for the pinned PCG64 sampling inputs. The snapshot is deliberately synthetic, including its versioned weekday calendar; it is not real exchange data or evidence of implemented financial engines. See the [fixture handoff](backend/tests/fixtures/README.md) for checksums, formulas, tolerances, limitations and later test owners. The current app does not yet load this snapshot; offline integration arrives with #25.

## PostgreSQL workspace

Set `DATABASE_URL` to a private PostgreSQL16 service using the `postgresql+psycopg://` driver. `.env.example` shows the format; the application reads environment variables rather than loading `.env` implicitly. Keep the database port unpublished. Set `YAMS_FIXTURE_ROOT` only to the trusted, committed fixture root when it differs from the repository default.

`make db-bootstrap` upgrades the single linear Alembic head and seeds one local workspace in the same transaction, serialized by a PostgreSQL advisory lock. Repeating it preserves the workspace UUID, locale and preferences. Run it before starting API/worker services; importing or starting the API never silently migrates a database. A failed migration exits nonzero with a sanitized message and rolls back. Connection, statement, lock and pool waits are bounded. Restore from a verified backup for rollback; destructive downgrade is intentionally unsupported.

Migration `0001_workspace` owns only `local_workspace` and Alembic metadata. Defaults are `en-US`, benchmark `SPY`, and theme `system`; a unique singleton marker and check constraint prevent a second workspace. There are no users, tenants, authentication or financial tables. Subsequent owners add linear revisions according to ADR-004 and must not rewrite this revision or reseed existing preferences. Workspace settings mutation remains with its later contract owner.

`GET /api/v1/health` returns200 only when database, schema, workspace and all synthetic snapshot artifact checks pass; otherwise503 with safe reason codes and no connection strings. Invalid database configuration is distinguished as `DATABASE_MISCONFIGURED`. Server logs identify failed probe components and exception classes without messages, SQL, values or tracebacks; bootstrap failures likewise expose only the exception class. `GET /api/v1/workspace` returns persisted configuration, or retryable `503 NOT_READY` when its database/schema/workspace is unavailable. Fixture metadata is explicitly synthetic. These read-only checks do not register snapshots, execute jobs or prove financial calculations.

`make test-integration` builds a hash-locked test image and starts a unique disposable Compose project, publishes no host ports, and tests empty/concurrent/repeated bootstrap, singleton enforcement, preferences, unavailable DB, mismatched schema, failed-migration rollback and missing fixtures. It restarts the actual PostgreSQL container and verifies identity/preferences afterward, then removes only its own containers/network/volumes. Existing user volumes are never reset. Docker and initial registry access are required; cached tests use no provider service. Unit tests exclude the `integration` marker explicitly; integration is a separate required command. After dependency changes, regenerate the test image's requirements with `uv export --locked --format requirements-txt --no-emit-project --output-file infra/docker/integration-requirements.txt`.
