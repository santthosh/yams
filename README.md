# YAMS

Yet Another Market Simulator is a local, single-user paper research workspace. It never connects to a brokerage or trades real money.

## Current state

The `0.0.1` scaffold provides an importable FastAPI package, a labeled Next.js shell and working quality commands. `/livez` checks only that the API process responds. Database/fixture readiness, persistent workspace, durable jobs, Docker Compose, CI and release packaging are still tracked foundation work. No market data, portfolio values or investment results are seeded by this scaffold.

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
make build
```

`lint-backend` runs Ruff checks and formatting; `lint-web` runs ESLint and Prettier. `typecheck-backend` runs strict mypy separately from frontend `next typegen`/TypeScript. `test-backend` exercises liveness and unavailable routes without a DB; `test-web` renders the paper-only/empty shell with Vitest. `build-backend` creates a wheel/sdist and `build-web` creates a production Next.js build. These targets propagate failures and contain no empty success stubs.

Playwright is pinned and its CLI is available through `pnpm --filter @yams/web playwright`; browser journeys and `make test-e2e` arrive with #24. PostgreSQL integration checks arrive with #22, and `make dev`/`make smoke` with #25. Do not interpret these planned commands as existing checks. Tailwind/shadcn components and chart dependencies arrive with their UI owners when used.

Read [AGENTS.md](AGENTS.md), the [implementation blueprint](docs/IMPLEMENTATION_BLUEPRINT.md), and the scoped GitHub issue before changing financial semantics. Milestone `0.0.1` is not released merely because the scaffold builds.
