"""Market data: Yahoo Finance download, on-disk cache, committed sample fallback (SPEC §3)."""

from __future__ import annotations

import json
import shutil
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from app.config import CACHE_DIR, SAMPLE_DIR, STALE_AFTER_DAYS, STRATEGY

WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NY = ZoneInfo("America/New_York")


@dataclass
class MarketData:
    close: pd.DataFrame  # index: session dates, columns: tickers (adjusted close)
    open: pd.DataFrame
    volume: pd.DataFrame
    universe: pd.DataFrame  # index: ticker; columns: name, sector, member (bool)
    as_of: str  # last completed session, YYYY-MM-DD
    fetched_at: str
    source: str  # "sample" | "live"
    missing: list[str]

    @property
    def members(self) -> list[str]:
        u = self.universe
        return [t for t in u.index[u["member"]] if t in self.close.columns]

    def sector(self, ticker: str) -> str | None:
        if ticker in self.universe.index:
            s = self.universe.at[ticker, "sector"]
            return s if isinstance(s, str) and s else None
        return None

    def name(self, ticker: str) -> str:
        if ticker in self.universe.index:
            n = self.universe.at[ticker, "name"]
            if isinstance(n, str) and n:
                return n
        return ticker

    def latest_close(self, ticker: str) -> float | None:
        if ticker not in self.close.columns:
            return None
        s = self.close[ticker].dropna()
        return float(s.iloc[-1]) if len(s) else None

    def status(self) -> dict:
        age = (datetime.now(NY).date() - pd.Timestamp(self.as_of).date()).days
        return {
            "as_of": self.as_of,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "stale": age > STALE_AFTER_DAYS,
            "age_days": age,
            "ticker_count": len(self.members),
            "missing": self.missing,
        }


# ---------------------------------------------------------------- persistence


def _write(md_dir: Path, close, open_, volume, universe, meta) -> None:
    """Write a snapshot to md_dir atomically (temp dir + rename)."""
    tmp = md_dir.with_name(md_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    long = (
        pd.concat({"close": close, "open": open_, "volume": volume}, axis=1)
        .stack(level=1, future_stack=True)
        .dropna(how="all")
        .reset_index()
    )
    long.columns = ["date", "ticker", "close", "open", "volume"]
    long["ticker"] = long["ticker"].astype("category")
    long.to_parquet(tmp / "prices.parquet", compression="zstd", index=False)
    universe.reset_index().to_csv(tmp / "universe.csv", index=False)
    (tmp / "meta.json").write_text(json.dumps(meta, indent=2))
    old = md_dir.with_name(md_dir.name + ".old")
    if md_dir.exists():
        if old.exists():
            shutil.rmtree(old)
        md_dir.rename(old)
    tmp.rename(md_dir)
    if old.exists():
        shutil.rmtree(old)


def _read(md_dir: Path, source: str) -> MarketData:
    long = pd.read_parquet(md_dir / "prices.parquet")
    long["ticker"] = long["ticker"].astype(str)
    long["date"] = pd.to_datetime(long["date"])
    wide = long.pivot(index="date", columns="ticker").sort_index()
    universe = pd.read_csv(md_dir / "universe.csv", keep_default_na=False).set_index("ticker")
    universe["member"] = universe["member"].astype(str).str.lower().isin(["true", "1"])
    meta = json.loads((md_dir / "meta.json").read_text())
    return MarketData(
        close=wide["close"],
        open=wide["open"],
        volume=wide["volume"],
        universe=universe,
        as_of=meta["as_of"],
        fetched_at=meta["fetched_at"],
        source=source,
        missing=meta.get("missing", []),
    )


def load() -> MarketData:
    """Load the runtime cache; on first boot seed it from the committed sample. No network."""
    if not (CACHE_DIR / "meta.json").exists():
        CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SAMPLE_DIR, CACHE_DIR, dirs_exist_ok=True)
    meta = json.loads((CACHE_DIR / "meta.json").read_text())
    return _read(CACHE_DIR, meta.get("source", "sample"))


# ---------------------------------------------------------------- download


