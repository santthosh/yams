# From POC to target architecture

YAMS today is a **proof of concept**: one process that delivers the whole decision loop (data → picks → trades →
forecast → backtest → paper ledger) in the simplest runnable form. The **target state** is the fuller local research
product described in [`archive/`](archive/), mainly `TECHNOLOGY_STRATEGY.md`, `PRODUCT_STRATEGY.md` and
`IMPLEMENTATION_BLUEPRINT.md`. This page compares the two and shows how the POC grows into the target without a rewrite.

Both share the same principles: **paper money only**, runs on one machine with `docker compose up`, no accounts, no
brokers, no cloud, and **one shared decision engine** used by live recommendations and backtests alike.

## Current: POC (this repository)

```mermaid
flowchart LR
  U([Browser]) -->|:8000| APP
  subgraph APP [One container: FastAPI app]
    direction TB
    M[Pages + /api<br/>Jinja2, Chart.js] --> S[service.py]
    S --> E[engine.py<br/>pure decision engine]
    S --> BT[backtest.py] --> E
    S --> FC[forecast.py]
    S --> X[explain.py · glossary.py]
    M --> D[data.py]
  end
  S --> L[(SQLite ledger<br/>trades, recommendations)]
  D --> C[(Parquet cache<br/>one market snapshot)]
  D -.seed.-> SM[(data/sample)]
  D -.on click.-> Y{{Yahoo · Wikipedia}}
```

Everything runs in the request: a recommendation (scoring 500 stocks, a 3-year backtest and 2,000 forecast paths)
takes well under a second (about 0.5 s cold, cached after), so no job queue is needed. State is one SQLite file plus one cached market snapshot, both on a
Docker volume.

## Target: full design

```mermaid
flowchart TB
  B([Browser 127.0.0.1:3000]) --> W[Next.js web<br/>TypeScript, Tailwind, shadcn/ui, Plotly]
  W -->|internal HTTP /api/v1| A[FastAPI API<br/>Pydantic, OpenAPI, generated TS client]
  A --> PG[(PostgreSQL<br/>ledger, strategies, recommendations,<br/>journal, arena, jobs)]
  A -->|enqueue / status| J[(Job table<br/>FOR UPDATE SKIP LOCKED)]
  WK[Worker + scheduler<br/>refresh, backtests, forecasts,<br/>scheduled evaluations, outcomes] -->|claim| J
  WK --> PG
  A --> Q[Shared quant engine<br/>eligibility, features, scoring,<br/>allocation, risk, orders, execution]
  WK --> Q
  Q --> R[Market-data repository]
  WK --> R
  R --> P[(Parquet snapshots + artifacts<br/>manifest and content hashes)]
  R --> DK[DuckDB, embedded]
  WK -.optional internet.-> PR{{Provider adapters<br/>fixtures, cache, Yahoo, more}}
```

Four long-running containers (`web`, `api`, `worker`, `postgres`) and a one-shot migration task. Only the web port
is published, on loopback.

### Target data and decision flow

```mermaid
flowchart LR
  PR{{Providers}} --> SN[Immutable dataset snapshot<br/>point-in-time universe,<br/>corporate actions, hashes]
  SV[Strategy version<br/>immutable JSON config] --> DC
  SN --> DC[Decision contract<br/>strategy + snapshot + as_of<br/>+ portfolio + execution policy]
  DC --> REC[Recommendation<br/>targets, orders, evidence, forecast]
  DC --> EXP[Experiment run<br/>walk-forward backtest, holdout]
  DC --> AR[Arena entrants<br/>independent paper portfolios]
  REC -->|apply| LED[Paper orders and fills<br/>cash ledger, position events]
  REC --> JR[Decision journal<br/>immutable record]
  JR -->|horizon matures| OUT[Outcome vs forecast,<br/>vs SPY and vs no-change]
```

### Target scheduled evaluation

