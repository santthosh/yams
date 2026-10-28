"""FastAPI app: server-rendered pages + JSON API (SPEC §10–11)."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import data, service
from app.config import DB_PATH, ROOT, STRATEGY
from app.ledger import Ledger
from app.service import AppError

STATE: dict = {}
LOCK = threading.Lock()  # serialises refresh / recommend / apply / reset


@asynccontextmanager
async def lifespan(_: FastAPI):
    md = data.load()
    ledger = Ledger(DB_PATH)
    ledger.ensure_portfolio(Decimal("1000.00"), md.latest_close(STRATEGY.benchmark), md.as_of)
    STATE.update(md=md, ledger=ledger)
    yield


app = FastAPI(title="YAMS — Yet Another Market Simulator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "app" / "templates")


def _money(x, signed=False):
    if x is None:
        return "—"
    return f"{'+' if signed and x > 0 else ''}{'-' if x < 0 else ''}${abs(x):,.2f}"


def _pct(x, digits=1, signed=False):
    if x is None:
        return "—"
    return f"{x * 100:{'+' if signed else ''}.{digits}f}%"


templates.env.filters.update(money=_money, pct=_pct)
templates.env.globals.update(strategy=STRATEGY)


def md() -> data.MarketData:
    return STATE["md"]


def ledger() -> Ledger:
    return STATE["ledger"]


def render(request: Request, name: str, **ctx):
    ctx.update(status=md().status(), msg=request.query_params.get("msg"), err=request.query_params.get("err"))
    return templates.TemplateResponse(request, name, ctx)


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)
    back = request.headers.get("referer") or "/"
    back = back.split("?")[0]
    return RedirectResponse(f"{back}?err={quote(exc.message)}", status_code=303)


# ------------------------------------------------------------------ actions (shared by API + forms)


def do_refresh() -> data.MarketData:
    with LOCK:
        holdings, _ = ledger().state()
        try:
            STATE["md"] = data.refresh(sorted(holdings), md())
        except Exception as e:  # network, provider or validation failure: keep the old cache
            raise AppError("PROVIDER_UNAVAILABLE", f"Refresh failed, kept existing data: {e}", 503) from e
    return md()


def do_reset(initial_cash: str | float) -> None:
    try:
        cash = Decimal(str(initial_cash))
    except InvalidOperation as e:
        raise AppError("VALIDATION_ERROR", "Starting cash must be a number.", 422) from e
    if not (Decimal("100") <= cash <= Decimal("10000000")):
        raise AppError("VALIDATION_ERROR", "Starting cash must be between $100 and $10,000,000.", 422)
    with LOCK:
        ledger().reset(cash, md().latest_close(STRATEGY.benchmark), md().as_of)


def do_recommend() -> dict:
    with LOCK:
        return service.build_recommendation(md(), ledger())


def do_apply(rec_id: str):
    with LOCK:
        return service.apply_recommendation(md(), ledger(), rec_id)


# ------------------------------------------------------------------ pages


@app.get("/")
def dashboard(request: Request):
    return render(request, "dashboard.html", p=service.portfolio_view(md(), ledger()),
                  trades=ledger().trades(25), recs=ledger().list_recommendations(10))


@app.get("/recommendations/{rec_id}")
def recommendation_page(request: Request, rec_id: str):
    rec = ledger().get_recommendation(rec_id)
    if rec is None:
        return RedirectResponse("/?err=" + quote("Recommendation not found."), status_code=303)
    stale = rec["status"] == "ready" and (
        rec["trade_count"] != ledger().trade_count() or rec["data_fetched_at"] != md().fetched_at)
    return render(request, "recommendation.html", rec=rec, stale=stale, caption=service.FORECAST_CAPTION)


@app.get("/backtest")
def backtest_page(request: Request):
    initial = float(ledger().portfolio()["initial_cash"])
    bt = service.get_backtest(md(), initial)
    from app.explain import verdict

    return render(request, "backtest.html", bt=bt, verdict=verdict(bt))


@app.post("/ui/recommend")
def ui_recommend():
    rec = do_recommend()
    return RedirectResponse(f"/recommendations/{rec['id']}", status_code=303)


@app.post("/ui/recommendations/{rec_id}/apply")
def ui_apply(rec_id: str, confirm: str = Form("")):
    if confirm != "yes":
        raise AppError("VALIDATION_ERROR", "Tick the confirmation box to apply paper trades.", 422)
    fills = do_apply(rec_id)
    return RedirectResponse("/?msg=" + quote(f"Applied {len(fills)} simulated paper trades."), status_code=303)


@app.post("/ui/refresh")
def ui_refresh():
    m = do_refresh()
    return RedirectResponse("/?msg=" + quote(f"Market data refreshed: as of {m.as_of}."), status_code=303)


@app.post("/ui/reset")
def ui_reset(initial_cash: str = Form("1000")):
    do_reset(initial_cash)
    return RedirectResponse("/?msg=" + quote("Portfolio reset."), status_code=303)


# ------------------------------------------------------------------ JSON API


class ResetBody(BaseModel):
    initial_cash: float = Field(1000.0)


@app.get("/api/status")
def api_status():
    return md().status()


@app.post("/api/data/refresh")
def api_refresh():
    return do_refresh().status()


@app.get("/api/portfolio")
def api_portfolio():
    return service.portfolio_view(md(), ledger())


@app.post("/api/portfolio/reset")
def api_reset(body: ResetBody | None = None):
    do_reset((body or ResetBody()).initial_cash)
    return service.portfolio_view(md(), ledger())


@app.post("/api/recommendations")
def api_recommend():
    return do_recommend()


@app.get("/api/recommendations")
def api_recommendations():
    return ledger().list_recommendations(50)


@app.get("/api/recommendations/{rec_id}")
def api_recommendation(rec_id: str):
    rec = ledger().get_recommendation(rec_id)
    if rec is None:
        raise AppError("NOT_FOUND", "Recommendation not found.", 404)
    return rec


@app.post("/api/recommendations/{rec_id}/apply")
def api_apply(rec_id: str):
    fills = do_apply(rec_id)
    return {"applied": [{k: str(v) for k, v in asdict(f).items()} for f in fills],
            "portfolio": service.portfolio_view(md(), ledger())}


@app.get("/api/backtest")
def api_backtest():
    bt = service.get_backtest(md(), float(ledger().portfolio()["initial_cash"]))
    return asdict(bt)
