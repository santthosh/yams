# YAMS — Yet Another Market Simulator

*Invest fake. Learn real.* A web app that runs a **paper-money** stock portfolio (default $1,000) and tells you what
to do next. It scores the S&P 500, builds a risk-capped portfolio, backtests the same rules against SPY, forecasts
90 days ahead, and explains every position in plain English. No real money and no broker: every order and fill is simulated.

This is a **scoped-down proof of concept** (~4 h) of the larger design in [`docs/archive/`](docs/archive/). The build
spec is [`docs/SPEC.md`](docs/SPEC.md). See [Scope and tradeoffs](#scope-and-tradeoffs) for what was cut.

## Run it

From the repository root (needs Docker):

```bash
docker compose up --build          # → http://localhost:8000
```

No API keys are needed. The app starts offline from a committed Yahoo Finance snapshot in `data/sample/`.
Portfolio state lives in a Docker volume, so it survives `docker compose restart` and `down`/`up`;
`docker compose down -v` wipes it. Without Docker (needs [uv](https://docs.astral.sh/uv/)):
`uv sync && uv run uvicorn app.main:app --port 8000`. Tests: `uv run pytest` (29 tests, no network).

## Use it

1. **Portfolio:** a *next step* card always shows what to do: get prices → get a recommendation → review and apply.
   While the market is open, holdings are valued at live Yahoo prices with today's change (for display only).
   Every metric has a **?** that explains it in plain English.
2. **Recommendation:** the summary and the **Apply paper trades** box are at the top. Below them: the proposed
   portfolio with a reason for each stock, the trades, the 90-day forecast (bad, middle and good case; apply vs keep),
   the 3-year track record, and close calls that just missed.
3. **Refresh data** after the close (~1 min, needs internet), then check again. It proposes *changes* to what you
   hold and leaves small drifts alone.
4. **Backtest:** pick any start date; see metrics, value and drawdown charts vs SPY, and the assumptions.

JSON API: `GET /api/status`, `GET /api/portfolio`, `POST /api/recommendations`, `POST /api/recommendations/{id}/apply`,
`GET /api/backtest?start=YYYY-MM-DD`, `POST /api/data/refresh`, `POST /api/portfolio/reset`.

## How it decides (fixed in advance, not tuned to the backtest)

Risk-adjusted momentum: own the S&P 500 stocks that have risen most steadily, capped and diversified, and move to
cash when the market turns down. Rationale, rules and weaknesses: [`docs/STRATEGY.md`](docs/STRATEGY.md).

| Step | Rule |
|---|---|
| Universe and filters | Today's S&P 500 (Wikipedia). ≥1 year of prices, price ≥ $5, ≥ $10M daily dollar volume, above 200-day average |
| Score | `0.60·z(6-mo return) + 0.25·z(3-mo return) − 0.15·z(volatility)` |
| Portfolio | Top 8 (max 3 per sector), inverse-volatility weights, **≤20% per stock, ≤40% per sector, ≥5% cash** |
| Risk-off | SPY below its 200-day average → **≥50% cash** |
| Frictions | 10 bps slippage; skip trades < $5 or < 2 points of drift; fractional shares |
| Backtest | Monthly walk-forward, decide at the close, fill at the **next open**; same engine code as live |
| Forecast | 5-day block bootstrap of the last year, 2,000 paths, 90 days; each stock's mean return set to SPY's |

## Tech and architecture

Python 3.12 · FastAPI · Jinja2 (server-rendered) · Chart.js (vendored) · pandas/NumPy · yfinance · SQLite · pytest · Docker.
One process, no build step, no external services.

```text
Browser ─▶ app/main.py (pages + /api)
            ├ service.py   valuation, build/apply recommendation      ├ engine.py   filters→score→weights→orders→fills (pure)
            ├ backtest.py  walk-forward on engine.py                  ├ forecast.py bootstrap, proposed vs hold
            ├ explain.py   reasons from numbers (no LLM)              ├ glossary.py metric tooltips
            ├ ledger.py    SQLite trades + immutable recommendations  └ data.py     Yahoo → validate → atomic cache
```

Money uses `Decimal`; holdings and cash are derived from the trade ledger. A recommendation applies **once** and is
rejected (409) if the portfolio or the data changed since it was made.

## Scope and tradeoffs

| Chose | Instead of (full design) | Why / cost |
|---|---|---|
| One process, SQLite, server-rendered pages | Postgres, worker, Next.js | Runs anywhere with one command; no scale or multi-user |
| Click to evaluate | Scheduled daily evaluation | Simpler and deterministic; "ongoing" only when you click |
| Today's S&P 500 list in the backtest | Point-in-time membership | No extra data source; **survivorship bias flatters results** (treat as an upper bound) |
| Caps, cash buffer, trend switch | Stop-losses, volatility targeting | Easy to explain; worst drop (−33%) is deeper than SPY's (−19%) |
| Prices, sectors, market trend | Fundamentals, earnings, news | Free and reliable; less context |
| Bootstrap scenario forecast | Calibrated, back-tested forecasts | Honest ranges; not validated against outcomes |
| Fills at the last close (live) | Pending next-open orders | No order state; the backtest still uses next-open fills |
| yfinance + committed snapshot | Licensed market data | Free, works offline; unofficial, personal-use terms, 9 MB in the repo |
| One portfolio and strategy | Strategy lab, multiple portfolios, auth | Out of scope for a POC |

Also: adjusted prices treat dividends as reinvested; cash earns 0%; live intraday prices never feed decisions
(`YAMS_LIVE_QUOTES=0` turns them off); a refresh fails safely, keeping old data, if a held stock or SPY can't be
downloaded. Regenerate the sample with `uv run python scripts/make_sample.py`. **Not investment advice.**
