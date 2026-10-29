# YAMS — UX and Interaction Specification

**Version:** 1.0 • **Status:** Product/engineering implementation specification  
**Product:** Yet Another Market Simulator • **Audience:** One local operator  
**Implementation:** Next.js App Router, TypeScript, Tailwind, shadcn/ui, accessible charts  
**Related:** [Product Strategy](PRODUCT_STRATEGY.md) · [Implementation Blueprint](IMPLEMENTATION_BLUEPRINT.md) · [API Contracts](DOMAIN_AND_API_CONTRACTS.md)

## 1. Experience promise

**The interface should help a curious investor answer four questions in order:**

1. **What should my virtual portfolio own now?** A genuine set of holdings/target weights generated from a strategy, not a favorites watchlist.
2. **Why?** Measurable signals, rules, constraints and rejected alternatives, in accessible language.
3. **What could happen?** A numerical future *scenario* over a stated horizon alongside downside and limitations.
4. **Was it useful?** A reproducible backtest and eventually real-time paper evaluation, compared with an index and doing nothing.

**Brand:** YAMS — Yet Another Market Simulator. Voice: curious, precise, approachable, a little playful; never hype, certainty, urgency, or investment advice. Tagline: **Invest fake. Learn real.** Always label `Paper only` and clearly distinguish synthetic fixtures from research market data.

## 2. Navigation and information architecture

Primary navigation and routes:

| Route | Page | Core jobs to be done | Initial milestone |
|---|---|---|---|
| `/` | Dashboard | See overall virtual value, latest actions, data health and quick start | 0.0.1 scaffold, 0.0.5 final |
| `/lab` | Strategy Lab | Browse templates, versions, experiments | 0.0.3 |
| `/lab/strategies/new` | Strategy editor | Configure/fork declarative strategy rules | 0.0.3 basic, 0.0.8 advanced |
| `/lab/strategies/[id]` | Strategy detail | See versions, explanation, launch experiment | 0.0.3 |
| `/lab/experiments/[id]` | Experiment report | Explore equity curve, metrics, trade evidence and limitations | 0.0.3 |
| `/lab/compare` | Strategy comparison | Compare same-period experiments; challenge/fork | 0.0.3 |
| `/portfolios` | Paper Portfolios | Browse independent paper accounts, create portfolio | 0.0.4 |
| `/portfolios/[id]` | Portfolio detail | Holdings, cash, valuation, status and history | 0.0.4 |
| `/portfolios/[id]/decisions` | Decision Center | Review recommendation, scenarios, synthetic trade preview | 0.0.5 |
| `/arena` | Strategy Arena | Compare independently running entrants | 0.0.6 |
| `/arena/[id]` | Arena competition | Champion/challengers, fairness and promotion | 0.0.6 |
| `/journal` | Decision Journal | Search prior evidence, forecasts and outcomes | 0.0.7 |
| `/journal/[id]` | Decision details | Original evidence and later result | 0.0.7 |
| `/settings` | Local Settings & Data | Data sources, freshness, experiment limits, backup, logs | 0.0.1 basics, 0.0.9 full |

Navigation order: **Dashboard / Lab / Portfolios / Arena / Journal / Settings**. Disabled/unimplemented routes are hidden or labeled `Coming later`; never present an inert button. Global top bar: YAMS wordmark, `Paper only` status, current data source/mode, data as-of session, accessible refresh/jobs status. On phone/tablet use collapsed responsive navigation; desktop has sidebar.

## 3. First-run and local startup

**Zero login steps.** In **0.0.1**, first boot after `docker compose up --build` opens an idempotently seeded local workspace with labeled fixture metadata, navigation, health and basic settings. Contract examples and expected-value tables are fixture material, not persisted experiments or accounts. Hide unavailable financial actions. [ADR-008](adr/0008-lifecycle-api-additions.md) defines progressive first-run behavior.

