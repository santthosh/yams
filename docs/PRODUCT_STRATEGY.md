# YAMS — Product Strategy, Vision & Roadmap

**Status:** Approved product-planning baseline  
**Version:** 1.0  
**Updated:** October 26, 2026  
**Product category:** Local investment strategy research and simulated portfolio management
**Deployment:** Single-user, local-only Docker Compose; no hosted service
**Companions:** `TECHNOLOGY_STRATEGY.md`, `IMPLEMENTATION_BLUEPRINT.md`, `DOMAIN_AND_API_CONTRACTS.md`, `UX_SPECIFICATION.md`, `../AGENTS.md`  
**Operating boundary:** Real market data; virtual capital and synthetic execution only

---

## 1. Executive Summary

**YAMS is an investment strategy laboratory that connects research, testing, portfolio decisions, and accountability.**

The local operator creates or adapts systematic investment strategies, test them against historical market data, compare them on consistent assumptions, and deploy promising strategies into persistent paper portfolios. YAMS continually evaluates those portfolios, recommends what to buy, sell, reduce, increase, or hold, and records whether earlier decisions and forecasts held up.

**Product promise:** *Develop a hypothesis. Challenge it with evidence. Deploy it with virtual capital. Learn from the outcome.*

The product does **not** promise market-beating returns or provide brokerage execution. Its purpose is to improve the transparency, rigor, and repeatability of investment decisions.

### The core loop

**Discover → Formulate → Backtest → Compare → Deploy → Recommend → Simulate → Evaluate → Improve**

The experience must also work in the opposite direction: a first-time user can start with a default, documented strategy and receive an actionable, evidence-backed paper-portfolio recommendation immediately, without first becoming a quantitative researcher.

---

## 2. Problem & Opportunity

Investors and curious learners face a fragmented workflow:

- **Stock screeners** surface candidates but rarely explain how a selection translates into a defensible, managed portfolio.
- **Backtesting tools** reveal what might have worked historically but can encourage overfitting and often stop short of ongoing decisions.
- **Portfolio trackers** show holdings and returns but do not necessarily evaluate whether a proposed change improves the strategy.
- **Trading simulators** practice execution but may not preserve the original hypothesis, forecast, and evidence behind each trade.

The harder problem is not finding stocks that rose in the past. It is determining **what to own now, why, what may happen next, what could go wrong, and whether the decision was better than realistic alternatives**.

YAMS addresses that gap through an integrated research-to-decision workflow and prospective, side-by-side paper evaluation.

### Positioning

> **A flight simulator for investment strategies:** build and challenge systematic ideas, test them fairly, put virtual capital behind them, and hold every decision accountable.

### Initial audience

1. **Curious individual investors:** Want understandable, evidence-backed investing decisions without needing to code.
2. **Strategy experimenters:** Want to create, modify, compare, and test rules rapidly.
3. **Technical builders and researchers:** Want reproducible strategy definitions, transparent calculations, and auditable results.

**Initial wedge:** Individuals who want to answer, “If I have $1,000 of virtual capital, what should I own today, why, and is this strategy more credible than buying and holding a broad-market index?”

---

## 3. Product Principles

1. **Decisions, not dashboards.** Every meaningful analysis should lead to a comprehensible action or a defensible decision to hold.
2. **Evidence over confidence.** Show methodology, uncertainty, limitations, and counterfactuals rather than unsupported return claims.
3. **Dynamic by design.** Investment candidates and allocations emerge from data and explicit rules, not a manually curated list of favorite stocks or fixed target weights.
4. **Risk is first-class.** Return, drawdown, concentration, liquidity, turnover, and uncertainty influence recommendations.
5. **Research is reproducible.** Version strategies, preserve experiment inputs, record assumptions, and make reruns consistent.
6. **Test future relevance, not just historical fit.** Separate development data, out-of-sample evaluation, and truly prospective paper performance.
7. **Explain decisions to non-specialists.** Present plain-language rationales with the actual metrics and rules available for inspection.
8. **Never silently trade.** A recommendation, a operator-approved paper trade, and a simulated fill are distinct events.
9. **AI assists; the quantitative engine decides.** AI may translate hypotheses and explain evidence, but must not invent market data, scores, positions, or return forecasts.
10. **Paper-only, always.** No real-money accounts, brokerage orders, leverage, or hidden live execution paths.

