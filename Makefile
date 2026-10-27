.PHONY: install lint lint-backend lint-web typecheck typecheck-backend typecheck-web test test-backend test-web build build-backend build-web

install:
	uv sync --locked
	pnpm install --frozen-lockfile

lint: lint-backend lint-web
lint-backend:
	uv run --locked ruff check backend
	uv run --locked ruff format --check backend
lint-web:
	pnpm lint

typecheck: typecheck-backend typecheck-web
typecheck-backend:
	uv run --locked mypy
typecheck-web:
	pnpm typecheck

test: test-backend test-web
test-backend:
	uv run --locked pytest
test-web:
	pnpm test

build: build-backend build-web
build-backend:
	uv build
build-web:
	NEXT_TELEMETRY_DISABLED=1 pnpm build

.PHONY: contracts contracts-check
contracts:
	uv run --locked python -m backend.api.openapi
	pnpm --filter @yams/web exec node scripts/contracts.mjs
contracts-check:
	uv run --locked python -m backend.api.openapi --check
	pnpm --filter @yams/web exec node scripts/contracts.mjs --check