def fetch_universe() -> pd.DataFrame:
    req = urllib.request.Request(WIKI_SP500, headers={"User-Agent": "Mozilla/5.0 (YAMS research app)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8")
    table = pd.read_html(StringIO(html), attrs={"id": "constituents"})[0]
    df = pd.DataFrame(
        {
            "ticker": table["Symbol"].astype(str).str.strip().str.replace(".", "-", regex=False),
            "name": table["Security"].astype(str).str.strip(),
            "sector": table["GICS Sector"].astype(str).str.strip(),
        }
    )
    df["member"] = True
    return df.drop_duplicates("ticker").set_index("ticker")


def fetch_market(held: list[str] | None = None, previous: MarketData | None = None, period: str = "5y"):
    """Download universe + held tickers + benchmark. Returns (close, open, volume, universe, meta)."""
    import warnings

    import yfinance as yf

    warnings.filterwarnings("ignore", module="yfinance")
    universe = fetch_universe()
    extra = sorted({*(held or []), STRATEGY.benchmark} - set(universe.index))
    rows = []
    for t in extra:
        name, sector = t, ""
        if previous is not None and t in previous.universe.index:
            name = previous.universe.at[t, "name"]
            sector = previous.universe.at[t, "sector"]
        rows.append({"ticker": t, "name": name, "sector": sector, "member": False})
    if rows:
        universe = pd.concat([universe, pd.DataFrame(rows).set_index("ticker")])
    tickers = list(universe.index)

    raw = yf.download(
        tickers, period=period, interval="1d", auto_adjust=True, progress=False, threads=True, group_by="column"
    )
    if raw is None or raw.empty:
        raise RuntimeError("Yahoo Finance returned no data")
    close, open_, volume = raw["Close"].copy(), raw["Open"].copy(), raw["Volume"].copy()
    # yfinance's threaded download occasionally drops a ticker (e.g. its sqlite cache lock); retry those once.
    failed = [t for t in tickers if t not in close.columns or close[t].isna().all()]
    if failed:
        retry = yf.download(
            failed, period=period, interval="1d", auto_adjust=True, progress=False, threads=False, group_by="column"
        )
        if retry is not None and not retry.empty:
            for field, df in (("Close", close), ("Open", open_), ("Volume", volume)):
                for t in retry[field].columns:
                    if retry[field][t].notna().any():
                        df[t] = retry[field][t].reindex(df.index)
    for df in (close, open_, volume):
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()

    # Drop today's bar if the session is not complete yet (last *completed* session only).
    now = datetime.now(NY)
    if len(close) and close.index[-1].date() == now.date() and (now.hour, now.minute) < (16, 15):
        close, open_, volume = close.iloc[:-1], open_.iloc[:-1], volume.iloc[:-1]

    keep, missing = [], []
    must_keep = {*(held or []), STRATEGY.benchmark}
    for t in tickers:
        if t not in close.columns:
            missing.append(t)
            continue
        c = close[t]
        bad = (c <= 0).any() or (open_[t] <= 0).any()
        enough = c.notna().sum() >= STRATEGY.min_history_sessions
        if bad or (not enough and t not in must_keep) or c.notna().sum() == 0:
            missing.append(t)
        else:
            keep.append(t)
    lost = sorted(t for t in must_keep if t not in keep)
    if lost:  # never drop the price of something we hold (or the benchmark): keep the old cache instead
        raise RuntimeError(f"could not download {', '.join(lost)}; try again later")
    close, open_, volume = close[keep], open_[keep], volume[keep]
    close = close.dropna(how="all")
    open_, volume = open_.loc[close.index], volume.loc[close.index]
    universe = universe.loc[keep]
    meta = {
        "as_of": close.index[-1].strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker_count": int(universe["member"].sum()),
        "missing": sorted(missing),
        "provider": "Yahoo Finance via yfinance (auto-adjusted daily OHLCV); S&P 500 list from Wikipedia",
    }
    return close, open_, volume, universe, meta


def refresh(held: list[str], previous: MarketData | None) -> MarketData:
    """Download fresh data into the runtime cache. On any failure the old cache is untouched."""
    close, open_, volume, universe, meta = fetch_market(held, previous)
    meta["source"] = "live"
    _write(CACHE_DIR, close, open_, volume, universe, meta)
    return _read(CACHE_DIR, "live")


def write_sample(dest: Path = SAMPLE_DIR) -> dict:
    close, open_, volume, universe, meta = fetch_market()
    meta["source"] = "sample"
    meta["license_note"] = (
        "Snapshot of Yahoo Finance data for personal/educational research only; "
        "subject to Yahoo's terms. Do not redistribute commercially."
    )
    _write(dest, close, open_, volume, universe, meta)
    return meta