```mermaid
sequenceDiagram
  participant Sch as Scheduler (in worker)
  participant Job as Job table
  participant Wk as Worker
  participant Eng as Quant engine
  participant DB as PostgreSQL
  Sch->>Job: enqueue refresh + evaluate (idempotency key)
  Wk->>Job: claim with lease + heartbeat
  Wk->>Eng: evaluate(strategy version, snapshot, as_of, portfolio)
  Eng-->>Wk: targets, orders, evidence, forecast
  Wk->>DB: store immutable recommendation + journal entry
  Note over Wk,DB: Policy decides whether to auto-apply or wait for the user
  Wk->>Job: completed (or failed with retry/backoff)
  Note over Sch: Runs only while the app is up, and missed periods replay in order on restart
```

## Side by side

| Concern | POC (now) | Target | Why it matters |
|---|---|---|---|
| Deployment | 1 container | 4 containers + migration task | Heavy work leaves the request path |
| UI | Server-rendered Jinja2 + Chart.js | Next.js, Tailwind, shadcn/ui, Plotly | Richer interactive research and comparison |
| Durable state | SQLite: trades + recommendations | PostgreSQL + Alembic migrations, full domain model | Many portfolios, strategies, journal, arena |
| Market data | One Parquet cache, overwritten on refresh | Immutable, hashed snapshots + DuckDB | Reproducible experiments; provenance |
| Universe | **Today's** S&P 500 | **Point-in-time** membership and corporate actions | Removes survivorship bias from backtests |
| Strategies | One, fixed in `config.py` | Versioned JSON configs, Strategy Lab, templates | Test ideas without code changes |
| Evaluation | When the user clicks | Scheduler + job queue, catch-up on restart | Truly ongoing decisions |
| Backtests | In-request, 3-year window | Async jobs, in-sample vs **untouched holdout** | Honest validation, larger experiments |
| Forecast | Bootstrap scenario | Same baseline + **journal tracks realized outcomes** and calibration | Know whether forecasts deserve trust |
| Competition | — | Strategy Arena: frozen entrants, equal capital | Fair forward comparison of strategies |
| Context data | Prices, sectors, market trend | Provider interface for fundamentals and events, with availability dates | Richer, point-in-time signals |
| Fills | Last close ± slippage | Explicit execution policy, unadjusted fill prices, pending orders | More realistic paper trading |
| Quality | pytest (29 tests) | pytest + Vitest + Playwright, CI, release pipeline | Safe parallel development |

## What carries over unchanged

The POC was built so that its core survives the move:

- **`engine.py`** is already the target's "single decision contract": pure functions from prices, sectors, holdings
  and parameters to targets, orders and fills, shared by live and backtest. It moves into the quant-engine package as is.
- **Decimal ledger semantics**: holdings derived from trades, immutable recommendations, and apply-once with a 409 on
  stale state map directly onto the target's paper orders, fills and idempotency rules.
- **Explanations from numbers** (`explain.py`, `glossary.py`) stay deterministic: no LLM computes results.
- **Forecast method** (bootstrap, same paths for proposed vs hold, drift adjustment) is the target's stated baseline.
- **API shapes** (`/api/recommendations`, `/apply`, `/backtest`, error envelope) move under `/api/v1`.

## Migration path

```mermaid
flowchart TB
  subgraph CR [Core release, 0.0.1–0.0.5]
    direction LR
    POC[POC today<br/>thin slice of 0.0.2–0.0.5] --> M1[Postgres + migrations<br/>move ledger, keep engine] --> M2[Worker + job table<br/>async backtests, scheduling]
    M2 --> M3[Snapshots + point-in-time universe<br/>removes survivorship bias] --> M4[Versioned strategies<br/>Strategy Lab, holdout] --> M5[Next.js UI<br/>generated API client]
  end
  subgraph AD [Additive releases]
    direction LR
    R1[0.0.6 Arena] --> R2[0.0.7 Journal] --> R3[0.0.8 Assisted authoring] --> R4[0.0.9 Reliability]
  end
  CR --> AD
```

Order of value: **Postgres + worker** first (unblocks scheduling), then **point-in-time data** (fixes the biggest
credibility gap), then **strategy versioning**, then the **new UI**. The Arena, Journal, assisted authoring and
reliability milestones are additive after the core release.
