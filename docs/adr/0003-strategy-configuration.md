# ADR-003: Closed strategy configuration and deterministic operators

Status: Accepted for implementation under #14. Date: 2026-10-27. Approved Q02 excludes zero volatility from inverse weighting without a floor. This ADR specifies contracts; #20 implements schemas, #21 fixtures and #32/#33 the engine. No runtime engine is delivered here.

## Closed schema

The object in [API §3](../DOMAIN_AND_API_CONTRACTS.md#3-strategy-configuration-contract) is the complete v1 field inventory. Every shown field is required; every object rejects additional properties. Reject duplicate JSON keys, nulls, arrays in place of objects, boolean-as-integer coercion, numeric strings where numbers are required, nonfinite numbers and executable expressions. Do not silently supply omitted defaults during publication: the UI/template expands the following defaults into a complete config first.

| Object / fields | Type and inclusive bounds / allowed values | Default |
|---|---|---|
| root `schema_version` | Integer, const 1 | 1 |
| root `display_name` | String, trimmed, 1–120 Unicode code points, no control characters | Risk-Adjusted Momentum |
| universe `kind` | Enum `liquid_us_equities` | same |
| universe `min_price_usd`, `min_median_dollar_volume_usd` | Nonnegative decimal strings, at most 2 fractional digits, maximum 999999999999.99 | `5.00`, `1000000.00` |
| universe `min_history_sessions` | Integer 252–2520 | 252 |
| signals `kind` | Enum `risk_adjusted_momentum` | same |
| signals `momentum_long_sessions`, `momentum_short_sessions` | Integer 1–2519; short < long | 126, 63 |
| signals `volatility_sessions` | Integer 2–2519 | 60 |
| signals `trend_sma_sessions` | Integer 1–2520 | 200 |
| signals `require_positive_trend` | Boolean | true |
| signals `z_score_weights.momentum_long`, `.momentum_short` | Finite JSON numbers, 0–1, at most 6 fractional decimal digits | 0.60, 0.25 |
| signals `z_score_weights.volatility_penalty` | Finite JSON number, −1–0, at most 6 fractional decimal digits | −0.15 |
| portfolio `max_positions` | Integer 1–100 | 8 |
| portfolio `weighting` | Enum `inverse_volatility` | same |
| portfolio `max_position_weight`, `max_sector_weight` | Decimal strings, >0 and <=1, at most 6 fractional digits | `0.20`, `0.40` |
| portfolio `min_cash_weight`, `rebalance_band_absolute_weight` | Decimal strings, 0–1, at most 6 fractional digits | `0.05`, `0.02` |
| portfolio `min_trade_usd` | Nonnegative decimal string, at most 2 fractional digits, maximum 999999999999.99 | `5.00` |
| rebalance `frequency` | Enum `monthly` | same |
| execution_policy `id` | Enum `us_eod_next_open_v1` | same |

Decimal strings accept only unsigned base-10 digits with an optional decimal point and digits; no exponent, whitespace, sign, empty fractional part or leading zeros except zero itself. Score-weight JSON numbers may use exponent notation if their exact decimal value meets the bounds/precision. Require long + short + absolute(penalty) = 1 exactly in decimal arithmetic. Require history >= max(long+1, short+1, volatility+1, trend SMA, 20). The bounded history/position ranges are v1 validation limits, not performance promises or tuned investment recommendations. A smaller sector than position cap is valid; residual cash makes low-cap policies feasible. A 100% cash floor is valid and yields no asset allocation. Negative/zero position or sector caps are invalid.

Invalid configuration returns `422 VALIDATION_ERROR` with field paths. Validation is atomic and cannot publish a partial version. Validate syntax independently of data; evaluation separately verifies the pinned universe/data availability and reports exclusions or insufficient coverage. Missing data must not be treated as invalid JSON or silently change the config.

## Immutability and canonical hash

Publishing creates an immutable config/version. Metadata naming follows ADR-008; a config edit creates a new version even if old experiments still reference the old one. Preserve the submitted config for audit, but hash its validated normalized value. A hash identifies config content, not an experiment: snapshot, engine, calendar and seed remain separate immutable run inputs.

Canonicalization v1 is fully specified as follows:

1. Strictly parse JSON, rejecting duplicate keys and invalid Unicode scalar sequences. Parse numeric tokens as exact decimal values before validation; never pass through binary float for hashing.
2. Trim `display_name` using Unicode White_Space characters; retain internal characters and their exact Unicode scalar sequence. No case folding or Unicode normalization of config values. Normalize decimal strings to plain decimal notation by removing trailing fractional zeros and the point when integral (`0.20` becomes `0.2`, `5.00` becomes `5`). Normalize numeric values the same way, with zero serialized as `0`, retaining their JSON number type. Negative zero becomes zero.
3. Recursively sort object keys by Unicode scalar order. Serialize compact JSON with no whitespace outside strings. Strings emit Unicode scalars directly, escaping only quote/backslash and U+0000–U+001F (lowercase `\u00xx`, without short escape aliases). Encode UTF-8 without BOM or final newline. Integers have no exponent or leading zeros. No arrays exist in this schema.
4. SHA-256 over those exact bytes, lowercase hexadecimal. Include every config field, including `schema_version` and normalized `display_name`; exclude transport IDs, timestamps and database version number. Changing any semantic config value changes the canonical bytes. Key order, insignificant numeric zeros and outer display-name whitespace do not.

Publish a canonical-byte/hash golden vector in #21 and reproduce it through schema and generated-client tests in #20. Do not use an unspecified language-default JSON serializer as the contract.

## Session windows and scoring

Index the pinned exchange calendar, not the rows returned by a provider. At completed session T, require a contiguous window of `min_history_sessions` scheduled sessions ending at T with valid adjusted close and volume, available by the cutoff. Holidays are absent from the schedule; a missing scheduled bar fails `MISSING_HISTORY`, even if older rows could bring the row count to 252. Do not shorten a lookback or fill missing bars. ADR-002 governs source chronology and raw-price support.

For defaults, M126 needs prices at T and T−126 (127 indexed closes); M63 uses T−63. VOL60 uses the 60 log returns from T−59 through T, requiring closes T−60 through T; sample variance divides by 59, then annualize with sqrt(252). SMA200 is the arithmetic mean of closes T−199 through T. The trend gate is strict `close[T] > SMA200`. Median dollar volume uses 20 raw-close × raw-volume products T−19 through T with a coherent raw share basis; for an even count take the mean of the two middle products. Raw price and liquidity comparisons include equality at their thresholds.

Apply eligibility and finite-input checks first, then compute population z-scores over the eligible candidates in stable asset_id order. Zero feature dispersion yields z=0, including a one-asset cross section. Score is the configured weighted sum. Sort descending score, then ascending immutable asset_id (lexicographic canonical string); preserve full numerical values, not rounded display scores. Invalid/nonfinite intermediate results exclude that asset with `NONFINITE_FEATURE` before final cross-sectional scoring; recompute the valid cross section. Record inputs, exclusions and contributions.

Zero VOL60 is a distinct condition: keep its diagnostic score if otherwise eligible, but remove it from inverse-volatility selection with `ZERO_VOLATILITY` **before** selecting up to max_positions. Do not consume a top-N slot, divide by zero, invent epsilon or erase the diagnostic reason. Positive volatility, however small, is not zero; use numerically stable normalized inverse weights and reject nonfinite calculation results visibly. Reordering input rows must not change the cross section, ranks or selected IDs.

## Deterministic capped allocation

Select the top N allocation-eligible candidates. Set weights to zero and remaining budget to 1−cash floor. Use inverse volatility as each candidate's positive allocation rate. Repeatedly increase all active weights in proportion to those rates until the earliest of: budget exhausted, a position cap reached, or a sector's total cap reached. Compute the increment as the minimum of budget/sum(active rates), each position's remaining capacity/rate, and each sector's remaining capacity/sum(its active rates). Freeze all simultaneously reached constraints, including every active member of a capped sector, and repeat. Never sequentially privilege the first candidate within a tied constraint. Stable asset_id order governs reductions and summation. `Unknown` is one sector.

Stop when budget is exhausted or no active capacity remains. Cash is exactly the residual 1−sum(asset weights); it can exceed its floor. Empty selection yields all cash. Keep full precision through allocation; order sizing applies ADR-001 rounding. API invariant tolerance is 1e-8 for the full weight sum; this tolerance never licenses a material cap breach or negative cash. Implementations must define and fixture-test their numerical boundary handling, without adding cash by rounding every weight independently.

## Independent FIX-01/02 oracles

- Feature vector [1,2,3]: mean 2, population variance 2/3, z = [−sqrt(1.5),0,sqrt(1.5)], compare within 1e-12. Constant vector [2,2,2] yields all zero. Equal feature vectors across assets yield score 0 and ascending asset_id tie order; shuffling rows preserves it.
- If adjusted closes at T−126 and T are 50 and 60, M126 = 0.2 exactly. Removing T−1 from a required 252-session window produces `MISSING_HISTORY`, even with 252 older observed rows.
- Zero-volatility asset A ranks first diagnostically; positive-volatility B ranks second, max_positions=1. A receives `ZERO_VOLATILITY`; select B and apply caps. No epsilon and no empty slot while B is available. If all candidates have zero volatility, target cash=1.
- Eight assets have equal positive volatility and distinct sectors: default target per asset = 0.95/8 = 0.11875, cash=0.05. If all eight share one sector, per asset = 0.40/8 = 0.05 and cash=0.60. With only two candidates in distinct sectors each reaches 0.20, leaving cash=0.60.
- Nonfinite feature, unknown nested key, unsupported operator, zero position cap, cash floor 1.01 or history shorter than a required window are explicit negative cases. Empty data never produces invented features or holdings.

## Extension rule

Adding operators requires a reviewed contract and independent golden fixtures, explicit tagged-union schemas, generated-client updates and reproducibility/version tests before acceptance. #37 owns later mean-reversion/low-volatility operators. Never accept arbitrary expressions, Python, SQL or JavaScript, including AI-generated code. Incompatible semantics require a new schema/operator version and coordinated migration; do not reinterpret previously published config hashes.