---

## 4. End-to-End User Experience

### 4.1 Start a lab

The operator starts within one local workspace (no account registration) with:

- Starting paper capital (default **$1,000**).
- Investment horizon and a forecast horizon (default **90 calendar days**, translated to trading sessions for calculations).
- Risk preference and basic constraints: maximum position and sector exposure, eligible securities, rebalancing frequency, and optional cash reserve.
- A benchmark, initially a broad-market index proxy such as SPY with adjusted-price assumptions disclosed.

**First-use fast path (complete core release, 0.0.5):** YAMS proposes a starter strategy, evaluates the latest eligible market data, and immediately displays a draft target portfolio, recommended virtual trades, rationale, and 90-day forecast. Users can inspect or change the assumptions before deploying. The 0.0.1 foundation instead ships the seeded workspace, labeled fixture metadata and healthy shell; [ADR-008](adr/0008-lifecycle-api-additions.md) defines the intermediate journeys without reducing the full core scope.

### 4.2 Discover or design a strategy

The Strategy Lab supports documented starting templates:

- **Momentum:** Favor securities demonstrating sustained relative strength.
- **Mean reversion:** Evaluate potential rebounds after unusually weak price action, subject to trend and risk filters.
- **Low volatility:** Favor comparatively stable securities with appropriate diversification.
- **Passive benchmark:** Buy-and-hold reference for measuring whether complexity adds value.

Each strategy is defined by **universe → eligibility filters → scoring → selection → weighting → risk rules → rebalance/exit rules**.

Users can fork a strategy into immutable versions, change individual parameters, and compare results. Later releases add a visual rule builder and AI-assisted hypothesis translation. A strategy's parameters and universe membership rules are always inspectable.

### 4.3 Run a historical experiment

A backtest simulates decisions using only information available at each evaluation timestamp. Results include:

- Portfolio value and cumulative/annualized return.
- Benchmark comparison, including net return after simulated trading friction.
- Volatility, maximum drawdown, and risk-adjusted performance.
- Trade history, turnover, concentration, and cash exposure.
- Plain-language explanations of material wins, losses, and failure modes.
- Dataset coverage, data-quality warnings, and limitations such as survivorship bias.

Where feasible, split data into development and untouched evaluation windows. Strategy optimization never reports in-sample performance as independent validation.

### 4.4 Compare and challenge hypotheses

A user selects multiple strategy versions and runs them on **the same dates, universe assumptions, initial capital, costs, and benchmark**. The interface makes differences in outcome and risk visible.

**Challenge This Strategy** creates a new version and reruns an experiment after a controlled change, such as lowering the maximum single-stock weight from 25% to 10%. The original version and its results remain intact.

The UI must distinguish **best historical return** from **most credible prospective candidate**.

### 4.5 Deploy a paper portfolio

The user deploys a strategy into a simulated account. The system:

1. Calculates a current, feasible target portfolio from the latest eligible data.
2. Converts target weights into specific synthetic orders, including cash and transaction-cost effects.
3. Displays a preview before the user applies the paper trades.
4. Records simulated fills, share quantities, prices, remaining cash, strategy version, and timestamps.
5. Maintains an auditable ledger of holdings, cash flows, and portfolio valuation.

Multiple virtual portfolios may be operated independently for competing hypotheses; capital is not double-counted within any one account.

### 4.6 Get ongoing recommendations

At each scheduled or user-triggered evaluation, the engine compares **current holdings** with the strategy's **new target portfolio**, then proposes:

**BUY / SELL / INCREASE / REDUCE / HOLD / ALLOCATE TO CASH**

Each recommendation contains:

