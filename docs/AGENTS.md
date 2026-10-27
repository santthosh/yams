# AGENTS.md — YAMS Engineering & Coding-Agent Playbook

**Project:** YAMS — Yet Another Market Simulator  
**Product boundary:** Single-user, local Docker Compose, synthetic capital and orders only. **Not SaaS, not a broker.**  
**Purpose:** Provide consistent instructions for human contributors, Codex, Claude Code, and other coding agents implementing scoped GitHub issues.

## 1. Read before changing code

Use planned release versions `0.0.1`–`0.0.9` for milestones, issue references and branch examples. `0.0.5` is the first complete core release. A milestone name does not mean a tag or release has been published.

Read the relevant sections of the following source-of-truth documents **in this order**:

1. [`docs/PRODUCT_STRATEGY.md`](docs/PRODUCT_STRATEGY.md) — capabilities FR-01–FR-15, product flows, 0.0.1–0.0.9.
2. [`docs/TECHNOLOGY_STRATEGY.md`](docs/TECHNOLOGY_STRATEGY.md) — stack, local deployment, storage, workers and test boundaries.
3. [`docs/IMPLEMENTATION_BLUEPRINT.md`](docs/IMPLEMENTATION_BLUEPRINT.md) — normative quant/data/clock/trading/forecast rules and baseline defaults.
4. [`docs/DOMAIN_AND_API_CONTRACTS.md`](docs/DOMAIN_AND_API_CONTRACTS.md) — models, timestamps, REST contracts, errors and states.
5. [`docs/UX_SPECIFICATION.md`](docs/UX_SPECIFICATION.md) — flows, accessibility, financial labels, pending/error states.
6. This `AGENTS.md` — contribution and verification policy.

When rules conflict, **stop implementation of the conflicting part**, describe the conflict in the GitHub issue/PR and propose an ADR. Do not silently choose the easiest interpretation. Contract changes require coordinating the engine, API, frontend, docs, tests, and data fixtures.

## 2. Non-negotiable rules

- **NEVER connect to real brokerages, trade real money, add payment/billing, create multiuser auth or cloud-only dependencies.** All accounts, assets and fills are synthetic; market data may be real when separately marked.
- **NEVER fabricate market data, stock returns, investment signals or forecast figures** to make a demo or test pass. Seeded generated fixtures are allowed only when clearly labeled `SYNTHETIC_DATA_ONLY`.
- Never imply that backtest performance or bootstrap forecast intervals are guaranteed or calibrated future predictions.
- Never use future price, symbol membership, fundamental publication, or corporate-action evidence in a historical decision. Handle survivorship limitations visibly.
- A recommendation, an operator-approved paper order, and a posted synthetic fill are different events. Never mutate holdings at recommendation/preview time.
- Use Decimal/integer-cents-style accounting for cash and trade prices; no float-based cash ledger. Idempotent fills, nonnegative cash and long-only holdings are hard invariants.
- The **same Python strategy, allocation, risk and execution logic** must serve backtests, live-like portfolios and Arena competitors. No frontend-owned portfolio math.
- Version strategies and snapshots immutably. Persist reproducibility metadata: engine version, dataset hash, parameters, assumptions, market clock, seed.
- Treat user-entered rules and AI proposals as validated declarative config. Do not `eval`, execute arbitrary strategy code, or blindly trust generated quant claims.

## 3. Repository layout and module ownership

```text
yams/
├── AGENTS.md
├── docs/
│   ├── PRODUCT_STRATEGY.md
│   ├── TECHNOLOGY_STRATEGY.md
│   ├── IMPLEMENTATION_BLUEPRINT.md
│   ├── DOMAIN_AND_API_CONTRACTS.md
│   ├── UX_SPECIFICATION.md
│   └── adr/
├── apps/web/                   # Next.js, TS, Tailwind, shadcn/ui
├── backend/
│   ├── api/                   # FastAPI transport/application services
│   ├── domain/                # Shared typed domain contracts
│   ├── market_data/           # Adapters, validation, snapshots, provenance
│   ├── strategies/            # Eligibility, features, ranking
│   ├── portfolio/             # Constraints, ledger, fills, valuation
│   ├── backtesting/           # Walk-forward and benchmark engine
│   ├── forecasting/           # Historical scenario model
│   ├── arena/                 # Prospective entrants
│   ├── journal/               # Decisions, outcomes
│   ├── jobs/                  # Queue, worker, scheduling
│   ├── persistence/           # SQLAlchemy/Alembic
│   └── tests/
├── data/fixtures/             # Small committed deterministic data
├── infra/docker/
├── compose.yaml
├── Makefile
├── .env.example
└── README.md
```

