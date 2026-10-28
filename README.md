# YAMS — Yet Another Market Simulator

*Invest fake. Learn real.* A small web app that manages a **paper-money** stock portfolio (default $1,000)
and tells you what to do next. It scores the S&P 500, builds a risk-capped portfolio,
backtests the same rules against SPY, forecasts 90 days ahead, and explains every position in plain English.
No real money, no broker: all orders and fills are simulated.

## Run it

```bash
git clone <repo-url> stock-maxxer && cd stock-maxxer
docker compose up --build          # → http://localhost:8000
```

That's all. No API keys are needed, and the app works offline using a committed Yahoo Finance snapshot in
`data/sample/`. Portfolio state lives in a Docker volume, so it survives `docker compose restart`/`down`/`up`.
`docker compose down -v` wipes it.

Without Docker (needs [uv](https://docs.astral.sh/uv/)): `uv sync && uv run uvicorn app.main:app --port 8000`.
Tests: `uv run pytest` (24 tests, no network).

## Use it

1. **Dashboard:** the portfolio starts as $1,000 cash. Click **Get recommendation**.
2. **Recommendation page**, read top to bottom:
   - **Proposed portfolio**: up to 8 stocks plus cash, each with a plain-English reason (momentum, rank, volatility, caps).
   - **Trades**: BUY / INCREASE / REDUCE / SELL / HOLD, with shares, dollars and why.
   - **90-day forecast**: median, bad case (P10), good case (P90) and chance of loss, for *applying the trades* vs *keeping
     what you hold*, on the same simulated paths.
   - **Track record**: what these exact rules would have done over the last 3 years vs SPY.
   - **Close calls**: the next-best stocks, and why they weren't picked.
   - Tick the box and click **Apply paper trades**. Holdings update and are explained on the dashboard.
3. Come back later, click **Refresh data** (needs internet, ~1 min), then **Get recommendation** again. It now proposes
   *changes* to what you hold. Small drifts are left alone (HOLD).
4. **Backtest** page: full metrics, equity and drawdown charts, and assumptions. **Reset** lets you restart with any starting cash.

JSON API: `GET /api/status`, `GET /api/portfolio`, `POST /api/recommendations`,
`POST /api/recommendations/{id}/apply`, `GET /api/backtest`, `POST /api/data/refresh`, `POST /api/portfolio/reset`.

## How it decides (fixed rules, not tuned to the backtest)

| Step | Rule |
|---|---|
| Universe | Today's S&P 500 list (Wikipedia) with GICS sectors. Rule-based, not hand-picked |
| Filters | ≥1 year of clean prices, price ≥ $5, median daily dollar volume ≥ $10M, price above its 200-day average |
| Score | `0.60·z(6-mo return) + 0.25·z(3-mo return) − 0.15·z(volatility)` |
| Portfolio | Top 8 (max 3 per sector), weighted by inverse volatility, **≤20% per stock, ≤40% per sector, ≥5% cash** |
| Market regime | If SPY is below its 200-day average, hold **≥50% cash** |
| Trading frictions | 10 bps slippage per trade; skip trades < $5 or < 2 points of weight drift; sells fund buys; fractional shares (6dp) |
| Backtest | Monthly walk-forward over 3 years, deciding at the close and filling at the **next day's open**; same engine code as live |
| Forecast | 5-day block bootstrap of the last 252 daily returns, 2,000 paths, seed 42, 90 calendar days ≈ 62 sessions. Each stock's average return is replaced by SPY's so past winners don't project their past forward |

## Tech and architecture

Python 3.12 · FastAPI · Jinja2 (server-rendered HTML) · Chart.js (vendored) · pandas/NumPy · yfinance · SQLite · pytest · Docker.
One process, no build step, no external services.

```text
Browser ──▶ FastAPI app/main.py  (HTML pages + /api JSON)
              ├─ service.py   valuation, build/apply recommendation, backtest cache
              ├─ engine.py    filters → features → score → capped weights → orders → simulated fills   (pure, shared)
              ├─ backtest.py  monthly walk-forward, calls engine.py
              ├─ forecast.py  block bootstrap, proposed vs hold on the same paths
              ├─ explain.py   plain-English templates from computed numbers (no LLM)
              ├─ ledger.py    SQLite: trades + immutable recommendations; holdings & cash derived from trades
              └─ data.py      Yahoo download → validate → atomic write; falls back to data/sample/
data/sample/   committed snapshot (prices.parquet, universe.csv, meta.json) · data/runtime/   cache + yams.db (volume)
```

Money values (cash, prices, shares) use `Decimal`. A recommendation can be applied **once**. It is rejected (409) if
the portfolio or the market data changed after it was made. The full spec is in [`docs/SPEC.md`](docs/SPEC.md).

## Assumptions and limitations

- **Survivorship bias:** the backtest uses *today's* S&P 500 members, so it flatters past results. With momentum on
  the committed sample, the backtest is far ahead of SPY. Treat that as an upper bound, not an expectation.
- **Adjusted prices everywhere:** dividends are treated as reinvested via Yahoo's adjusted prices. There is no
  separate dividend or split accounting.
- **Live paper fills use the latest close** (±slippage), so there are no pending orders. The backtest uses next-day
  opens to avoid look-ahead bias.
- The forecast is a **scenario, not a prediction**. Cash earns 0%. There is no out-of-sample holdout; instead,
  parameters were fixed in advance.
- **Data:** yfinance is unofficial and occasionally drops tickers. A refresh fails safely, keeping the old data, if a
  held stock or SPY can't be downloaded. The sample snapshot is Yahoo data for personal/educational research only
  (see `data/sample/meta.json`). Regenerate it with `uv run python scripts/make_sample.py`.
- There is no scheduler: the app evaluates only when you click. Not investment advice.