- Current and proposed quantity, weight, and virtual dollar value.
- Estimated turnover and simulated trading cost.
- Evidence behind the change: scores, signals, risk rules, and constraints.
- An explicit forecast horizon and numerical return estimate for the **proposed portfolio**.
- A return range/downside scenario and comparison against **holding the existing portfolio**.
- A transparent description of uncertainty and assumptions.

Doing nothing must be a supported, explainable recommendation. Actual paper holdings change only when a synthetic trade is applied under the chosen account's execution policy.

### 4.7 Learn through a Decision Journal

Every recommendation is stored with its strategy version, market-data timestamp, available evidence, portfolio state, forecast, proposed trades, and whether those trades were applied.

When its horizon matures, the system evaluates the outcome against:

- The recommendation's original return estimate and uncertainty range.
- The previous portfolio without the proposed changes.
- The passive benchmark and cash baseline.

Users can review decision accuracy, forecast calibration, realized drawdowns, and whether higher activity actually added value.

### 4.8 Compete in the Strategy Arena

The Arena lets users allocate **independent, equal starting paper balances** to a champion, challengers, and a passive benchmark. Strategies are version-frozen at launch and evaluated prospectively on newly arriving market data.

The Arena presents comparative return, risk, turnover, and consistency. Users may promote a challenger after sufficient evidence, but the product does not declare a winner based on a short lucky streak.

---

## 5. Product Capabilities & Functional Requirements

| ID | Capability | Required behavior |
|---|---|---|
| FR-01 | Market-data ingestion | Retrieve, validate, cache, and timestamp historical/current prices plus contextual signals such as volume and sector; disclose freshness and gaps. |
| FR-02 | Data-driven universe | Construct the candidate set from declared eligibility and universe rules; no fixed, hand-picked favorites. |
| FR-03 | Candidate scoring | Rank eligible securities using documented, versioned, deterministic strategy logic. |
| FR-04 | Portfolio construction | Calculate feasible holdings and weights under capital, concentration, diversification, and risk constraints. |
| FR-05 | Persistent position | Maintain actual synthetic quantities, weights, cash, trade ledger, and valuation. |
| FR-06 | Forward recommendation | Produce specific BUY/SELL/HOLD/rebalance actions for the current portfolio, including a numerical forecast over a stated horizon. |
| FR-07 | Explainability | Explain every position and material action in plain language, grounded in real engine outputs. |
| FR-08 | Historical testing | Run walk-forward simulations with realistic execution assumptions and no future-data leakage. |
| FR-09 | Risk management | Model position/sector limits, volatility, drawdowns, turnover, trading friction, and cash fallback. |
| FR-10 | Strategy experimentation | Create/fork/version configurable strategies and evaluate them through the same framework. |
| FR-11 | Comparative evaluation | Compare strategies against one another, holding unchanged, cash, and a passive market benchmark. |
| FR-12 | Paper execution | Preview, approve, record, and reconcile virtual transactions; never place real orders. |
| FR-13 | Decision accountability | Record recommendations and forecasts immutably and reconcile them against subsequent outcomes. |
| FR-14 | Prospective Arena | Run multiple independent, version-frozen paper strategies on new data with fair comparisons. |
| FR-15 | Accessible web product | Provide a responsive web interface, straightforward setup, and a working local Docker demo. |

### Nonfunctional requirements

- **Reproducibility:** A strategy version, data snapshot, evaluation time, and assumptions identify an experiment uniquely.
- **Point-in-time integrity:** Decisions must not access price bars or fundamentals published after their historical decision timestamps.
- **Auditability:** Source provenance, calculations, recommendations, and synthetic transactions can be inspected.
- **Reliability:** Data-provider failures, stale quotes, gaps, and partial runs fail visibly and safely; never produce silently incomplete recommendations.
- **Performance:** Routine portfolio evaluations feel interactive; heavy historical experiments execute as trackable jobs.
- **Testability:** Financial calculations and risk constraints have deterministic unit and integration tests.
- **Security:** Keep provider secrets server-side; bind services to localhost; validate file paths and market-data inputs; reject real-money and broker execution paths.
- **Usability:** Financial jargon has explanations and the product always distinguishes observed returns from forecasts.

