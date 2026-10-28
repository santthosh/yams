"""SQLite paper ledger (SPEC §9). Holdings and cash are derived from the trades table."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.engine import Fill

SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    initial_cash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    spy_start_price TEXT NOT NULL,
    start_as_of TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    rec_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    qty TEXT NOT NULL,
    price TEXT NOT NULL,
    cost TEXT NOT NULL,
    cash_delta TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data_as_of TEXT NOT NULL,
    data_fetched_at TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


class Conflict(Exception):
    pass


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------ portfolio
    def ensure_portfolio(self, initial_cash: Decimal, spy_price: float, as_of: str) -> None:
        with self._conn() as c:
            if c.execute("SELECT 1 FROM portfolio").fetchone() is None:
                c.execute("INSERT INTO portfolio VALUES (1, ?, ?, ?, ?)",
                          (str(initial_cash), now(), repr(spy_price), as_of))

    def reset(self, initial_cash: Decimal, spy_price: float, as_of: str) -> None:
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM trades")
            c.execute("DELETE FROM recommendations")
            c.execute("DELETE FROM portfolio")
            c.execute("INSERT INTO portfolio VALUES (1, ?, ?, ?, ?)",
                      (str(initial_cash.quantize(Decimal("0.01"))), now(), repr(spy_price), as_of))
            c.execute("COMMIT")

    def portfolio(self) -> dict:
        with self._conn() as c:
            row = dict(c.execute("SELECT * FROM portfolio").fetchone())
        row["initial_cash"] = Decimal(row["initial_cash"])
        row["spy_start_price"] = float(row["spy_start_price"])
        return row

    def state(self) -> tuple[dict[str, Decimal], Decimal]:
        """(holdings by ticker, cash), derived from the trade log."""
        with self._conn() as c:
            initial = Decimal(c.execute("SELECT initial_cash FROM portfolio").fetchone()[0])
            rows = c.execute("SELECT ticker, side, qty, cash_delta FROM trades ORDER BY id").fetchall()
        holdings: dict[str, Decimal] = {}
        cash = initial
        for r in rows:
            q = Decimal(r["qty"])
            holdings[r["ticker"]] = holdings.get(r["ticker"], Decimal(0)) + (q if r["side"] == "BUY" else -q)
            cash += Decimal(r["cash_delta"])
        return {t: q for t, q in holdings.items() if q > 0}, cash

    def trades(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def trade_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    # ------------------------------------------------------------ recommendations
    def save_recommendation(self, rec: dict) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO recommendations VALUES (?, ?, ?, ?, ?, 'ready', ?)",
                (rec["id"], rec["created_at"], rec["data_as_of"], rec["data_fetched_at"], rec["trade_count"],
                 json.dumps(rec)),
            )

    def _rec(self, row) -> dict:
        rec = json.loads(row["payload"])
        rec["status"] = row["status"]
        return rec

    def get_recommendation(self, rec_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM recommendations WHERE id = ?", (rec_id,)).fetchone()
        return self._rec(row) if row else None

    def list_recommendations(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM recommendations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._rec(r) for r in rows]

    def latest_applied(self) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM recommendations WHERE status = 'applied' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return self._rec(row) if row else None

    def apply(self, rec_id: str, fills: list[Fill], data_fetched_at: str) -> None:
        """Write all fills and mark the recommendation applied, atomically. Raises Conflict if stale."""
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute("SELECT * FROM recommendations WHERE id = ?", (rec_id,)).fetchone()
                if row is None:
                    raise Conflict("Recommendation not found.")
                if row["status"] != "ready":
                    raise Conflict(f"This recommendation is already {row['status']}.")
                if c.execute("SELECT COUNT(*) FROM trades").fetchone()[0] != row["trade_count"]:
                    raise Conflict("The portfolio has changed since this recommendation was made. Get a new one.")
                if row["data_fetched_at"] != data_fetched_at:
                    raise Conflict("Market data was refreshed since this recommendation was made. Get a new one.")
                ts = now()
                for f in fills:
                    c.execute(
                        "INSERT INTO trades (created_at, rec_id, ticker, side, qty, price, cost, cash_delta) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (ts, rec_id, f.ticker, f.side, str(f.qty), str(f.price), str(f.cost), str(f.cash_delta)),
                    )
                c.execute("UPDATE recommendations SET status = 'applied' WHERE id = ?", (rec_id,))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