By **0.0.5**, first run supports a default strategy, dataset, historical experiment and $1,000 paper account. New accounts are cash-only; any test-only held state is labeled **synthetic example state**. Computed fixture results are distinguished from market returns. The onboarding panel below describes that core-release flow, not the foundation shell.

A compact onboarding panel:

```text
YAMS                                    Paper only · Sample data
Invest fake. Learn real.

Start with $1,000 of virtual capital.
[See a sample recommendation]  [Explore Strategy Lab]

Data: Synthetic demo data | Last sample session: YYYY-MM-DD
[Connect optional market-data source]
```

**Two modes are always visible:**

- `Synthetic demo` — generated fixtures for offline exploration and testing. Forecasts and charts are illustrative outcomes of those fixtures, not results from securities markets.
- `Market research data` — downloadable real history with provider, as-of, quality flags and legal limitations. No brokerage connections, no live-money execution.

If provider access is unavailable, YAMS still starts in fixture mode. Foundation metadata and health remain available; implemented fixture experiments can be replayed from 0.0.3. Show offline status and never silently switch a research portfolio into fixture values.

## 4. Default happy path — core release

### 4.1 First recommendation (0.0.5)

**Entry:** From Dashboard choose `See portfolio recommendation`. With a preconfigured default strategy, data snapshot and demo portfolio, show current holdings and **draft target immediately if previously computed**, otherwise show a cancellable job state. User sees:

- Existing virtual value, cash and holdings with valuation as-of timestamp.
- New target allocation, sector exposure and cash reserve; candidate names and weight rationales.
- Actions `BUY / SELL / REDUCE / INCREASE / HOLD`, quantitative estimated notional/quantity, and reasons.
- **90-calendar-day** scenario median return, P10/P90 range, probability of loss and projected virtual balance.
- Side-by-side `Apply proposed targets` vs `Hold current holdings`, with common model assumptions and costs.
- `Preview paper orders` and separate `Approve synthetic orders` actions, with plain warnings about execution timing.

A status banner must explain if the next valid fill is pending (e.g. `Queued for next eligible market open after approval`). The preview is **not** an executed trade; portfolio totals change only when an approved fill posts.

### 4.2 New paper portfolio (0.0.4)

`Create paper portfolio` form: name, opening virtual cash (default $1,000), strategy version, source dataset/mode, benchmark and risk policy. Show validation inline (`capital > 0`, only supported instruments, no duplicate name within local workspace if disallowed). After creation, view starts with **100% cash**, not a falsely held portfolio; link to evaluate.

### 4.3 Return visit (0.0.5)

Dashboard shows current portfolio value, most recent settled fills, pending paper orders, last recommended changes, forecast-horizon countdown, next scheduled review and data freshness. If the application was shut down, show `Monitoring paused while YAMS was closed`; after restart, show what due work was safely caught up (if anything). Qualify this as Docker shutdown, not closing a browser tab. Do not claim 24/7 monitoring.

## 5. Screen-by-screen requirements

### 5.1 Dashboard (`/`)

**Regions:** summary card (virtual total, cash, benchmark comparison), latest recommendation card, portfolio selector, mini equity curve, `Run evaluation`, `New experiment`, data status/job queue. First-time and all-cash cases are valid. Primary CTA should remain obvious even without any experiment history.

**Success:** user can answer current position and next suggested action in under one viewport scroll on desktop. **Failures:** if valuation unavailable, display `Value unavailable — no validated price for [session]`, not `$0`.

### 5.2 Strategy Lab (`/lab`)

Cards for Momentum, Mean Reversion and Low Volatility, with a separately labeled Passive Benchmark reference (SPY is benchmark-only under Q07; no publish/deploy action). Each has a plain-language thesis, underlying input data, risk profile note and supported features. `Create version`, `Run backtest`, `Compare`. Strategy configuration is form-driven; advanced/unsupported operators are absent or explicitly disabled. The original version remains inspectable after a fork. [ADR-011](adr/0011-strategy-templates.md) owns alternative-family formulas and staging; show unsupported kinds as unavailable until their schema/engine owner lands.