---

## 6. Investment Intelligence & Scientific Integrity

### Strategy execution contract

Every strategy must implement a common conceptual interface:

`eligible_universe(as_of) → features(as_of) → scores(as_of) → target_weights(as_of, constraints) → orders(current_positions)`

The engine, not presentation-layer code or an LLM, owns ranking, sizing, constraints, forecasting, and simulated execution. Ineligible or missing-data securities are handled according to explicit rules.

### Data and modeling rules

- Use real historical market data from replaceable provider adapters; virtual cash and trades are synthetic.
- Handle or document price adjustments for stock splits, distributions, delistings, and missing sessions.
- Record price type, trading-calendar conventions, currency, timezone, publication/availability time, and source.
- Identify survivorship bias where historical constituent membership is unavailable; never present today's universe as point-in-time historical membership without qualification.
- Prevent look-ahead bias with as-of data access and execution on a subsequent eligible bar, not a price already used to make the decision.
- Include configurable fees, bid/ask or slippage assumptions, fractional-share policy, and insufficient-cash handling.
- Avoid parameter fishing: preserve untouched validation windows and show when results were selected after repeated experiments.

### Forecasting standard

Initial forecasts can use a transparent historical-return resampling or bootstrap model. Reports must identify the return statistic (e.g., median), scenario range, horizon, sample period, and assumptions. **Historical resampling is a scenario model, not proof of future predictive accuracy.** Advanced forecasting models are optional and must outperform a documented baseline on unseen data before replacing it.

### Initial portfolio policy (configurable defaults)

- Long-only stocks and ETFs; no margin, short selling, derivatives, or leverage.
- Risk-adjusted, data-driven weights, **not** fixed allocations.
- Maximum single-position and sector exposure, with sensible minimum position sizes.
- Optional volatility or trend filters; allocation to cash when conditions or constraints warrant it.
- Periodic scheduled rebalance, with tolerance bands to prevent unnecessary turnover.

These are starting policies, not immutable product limits or assertions of investment superiority.

---

## 7. Product Architecture (Target Direction)

A modular monolith or small number of services is preferred over premature microservices.

```text
Web UI (Dashboard / Lab / Arena / Portfolios / Journal)
                         |
                  Application API
                         |
     +-------------------+------------------+
     |                   |                  |
Strategy &          Paper Portfolio     Experiment &
Decision Engine     Ledger/Execution     Backtest Runner
     |                   |                  |
     +-------------------+------------------+
                         |
               Market Data Service
             (provider adapters + cache)
                         |
            Persistent Storage + Jobs
```

**Implementation baseline:** Next.js/TypeScript frontend, Python FastAPI API and research worker, PostgreSQL for portfolios/strategies/jobs/decisions, and local Parquet files queried with embedded DuckDB for market data and experiment artifacts. The application runs entirely under Docker Compose, with no authentication or cloud services. See `TECHNOLOGY_STRATEGY.md` and `IMPLEMENTATION_BLUEPRINT.md` for normative details.

### Core domain objects

- **LocalWorkspace:** Singleton configuration and local research context; no account or tenant identity.
- **StrategyDefinition / StrategyVersion:** Immutable rules, parameters, universe and risk policy.
- **MarketDataset / Snapshot:** Data source, as-of/availability times, coverage, provenance, and version.
- **ExperimentRun:** Strategy version, exact inputs, assumptions, results, warnings, and artifacts.
- **PaperPortfolio:** Virtual funding, deployment policy, benchmark and strategy association.
- **Holding / Transaction / CashLedgerEntry:** Synthetic account state and auditable movements.
- **Recommendation / Forecast:** Proposed trades, evidence, current-vs-target comparison, horizon and uncertainty.
- **DecisionOutcome:** Realized paper result after the forecast horizon, with counterfactuals.
- **ArenaCompetition / Entrant:** Frozen strategies evaluated on comparable prospective periods.

### API/engine boundaries