The API and worker share an importable Python package/quant engine. The Next.js app uses a generated TS client from FastAPI OpenAPI types; no separately hand-maintained pseudo-API models. Follow the target structure as it is incrementally implemented—do not fabricate missing folders simply for appearances.

## 4. Working from GitHub issues

### Definition of ready (`agent-ready` label)

An agent may begin implementation only when the issue includes:

- Clear business/user outcome and requirement IDs (FR-xx), milestone, priority, area.
- Exact scoped files/modules and **explicit exclusions**.
- Inputs/outputs, expected states, linked versioned contracts and applicable ADRs.
- Observable acceptance criteria, happy path **and negative/empty cases**.
- Golden fixture IDs and testing expectations (unit/integration/E2E as appropriate).
- Dependencies resolved or named and visibly blocked.
- PR boundary narrow enough to review without a repository-wide rewrite.

Agents should not self-mark a blocked issue `agent-ready` to bypass dependencies. If incomplete, post clarifying questions on the GitHub issue **without implementing financial semantics from guesses**. Work on safe independent work or fixture scaffolding while awaiting resolution.

### Recommended issue template

```markdown
## Outcome / requirement
What user-visible behavior changes? FR-xx, target release version.

## Scope
In-scope modules, exact non-goals, proposed files.

## Contract
Inputs, outputs, API/schema references, state transitions and ADRs.

## Acceptance criteria
- [ ] Observable happy-path behavior
- [ ] Errors, stale/missing data, empty states
- [ ] Reproducible timing and security/financial invariants

## Tests / fixtures
Golden fixture ID(s), unit/integration/E2E, expected results/tolerances.

## Dependencies
Blocked by #..., can run in parallel with #...

## Agent handoff
Branch/PR boundary, any migration or generated-client update.
```

### Workflow

1. **Read** issue, dependencies, contracts, relevant existing code and tests.
2. **State a small plan** in the issue/PR: files to edit, interfaces, test criteria and risk.
3. Work on one issue/PR with a branch name like `feat/0.0.2-123-market-snapshot` or `fix/0.0.4-204-ledger-idempotency`.
4. Implement the minimum complete behavior; avoid unrelated refactors or opportunistic library changes.
5. Add tests and fixtures **before or alongside** financial logic; run lint/type checks and at least targeted tests.
6. If an API or schema changes, regenerate TS types, update migrations and docs, and add backward-compatibility tests or an ADR.
7. Open a PR linking the issue (`Closes #123`) with risk notes, proof of commands/tests, screenshots for UI, and precise unresolved limitations.
8. Do **not** self-merge architecture/ledger/backtest/security changes without the required review and green CI.

## 5. Parallel-agent coordination

The dependency order matters more than number of simultaneous agents:

```text
0.0.1 Contracts, ADRs, seeds and Compose
            |
0.0.2 Data/Snapshots -> Strategy Features/Ranking -> Allocation
            |                                   |
            +-> 0.0.3 Backtest/Benchmarks          +-> 0.0.4 Ledger/Orders
                        \                       /
                         \----> 0.0.5 Decisions/Forecasts
                                       |
                            0.0.6 Arena; 0.0.7 Journal
                                       |
                           0.0.8 Assisted Authoring; 0.0.9 Hardening
```

Safe early parallel tracks **after 0.0.1 contracts land:** provider adapter vs frontend shell vs independent golden test generator vs API schema migrations. Avoid parallel PRs that both redefine `StrategyConfigV1`, fill pricing semantics, or ledger entities. Preferred integration cadence: interface-only PR → focused implementation PRs → E2E wiring PR → milestone demo.

Recommended issue labels: `type:epic`, `type:feature`, `type:bug`, `type:chore`, `area:web`, `area:api`, `area:data`, `area:quant`, `area:backtest`, `area:portfolio`, `area:forecast`, `area:arena`, `area:journal`, `priority:p0`, `priority:p1`, `priority:p2`, `agent-ready`, `blocked`, `needs-adr`.

