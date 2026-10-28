# ADR-011: Simple alternative strategy families and benchmark boundary

Status: Proposed in #37; accepted when this decision PR merges. Implements the
recorded Q07 family choice in #72. Runtime support and canonical config/engine
fixtures belong to #38. No new operator is activated by this document.

## Decision and shared rules

Add two transparent stock baselines alongside unchanged Risk-Adjusted Momentum:
**Mean Reversion v1** ranks distance below a 20-session simple moving average;
**Low Volatility v1** ranks ascending 60-return annualized sample log volatility.
SPY remains **benchmark-only**, not a third publishable strategy family. These are
inspectable hypotheses, not recommendations or claims of outperformance. Defaults
are authored baselines; neither holdout results nor parameter search select them.

All stock families use the same `liquid_us_equities` universe, contiguous scheduled
history, as-of availability, eligibility, allocation, policy and execution code.
Keep ADR-003's ordinary USD equity/venue/alias/sector checks, raw close >=5 USD,
20-session raw-share median dollar volume >=1,000,000 USD, default 252-session
history and default strict positive SMA200 trend filter. `Unknown` is one capped
sector; missing classification evidence is not an inferred `Unknown` observation.
Q17's pinned next opening minus one hour cutoff applies. Never use information
published after that cutoff or a future universe membership.

At the completed session T, use adjusted closes for features only. Positive finite
prices and required as-of observations are mandatory. A scheduled gap, unsupported
raw price/volume basis, missing alias/sector or insufficient history yields the
existing explicit eligibility reason; do not shorten windows, carry prices,
replace missing features with zero or choose a different family. Invalid/nonfinite
intermediates yield `NONFINITE_FEATURE` and are removed before cross-sectional
normalization; recompute the valid cross section.

## Exact operators

Let `P[t]` be as-of adjusted close and `z(x)` ADR-003's population z-score over all
eligible finite candidates, in canonical asset-ID order. Zero dispersion yields
zero, including a singleton. The score is a ranking statistic, not an expected
return or probability. No new fitted coefficients are introduced.

| Family | Feature / score | Default signal fields |
|---|---|---|
| Existing momentum | ADR-003 unchanged:0.60 z(M126)+0.25 z(M63)-0.15 z(VOL60) | Existing complete `signals` object unchanged |
| Mean reversion | `SMA_W(T) = sum(P[T-W+1:T+1])/W`; `distance = 1-P[T]/SMA_W(T)`; `score = z(distance)` | `kind="mean_reversion"`, `mean_reversion_sessions=20`, `volatility_sessions=60`, `trend_sma_sessions=200`, `require_positive_trend=true` |
| Low volatility | `r_j = ln(P[j]/P[j-1])` for the final N returns; `VOL_N = sqrt(sum((r_j-mean(r))^2)/(N-1))*sqrt(252)`; `score = -z(VOL_N)` | `kind="low_volatility"`, `volatility_sessions=60`, `trend_sma_sessions=200`, `require_positive_trend=true` |

SMA20 needs 20 closes including T, not21. VOL60 needs 61 closes and uses denominator 59;
annualization stays 252 even for a pinned calendar with another annual session count.
Mean-reversion distance is positive below SMA20, zero at it and negative above it.
There is no implicit below-SMA20-only gate: rank all otherwise eligible finite
candidates. Its SMA200 trend filter is independent and can exclude a security even
when its short-window distance is attractive. Low-volatility ordering is ascending
VOL60 because of the negative z-score. All score ties break by ascending canonical
`asset_id`; stable input permutation must preserve ranks and targets.

For both new families, compute VOL_N for inverse-volatility allocation. As in Q02,
a zero-volatility candidate may remain in diagnostic ranks but receives
`ZERO_VOLATILITY` and is removed **before** top-N allocation selection. Do not
consume its selection slot or invent a floor. Positive but tiny volatility follows
ADR-003's finite/resolution checks. All-zero allocation candidates mean100% cash.
Empty/failed eligible universes remain explicit cash-only outcomes, not invented
scores or performance. The positive-trend gate can independently exclude a flat
series; zero-volatility probes disable it when isolating that operator.

## Parameters, risk and lifecycle

Both new `signals` variants are closed and require exactly their listed fields.
`mean_reversion_sessions` is a strict integer 2–2520 (default 20);
`volatility_sessions` is a strict integer 2–2519 (default 60);
`trend_sma_sessions` is a strict integer 1–2520 (default 200);
`require_positive_trend` is a strict boolean. Enforce history >= the maximum of
20 liquidity closes, the trend window, volatility window+1 and the mean-reversion
window when present. The existing universe minimum remains 252–2520. No omitted
field is defaulted by publication; templates expand complete defaults first.
Momentum-only fields/weights in either alternative variant, alternative fields in
momentum, unknown kinds/keys, executable expressions and nonfinite values return
422 VALIDATION_ERROR. Existing numeric/string precision rules remain unchanged.