Treat market ingestion, feature computation, strategy evaluation, portfolio construction, order simulation, and explanations as separately testable modules. Version the critical contracts before parallel agent implementation. Store experiment inputs and outputs so users can inspect, export, and rerun decisions.

---

## 8. Milestone Roadmap

Milestones `0.0.1`–`0.0.9` are planned release targets, not published releases. `0.0.5 — Decision Center` is the first complete core release; later versions add the documented capabilities. Document version metadata is separate from these product release targets.

The roadmap prioritizes a **complete, trustworthy vertical slice** before advanced experimentation. Milestones are sequenced for GitHub planning; each produces a demonstrable result.

| Milestone | Outcome | Key deliverables | Exit criteria |
|---|---|---|---|
| **0.0.1 — Foundation** | The project is ready for parallel development. | Repository standards, PRD, ADRs, domain model, data/strategy contracts, CI, local bootstrap, design system. | Fresh clone runs; tests/linters execute; example data contract validated. |
| **0.0.2 — Market Data & Quant Core** | Deterministic stock-selection engine. | Provider adapter, historical prices/context, candidate universe, feature pipeline, initial strategy, risk-aware allocation. | From data and an as-of date, engine returns scored candidates and a feasible target portfolio with explanations. |
| **0.0.3 — Strategy Lab & Backtesting** | Users can scientifically test investment ideas. | Template strategies, versioning, walk-forward backtester, benchmarks, costs, risk metrics, comparison UI, validation split. | Repeatable experiments generate correct metrics and reveal leakage/data limitations. |
| **0.0.4 — Paper Portfolios** | A virtual portfolio can be deployed and maintained. | $1,000 default, position/cash ledger, order preview, synthetic fills, holdings, valuation, portfolio dashboard. | Trades reconcile to cash and positions; restarting does not lose state. |
| **0.0.5 — Decision Center** | End-to-end investment decision workflow. | Scheduled/on-demand review, BUY/SELL/HOLD, current-vs-target deltas, numerical horizon forecast, uncertainty, grounded explanations. | New user can obtain a recommendation, deploy it, and later request an updated action with all required evidence. **First complete product release.** |
| **0.0.6 — Strategy Arena** | Strategies compete under fair forward conditions. | Champion/challengers, equal virtual starting capital, frozen versions, prospective runs, benchmark race, promotion workflow. | Parallel portfolios remain independent and comparisons use aligned periods and assumptions. |
| **0.0.7 — Decision Journal** | The system measures decision quality over time. | Immutable decision records, horizon maturity jobs, forecast-vs-outcome, hold/no-change counterfactual, attribution, calibration dashboard. | Users can audit a recommendation from original evidence through measured outcome. |
| **0.0.8 — Assisted Authoring** | Users can formulate hypotheses more easily. | Visual strategy composer, AI-to-config proposal, validation/approval, experiment critiques, plain-language insights. | AI outputs explicit reviewable rules; no arbitrary generated returns or unapproved execution. |
| **0.0.9 — Reliability & Research Depth** | Reliable ongoing operation and deeper research. | Multi-provider resilience, data usage review, local health diagnostics, job recovery, backup/export, more realistic market data and research coverage. | Data reliability, security, operational readiness, and research quality meet local reliability and research-quality release criteria. |

### Release gates

**Core Release (0.0.1–0.0.5):** Real market-data ingestion and context; dynamically discovered/scored stocks; risk-constrained target portfolio; persistent synthetic holdings; explicit next-action recommendations; numerical forward forecast; historical profitability evaluation; position explanations; runnable web UI and concise startup/architecture README.

**Research Release (0.0.6–0.0.7):** Prospective competing strategies and accountable forecast/outcome tracking.

**Creator Release (0.0.8–0.0.9):** Accessible authoring and research assistance, with quant execution remaining deterministic and auditable.

Do not delay Core Release for a sophisticated AI assistant, arbitrary strategy DSL, advanced charting, or distributed/cloud infrastructure.

---

## 9. GitHub Delivery & Agent Execution Model

