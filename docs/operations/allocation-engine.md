# Shared target allocation and risk evidence

Issue #33 implements ADR-003 in `backend/portfolio/allocation.py` and `risk.py`.
This is a pure shared engine for the future diagnostics API, backtester,
portfolio and Arena. It creates targets, never orders, holdings or cash events.

Call `allocate(candidates, config.portfolio)` with validated `AllocationCandidate`
values (immutable asset ID, nonempty sector, finite score and nonnegative finite
volatility). Duplicate IDs and invalid policies fail explicitly. `Unknown` is one
capped sector; absent sector evidence must be excluded upstream, not renamed.
Ineligible and exactly-zero-volatility candidates are excluded before top-N
selection. Rank descending score, then ascending immutable asset ID. Positive
volatility has no epsilon or floor.

For a pinned momentum evaluation, use
`allocate_momentum(evaluation, strategy_config)`. It checks the config hash and
selected IDs, and returns `AllocatedMomentum` retaining the complete momentum
evidence (source mode, snapshot/config/calendar hashes, cutoff, session, engine
version, rejected candidates and quality diagnostics) alongside the allocation.
An evaluation with incompatible configuration cannot be silently reallocated.
The owning #34 API must retain this evidence when persisting its result.

## Numerical boundaries

Water-fill uses exact rational arithmetic. The finite input volatility's shortest
round-trip decimal representation defines its rate; rates are normalized by the
minimum positive volatility, avoiding overflowing reciprocals. Each step stops at
the earliest exact budget, position or sector boundary. All simultaneously binding
constraints freeze together, with every member of a capped sector frozen. Stable
asset-ID order determines reductions. No floating-point tolerance relaxes a cap.

Only the final transport converts rational per-asset targets to finite decimal
strings. A joint largest-remainder apportionment uses a grid of at least 36
decimal places, expanding until the smallest positive target has at least 36
significant digits. Ties use asset ID; every increment must fit the exact position
and sector limits. The aggregate invested weight is preserved exactly: binding
budgets/caps have at most six decimal places. Cash is its exact residual, with no
per-asset rounding residue added to cash. Each individual error is below one grid
unit (at most `1e-36`), independent of the process Decimal context. This numerical
serialization is separate from ADR-001's order/share/currency rounding in #35.

## Observable examples and diagnostics

All examples below are authored **SYNTHETIC_DATA_ONLY** test cases.

| Candidates under default policy | Asset weights | Cash |
| --- | --- | --- |
| None / all zero volatility | None | 1 |
| One positive-volatility asset | .20 | .80 |
| Eight equal-volatility, distinct sectors | .11875 each | .05 |
| Eight equal-volatility, one sector | .05 each | .60 |
| Five equal-volatility, `Unknown` sector | .08 each | .60 |

`selected_ids` retains rank order; `targets` and exclusions use stable asset-ID
order. A full cash floor may select candidates diagnostically but emits no asset
targets. Reasons distinguish empty eligibility, full-cash policy and unallocatable
capacity. Exclusions identify ineligibility, zero volatility and rank-limit removal.

`RiskReport` records compliance/violations, invested/cash weights, unmet investable
capacity, maximum position/sector concentration, configured limits, capped assets
and sector totals. `assess_targets` independently checks externally supplied
targets and reports breaches without repairing them. Over-one-capital asset totals
or invalid scalars fail rather than constructing an invalid bounded report.
This is a target constraint report, not an estimated loss or predictive risk model.

## Verification and boundaries

`uv run --locked pytest backend/tests/portfolio -q` covers the committed FIX-01
allocation vectors; manually solved unequal-rate redistribution and simultaneous
caps; repeating-decimal conservation; empty, sparse, full-cash, zero and extreme
positive-volatility cases; risk breaches; and 120 deterministic arbitrary-policy
cases with shuffled inputs. FIX-03 is checked only for the allocation/size boundary:
allocation produces weights, while #35 owns executable prices, affordability,
minimum trades and six-decimal share sizing. The pinned-snapshot momentum handoff
retains reproducibility and rejection evidence. No API, migration, portfolio
mutation or UI is added by #33.