Keep complete existing `universe`, `portfolio`, `rebalance` and `execution_policy`
objects verbatim: default 8 positions, inverse volatility,20% position/40% sector
caps,5% cash floor,5 USD minimum trade,2 percentage-point rebalance band, monthly
rebalance and `us_eod_next_open_v1`. Use simultaneous capped allocation and leave
unallocatable residual in cash. No new stop-loss, sell threshold, daily rebalance,
leverage or shorting rule is implied. On scheduled rebalance the shared planner
compares new targets with current holdings and applies existing band/minimum/risk
rules; preview does not post holdings. All stock families use the same execution,
action, fee/slippage, rounding, cancellation and cash policies in ADR-001/004.

## Version/schema compatibility and ownership

#38 extends `StrategyConfigV1.signals` with a closed discriminated union keyed by
`kind`. Preserve schema_version 1, the complete existing momentum variant and its
canonical bytes/hash, all published version IDs and immutable reference semantics.
ADR-003 already reserves additional kinds behind reviewed contracts and fixtures;
this is an additive supported-kind extension, not reinterpretation of old configs.
Old binaries must reject unfamiliar kinds rather than silently execute momentum.
Downgrade after publishing alternative versions is unsupported without restoring a
compatible backup. Coordinate engine, API, generated client, docs, tests and seeds.

#38 owns validated models, family dispatch/feature and score evidence, generated
contracts/client, immutable seeds and independent runtime fixtures; #73 owns the
Lab authoring UI. The existing evaluation/worker path must dispatch from the pinned
validated kind and retain complete config/hash/build/snapshot/calendar lineage.
Family-specific feature/score evidence must be closed and inspectable; no momentum
feature placeholders for an alternative family. Keep old stored momentum evidence
readable. Validate the kind before runtime dispatch; unsupported inputs cannot
enter a published version or fall back to another strategy.

Use `mean_reversion_v1` and `low_volatility_v1` as immutable template keys, with
preferred metadata names `Mean Reversion` and `Low Volatility`. Derive root UUIDv5 IDs by the existing
URL namespace convention: `https://yams.local/strategies/mean-reversion` and
`https://yams.local/strategies/low-volatility`; version 1 is UUIDv5(root,"1"). Expand
the default signal objects above plus the unchanged shared defaults. Display names
are `Mean Reversion` and `Low Volatility`; canonical hashes include them. Bootstrap
must atomically validate/reuse stable seeds and reject conflicting identities; it
must not overwrite user versions. For a new seed whose preferred metadata name is
already taken, preserve the user's strategy and select the first available
`<preferred name> (template N)` with positive integer N, under the existing
serialized bootstrap transaction and casefold uniqueness guard. Persist that name;
later bootstrap reuses it rather than renaming. Config display_name and its
canonical hash stay fixed, since metadata is separate. Test this upgrade collision
without resetting data. New template publication is not implemented here.

Independent [worked fixtures](../verification/37-templates/README.md) define feature,
ranking, allocation, ties, missing/zero and benchmark probes. #38 extends FIX-01/02
and the canonical fixture generator/manifest with full252+-session as-of inputs,
independently authored config bytes/hash vectors for both new defaults, input
permutation and mutation controls. Do not derive expected values by calling the
implementation under test. Retain every existing fixture identity/byte unless a
separately explained fixture version is required. #40 consumes the benchmark
boundary and FIX-07; #75 exposes aligned comparison, not a passive strategy card
that can be deployed.

## Passive SPY boundary

SPY is an ETF reference outside the ordinary-equity candidate universe. It has no
`signals.kind`, published stock template or allocation override. The existing
blueprint §7 requires the same initial capital/start dates and aligned benchmark
samples, using a disclosed adjusted-price total-return approximation. Never add
cash dividends again to that adjusted series. Raw execution/explicit action
accounting remains a distinct supported-data path under ADR-002/010.

A passive reference may have 100% SPY exposure and a different cash/friction policy
from an 8-stock capped portfolio; display those differences rather than pretend
both share constraints. #40 must document its exact friction/cash treatment and
retain start/end alignment and missing-price failure evidence. A short gross
price-ratio fixture is not a fee-inclusive backtest or proof of raw action coverage.
Missing benchmark observations produce explicit insufficient-data/unavailable
results; do not align surviving rows or substitute another asset. `SYN:SPY` fixtures
are synthetic demonstrations, not historical SPY. Product/UX descriptions must show
Momentum, Mean Reversion, Low Volatility, and a separately labeled benchmark.

## Verification and limits

This decision delivers contracts and hand-derived examples only. Review signs,
window endpoints, parameter bounds, complete fields, numerical tolerances, old
momentum/hash compatibility and ownership against ADR-001/003 and Q07/Q17.
No runtime schema, seed, strategy return, optimization or benchmark accounting is
claimed. #38 cannot be agent-ready until this reviewed contract and #36 publication
are delivered. Source limits, survivorship and action coverage remain visible for
every family; changing a scoring rule cannot repair absent historical evidence.
