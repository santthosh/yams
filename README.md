# YAMS

Yet Another Market Simulator is a local, single-user paper research workspace. It never connects to a brokerage or trades real money.

## Current state

The source checkout includes the 0.0.2 market repository, immutable snapshots and
strategy registry, shared momentum/allocation engine, and asynchronous candidate
inspection backed by PostgreSQL and a supervised worker. The synthetic Docker
journey produces measured candidates, exclusions and feasible targets, with
reproducible results retained through restart. Portfolio approval, backtesting and
forecasts remain with their later milestone owners; the shared execution kernel
is available but does not itself post durable trades.

Development toward 0.0.3 also adds named strategy creation, detail and immutable
version publication/history APIs over the existing registry, plus the ratified
mean-reversion and low-volatility templates through the shared diagnostic worker.
See the [strategy workflow](docs/operations/strategy-registry.md) and
[template rules/limits](docs/operations/strategy-templates.md). SPY remains
benchmark-only. The [Strategy Lab](docs/operations/strategy-lab.md) now browses
saved versions, reviews supported parameter changes and explicitly publishes
versions or named forks. Open `/lab` or `/lab/strategies`; originals remain
inspectable. Historical experiment submission/reports and comparison remain with
their owning issues.

Download published bundles and platform evidence from [GitHub Releases](https://github.com/santthosh/yams/releases).
Source implementation alone does not establish publication: use each release's
exact tag, immutable image digests, checksums and supported-capability notes.
The 0.0.2 release gate includes a verified real provider-derived universe and
native linux/amd64 and linux/arm64 packaged installation, tracked in
[epic #3](https://github.com/santthosh/yams/issues/3).

[v0.0.1](https://github.com/santthosh/yams/releases/tag/v0.0.1) is the immutable
foundation prerelease; its [verification evidence](docs/verification/28-release/README.md)
and original assets remain intact. For that first release, follow its release-note
filename-copy step before verifying downloaded checksums. See the
[installation/upgrade guide](docs/releases.md) for the current bundle workflow.

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

Read [AGENTS.md](AGENTS.md), the [implementation blueprint](docs/IMPLEMENTATION_BLUEPRINT.md), and the scoped GitHub issue before changing financial semantics. Milestone completion requires integrated release evidence beyond a successful scaffold build.

## Versioned contracts

`backend/domain` implements closed Pydantic contracts for strategies, market bars and snapshot manifests, recommendations, forecasts, paper orders, experiments, jobs, errors and pagination. Money, quantities, prices and allocation weights remain decimal strings; statistical numbers must be finite. Cross-field validators enforce complete allocations and lifecycle-dependent results. These validators do not implement financial calculations, storage, calendar verification or artifact-byte verification.

Run `make contracts` after changing a model or route. It regenerates `contracts/openapi.json`, input/output JSON schema goldens and `apps/web/src/api/generated/` using pinned tools. Commit these artifacts together. `make contracts-check` compares them byte-for-byte without rewriting; Python and frontend tests deliberately introduce isolated schema drift and require failure before regeneration. The generated `createApiClient` accepts a base URL and optional fetch implementation. Implemented typed paths include health/workspace, job inspection, data discovery/refresh, strategy creation/detail/version history/publication and asynchronous strategy evaluation. The generated OpenAPI path inventory is authoritative; future domain components do not activate financial endpoints.

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
separate resource-limited process executes the handler. Registered kinds are
`diagnostic`, `refresh_market_data` and `evaluate_strategy`. Backtest, forecast and
durable trade-posting handlers remain unavailable. `GET /api/v1/jobs/{job_id}` is
read-only; public cancellation is owned by #41.

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
browser. The browser uses same-origin `/api/v1` routes. The proxy allows the owned health/workspace/job, data/asset/default-strategy and
diagnostic evaluation routes, with closed methods, paths and query parameters,
does not forward cookies/authorization, rejects redirects, and bounds upstream
requests at three seconds. Failures carry safe correlation IDs.

[Web-shell handoff and verification](docs/verification/24-web-shell/README.md)
describes components, fixtures, browser evidence and the boundary between these
transport tests and #25's integrated Docker/persistence journey.

The [pinned market repository](docs/MARKET_REPOSITORY.md) documents immutable Parquet reads, temporal evidence, quality exclusions and the filesystem publication handoff for milestone 0.0.2.

See [market refresh operations](docs/operations/market-refresh.md) for internal refresh jobs, optional research acquisition, publication recovery and current capability limits.

The [shared momentum engine](docs/operations/momentum-engine.md) documents deterministic eligibility, ranking evidence and the allocation handoff.
The [shared allocation engine](docs/operations/allocation-engine.md) documents capped inverse-volatility targets, exact cash conservation and risk evidence.
The [default strategy registry](docs/operations/strategy-registry.md) documents stable immutable versions, bootstrap seeding and paginated discovery.
The [shared paper execution kernel](docs/operations/paper-execution-kernel.md) documents target planning, conditional previews, eligible raw-open effects and split/dividend arithmetic.

The [candidate inspection diagnostic](docs/operations/strategy-evaluations.md) connects
registered snapshots and immutable strategy versions to the supervised shared engine.
Prepare a synthetic snapshot in Settings & data, open Candidate inspection and select
as-of session `2028-07-17` for the authored populated fixture, or `2027-01-04` for
cash-only insufficient history. The cutoff is one hour before the next pinned
session's open. Calendar lookahead is required; missing coverage produces an
explicit error. Targets are diagnostic evidence; this flow cannot approve orders
or change holdings.

## Optional real-data credentials

Offline startup and the synthetic demonstration need no provider account. For
Tiingo capability verification, use your own free personal-use API token from the
[Tiingo account](https://www.tiingo.com/). Create or edit the repository-root `.env`
without replacing existing configuration:

```dotenv
TIINGO_API_TOKEN=your_personal_token
```

Keep the file local (`.env` is ignored by Git) and restrict it with `chmod 600 .env`.
Do not put the token in browser code, a `NEXT_PUBLIC_` variable, issues, screenshots
or release files. Provider responses belong in ignored `data/downloads/` or local
artifact storage; public images and fixtures contain authored synthetic data only.

Use the explicit research override to inject the token and add a research egress
network to the worker:

```sh
docker compose --env-file .env -f compose.yaml -f compose.research.yaml up --build -d --wait
```

In Settings → Market data, select Market research data and submit this research
source configuration:

```json
{
  "schema_version": 1,
  "provider": "tiingo_eod",
  "rights_verified_local_use": true,
  "history_sessions": 400,
  "max_assets": 20
}
```

After the refresh completes, open Candidate inspection and select its research
snapshot, a published strategy and the covered as-of session. The real-data cutoff
must have elapsed: one hour before the next pinned trading session opens. Only
evidence observed by that cutoff is eligible; a historical download cannot be
backdated. Reevaluate the same immutable snapshot without another provider fetch.

The published selection rule uses a deterministic, budget-sampled cohort derived
from the provider directory, with current identity/sector checks and explicit
exclusions for ambiguous or unsupported securities. This is not full US coverage
or historically correct membership. A typical20-name refresh uses about41 API
calls; actual quotas apply, and safe failures preserve the previous snapshot.

See the [local Tiingo workflow](docs/operations/tiingo-research.md) for configuration,
budgets, failure recovery and timing, and the [dated provider review](docs/data-provider-evidence.md)
for source evidence. These snapshots support diagnostics only. Complete corporate-
action accounting, historical publication evidence and paper execution remain
unsupported; no order or holding changes occur in Candidate inspection. Credentials
do not authorize redistribution of cached source data.

Backtest core implementation for0.0.3 is tracked in#39; see the
[internal engine handoff](docs/operations/backtest-core.md). The proposed
[walk-forward conventions](docs/adr/0012-walk-forward-core.md) document exact
session boundaries, strict missing-data failures and shared accounting. This
source work does not add a public experiment endpoint or change the published
0.0.2 installation. Tiingo data remains diagnostic-only until historical raw
execution/action/publication/membership capabilities are verified.