**Version detail:** human-friendly summary with exact parameter values and `See underlying rules` expandable section; dataset eligibility and warnings. Track immutable version IDs and experiment links. Avoid showing investment recommendations sourced only from description text.

### 5.3 Experiment builder and report (`/lab/experiments/[id]`)

**Builder:** choose strategy version, snapshot/source, benchmark, start/end date, capital, transaction friction and development/holdout split. Estimate data coverage before enabling submission. On submit, show a durable job and progress rather than waiting on a blocking network request.

**Report:** status and data provenance at top; equity curve vs SPY, summary metrics, drawdown chart, holdings/concentration over time, full trade log, strategy explanation, experiment config, warning panel, and an exact `Rerun with same inputs` action. Show **separate exploration vs untouched holdout** sections; never imply that optimizing on the holdout was independent verification.

The implemented [experiment lab](operations/experiment-lab.md) uses paginated
published versions and synthetic snapshots, covered half-open windows and readonly
execution-policy costs. Current real providers remain diagnostic-only. It shows
separate unavailable/empty/pending/cancelled/failed states, backend-owned charts and
exact accessible tables, explicit partial-window/page notices, and canonical-input
reruns that preserve full-range seeds. Viewing a narrower sample window does not
recompute or relabel the original summary metrics. No browser financial math or
paper-ledger posting is performed.

**No comparison without alignment:** if two experiments differ in dates, costs, universe or benchmark, the UI must highlight their incompatible settings; `Compare fairly` prompts rerunning with shared settings.

### 5.4 Comparison (`/lab/compare`)

Select 2–4 finished experiments. Plot comparable equity curves, cumulative return, max drawdown, risk-adjusted return, turnover, costs and cash exposure. A sorting control may rank by a chosen metric but MUST display the chosen rule (e.g. `Sorted by max drawdown`); never state `Best investment` based solely on historical profit.

**Challenge strategy:** `Change one rule` pre-fills a new version with a one-parameter diff and experiment settings, preserving the original. Show before/after parameters and warnings about repeated parameter tuning.

The implemented [comparison workflow](operations/experiment-comparison.md) uses
stored backend alignment terms, explicit shared-setting reruns and a constrained
maximum-position-weight challenge. It retains immutable source/target IDs in a
shareable comparison link and derives rule diffs from saved configurations.
Incompatible runs have exact differences and no ranking/curves; partial pages,
benchmark gaps, failed submissions and full forks remain explicit.

### 5.5 Portfolio detail (`/portfolios/[id]`)

**Top:** value + change over selected historical period + cash + price as-of + active strategy/version. **Middle:** current actual synthetic holdings table with price, fractional shares, value, current weight, target weight, rationale and sector; cash is explicit. **Bottom:** open order batches, fill history, fees, valuation and ledger reconciliation status. A missing price makes valuation stale/unavailable with a reason rather than carrying forward silently without a warning.

The 0.0.4 [account-screen handoff](operations/paper-portfolios.md) implements
creation/list/detail and posted ledger inspection. Valuation, quantities and
weights come from the API. Live pending-batch transport and approval remain
explicitly staged until the #52 screen integrates the #50 transport; a typed service-fixture component separately
proves pending/terminal-partial/cancelled presentation without a fake endpoint.
Performance change, targets, rationale and forecasts remain with their producers.

### 5.6 Decision Center (`/portfolios/[id]/decisions`)

A consistent four-step presentation:

1. **Existing portfolio**: holdings and current risk.
2. **Proposed target**: changes, individual signal evidence, constraints, remaining cash.
3. **Future scenarios**: proposed vs unchanged forecast under same assumptions; P10/P50/P90, probability of loss, horizon, limitations.
4. **Approve virtual trades**: order preview, execution assumptions, safe modal confirmation.