## 6. Verification standards

**Target commands** (once the scaffold implements them; do not claim they already exist):

```bash
docker compose up --build
make lint
make typecheck
make test
make test-integration
make test-e2e
make smoke
```

Required tests by module:

| Module | Mandatory proofs |
|---|---|
| Market data | Invalid/stale/missing bars, manifest hashing, as-of filtering, immutable snapshots |
| Strategy | Deterministic scores, tie-breaks, eligibility and zero-dispersion z-score |
| Allocation/risk | Water-fill caps, cash reserve, sector `Unknown`, sum-to-1, empty universe |
| Backtest | Close-to-next-open, no look-ahead, benchmark fairness, fees, max drawdown, holdout separation |
| Portfolio | Exact cent cash, 6dp shares, duplicate POST, fill idempotency, crash/restart/replay, no negative balances |
| Forecast | Fixed seed, correlated block vectors, consistent 90-day calendar mapping, scenario limitations |
| Arena | Same terms, independent ledgers, no retroactive participation |
| Journal | Immutable recommendation, outcome maturity, traceable counterfactual |
| API | Pydantic validation, consistent error shape, job statuses, generated client compatibility |
| UX | Paper-only badge, pending vs filled, stale/unavailable, keyboard/ARIA, no fake values |

Use the `FIX-01`–`FIX-10` canonical fixture plan in `docs/IMPLEMENTATION_BLUEPRINT.md`. Golden expected values must be independently derived and committed, not generated using the function being tested. CI gates: Python formatter/linter/type checks, TypeScript formatting/lint/type checks, fast unit tests, contract drift check and Compose offline smoke. Heavy workloads may run as separate CI jobs.

## 7. Definition of done for a PR

- [ ] Meets every issue acceptance criterion, including negative states.
- [ ] Respects approved docs and ADRs; any changed contract has coordinated migrations/generated types.
- [ ] Adds/updates deterministic tests and golden fixtures; relevant CI passes.
- [ ] Handles provider errors and stale data safely, without fabricated outputs.
- [ ] Logs meaningful structured diagnostics without provider secrets or private credentials.
- [ ] Does not introduce cloud/SaaS/auth/broker infrastructure.
- [ ] Includes user-visible `Paper only` and data provenance labels where relevant.
- [ ] README/documentation updated for any operational or architecture behavior change.
- [ ] For UI change: screenshot + mobile/keyboard/empty/error-state evidence.
- [ ] PR description lists explicit tradeoffs, known limits and follow-up issue(s).

**Milestone completion is different from PR completion.** 0.0.1–0.0.5 **core release** closes only when a fresh Docker clone can demonstrate a dynamic, data-derived $1,000 recommendation, audited historical backtest, risk-constrained portfolio, next-action orders, numerical forward scenario and durable paper fills. 0.0.6–0.0.9 are additive capabilities.

## 8. Security, data terms and local environment

- Bind only the web port to `127.0.0.1`; API/Postgres remain internal. No need for authentication when locally isolated, but do not claim loopback protection if user explicitly changes networking.
- Keep `.env`, provider tokens, backups and cache data out of Git. Use example config with safe defaults and offline fixture mode.
- Respect data-source terms (especially third-party Yahoo research use) and attribute providers; never commit redistributed licensed market datasets without explicit rights.
- Validate uploaded paths, SQL, parameters, model payloads and job budgets; prevent arbitrary filesystem writes and unbounded job execution.
- Use deliberate, warned commands for destructive volume reset; normal startup and migrations must not erase portfolios or journals.
- Scheduled jobs run only while Docker is active. Never promise monitoring when powered off.

## 9. Documentation and scope-change policy

If a product assumption changes, open a GitHub issue or ADR first. For changes to **decision timing, price adjustments, portfolio ledger, snapshots, forecasting, strategy schema or queue guarantees**, update the affected specs and fixtures **in the same PR**. Keep product name YAMS everywhere. Keep the core financial engine deterministic and inspectable; AI assistance is optional and may only propose reviewable configurations and summaries grounded in stored evidence.

> **Guiding principle:** A feature isn't complete merely because its UI looks right. It is complete when another engineer can reproduce its decision, verify the money-like arithmetic, and explain its limitations using the committed artifacts.
