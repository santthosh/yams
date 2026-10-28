# Momentum engine (#32)

`backend.strategies.momentum.evaluate_snapshot(snapshot, config, cutoff, session_date,
engine_version=..., live=False)` is the shared deterministic entry point. It owns no
network, database writes or account state. Pass a hash-verified `PinnedSnapshot` and
validated `StrategyConfigV1`. The snapshot reader owns both the calendar and bars;
`live=True` additionally enforces original ingestion by cutoff. The lower-level
`evaluate_momentum(view, calendar, config, ...)` expects a validated matching view/calendar.

The result is a frozen `MomentumEvaluation` contract. Serialize with `model_dump_json()`
and validate with `MomentumEvaluation.model_validate_json()` when persisting an evaluation.
It contains snapshot/manifest/config/calendar identity, cutoff/session/source mode and engine
version, repository quality diagnostics, per-candidate window hash, filters, features, cross-sectional z-scores, weighted
contributions, scores/ranks and selection. #34 owns durable evaluation jobs/results/API/UI;
#32 provides the pure evidence contract, not a pretend persisted evaluation endpoint.

Eligibility requires contiguous scheduled completed sessions ending at T (252 by default),
as-of effective alias and sector evidence, USD ordinary-equity support and validated raw
price/share-volume inputs for the 20-session liquidity window. Supported initial venues
match implemented provider identity mappings: XNAS, XNYS, XASE and ARCX. Other venues
are explicitly excluded. `Unknown` is valid sector evidence; missing sector is not inferred.
Price and median-dollar-volume thresholds include equality. Trend is strictly adjusted
close greater than the arithmetic SMA, with no epsilon or display rounding. Unsupported
raw basis or blocked snapshot quality cannot become an eligible investment candidate.

M126/M63 index T−126/T−63. Sample VOL60 needs 61 prices, uses log returns with denominator
59 and annualizes by sqrt(252). Population z-scores use stable asset-ID order; zero dispersion
returns zero. Configured signed weights multiply the three z-scores; the default is
0.60/0.25/−0.15. Descending full score then ascending immutable asset ID determine ranks.
Zero-volatility candidates retain diagnostic ranks but do not consume top-N allocation slots.
#33 owns capped allocation; selected IDs here are not orders, recommendations or holdings.

Prices/liquidity/trend comparisons use Decimal. Statistical outputs are finite floats;
Decimal log returns and scaled statistics avoid common tiny-return/overflow failures.
Unrepresentable numerical results fail visibly; no epsilon floor is invented. Conflicting
same-session observations are quarantined independent of input ordering. Extra future evidence
is excluded; missing scheduled bars cannot be replaced by older rows or fabricated data.

Verification: `pytest backend/tests/strategies` covers authored FIX-01 numerical oracles,
fixture-backed eligibility, exact boundaries, strict trend, empty/missing metadata/history,
cutoff equality, future additions, ties/permutations, duplicate conflicts and zero-volatility
selection. Fixture expected values are synthetic evidence, not provider performance claims.