`HOLD` is a genuine full-screen outcome, not an error: `No changes meet the threshold` plus signals and re-evaluation date. The user can dismiss, approve a batch, or return to the Lab. A changed portfolio revision or stale market snapshot invalidates the preview and asks for re-evaluation. A forecast that cannot be computed shows **unavailable** and clear reason; do not substitute arbitrary projected returns. If data restrictions prevent a safe actionable order, approval must be disabled, but the last historical analysis remains viewable.

The [public paper controls](operations/paper-controls.md) are available to the
#52 screen owner. Persist the UUID approval key before submitting; recover the
original identity after response loss and poll batch GET for current state.
Synthetic replay must visibly distinguish logical fixture time from actual UTC
operator audit. After approval show pending intent and an explicit fixture-advance
action; never automatically invent future sessions. Unavailable opening evidence
stays pending, even after an accepted step. Cancellation shows the actual partial
or filled race outcome and retains posted effects. HOLD/cash-only results without
executable orders cannot enable approval. Monthly scheduling and its accessible Decision Center integration are implemented
by #51/#52.

The [monthly review status](operations/portfolio-schedules.md) supplies current
versus last-observed replay time, latest explicit manual review cutoff, next due,
nullable backlog, recent missed/skipped/waiting outcomes, real jobs and observed
supervisor gaps. Explain that selecting a later manual synthetic session advances
virtual review observation without trading; cancelling accepted computation does
not rewind that selection. Background scheduling never advances time or approves
orders. Show a missing calendar/source or unresolved earlier review explicitly,
and disclose that an unobserved heartbeat interval is not an exact shutdown time.
The delivered #52 screen consumes these generated transport types; the 0.0.5 core
release gate verifies the combined public journey and restart behavior.

### 5.7 Arena (`/arena`, `/arena/[id]`)

Create competition with independent equal virtual starting capital, common launch session, benchmark, execution policy and frozen strategy versions. Table columns: entrant, version, start, value, relative return, max drawdown, turnover, data completeness, status. Visual comparison uses exactly aligned dates. Entrants joining later get a distinct cohort/launch date rather than fake backdated performance. `Promote challenger` requires explicit confirmation and presents both risk and performance evidence; no automatic promotion by lucky short returns.

### 5.8 Journal (`/journal`, `/journal/[id]`)

Filter by portfolio, strategy version, action type, forecast horizon and decision date. Decision detail is a timeline: **what was known → what was recommended → approved/rejected → synthetic fill outcome → result at horizon**. Immutable original numbers remain beside later realized returns; counterfactual `hold unchanged` and SPY are distinguishable. `Outcome pending until date` is correct when horizon has not matured. Missing market data means `Cannot evaluate`, not a guessed accuracy score.

### 5.9 Settings and Diagnostics (`/settings`)

Data source selector (fixtures default; optional real research mode), data refresh and cache coverage, provider errors, resource budget (job concurrency/time/tickers), local time display preference, Docker storage/backup help, app/build version, and destructive reset confirmation. No API tokens displayed after saved; no account-management UI.

## 6. Reusable UI components and consistency

| Component | Required behavior |
|---|---|
| `DataProvenanceBadge` | mode, provider, completed session, freshness, quality warning details |
| `Money` and `ReturnPercent` | locale-aware USD; negative values signed; **never** ambiguous `0` for unavailable |
| `StrategyVersionPicker` | immutable version label and underlying identifier accessible |
| `AllocationTable` | holdings + cash sum 100%, current vs target, rationale expansion |
| `SignalBreakdown` | metric, threshold, measured value, contribution, timestamp |
| `JobProgress` | queued/running/completed/failed/cancelled, safe cancel, retry guidelines |
| `ScenarioComparison` | same axes/model; horizon+scenario caveat; current vs target |
| `RiskSummary` | concentration, drawdown, volatility, turnover and coverage caveats |
| `TradePreview` | SELL/BUY/HOLD, shares, estimated notional, friction, next eligible fill |
| `WarningsPanel` | non-dismissible blocking integrity errors; dismissible informational notes only |
| `ExperimentFingerprint` | strategy version + dataset snapshot + config/policy hash + seed |
| `EmptyState` | genuine CTA when no records, distinct from error/failed query |

