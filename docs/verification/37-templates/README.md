# Independent worked template fixtures (#37)

**SYNTHETIC_DATA_ONLY.** These are hand-derived operator/ranking/allocation probes
for [ADR-011](../../adr/0011-strategy-templates.md), not full market histories,
performance results or passing runtime tests. #38 must add full as-of history and
canonical config fixtures to FIX-01/02 before activating the operators. #40 retains
benchmark/metric ownership. No holdout data or fitted defaults were used.

## Mean reversion, including the endpoint

Each row supplies exactly 20 adjusted closes ending at T. Notation `18×100` means
eighteen observations equal to 100. The values are positive decimal prices.

| Asset | Close sequence | Sum / SMA20 | T close | `1-P[T]/SMA20` | Population z / score |
|---|---|---|---|---|---|
| SYN:A |18×100,110,90|2000 /100|90|0.1|`+sqrt(3/2)` =1.224744871391589 |
| SYN:B |18×100,100,100|2000 /100|100|0|0 |
| SYN:C |18×100,90,110|2000 /100|110|-0.1|`-sqrt(3/2)` =-1.224744871391589 |

Cross-sectional mean distance is 0 and population variance is
`(0.1²+0+(-0.1)²)/3 = 1/150`; divide by its positive square root.
Ranks A,B,C follow descending score. These short probes omit 252-session eligibility,
SMA200 and VOL60 and must not be presented as end-to-end eligible snapshots.

For a separate allocation probe, assume all three passed eligibility and have
independently supplied positive volatilities 0.1,0.2,0.3 and different sectors.
Set `max_positions=2` only for the probe; keep position cap0.20, sector cap0.40,
cash floor0.05 and inverse-volatility weighting. Select A,B. Rates are 10 and 5;
A first reaches0.20 while B reaches0.10. Freeze A and increase B to 0.20; no
uncapped assets remain, so cash is 0.60. These supplied volatility inputs are not
claimed to be the volatility of the 20-close sequences above.

Negative controls: excluding T or using 21 closes must fail the SMA/distance oracle;
using `P/SMA-1` reverses the sign; a missing scheduled close produces MISSING_HISTORY
rather than a 19-close average. A nonfinite intermediate is excluded before z-score
normalization. Equal finite distances yield zero scores and ascending IDs. All
finite negative distances are still rankable; there is no unapproved sign filter.

## Low volatility and sample denominator

For 61 prices alternating 100,101,100,101,...,100, the 60 returns alternate
`+ln(101/100), -ln(101/100)`. Their mean is 0, sum of squared deviations is
`60*ln(101/100)²`, and annualized sample volatility is exactly
`ln(101/100)*sqrt(60*252/59)`. This expression is the independent expected value;
compare a float64 implementation to a high-precision evaluation within absolute
1e-12. Using60 instead of59 in the denominator is a failing mutation. No annual
price return is inferred from this deliberately oscillating operator probe.

For an independent ranking probe with already supplied volatilities A=0.1,
B=0.2,C=0.3, population mean is0.2 and variance 1/150. Thus z-scores are
`[-sqrt(3/2),0,+sqrt(3/2)]`; scores negate these and rank A,B,C. With the same
explicit top 2 allocation probe above, A=0.20,B=0.20,cash=0.60.

Tie/zero controls:

- A=0.1,C=0.1,B=0.2 rank A,C,B; top 1 chooses A regardless of input row order.
- Add SYN:ZERO with VOL=0. It may rank highest diagnostically but must receive
  ZERO_VOLATILITY and be removed before top-N allocation; it never takes a slot.
- All VOL=0 gives zero cross-sectional scores and100% allocation cash; no epsilon.
- Equal **positive** volatilities give zero scores and deterministic selection,
  and remain allocatable. Zero dispersion is not zero volatility.
- Isolate zero-volatility checks with `require_positive_trend=false`; an enabled
  strict SMA trend gate otherwise correctly rejects a flat price series earlier.
- Missing one of the61 scheduled closes cannot be replaced with an older close;
  future-only price/membership/sector changes after cutoff cannot change output.

## Passive reference and alignment

With adjusted benchmark closes 100 then 110, the gross, zero-friction **price-ratio
probe** has return 110/100-1=0.10;1000 USD becomes1100 USD before any separately
declared friction. It is not a posted fill ledger or a fee-inclusive backtest.
FIX-07 independently supplies aligned flat benchmark NAV[100,100,100,100], so its
gross cumulative return is 0 while the authored strategy probe NAV[100,120,90,108]
returns 0.08 with max drawdown 0.25. These are arithmetic examples, not strategies'
realized returns. #40 must add its actual declared fee/cash-policy expectations.

Same dates, capital, source assumptions and supported observations are mandatory.
Deleting a benchmark session produces insufficient data, not a shorter aligned
series. Never apply stock eligibility to manufacture a SPY candidate or add
separate dividend cash to an adjusted total-return approximation. Label synthetic
benchmark inputs and disclose full-exposure vs capped-stock/cash differences.

## Handoff checks

Keep scalar statistics within absolute 1e-12 and complete weight sums within 1e-8;
expected caps/cash above are exact decimal fractions. IDs, config bytes/hashes and
cutoff/session lineage compare exactly. Existing FIX-01 canonical momentum hash
`2093c63d190815eba052508d6d42d8ae0c93400cf777602d2c5f759627f43f21` stays unchanged.
#38 independently authors and commits new default canonical bytes/hash vectors;
it must not regenerate an expected hash from its own canonicalizer. Publication
roundtrips, unsupported-kind/field rejection, real PostgreSQL restart and shared
worker dispatch are implementation proofs, not results delivered by this decision.