### Planning hierarchy

**Milestone → Epic issue → Small implementation issue → Pull request → Demonstration / acceptance test**

Each implementation issue should specify:

- **User/problem outcome:** Why this work matters.
- **Scope and exclusions:** What to implement and what not to touch.
- **Contract:** Inputs, outputs, domain types, APIs, and persistence changes.
- **Acceptance criteria:** Observable behavior, including error and empty states.
- **Tests:** Unit/integration/e2e requirements and fixture expectations.
- **Dependencies:** Blocking issues, migrations, data adapters, design decisions.
- **Agent notes:** Relevant files/modules, architecture guardrails, and suggested PR boundaries.

### Suggested labels

`type:epic`, `type:feature`, `type:bug`, `type:tech-debt`, `area:data`, `area:quant`, `area:backtest`, `area:portfolio`, `area:web`, `area:forecast`, `area:ai`, `priority:p0`, `priority:p1`, `priority:p2`, `agent-ready`, `blocked`, `needs-adr`.

### Initial epics to groom

1. **Repository and quality baseline** — local setup, CI, fixtures, versioned contracts.
2. **Market-data pipeline** — source adapters, context, caching, freshness, quality reporting.
3. **Strategy framework** — strategies, deterministic features, candidate scoring, eligibility.
4. **Allocation and risk engine** — sizing, constraints, cash, trade feasibility.
5. **Backtest and benchmark engine** — walk-forward events, friction, returns, risk, validation.
6. **Strategy Lab UI** — strategy creation/forking, experiment controls, comparison results.
7. **Paper portfolio ledger** — synthetic orders/fills, holdings, cash, reconciliation.
8. **Decision and forecast engine** — portfolio deltas, scenario models, explanations.
9. **Arena orchestration** — frozen entrants, scheduled evaluations, fair comparisons.
10. **Journal and outcomes** — immutable decision snapshots, maturity, counterfactuals.
11. **AI-assisted research** — explicit proposed strategy configurations and safeguards.

### Coding-agent operating rules

- Work from a single issue and preserve its boundaries; avoid unrelated rewrites.
- Do not invent financial data or hardcode securities to make demonstrations succeed.
- Add tests for every change to a financial invariant or strategy decision.
- Keep numerical decisions deterministic and explainable; label illustrative fixtures as synthetic.
- Pin dependencies and provide reproducible setup commands.
- Prefer small reviewable PRs, documented contract changes, and green CI.
- Never merge financial-model changes without reviewing assumptions and backtest leakage risks.

---

## 10. Success Measures

### User value

- **Time to first recommendation:** How quickly a new user sees a complete, defensible paper allocation.
- **Experiment-to-deploy conversion:** Whether research produces a user-understood decision.
- **Repeat engagement:** Whether people return to review recommendations, outcomes, and competing hypotheses.
- **Decision comprehension:** Whether users can explain why positions were selected and what risks are involved.

### Research quality

- **Reproducible runs:** Same versioned inputs yield matching results.
- **Data integrity:** Coverage, staleness, point-in-time limitations, and provider failures are visible.
- **Backtest validity:** No known future-data leakage; costs and benchmark assumptions are explicit.
- **Forecast accountability:** Track realized outcomes and empirical interval coverage over sufficient samples; do not claim calibration prematurely.

### System quality

- Deterministic tests for sizing, returns, orders, ledger reconciliation, and constraints.
- End-to-end tests for the default user journey and ongoing rebalance.
- Observable background runs with retry safety and unambiguous failure states.
- Documented local setup and stable release builds.

Initial numerical targets should be set after a baseline prototype and measured user tests, not invented as historical achievements.

---

## 11. Risks, Trade-offs & Non-Goals

