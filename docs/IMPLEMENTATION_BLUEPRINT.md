# YAMS — Implementation Blueprint

**Version:** 1.0 • **Status:** Implementation baseline (proposed defaults to ratify in 0.0.1 ADRs)  
**Product:** YAMS — Yet Another Market Simulator  
**Scope:** Single operator, local Docker Compose, US-listed equities/ETFs, USD, synthetic portfolios only  
**Dependencies:** [Product Strategy](PRODUCT_STRATEGY.md) · [Technology Strategy](TECHNOLOGY_STRATEGY.md) · [Domain/API Contracts](DOMAIN_AND_API_CONTRACTS.md) · [UX Specification](UX_SPECIFICATION.md)

## 1. Intent, priority and non-negotiable vertical slice

This is the engineering decision record that prevents independent agents from inventing mutually incompatible investment rules. **Normative baseline choices are marked `MUST`**; recommended starting numeric defaults are marked `DEFAULT` and can only change through a strategy version or approved ADR. This is a specification, not a claim of proven trading profitability.

**Core release demonstration (0.0.1–0.0.5):** fresh clone → `docker compose up --build` → seeded/offline lab → ingest/use real price and context data → provider-derived candidate universe → score and allocate to a feasible paper portfolio → show $1,000 current position and rationale → historical walk-forward backtest vs SPY → numerical 90-calendar-day proposed-vs-current scenario forecast → preview/apply synthetic BUY/SELL/HOLD decisions → persist holdings and cash across restart. **Every step MUST be traceable to immutable inputs.**

**Architecture shape:** Next.js web (browser), FastAPI API (request/validation), Python worker (jobs/scheduler), PostgreSQL (transactions/metadata/jobs), local Parquet (market snapshots/artifacts), embedded DuckDB (read-only analytics). Exactly four long-running services, no cloud requirement.

## 2. Execution principles and document ownership

- One **shared engine** implements the decisions, constraints and synthetic-execution rules for live-like paper portfolios, backtests, and Arena entrants. Backtests supply historical as-of timestamps; portfolio evaluation supplies the latest completed session; neither bypasses the contract.
- An experiment is identified by **strategy version + dataset snapshot ID + universe snapshot/coverage + evaluation period + execution policy + forecast configuration + engine version + seed**. Same inputs produce the same financial outputs (within stated numeric precision).
- A portfolio's **recommendation**, **approval**, **order**, and **fill** are separate durable records. Repeated HTTP requests must never create duplicate fills.
- No hidden real-money integrations, automatic online execution, arbitrary uploaded Python strategies or fabricated data.
- Public/provider historical series do **not** automatically imply unbiased historical constituents. Unknown history must be labeled, never silently reconstructed.

## 3. Market-data and universe policy (ADR-002, ADR-007)

### 3.1 Asset identity and required data

**MUST:** canonical identifier `{venue}:{symbol}` with explicit currency and effective-dated symbol aliases when available (e.g., `XNYS:ABC`); symbol alone is not a guaranteed permanent identity. Maintain provider-native IDs and preserve lineage. V1 may support a practical `asset_id` surrogate and source mappings, but must not merge assets on ticker alone across venues/dates.

**Required daily market bar** (all timestamps in UTC; exchange session date is a separate `YYYY-MM-DD`): `asset_id`, `session_date`, `open`, `high`, `low`, `close`, `volume`, `adjusted_close`, `currency`, `provider`, `published_at` or source availability proxy, `ingested_at`, and quality flags. Prices are positive finite decimals, volume nonnegative integer; detect duplicate bars, extreme discontinuities and missing sessions. Adjustment basis and actions MUST be described in snapshot metadata.

**Contextual inputs:** volume and sector classification are mandatory for eligible live stock candidates; data freshness, exchange calendar and benchmark quotes are mandatory contextual controls. Industry, fundamentals and macro factors are future optional adapters, each with its own `available_at` semantics.

### 3.2 Initial providers and selectable universe