Prefer tables when numerical precision matters; charts complement, never replace, numbers and methodology. All curves have labels, units, as-of dates, hover/tooltips, accessible legends and a table/text equivalent. Don't use red/green alone to communicate profit/loss.

## 7. Interaction states and error treatment

| State | What user sees | Allowed action |
|---|---|---|
| First boot loading | `Initializing local workspace` + progress / checks | Wait, see diagnostics if failure |
| Data absent | `No local market snapshot` + explanatory fixture prompt | Load bundled fixtures / retry refresh |
| Data stale | Sticky as-of warning; stale analysis marked | View older history, refresh; block current execution |
| Provider failure | Original last-valid dataset remains, provider reason shown | Retry; use clearly labeled offline fixtures |
| Candidate universe empty | `No assets passed eligibility filters` with rejections | Inspect filters, change strategy version |
| Backtest running | Durable status, elapsed progress/step if known | Navigate away, cancel if supported |
| Backtest failed | Error + run fingerprint and retry eligibility | Retry safely; inspect job log |
| Portfolio all cash | `$1,000 cash, no positions yet` | Evaluate strategy, review target |
| Recommendation HOLD | Explanation of why no adjustment meets criteria | Return, inspect evidence, run next evaluation |
| Fill pending | Approved, **not executed**; expected future session and cause | Inspect/cancel if policy permits |
| Fill blocked | Clear insufficient funds/missing next open/price issue | Refresh or re-evaluate, never fabricate fill |
| Forecast unavailable | `No reliable scenario from available history` | View other analysis; avoid fake return number |
| Journal horizon unmatured | `Outcome pending` with maturity date | Review original evidence only |
| Docker was stopped | `Scheduled analysis paused while offline` | Run catch-up, inspect missed work |

**Severity system:** error blocks financial action; warning changes interpretation or data confidence; info clarifies assumptions. Avoid alarming language when outcomes are uncertain rather than invalid.

## 8. Approval and safety UX

**Synthetic order confirmation modal** MUST summarize: paper-only badge, portfolio and version, decision as-of, list of buys/sells and cash changes, estimated costs, next eligible fill (which may not occur immediately), order-pending lifecycle and duplicate-click prevention. `Approve paper trades` sends a unique `Idempotency-Key` generated per deliberate approval. After success navigate to the order batch state, not directly to assumed updated holdings. Disable duplicate submit until response resolves; on network failure fetch by idempotency key/result where available before retry.

Use explicit labels: `Estimated`, `Forecast scenario`, `Simulated fill`, `Historical backtest`, `Actual market dataset`, `Synthetic demonstration`. Avoid `Guaranteed`, `AI predicts`, `Risk-free`, `Beat the market`, `Live trade` or `Your profit will be`. The app provides research and paper simulation, not personalized financial advice.

## 9. Responsive, accessibility and performance standards

- Desktop-first productivity UI at ~1280px; usable from 360px width. At small widths, comparison tables scroll horizontally and multi-panel views stack intentionally.
- Keyboard navigable controls; visible focus indicators; semantic headings, data table headers, modal focus management, proper form labels and helpful validation text.
- Meet WCAG 2.2 AA as a goal: sufficient contrast, reduced-motion respect, color-independent risk indication, non-hover alternatives for chart insights.
- Prefer server fetching for initial page metadata; poll job status with sensible interval and backoff, pause polling when route unmounted. WebSocket not required.
- Lazy load charts; cap visible points or downsample with disclosed method; never alter underlying stored financial data.
- API error envelopes map to readable messages and diagnostics IDs; avoid showing raw stack traces or secrets.
- Rendering a large experiment should remain responsive, and jobs must not block the browser or synchronous API calls.

## 10. Milestone-wise UX acceptance scenarios

