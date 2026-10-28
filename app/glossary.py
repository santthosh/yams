"""Plain-English definitions shown as tooltips next to every metric (one place, so wording stays consistent)."""

from markupsafe import Markup, escape

GLOSSARY = {
    # portfolio
    "total_value": "Your cash plus the current value of every stock you hold.",
    "today": "Change since the last market close, using live prices.",
    "since_start": "Gain or loss compared with the paper cash you started with.",
    "invested": "Money currently in stocks, at today's prices.",
    "cash": "Uninvested paper money. It earns nothing; the strategy always keeps at least 5% as a buffer.",
    "spy_since_start": "How much SPY, a fund that tracks the S&P 500, has moved since you started. "
                       "It is the yardstick: could you have done just as well by buying the index?",
    "vs_spy": "Your return minus SPY's return since you started, in percentage points. Positive means you are "
              "ahead of the index.",
    "data_as_of": "Decisions use daily closing prices. A new close is available after about 4:15 PM New York time; "
                  "click Refresh data to download it.",
    "price": "Latest price per share (live while the market is open, otherwise the last close).",
    "weight": "This position's share of the whole portfolio. No single stock may exceed 20%.",
    # signals
    "target": "The share of the portfolio this stock should have after the trades.",
    "m126": "Return over the last 6 months (126 trading days). The main momentum signal: stocks that rose strongly "
            "have tended to keep rising for a while.",
    "m63": "Return over the last 3 months (63 trading days). A shorter-term momentum check.",
    "volatility": "How much the price swings, as a yearly figure based on the last 60 days. 30% means a typical "
                  "year's move is about ±30%. Higher means riskier; riskier picks get smaller weights.",
    "rank": "Position among all stocks that passed the filters, by score. The score blends 6- and 3-month momentum "
            "and subtracts a little for volatility, each compared with the other stocks. #1 is best.",
    "action": "BUY opens a new position, INCREASE adds to one, REDUCE trims one, SELL exits completely, and HOLD "
              "leaves it alone because it is within 2 points of its target.",
    "now": "This stock's share of the portfolio today.",
    "trades": "Number of buys and sells this recommendation would make. Positions already close to target are left alone.",
    "est_cost": "Simulated trading cost: every trade is priced 0.10% worse than the market (slippage), "
                "to mimic real-world costs.",
    "regime": "If SPY is below its 200-day average price, the market is in a downtrend and the strategy keeps at "
              "least half the portfolio in cash.",
    # forecast
    "median_90": "The middle outcome of 2,000 simulated 90-day futures: half end higher, half end lower. "
                 "A scenario, not a prediction.",
    "p10": "Bad case: 1 in 10 simulated futures end below this.",
    "p90": "Good case: 1 in 10 simulated futures end above this.",
    "prob_loss": "Share of simulated futures that end below today's value.",
    "fan": "Each shaded band shows where the simulated futures fall on each day. The wide, light band holds 8 in 10 "
           "of them (P10 to P90); the darker band holds the middle half. Wider means less certain.",
    "median_ending": "Portfolio value in the middle (median) simulated future after 90 days.",
    # backtest
    "ending_value": "What the starting cash would have grown (or shrunk) to by the end of the test.",
    "total_return": "Overall gain or loss over the whole test period.",
    "cagr": "Annualized return: the steady yearly growth rate that would produce the same overall result.",
    "ann_vol": "How much the portfolio's value swung, as a yearly figure. Higher means a bumpier ride.",
    "sharpe": "Return per unit of risk: average return divided by volatility, per year. Higher is better; "
              "above 1 is generally good. Compare it with SPY's.",
    "drawdown": "How far the portfolio fell from its previous high before recovering. A worst drawdown of −33% means "
                "that at one point it was worth a third less than at its peak.",
    "bt_trades": "Number of simulated buys and sells over the whole test.",
    "bt_costs": "Total slippage paid on those trades (0.10% of each trade's value).",
    "turnover": "Average share of the portfolio bought and sold at each monthly rebalance. More turnover means more "
                "trading costs.",
    "rebalance": "Once a month the rules are re-run and the portfolio is traded back toward the new targets.",
    "survivorship": "The test uses today's S&P 500 list, which leaves out companies that dropped out of the index "
                    "(often after falling). That makes past results look better than they really were.",
}


def tip(key: str, align: str = "center") -> Markup:
    """A focusable ⓘ that shows the definition on hover, focus or tap."""
    text = escape(GLOSSARY[key])
    return Markup(f'<span class="tip tip-{align}" tabindex="0" role="note" aria-label="{text}" data-tip="{text}">?</span>')