- **Offline fixture adapter (required):** bundled *labeled synthetic* multi-year OHLCV/sector/asset metadata with deliberate split/dividend, stale quote, duplicate-fill, holiday and missing-bar test cases. This is not presented as real historical return evidence.
- **Research provider adapter (initial):** Yahoo Finance via `yfinance` as an optional network-backed feed, subject to current provider terms, rate limits and source reliability. The adapter is replaceable; downloaded data should not be redistributed without rights review.
- **Universe strategy:** `liquid_us_equities` obtains a broad **provider- or published-rule-derived listing**, not five manually named favorites. Save membership snapshot IDs and selection rules with each run. The passive ETF benchmark (initially SPY) is a **benchmark**, not a hardcoded winner/automatic portfolio constituent.
- **Historical membership honesty:** if the provider has only present-day membership, label runs `SURVIVORSHIP_BIAS_RISK`; do not describe them as point-in-time constituent-correct. More reliable membership-history support is 0.0.9.

### 3.3 Snapshot integrity

Data refresh fetches → validates → normalizes → writes temp Parquet → computes SHA-256 manifest → atomic publish → creates immutable `dataset_snapshot` row. Snapshot manifest includes provider and license caveat, schema version, price basis, exchange calendar version, asset coverage and missing days, corporate-action policy, retrieval time, hashes, and quality warnings. Consumers pin a snapshot ID; refresh **never mutates a completed snapshot**. A failed refresh cannot overwrite a usable prior snapshot.

**Freshness:** a recommendation names the latest *completed and validated* exchange session in its pinned snapshot. The UI displays as-of time and `fresh | stale | fixture` status; stale/partial data may permit retrospective browsing but MUST block new **current** paper-fill generation unless the operator explicitly runs a separately labeled replay in a fixture environment.

## 4. Time, prices and synthetic trading (ADR-001)

| Concern | Initial policy |
|---|---|
| Exchange | U.S. primary equity calendar; sessions in America/New_York |
| Stored timestamps | RFC3339 UTC `Z`; `session_date` separately |
| Decision cutoff | After the complete and validated closing bar for session **T** is available |
| Evidence | Only facts with `available_at <= decision_cutoff` (no future features) |
| Fill | **First eligible session opening after BOTH T close and operator approval** (normally T+1 if approved before that open); never same-bar close from a close-derived signal |
| Open unavailable | `PENDING_DATA` or `UNFILLED`, not guessed execution |
| Price series | Adjusted-close for continuous return/feature computation; raw/unadjusted opening price for synthetic executions |
| Shares | Long-only; fractional units at most **6 decimal places**, truncate buys conservatively |
| Friction | DEFAULT: **10 bps adverse slippage per side**, $0 commission; configurable and recorded |
| Cash | USD, no margin/borrowing; cash remaining after sizing and rounding |
| Minimum trade | DEFAULT $5 notional; skip smaller trades with recorded explanation |
| Rebalance tolerance | DEFAULT absolute weight deviation 2 percentage points, unless mandatory risk breach |
| Portfolio orders | Apply feasible sells before buys; reject duplicates and prevent negative cash |

**Important UX distinction:** pressing **Apply paper recommendation** commits an authorized synthetic order set. If tomorrow's open has not occurred/been ingested, orders are pending and holdings do not change. After the next eligible opening bar becomes available, an idempotent worker posts fills. Backtests and fixture replay can complete this lifecycle using only eligible bars in the replay chronology. Never backdate a real-time order to an opening price already in the past.

**Corporate actions:** backtester and live-like paper engine MUST use coherent split/dividend treatment. Splits scale share quantities and inverse-adjust average unit cost; cash dividends post explicit ledger entries when payable/recognized under declared policy. If the provider does not supply reliable event dates or raw prices, mark the affected run incomplete/limited and avoid asserting fully realistic total returns. Adjusted series cannot be mixed into raw-fill accounting or cause double-counted dividends. Initial support can be fixture-validated with known actions, followed by stricter live coverage as provider reliability is established.

## 5. Default strategy specification (ADR-003)

The first strategy is **Risk-Adjusted Momentum v1**, a transparent baseline, not a claim that momentum beats SPY. Other templates (mean reversion, low volatility) share the interface and are added in 0.0.3. A user may fork parameters to a new **immutable** strategy version.