| Gate | Acceptance scenario |
|---|---|
| 0.0.1 | Fresh Docker installation shows app, fixtures, global navigation and health; no signup |
| 0.0.2 | Operator selects a snapshot, sees eligible/scored candidates and filter reasons |
| 0.0.3 | Create/fork strategy, launch backtest, view comparison and inspect warnings |
| 0.0.4 | Create $1,000 cash account, inspect ledger, restart Docker and see same state |
| 0.0.5 | Get data-derived target, numerical 90-day scenarios, plain rationale, approve paper orders, see pending then posted fills, new holding state |
| 0.0.6 | Start Champion vs Challenger competition; dates/policies aligned and independent |
| 0.0.7 | Locate original recommendation, its forecast and matured result without overwriting history |
| 0.0.8 | Compose or AI-propose a strategy as **reviewable validated rules**, never opaque generated picks |
| 0.0.9 | Export/backup diagnostics, resolve data-provider failures, recover local job state safely |

### E2E flows for Playwright

- **Foundation first-run (0.0.1):** clean test volumes → workspace seed → labeled fixture metadata/health → basic settings → restart → same workspace; no credentials or financial action buttons.
- **Core first-run (0.0.5):** clean test volumes → initialize fixture → dashboard sample warning → computed recommendation → no external credentials.
- **Experiment:** fork a template → run fixed backtest → view curve/metrics/holdout → compare with SPY and another template.
- **Trade state:** create cash portfolio → recommendation → preview → approve → see pending → provide eligible next opening bar → see fill and reconciliation → restart → verify durability.
- **Safety:** stale data and duplicate approval cannot silently fill; unavailable forecast has no invented value; error states remain accessible.
- **Arena/Journal:** simultaneous entrants with frozen versions; original forecast vs outcome after simulated maturity.

## 11. Copywriting samples

- `Your strategy favors stronger recent trends, but this asset was excluded because its trading history is too short.`
- `Recommendation: HOLD. None of the proposed weight changes exceeded your rebalancing threshold.`
- `This is a 90-day scenario based on historical return resampling. It is not a prediction or guaranteed result.`
- `Paper orders approved. They have not filled yet; the next eligible market opening price is not available.`
- `Backtest limitation: historical universe membership could not be reconstructed. Results may be affected by survivorship bias.`
- `YAMS was closed during scheduled evaluations. No market monitoring occurred while it was stopped.`

## 12. Handoff rules

Frontend engineers use `DOMAIN_AND_API_CONTRACTS.md` as the only authoritative request/response contract and generated TypeScript client types as the source for runtime shapes. Never hardcode demo prices or ranks into production UI routes; wire state from APIs and show fixture status. Backends must emit reason codes, timestamps, nullable/unavailable states and risk warnings sufficient to render these screens. Missing UI states are actionable implementation issues, not reasons for agents to invent financial semantics.


### Delivered Decision Center source flow (#52)

At `/portfolios/{id}/decisions`, review 1) posted cash/holdings, 2) server targets and risk
with candidate/exclusion evidence, 3) common-shock 90-calendar-day scenarios in accessible
tables, then 4) explicit paper authorization. Missing marks/forecast outcomes are unavailable,
never zero. HOLD/cash-only decisions remain inspectable; no executable orders means
no approval. A readonly server context suggests the earliest calendar-supported session,
without selecting by returns. Changing/submitting a later synthetic session explicitly
observes its virtual cutoff without trading; the explanation precedes submission.

The confirmation names portfolio/revision/version/as-of, estimated quantities/costs
and indicative future opening. The server revalidates it. Original request keys and
bodies persist before mutation, so response loss/reload recovers the original result.
A changed-state conflict requires fresh review. Approval and pending states show no
optimistic holdings update. Explicit fixture steps are separate actions; missing quote
availability can leave a batch pending. Cancellation closes only remaining quantities;
posted fills and original decision/scenario evidence remain visible. The dashboard
shows real account state, pending work and next-due/supervisor diagnostics; no accounts
or balances are invented on startup. Other future routes remain staged.
