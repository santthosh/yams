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

Each document owns the area described above. Normative contracts take precedence over illustrative examples. When authoritative rules conflict, **stop implementation of the conflicting part**, describe the conflict to the user (and in the GitHub issue/PR when publishing is authorized), and propose an ADR. Do not silently choose the easiest interpretation. Contract changes require coordinating the engine, API, frontend, docs, tests, and data fixtures.

The repository contains the local `ship` skill, a FastAPI/Next.js scaffold, versioned contracts, canonical synthetic fixtures and PostgreSQL workspace/job persistence with a supervised diagnostic worker. `make install`, `make lint`, `make typecheck`, `make test`, `make build`, `make contracts-check`, `make fixtures-check`, `make db-bootstrap` and isolated `make test-integration` are implemented; see README for pinned runtimes and separate targets. Application Compose and E2E commands remain foundation targets until their owning issues land. Verify what exists before using other commands below.

### Working approach

Inspired by [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills):

- Surface assumptions and tradeoffs before coding. Resolve routine choices from repository evidence; ask when ambiguity changes the outcome, financial semantics, or architecture.
- Choose the smallest complete solution. Avoid speculative features, dependencies, configuration, and abstractions.
- Keep each edit tied to the requested outcome. Match surrounding conventions, remove code made unused by your change, and report unrelated problems separately.
- Define observable success and verify it. Keep trivial changes lightweight; use a brief plan and explicit checks for substantive work.
- Inspect the working tree first. Preserve existing edits and untracked work; never reset or overwrite unrelated changes.

## 2. Non-negotiable rules

- **NEVER connect to real brokerages, trade real money, add payment/billing, create multiuser auth or cloud-only dependencies.** Capital, portfolio positions, orders and fills are synthetic; underlying securities and market data may be real, with provenance clearly marked.
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

### Repository-specific user preferences

The user has explicitly preapproved all `git` and `gh` commands for `santthosh/yams`. Run task-related Git and GitHub CLI commands without asking again for command permission. This standing approval persists across sessions; continue to respect the requested task scope, preserve unrelated work, and honor repository review gates. Environment-enforced sandbox approvals may still be required and cannot be disabled by this document. Ask for unresolved product decisions separately from command execution permission.

