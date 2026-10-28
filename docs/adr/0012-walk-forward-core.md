# ADR-012: Deterministic walk-forward event boundaries

- Status: Proposed in the #39 core PR; accepted when that reviewed PR merges.
- Scope: FR-08/FR-09, milestone0.0.3, policy `walk_forward_v1`.
- Owners: #39 core/persistence, #40 report metrics/benchmark, #41 public transport.

## Context

Blueprint §7 and ADR-001 require monthly shared-kernel decisions, next-open
execution, half-open requested dates and an untouched chronological holdout. They
leave the initial investment anchor, partial months, split rounding and missing
price publication behavior unspecified. These details must be explicit before
persisted experiments depend on them. This ADR supplies engineering conventions;
it does not change Q01 immediate proceeds, Q12 reporting formulas or Q17 timing.

## Decision

1. Select only sessions in the pinned calendar within `[start_session,
   end_session_exclusive)`. A date boundary may be a non-session date within the covered date envelope. Reject an
   empty selection, uncovered price interval or missing next-calendar lookahead;
   never construct weekdays or silently shorten a requested covered interval.
2. Begin with the requested capital entirely in cash at the first selected close.
   This first point is the performance baseline and incurs no fictitious earlier
   trade. Make the initial decision at that session's Q17 cutoff. Subsequent
   decisions use true calendar month ends: the next pinned session has a different
   year/month. A truncated final month does not become a month end. A decision is
   omitted when its next eligible open lies outside the evaluation interval.
3. Approval equals the next pinned opening minus one hour. The shared planner sees
   only evidence available at that cutoff, including any preceding warmup. Its
   preview does not change state. Execute the ordered sells then buys through the
   existing kernel at the originally eligible open, strictly after approval.
   Every session's close is valued at that session's Q17 observation cutoff.
   Execution session, evidence availability and proposed replay time remain
   separate; an EOD bar arriving after its own open is not a same-close fill.
4. Strict gap policy: an eligible opening must be validated by that opening
   session's overnight cutoff. Missing/conflicting/unusable opening evidence,
   missing held-asset closes or an unplannable required target close fail the core.
   Keep failure diagnostics; publish no complete series. No stale-price carry,
   different-day fill, zero placeholder or retroactive revision of an earlier
   reported NAV. This deliberately narrower replay policy does not remove
   ADR-001's ability for ongoing paper orders to remain pending longer.
5. Shares, basis and cash come exclusively from shared execution/action effects.
   Coherent raw-close valuation is shared with the planner. Cash earns zero.
   Dividends are credited only on evidenced payable sessions; uncredited
   entitlements remain inspectable, not added to cash/NAV as invented receivables.
   Adjusted prices are feature/benchmark inputs, never raw ledger marks.
6. Apply visible actions before affected session trading, retaining ex-date
   entitlements through later sales. Unknown payable dates for nonzero
   entitlements, late evidence requiring chronological replay, unrepresentable
   splits, ambiguous multiple same-session actions on a held instrument, or a
   split crossing a pre-action approved order fail safely. Do not infer adjusted
   intent quantities, cash-in-lieu or action ordering. Zero-share unknown-payable
   entitlements create no distribution; warn visibly. Pre-start ex-events cannot
   confer entitlement on an initially all-cash experiment.
7. The strategy view retains point-in-time membership eligibility. A distinct
   accounting view retains validated raw prices/actions for already held assets
   that leave that universe. Universe exit cannot erase a holding or its evidence,
   and accounting visibility cannot add an eligible candidate.
8. With N closing points and requested fraction q, holdout size is
   `min(N-1, ceil(N*q))`; development has the remaining points. The first holdout
   point is explicitly recorded. Continue the same holdings/cash across the split;
   no fresh capital, forced liquidation, second initial investment or optimization.
   The first holdout return uses the immediately preceding development close.
   A one-point experiment has no holdout or return observations. #40 owns the
   approved Q12 metric formulas and explicit unavailable outcomes.
9. Warn `LIMITED_WARMUP` when fewer than configured minimum-history sessions
   precede the first point, `INSUFFICIENT_HOLDOUT` below252 holdout points, plus a
   repeated-selection caveat. Synthetic runs say `SYNTHETIC_DATA_ONLY`. Do not
   present short histories as independent validation.
10. Reject blocked/unverified raw accounting sources. Real-source replay requires
    hash-pinned explicit raw execution, complete actions, historical publication
    and historical membership capabilities; diagnostic support is insufficient.
    Existing Tiingo observations remain diagnostics-only. No new provider read,
    backdated availability, guessed payable date or redistributed data is needed.

## Core versus completed report

The internal core produces fingerprinted daily NAV/cash/holdings, decision/risk
and order evidence, executions, action effects, split boundary and warnings. #39
owns initial experiment persistence and reserved migration0005_experiments under
ADR-004. A sealed core is input to #40, not a completed public experiment. #41 must
preserve `ExperimentRunV1`'s complete metrics plus three sealed-artifact invariant;
no placeholder metrics, success-shaped partial artifacts or public endpoint is
introduced by the core phase. Cancellation/failure cannot seal a core result.

## Independent example and verification

[The authored core trace](../../data/fixtures/backtesting/core-case.json) extends
FIX-02/03/05/06/09 using the existing separately authored template oracle. On
2028-07-18 synthetic mean-reversion targets three assets at200.00 each. Shares
are `floor_6dp(200 / decision_close)`, not sized at tomorrow's opening. Applying
10bps adverse slippage at the next raw open yields debits200.34/200.34/206.48,
cash392.84 and daily NAV1000.00/999.40/993.66/1000.22. These figures were derived
with standalone decimal arithmetic from committed price formulas, not the runner.
The split probe doubles2.855103 shares to5.710206 while retaining200.34 total
basis; the dividend probe credits exactly3.57 once on its known payable session.

Required proofs include exact boundaries/month ends/holiday calendar, immutable
previous decisions after future evidence injection, no recommendation-time state
mutation, same inputs/same series, cross-split carry, missing opens/marks,
universe exits, dividends/splits, cancellation and fenced persistence/restart.
The core's strict unsupported cases remain visible limitations, not skipped tests.