### 5.1 Candidate eligibility

At session T for a given provider-derived universe:

- U.S.-listed ordinary equities, long-only, USD; exclude unsupported instrument types in the baseline strategy.
- At least **252 valid completed daily sessions** for adjusted-close and volume calculations.
- Last unadjusted close >= **$5**; 20-session median dollar volume >= **$1,000,000** (liquidity proxy, not execution guarantee).
- Sector classification present (`Unknown` is permitted but treated as one capped bucket); valid adjusted series and recent price data.
- Optional **positive trend filter**: adjusted close > SMA(200), DEFAULT enabled. A candidate failing a filter is excluded with recorded reasons.

### 5.2 Feature and score calculation

For candidate `i` as of T:

- `M126 = adjusted_close[T] / adjusted_close[T−126 sessions] − 1`
- `M63 = adjusted_close[T] / adjusted_close[T−63 sessions] − 1`
- `VOL60 = std(60 daily log returns) × sqrt(252)` using the sample standard deviation (`ddof=1`)
- Within the eligible cross section, compute **population z-scores** for each feature using `ddof=0`. If a feature has zero dispersion, assign z-score **0** for that feature to all candidates.
- `score = 0.60*z(M126) + 0.25*z(M63) − 0.15*z(VOL60)`. Deterministic tie-break is ascending canonical `asset_id`.

Skip candidates with missing/nonfinite inputs; record filters and quality flags. Save intermediate features and score contributions for explanations. These coefficient defaults should be versioned and independently tested—not optimized against a hidden evaluation window.

### 5.3 Target allocation

- DEFAULT: top **8** eligible scored assets; **20% maximum per position**, **40% maximum per sector**, **5% minimum cash reserve**. Sector of unknown assets counts as one `Unknown` sector.
- Allocate the **up to 95% investable budget** proportional to inverse 60-session volatility, then use a deterministic iterative capped-water-fill algorithm: respect position/sector caps, redistribute residual only among eligible uncapped positions, and leave unallocatable value in cash. Do not inflate into an invalid position.
- Portfolio target weights (including cash) sum to **1.000000** within a defined tolerance; numerical rounding occurs at order-planning, not in score evaluation.
- If no candidates pass, target **100% cash**, with a plain-language risk and coverage explanation.
- Reject policies that cannot satisfy basic invariants (negative cap, cash floor >1, invalid instrument). No leverage, shorts, or synthetic options.

**Alternative strategy plug-in contract:** `eligible_universe(as_of, snapshot)` → `features` → `ranking` → `targets` → `explanations`. Strategy classes do not write portfolios or bypass global constraints. Engine wraps every strategy in policy validation.

## 6. Portfolio planning, posting, and invariants (ADR-004)

- Calculate portfolio value from posted holdings at a coherent market price timestamp plus settled simulated cash; mark stale valuations clearly.
- Compare current weights with versioned targets and calculate trade deltas. If change is under tolerance, label `HOLD` unless a hard risk rule is violated.
- Orders declare `BUY | SELL`, `requested_qty` (6dp), projected gross, fees/slippage, currency, `as_of_session`, earliest permissible fill session, and reason/evidence identifiers.
- Trade previews account for sells first; **cash-feasibility** is verified again on actual opening prices. Partial buy sizing is allowed only if the execution policy explicitly permits it, and must be recorded (default: reduce buy quantity to affordable amount or skip if under $5).
- Ledger writes are one DB transaction per fill: `paper_fill`, cash entry, position event, order state transition. Idempotency key unique per portfolio/order/fill event. Failed transaction leaves no partial money-like changes.
- Invariants after every posted event: `cash >= 0`, `shares >= 0`, no unapproved asset or order route, debits/credits reconcile within cent rounding, replay matches projected holdings; repeated fill returns same result.
- Separate **recommendation** (may have many proposed actions) from **execution batch** (operator approval + pending/posted status) from **valuation** (mark to market). Ledger is the source of truth; position table is a derivable projection.

## 7. Backtesting methodology (0.0.3)