For now, MergeWatch review is sufficient for the PR review requirement (user decision Q05, recorded in issues #27 and #72). A separate human approving review is not required by this interim policy. Address review findings and retain required CI and conversation-resolution gates. Verify the actual MergeWatch integration and its enforceable review/check signal before configuring protection; do not assume that an automated comment counts as a GitHub approving review. This decision supersedes earlier guidance requiring a separate human reviewer and does not itself authorize a merge or protection change.

### Definition of ready (`agent-ready` label)

For issue-driven implementation, verify that the issue includes:

- Clear business/user outcome and requirement IDs (FR-xx), milestone, priority, area.
- Exact scoped files/modules and **explicit exclusions**.
- Inputs/outputs, expected states, linked versioned contracts and applicable ADRs.
- Observable acceptance criteria, happy path **and negative/empty cases**.
- Golden fixture IDs and testing expectations (unit/integration/E2E as appropriate).
- Every prerequisite artifact exists, is compatible and has verification evidence; required user decisions are recorded. Named but undelivered prerequisites mean `blocked`, not `agent-ready`.
- PR boundary narrow enough to review without a repository-wide rewrite.

Agents should not self-mark a blocked issue `agent-ready` to bypass dependencies. If incomplete, request the missing information from the user or, when authorized, on the GitHub issue **without implementing financial semantics from guesses**. Work on safe independent work or fixture scaffolding while awaiting resolution.

A direct user task does not require creating a GitHub issue. Apply the same relevant scope, contract, and verification criteria in the conversation; do not invent labels, fixture IDs, or unresolved financial semantics to fill gaps.

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
2. **State a small plan** in the conversation or authorized issue/PR: files to edit, interfaces, test criteria and risk.
3. Work on one issue/PR with a branch name like `feat/0.0.2-123-market-snapshot` or `fix/0.0.4-204-ledger-idempotency`.
4. Implement the minimum complete behavior; avoid unrelated refactors or opportunistic library changes.
5. Add tests and fixtures **before or alongside** financial logic; run lint/type checks and at least targeted tests.
6. If an API or schema changes, regenerate TS types, update migrations and docs, and add backward-compatibility tests or an ADR.
7. Open a PR linking the issue (`Closes #123`) with risk notes, proof of commands/tests, screenshots for UI, and precise unresolved limitations.
8. Do **not** self-merge architecture/ledger/backtest/security changes without the required review and green CI.
9. After an authorized merge, verify the delivered issue scope, reconcile its completion state and reassess downstream readiness using the procedure below.

### Shipping work

Use the repository-local [ship skill](.agents/skills/ship/SKILL.md) when asked to ship an issue or scoped change: `$ship <issue URL, number, or scope>`. It maintains a checklist through implementation, verification, PR review, and merge when authorized. Honor narrower requests to stop at a draft or review-ready PR. The skill does not bypass the required reviews or CI gates in this document.

Read the approved decisions in [#72](https://github.com/santthosh/yams/issues/72) and the owning issues before implementing their contracts. Explicit user decisions supersede earlier proposal wording; carry the decision into affected ADRs, specs and fixtures in the implementation PR. Ask one focused question for genuinely new ambiguity, record the answer, and continue independent work within the authorized scope.

### Completion and downstream readiness

Reassessing readiness is part of completing an issue. GitHub dependency links alone do not maintain `blocked` and `agent-ready` labels.

1. Verify the merged artifact against every acceptance criterion and required test/review result. Close the issue only when its complete scope is delivered; if a PR auto-closes an incomplete issue, reopen it and record the remaining work.
2. Inspect directly dependent issues through native blocking links and their bodies. For each, verify **all** prerequisite artifacts, approved decisions, contract compatibility and verification requirements. An issue being closed is evidence to inspect, not proof of delivery.
3. If every condition is satisfied, remove `blocked` and apply `agent-ready`. Otherwise retain `blocked`, remove any stale `agent-ready`, and identify the exact missing artifact or unresolved decision. Remove `needs-user-decision` only after its choices are recorded. Preserve legitimate dependency links for traceability.
4. Reconcile native dependencies with issue bodies, update parent epic checklists and refresh the readiness summary in #72. Parent membership is organizational and does not create an execution dependency by itself.
5. Record the delivered commit/PR and verification evidence in the issue handoff. Report newly ready work and remaining blockers; continue only within the user's assigned scope.

### Sequential milestone delivery

When assigned a sequence of milestones, ship them in the requested semver order. Within each milestone, execute issues in dependency order; use parallel agents only when authorized and ownership is disjoint. Do not start implementation in the next milestone until the current milestone's release gate passes.

- Verify the integrated milestone demonstration against its epic and the blueprint's exit criteria. Each milestone must ship its own documented increment without depending on features scheduled for later milestones. Stage unavailable UI honestly.
- Require applicable tests, generated-client/contract checks, GitHub Actions checks, MergeWatch review and resolved findings before authorized merges. Include Docker/offline, fresh-install, migration and persistence-after-restart evidence as applicable.
- For an authorized release, verify the exact release commit and candidate images on `linux/amd64` and `linux/arm64`. Publish public GHCR images with immutable digests, a digest-pinned Compose manifest, safe configuration, checksums/provenance and installation/upgrade guidance. Exclude credentials and licensed market datasets.
- Publish the corresponding immutable semver tag and GitHub Release, marking prereleases explicitly. Close the milestone only after its required deliverables and packaged installation pass; closed tickets or committed workflow YAML alone do not establish a shipped release.
- After each release, report the release link, delivered capabilities, verification evidence, known limitations and the next ready issues. Record this evidence in the milestone epic and refresh #72.

These procedures describe how to complete assigned work; they do not independently authorize shipping all milestones, changing protections, merging or publishing releases. Honor authorization already given in the active task without repeatedly requesting it, and respect any requested stopping point.

## 5. Parallel-agent coordination

When parallel agent work is authorized, establish contracts and module ownership before delegating. The dependency order matters more than the number of simultaneous agents:

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

Discover executable commands from actual manifests, scripts, and CI. **Target commands** (once the scaffold implements them; do not claim they already exist):

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

For bug fixes, reproduce the failure before verifying the correction where practical; preserve user work when testing prior behavior. Documentation-only edits need content, link, and whitespace review rather than a new test suite. Report checks as passed, failed, skipped, or unavailable; never present an unrun check as successful.

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

**Milestone completion is different from PR completion.** Each milestone has its own independently verifiable release increment. `0.0.1` ships an installable foundation with an offline fixture shell, contracts, infrastructure and verified delivery pipeline. The cumulative **core release gate at `0.0.5`** additionally requires a fresh Docker clone to demonstrate a dynamic, data-derived $1,000 recommendation, audited historical backtest, risk-constrained portfolio, next-action orders, numerical forward scenario and durable paper fills. Do not impose that later product gate on earlier milestones. `0.0.6`–`0.0.9` add their documented capabilities.

## 8. Security, data terms and local environment

- Bind only the web port to `127.0.0.1`; API/Postgres remain internal. No need for authentication when locally isolated, but do not claim loopback protection if user explicitly changes networking.
- Keep `.env`, provider tokens, backups and cache data out of Git. Use example config with safe defaults and offline fixture mode.
- Respect data-source terms (especially third-party Yahoo research use) and attribute providers; never commit redistributed licensed market datasets without explicit rights.
- Validate uploaded paths, SQL, parameters, model payloads and job budgets; prevent arbitrary filesystem writes and unbounded job execution.
- Use deliberate, warned commands for destructive volume reset; normal startup and migrations must not erase portfolios or journals.
- Scheduled jobs run only while Docker is active. Never promise monitoring when powered off.

## 9. Documentation and scope-change policy

If a product assumption changes, document it in an ADR or an authorized GitHub issue before dependent implementation. For changes to **decision timing, price adjustments, portfolio ledger, snapshots, forecasting, strategy schema or queue guarantees**, update the affected specs and fixtures **in the same PR**. Keep product name YAMS everywhere. Keep the core financial engine deterministic and inspectable; AI assistance is optional and may only propose reviewable configurations and summaries grounded in stored evidence.

> **Guiding principle:** A feature isn't complete merely because its UI looks right. It is complete when another engineer can reproduce its decision, verify the money-like arithmetic, and explain its limitations using the committed artifacts.
