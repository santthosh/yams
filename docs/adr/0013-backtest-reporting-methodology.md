# ADR-013: Backtest reporting and benchmark methodology

Status: Proposed in #40; accepted when its reviewed methodology PR merges.
Implements approved Q12 in #72 and reuses ADR-012's frozen walk-forward boundaries.
#40 runtime implementation waits for complete #39 delivery and this reviewed table.
FR-08/FR-09/FR-11, milestone0.0.3. #68 must reuse these reporting conventions.

## Observations and units

Report total, development and holdout separately. The total curve has N ordered
pinned-session closes and n=N-1 adjacent simple net NAV returns:
`r[t] = NAV[t] / NAV[t-1] - 1`. Do not count warmup, holidays or a fictitious
pre-start return. NAV already includes posted synthetic costs and payable-date
cash dividends; never subtract costs or add dividends a second time. Cash earns
zero under Q03. Values, costs and trade notional remain Decimal/Fraction money;
only dimensionless reported statistics are finite JSON numbers.

Development owns its existing closing points/returns. Holdout continues the same
cash/positions and uses the preceding development close as its return baseline,
so its first return is included. That preceding point is not another holdout daily
NAV observation for turnover or exposure averages. No reset, new capital,
liquidation or parameter search occurs at the split. Preserve the repeated-human-
selection caveat; a short holdout is not validated independent performance.

## Approved methodology table

Let `mean(r)` be the arithmetic mean, and sample variance be
`sum((r[t]-mean(r))^2)/(n-1)`. Drawdown is measured against the running peak,
including the period's baseline. Fractions, not percentages, are stored.

| Output | Exact convention | Unavailable cases |
|---|---|---|
| Cumulative return | `last_NAV / baseline_NAV - 1` | No return observation; nonpositive baseline |
| Annualized return | `(last_NAV / baseline_NAV)^(252/n) - 1`, geometric | No return observation; nonpositive baseline; unrepresentable finite transport result |
| Annualized volatility | Sample standard deviation of simple daily net NAV returns × `sqrt(252)` | Fewer than2 returns; zero return denominator |
| Sharpe ratio | `mean(r) / sample_std(r) × sqrt(252)`, daily risk-free rate0 | Fewer than2 returns; zero sample variance; zero return denominator |
| Maximum drawdown | `max(1 - NAV[t]/running_peak[t])`, nonnegative fraction | No return observation or nonpositive baseline |
| Period turnover | Sum of executed BUY **and** SELL gross notionals / arithmetic mean of the period's daily closing NAVs | Empty period or zero mean NAV |
| Fees/slippage | Sum the corresponding shared fill effects once; cents | Known even when a statistical ratio is unavailable |
| Trade count | Count filled/partially-filled execution effects; exclude skipped/pending intent | Known even for a zero-trade period |
| Cash exposure | Posted cash / coherent daily NAV | Zero NAV or unavailable marks |
| Position concentration | Largest coherent raw-close position value / daily NAV;0 for positive-NAV all-cash | Zero NAV or unavailable marks |

Turnover uses executed gross before commission (the kernel's actual adverse-price
notional), counts both sides, and is neither divided by2 nor annualized. Include
all and only daily closing observations owned by that period in its denominator.
Fees/slippage are attribution; the NAV return is already net of them. Daily
exposure/concentration uses the shared exact close valuation, never frontend or
basis-price valuation. Allocation and strategy decision logic is not rerun.

Use explicit `MetricValue(value=null, unavailable_reason=...)` for undefined
ratios, never NaN/Infinity or a fabricated0. Define reasons such as
`INSUFFICIENT_RETURN_HISTORY`, `ZERO_START_NAV`, `ZERO_RETURN_DENOMINATOR`,
`ZERO_VARIANCE`, `ZERO_MEAN_NAV`, `NO_OBSERVATIONS`, `NUMERICAL_RANGE` and
`INSUFFICIENT_MARKET_DATA`. Known zero volatility from at least2 flat returns is
valid; zero Sharpe with undefined variance is not. A one-point baseline cannot
establish performance/drawdown, although its cash/exposure and zero trade costs
remain known. Short histories keep explicit warnings even when a ratio is defined.

## SPY and cash baselines

SPY is a benchmark reference only under Q07, not a publishable/deployable strategy.
Use the requested pinned SPY identity, same calendar sessions, initial capital and
start close. For adjusted closes P, the benchmark's fully invested buy-and-hold
approximation is `initial_capital × P[t]/P[first]`, cent-rounded for reported NAV.
It has no cash reserve, commissions or slippage and approximates reinvested total
return; disclose those differences from the shared raw-execution portfolio,
including payable-date dividend cash recognition. Never add separate dividend
cash to an adjusted-return benchmark. The explicit cash baseline retains initial
capital on every exact matching session with zero yield.

Read benchmark evidence at each session's pinned Q17 cutoff from the verified
accounting view; it does not have to qualify as a stock candidate. No future bar,
unknown price, forward-fill or common-row dropping is permitted. Any missing or
unusable required benchmark session makes benchmark statistics/comparisons
unavailable with `INSUFFICIENT_MARKET_DATA`; retain the original requested dates
and visible gaps. Portfolio statistics and the labeled cash baseline may remain
inspectable. Never imply that a shortened benchmark is aligned.

Existing Tiingo observations remain diagnostic-only under ADR-010/012. No source
capability, historical publication, membership, payable date or real performance
claim is inferred from a successful synthetic replay.

## Comparability and ownership

A comparison must expose incompatible dates/session sequence, capital, snapshot/
universe assumptions, source mode, execution costs/policy, calendar/engine/core
policy, benchmark or split. Pin explicit comparison terms; matching strategy IDs
are not required, and different strategy parameters are the experiment. A metric
ranking over incompatible terms must not claim a fair winner. A user may inspect
incompatible reports with visible reasons; #43 owns comparison/challenge UX.

#40 supplies composable metrics/benchmark/exposure outputs over a sealed #39 core
and its immutable config. #41 owns persisted final reports, paginated series/
trades and generated public API types; #74 owns report UI. An internal core or a
methodology document is not a completed public experiment. No endpoint, extra
provider read or current cloud service is required by this decision.

## Independent FIX-07 example

The existing authored [FIX-07](../../data/fixtures/fix-07/case.json) is normative:
NAV `[100,120,90,108]` has3 returns `[.2,-.25,.2]`, cumulative return.08 and max
drawdown.25. Mean return.05, sample variance.0675 and sample volatility ×sqrt252
are4.124318125460256. Sharpe is3.0550504633038935. Geometric annualization is
`1.08^84-1 = 641.0893416360514` (an illustrative short-history annualization,
not a plausible forecast). Mean daily NAV is104.50; gross notionals40+60 imply
turnover100/104.5=200/209≈.9569377990430622. The flat aligned benchmark returns0.

Expected values were authored independently, not generated by production metrics.
Verify empty/one-point/flat/zero-denominator, missing benchmark, costs counted once,
phase carry and incompatible terms in addition to the positive example. Statistical
checks use the fixture's1e-12 absolute tolerance for simple ratios; cents/shares
stay exact. No synthetic example is evidence of actual investment performance.