**Algorithm:** for each portfolio rebalance session T, compute candidates and targets using snapshot evidence available at T close; schedule and fill orders at eligible T+1 open; apply actions and value through time; rebalance monthly using exchange session calendar. Use same strategies, allocation, order planner, corporate-action policy, and fill simulator as ongoing paper accounts. For unavailable bars, record a skip/error according to a documented gap policy—never invent fills.

**DEFAULT evaluation windows:** request at least 4 years of daily data when available: ~1 year warmup for 252-session features, ~2 years exploratory development and ~1 year untouched holdout. Shorter windows are permitted but flagged (`INSUFFICIENT_HOLDOUT`, `LIMITED_WARMUP`) and must not imply validated performance. An out-of-sample period can be used once for final evaluation but must not automatically drive parameter search. Repeated human selection across holdout runs must be indicated as a caveat.

**Required outputs:** cumulative return, annualized return (with trading-day convention), max drawdown, annualized volatility, Sharpe ratio with declared risk-free assumption (DEFAULT zero), trade count, fees/slippage, turnover, allocation history, cash % and benchmark-aligned SPY buy-and-hold. Benchmark begins with the **same capital and start date**, uses adjusted-price total-return approximation, and discloses any differences in friction/cash policy. Never fabricate numerical performance for fixture runs; show `Synthetic demonstration` prominently.

## 8. Forward forecasts (ADR-006)

**DEFAULT horizon:** **90 calendar days** from decision timestamp; use the exchange calendar to determine the corresponding eligible future sessions (do not simply call this '90 trading days'). **DEFAULT baseline:** 5-trading-day multivariate block bootstrap over the most recent 252 completed daily asset-return observations; 5,000 deterministic paths; seed stored with forecast. Resample **cross-asset return vectors together** to preserve historical cross-sectional co-movement; use common sampled vectors when comparing proposed targets against current holdings. Apply a documented rebalancing/constant-weight assumption (DEFAULT constant weight for scenario paths without additional trades) and apply forecast-upfront costs to the change case.

**Display:** P50 terminal return (called *scenario median*, NOT guaranteed expected return), projected P50 ending portfolio value, P10/P90 scenario range, probability of a negative return, a current-vs-proposed delta under shared assumptions, as-of timestamp and source snapshot. Caution: bootstrap percentiles are **model-generated scenario quantiles, not calibrated prediction intervals**. If return history is inadequate, return `FORECAST_UNAVAILABLE` with reason rather than manufactured values. Never use future bars in a forecast.

## 9. Jobs, replay and schedules (ADR-005)

**Jobs:** `refresh_market_data`, `backtest`, `forecast`, `evaluate_portfolio`, `apply_scheduled_fills`, `evaluate_arena`, `mature_journal`. Initial implementation uses Postgres row-based queue, `SELECT ... FOR UPDATE SKIP LOCKED`, a single bounded worker and cooperative cancel. `queued → running → completed|failed|cancelled`, plus retry with bounded exponential backoff for transient provider failures; safe restart leases with heartbeat and claim expiry. Retry of financial posting uses idempotent key and unique constraints.

**Clock behavior:** scheduler runs only when Docker is running. On restart, scan for pending fills and due evaluations; replay missed eligible periods **in order**, honoring original timestamps, without retroactively recommending as though an earlier decision were fresh. Surface `paused while app stopped` and recovery results in diagnostics. An Arena entrant may not be retroactively credited with trades from before it was launched.

## 10. Strategy Arena and Journal (0.0.6–0.0.7)

**Arena:** freeze each entrant's strategy version, initial $1,000 default, join/start instant, universe assumptions, fee schedule, benchmark and evaluation calendar. Competitors have **independent** cash/holdings and no cross-funding. Champion selection requires explicit action; compare equal elapsed periods and reveal missing-data exclusions. A new entrant does not gain fake historical paper-trading history from a backtest.

**Journal:** every recommendation is immutable with original evidence, forecast, alternatives, dataset hash, model seed, user decision and original observed timing. Horizon maturation computes realized outcome without changing old forecasts; compare to SPY and a no-change counterfactual using a declared valuation methodology and matching calendar. For a rejected recommendation, record counterfactual results without silently posting virtual trades.

