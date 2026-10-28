"""Strategy, forecast and backtest parameters.

Fixed a priori and documented in docs/SPEC.md §4–6. They were NOT tuned on the backtest.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StrategyConfig:
    # Eligibility (§4.1)
    min_history_sessions: int = 252
    min_price_usd: float = 5.0
    min_median_dollar_volume_usd: float = 10_000_000.0
    liquidity_window: int = 20
    trend_sma_sessions: int = 200
    # Features / score (§4.2). Weights are positive magnitudes; the volatility
    # penalty is subtracted in the formula, never stored as a negative number.
    momentum_long_sessions: int = 126
    momentum_short_sessions: int = 63
    volatility_sessions: int = 60
    w_mom_long: float = 0.60
    w_mom_short: float = 0.25
    w_vol_penalty: float = 0.15
    # Portfolio construction (§4.3)
    max_positions: int = 8
    max_position_weight: float = 0.20
    max_sector_weight: float = 0.40
    min_cash_weight: float = 0.05
    risk_off_cash_weight: float = 0.50
    # Frictions (§4.4)
    slippage_bps: float = 10.0
    min_trade_usd: float = 5.0
    rebalance_band: float = 0.02
    benchmark: str = "SPY"


@dataclass(frozen=True)
class ForecastConfig:
    horizon_calendar_days: int = 90
    horizon_sessions: int = round(90 * 252 / 365)  # 62
    lookback_returns: int = 252
    block_sessions: int = 5
    paths: int = 2000
    seed: int = 42


@dataclass(frozen=True)
class BacktestConfig:
    years: int = 3


STRATEGY = StrategyConfig()
FORECAST = ForecastConfig()
BACKTEST = BacktestConfig()

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "data" / "sample"
RUNTIME_DIR = Path(os.environ.get("YAMS_RUNTIME_DIR", ROOT / "data" / "runtime"))
CACHE_DIR = RUNTIME_DIR / "cache"
DB_PATH = RUNTIME_DIR / "yams.db"
STALE_AFTER_DAYS = 5
