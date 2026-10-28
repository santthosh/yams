"""As-of candidate eligibility; no network, database writes or price repairs."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from backend.domain.market import MarketBarV1
from backend.domain.strategy import StrategyConfigV1
from backend.market_data.models import Calendar
from backend.market_data.repository import MarketView
from backend.strategies.features import prices

SUPPORTED_US_VENUES = frozenset({"XNAS", "XNYS", "XASE", "ARCX"})


@dataclass(frozen=True)
class Eligibility:
    asset_id: str
    sector: str | None
    reasons: tuple[str, ...]
    window: tuple[MarketBarV1, ...]
    raw_close: str | None
    median_dollar_volume: str | None
    trend_sma: str | None

    @property
    def eligible(self) -> bool:
        return not self.reasons


def eligible_universe(
    view: MarketView, calendar: Calendar, config: StrategyConfigV1
) -> tuple[Eligibility, ...]:
    scheduled = [
        session.session_date
        for session in calendar.sessions
        if session.session_date <= view.session_date and session.close_at <= view.cutoff
    ]
    if not scheduled or scheduled[-1] != view.session_date:
        raise ValueError("Evaluation requires a completed pinned calendar session")
    required = config.universe.min_history_sessions
    expected = scheduled[-required:]
    expected_set = set(expected)
    indexed: dict[str, list[MarketBarV1]] = defaultdict(list)
    for bar in view.bars:
        if bar.session_date in expected_set and bar.available_at <= view.cutoff:
            indexed[bar.asset_id].append(bar)
    results = []
    for asset in sorted(view.assets, key=lambda item: item.asset_id):
        reasons = list(asset.reasons)
        if any(item.reason == "SNAPSHOT_BLOCKED" for item in view.diagnostics):
            reasons.append("SNAPSHOT_BLOCKED")
        if asset.instrument != "ordinary_equity" or asset.currency != "USD":
            reasons.append("UNSUPPORTED_INSTRUMENT")
        if (
            asset.alias is None
            or asset.alias.available_at > view.cutoff
            or not asset.alias.covers(view.session_date)
        ):
            reasons.append("MISSING_ASSET_ALIAS")
        elif asset.alias.venue not in SUPPORTED_US_VENUES:
            reasons.append("UNSUPPORTED_VENUE")
        sector = asset.sector
        if (
            sector is None
            or sector.available_at > view.cutoff
            or not sector.covers(view.session_date)
        ):
            reasons.append("MISSING_SECTOR")
            sector = None
        observed: dict[date, MarketBarV1] = {}
        conflicts: set[date] = set()
        for bar in indexed[asset.asset_id]:
            if bar.session_date in conflicts:
                continue
            previous = observed.get(bar.session_date)
            if previous is not None and previous != bar:
                reasons.append("CONFLICTING_BAR")
                conflicts.add(bar.session_date)
                del observed[bar.session_date]
                continue
            observed[bar.session_date] = bar
        window = tuple(observed[day] for day in expected if day in observed)
        raw_close = median_volume = trend_sma = None
        if len(expected) != required or len(window) != required:
            reasons.append("MISSING_HISTORY")
        else:
            try:
                adjusted = prices([bar.adjusted_close for bar in window])
                raw_close = window[-1].close
                raw_window = window[-20:]
                if any(
                    bar.price_basis != "raw_as_traded" or bar.volume_basis != "raw_shares_v1"
                    for bar in raw_window
                ):
                    reasons.append("UNVERIFIED_PRICE_VOLUME_BASIS")
                with localcontext() as context:
                    context.prec = max(len(bar.close) + len(str(bar.volume)) for bar in window) + 28
                    products = sorted(Decimal(bar.close) * bar.volume for bar in raw_window)
                    median = (products[9] + products[10]) / 2
                    median_volume = format(median, "f")
                    if Decimal(raw_close) < Decimal(config.universe.min_price_usd):
                        reasons.append("PRICE_BELOW_MINIMUM")
                    if median < Decimal(config.universe.min_median_dollar_volume_usd):
                        reasons.append("LIQUIDITY_BELOW_MINIMUM")
                    context.prec = max(len(bar.adjusted_close) for bar in window) + 28
                    period = config.signals.trend_sma_sessions
                    average = sum(adjusted[-period:], Decimal(0)) / period
                    trend_sma = format(average, "f")
                    if config.signals.require_positive_trend and adjusted[-1] <= average:
                        reasons.append("NONPOSITIVE_TREND")
            except (ValueError, ArithmeticError):
                reasons.append("NONFINITE_FEATURE")
        results.append(
            Eligibility(
                asset.asset_id,
                sector.sector if sector else None,
                tuple(sorted(set(reasons))),
                window,
                raw_close,
                median_volume,
                trend_sma,
            )
        )
    return tuple(results)