## 11. Quality bars and canonical fixtures

| Fixture ID | Intent | Required proof |
|---|---|---|
| `FIX-01` | 3+ deterministic assets with smooth and volatile return patterns | Scoring math, deterministic rank/ties, filtered constituents |
| `FIX-02` | Future information injected after cutoff | Identical historical decision result; leak regression |
| `FIX-03` | Fractional buy/sell, fees, rounding, insufficient cash | Cash and share conservation, cents accounting |
| `FIX-04` | Repeated fill/idempotency key | Exactly one durable posting |
| `FIX-05` | Stock split and cash dividend | No double counting, coherent raw/adjusted prices |
| `FIX-06` | Holiday, no open bar, stale quote | Pending or blocked order, never fabricated fill |
| `FIX-07` | Known return sequence including a drawdown | Verified max drawdown, CAGR, turnover and benchmark alignment |
| `FIX-08` | Forecast seeded correlated cross-asset series | Stable quantiles and shared-shock current/target comparison |
| `FIX-09` | Restart with pending jobs/orders | No missed/duplicate approved action |
| `FIX-10` | Arena portfolios launched together | Equal start date, capital, policies; isolated ledger |

**Golden fixture standard:** commit small source fixture inputs **and** independent expected outputs (not computed at test runtime by the same function under test). Numerical tolerances declared per quantity; use `Decimal`/integer cents for paper cash, float only for research statistics.

### 11.1 GitHub Actions: pull-request CI

Implement `.github/workflows/ci.yml` for pull requests targeting the default branch. Use reproducible, locked Python and Node dependencies and the same validation entrypoints documented for local development.

Required checks cover Python and TypeScript formatting, linting and type checking; unit tests; API/generated-client contract drift; application builds; PostgreSQL integration and migration tests; and a Docker Compose offline smoke test. The smoke test boots the application without provider credentials, validates the seeded fixture journey, and checks persistence across restart. Add financial and UI acceptance scenarios as their milestones land; scaffold-only checks must not be reported as full product coverage.

Expose one stable required aggregate check, `CI / required`, that succeeds only when every applicable gate passes. Documentation-only changes may use content/link checks, with application checks explicitly marked not applicable. Do not skip the entire required workflow through path filters or treat failed, cancelled, or unexpectedly skipped jobs as success. Preserve test reports, failure logs, and browser evidence for diagnosis.

PR jobs must use read-only repository permissions and must not receive publishing credentials or require live market services. Pin third-party actions to reviewed commit SHAs. Set job timeouts and cancel superseded PR runs.

### 11.2 GitHub Actions: default-branch verification

Run the same CI gates on every push to the default branch, verifying the actual merged commit rather than relying solely on the PR result. Retain the tested commit SHA with the run and reports. Include the offline Compose smoke test and applicable migration/restart checks.

A failed default-branch run blocks release publication for that commit. Diagnose and fix or revert through a reviewed PR; do not bypass checks to publish. If a merge queue is introduced, also run the required checks for its candidate merge commits before enabling the queue.

### 11.3 GitHub Actions: versioned Docker releases

Implement `.github/workflows/release.yml` for version tags such as `v1.2.3` and prerelease tags. Release tags must reference commits on the default branch that passed its required CI; verify that exact commit before publication. Restrict release-tag creation and prevent moving or deleting published version tags through repository rules.

Build and publish the application images for `web`, `api`, and `worker` to GitHub Container Registry (GHCR); API and worker may share an image with different entrypoints. PostgreSQL remains a pinned upstream image. Support `linux/amd64` and `linux/arm64` for the intended local Docker installations, and verify the release smoke journey for each published platform before declaring it supported. Record source SHA, version, platform, and image digest, and never overwrite a published version with different content.

Package a release Compose manifest referencing exact image digests, safe example configuration, release notes, and startup/upgrade instructions in a GitHub Release. Verify the packaged manifest against the candidate images using offline fixtures before publishing the final release. Mark prereleases explicitly. Publish checksums and build provenance for release artifacts; give only the release job the permissions needed to publish packages and release metadata.