| Risk | Mitigation |
|---|---|
| Historical overfitting | Immutable strategy versions, holdout periods, Arena's forward evaluation, clear in-sample labels. |
| Look-ahead and survivorship bias | As-of dataset access, next-bar execution, membership-history support when available, explicit limitations. |
| False certainty in forecasts | Quantitative scenarios with stated assumptions, uncertainty ranges, empirical validation over time. |
| Market-data gaps and provider changes | Provider abstraction, validation, provenance, caching, stale-data warnings and safe failure. |
| High simulated turnover | Transaction costs, slippage, minimum trade sizes, rebalancing bands and risk constraints. |
| Complexity obscuring value | Default recommendation first; progressive disclosure into Lab, Arena, and advanced controls. |
| AI inventing investment reasoning | Ground explanations in computed evidence, require human review of generated strategy rules. |
| Scope expansion delaying usability | Enforce Core Release gate before advanced features; ship milestone demonstrations. |
| Licensing/compliance risk | Review market-data terms and distribution rights; clear simulation-only disclosures; no real trading. |

**Explicit non-goals for the initial releases:** Real-money brokerage connections, personalized regulated investment advice, guaranteed alpha, high-frequency/day trading, derivatives, margin or leverage, social copy-trading, and autonomous real-money execution.

---

## 12. Decisions to Make Early

These should become short architectural/product decision records (ADRs), not unresolved blockers across the whole roadmap:

1. **Initial eligible universe:** Use explicit provider-derived liquid U.S. equities; track historical universe limitations and snapshot membership. Baseline defaults specified in `IMPLEMENTATION_BLUEPRINT.md`.
2. **Market-data provider and license:** Cost, coverage, corporate actions, rate limits, and redistribution terms.
3. **Default strategy:** A simple, published rule set suitable for a credible first recommendation, without claiming superiority.
4. **Paper-fill policy:** Baseline next-session-open, fractional-share, and transaction-friction semantics are specified in `IMPLEMENTATION_BLUEPRINT.md`.
5. **Forecast baseline:** Baseline 90-day historical block-resampling scenarios and shared-shock counterfactuals are specified in `IMPLEMENTATION_BLUEPRINT.md`.
6. **Core architecture:** Already selected: Next.js + Python/FastAPI with local Compose; finalize typed contracts and dev workflow.
7. **Scheduling semantics:** Evaluation calendar, data freshness, idempotency, restart catch-up, and explicit paused-when-offline behavior.
8. **Experiment fairness:** Comparable periods and transaction-cost assumptions, with clear treatment of unequal universe coverage.

---

## 13. Definition of a Complete Core Product

A user can open YAMS, begin with $1,000 in virtual capital, and receive a data-derived portfolio recommendation without choosing stocks manually. They can inspect why each position was selected, see concrete weights and synthetic trade quantities, understand the expected return and risk over a stated horizon, and deploy the portfolio without any real-money transaction. They can evaluate the same strategy through an auditable historical backtest, compare it against a passive benchmark, return later for updated BUY/SELL/HOLD guidance, and inspect how the portfolio and decisions evolved. The repository is independently runnable and documented.

**Long-term north star:** Every investment decision should be a testable hypothesis with preserved evidence, an explicit prediction, a synthetic action, and an observable outcome.

---

*YAMS is a research and simulated-investing product. Market data may be real, but all capital, orders, fills, and portfolios are virtual. Historical results and modeled forecasts are not guarantees of future returns.*

## 14. Local-Only Scope and Document Authority

YAMS has **exactly one local operator and one local workspace**. Multiple strategies, paper accounts, and Arena entrants are portfolio objects, not users or tenants. The application does not contain signup, identity management, billing, hosted collaboration, real-money execution, or multi-tenant access control. Scheduled work runs only while Docker Compose is up and catches up conservatively on restart.

This strategy owns **product outcomes and FR-01–FR-15**. `TECHNOLOGY_STRATEGY.md` owns stack and deployment decisions; `IMPLEMENTATION_BLUEPRINT.md` owns quantitative, data, and execution defaults; `DOMAIN_AND_API_CONTRACTS.md` owns schemas, API behavior, and state machines; `UX_SPECIFICATION.md` owns screen behavior; `AGENTS.md` owns contributor/agent quality gates. Record conflicting future changes via an ADR and update the affected documents together.