Release instructions must explain backup and migration requirements and identify when rollback needs a database restore; changing an image tag alone is not a safe rollback guarantee. Failed or partial publication must remain visibly incomplete, not a successful release. Users choose when to pull and upgrade: CD distributes locally runnable artifacts and does not deploy a hosted service or silently update local installations.

### 11.4 Branch protection and required reviews

Configure a GitHub ruleset or branch protection for the default branch during 0.0.1. Require pull requests, at least one approving review from a reviewer other than the author, resolution of review conversations, and a passing `CI / required` check for the current merge candidate. Dismiss stale approvals after code changes and require the branch to be current with its base, or use a verified merge queue.

Block force pushes and branch deletion. Apply the rules to administrators and automation where supported; the ship workflow must not bypass them. Add `.github/CODEOWNERS` with actual maintainers for financial-engine/ledger code, contracts/migrations, and CI/release workflows, and require their approval for affected paths. An automated review is additional evidence, not a substitute for required maintainer approval. If a reviewer or repository feature is unavailable, report the unmet gate instead of claiming protection is configured.

0.0.1 acceptance must include the workflow files, a successful PR run, a successful default-branch run, inspection of the active repository protection settings, and a verified prerelease installation. Committed YAML alone does not prove that checks, publishing permissions, or branch protections work.

## 12. Implementation gates and issue dependencies

| Milestone | Must be demonstrable before milestone closes | Dependency boundary |
|---|---|---|
| 0.0.1 — Foundation | `docker compose up --build`, offline seeded UI, migrations, lint/tests, typed contracts, ADRs 001–007; GitHub Actions PR/default-branch CI, protected reviews, verified Docker prerelease (§11.1–11.4) | None |
| 0.0.2 — Market Data & Quant Core | Snapshot → dynamic eligible securities → scores/explanations → feasible targets | 0.0.1 contracts |
| 0.0.3 — Strategy Lab & Backtesting | Versioned templates, jobs, walk-forward, benchmark, comparable curves/results | 0.0.2 quant + execution contract |
| 0.0.4 — Paper Portfolios | $1,000 virtual account, order preview, posting, persistence, reconciliation | 0.0.2 target; 0.0.1 ledger contract |
| 0.0.5 — Decision Center | Current vs proposed plan, next eligible fills, return scenarios and explanations | 0.0.3+0.0.4; **core release gate** |
| 0.0.6 — Strategy Arena | Independent champion/challenger paper portfolios, valid prospective comparison | 0.0.5 |
| 0.0.7 — Decision Journal | Immutable decision/outcome journal, no-change counterfactual | 0.0.5; Arena optional |
| 0.0.8 — Assisted Authoring | Validated visual/AI-to-config authoring, never direct LLM trades | 0.0.3 config schema |
| 0.0.9 — Reliability & Research Depth | Backups, provider diagnostics, more coverage and stronger calendar/action support | Existing contracts |

**Do not begin dependent PRs until contracts and fixtures land**. Good early parallel tracks: independently authored golden fixtures, offline data adapter, frontend shell, and migration scaffolding following approved schema.

## 13. Decisions and change control

Record ADRs in `docs/adr/` named `0001-execution-semantics.md` through `0007-dataset-snapshots.md`. The choices above are **working defaults** for initial grooming; 0.0.1 resolves provider limitations and ratifies them. Open questions that must not be silently chosen by agents: (a) Yahoo provider calendar/price availability, (b) historical symbol delistings and membership, (c) exact corporate-action raw-price convention, (d) whether partial open-session quotes are trustworthy, (e) downloaded market-data redistribution rights, and (f) nominal throughput/runtime budget on typical local hardware. If data quality prevents correctness, **reduce supported data scope or disclose limits**; never weaken the invariants.

**Normative references:** API schemas and state transitions are in `DOMAIN_AND_API_CONTRACTS.md`; UX treatment of pending fills, stale data and scenarios is in `UX_SPECIFICATION.md`; coding agent rules are in `../AGENTS.md`.
