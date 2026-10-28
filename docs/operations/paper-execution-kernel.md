# Shared pure paper execution kernel

Issue #35 implements the ADR-001/004 arithmetic reused by the later backtester,
paper portfolios and Arena. It performs no network/database I/O and exposes no
authorization API. Capital, orders, prices in examples and fills are synthetic.
The examples/tests below are labeled **SYNTHETIC_DATA_ONLY**.

## Inputs and sequencing

`PortfolioState` is the caller's posted cash, shares and total basis, plus retained
action identities and dividend entitlements. All financial inputs are validated
decimal strings. Positions and order intents include the same nonempty **as-of**
sector classification; `Unknown` is permitted, absent metadata is not invented.
Sector is calculation context, not an authoritative ledger projection column.

`ExecutionContext` pins snapshot ID/hash, calendar digest, source mode, engine
version, decision session/cutoff, original approval instant and explicit
`current_paper` or `historical_replay` mode. `MarketEvidence` must come from that
validated snapshot, with raw-as-traded bars, coherent corporate-action coverage
and explicit freshness. `verify_context` checks the lineage and calendar digest;
it does not load or register artifacts. Consumers must obtain inputs through the
pinned repository, never relabel research data as fixtures or raw-as-traded.

Consumers process events chronologically: apply effective splits and capture
ex-date entitlements **before affected-session trading**, recognize due dividends,
then execute approved orders and value posted holdings. Never pass a later
portfolio state into an earlier replay step. Pending action evidence/unsupported
split precision must block affected trading until resolved or explicitly replayed;
ignoring an action result does not establish coherent raw-price support.

## Planning and conditional previews

`plan_orders(state, targets, cash_target_weight, portfolio_config, context,
calendar, marks)` uses one completed decision-session raw close for every held or
target asset. Missing, unsafe, incomplete or future marks block the whole plan;
there is no guessed NAV. Empty targets are valid; zero portfolio value creates
no orders. Target allocation must pass the shared risk policy first.

Compare exact current/target weights with the configured absolute band. Below
2pp is HOLD by default; equality reaches the threshold. A reducing order that
corrects a position/sector cap, cash-floor or position-count breach bypasses the
band. It still obeys six-decimal precision and the executable-notional minimum.
Missing sector or inconsistent as-of classifications fail rather than hiding a
breach. Intended shares are conservatively floored to six decimals.

The plan includes actions, intended orders, a **conditional preview**, and
`projected_cash_usd`. Preview pricing calls the same `quote_order` arithmetic as
actual execution, processing sells before buys in stable asset-ID order. It
records requested versus executable quantity, affordability/minimum reasons,
costs and conditional state changes. Unfundable/under-minimum previews become
HOLD and emit no executable order. Partial previews retain requested intent and
show the smaller executable quantity explicitly. Fees/gaps can reduce it again
at the actual opening. Target weights describe the desired allocation, not a
guarantee that post-cost/opening-gap weights will equal them.

Preview transitions have no execution timestamps and are **not fills**. They
never mutate the input, authorize trading or produce spendable sale proceeds.
`quote_order` is a hypothetical pricing primitive, not a way to bypass the
market clock. Public authorization/posting remains staged to its owning issues.

## Eligible execution and accounting

`next_eligible_session` selects the first pinned opening strictly after both the
decision cutoff and original approval time. Equality is late. Missing/uncovered
calendars fail explicitly; no weekday fallback exists. A decision must follow
the declared session's scheduled close.

`execute_order` accepts posted state, an immutable intent, context/calendar,
market evidence, explicit observation time and minimum trade. Before the eligible
opening it returns pending. Missing/unsafe/unavailable raw opening data stays
pending for that **original** eligible session; it never substitutes an earlier
close or later session. Current-paper mode rejects stale snapshots and data not
yet ingested. Historical replay may use later-ingested evidence only when its
documented availability is no later than the replay observation; it remains
labeled replay. A later validated daily bar may support the original eligible
open: execution, evidence availability and proposed/posting times stay distinct.

The shared quote/execution arithmetic applies:

- Default adverse slippage .001: buy raw ×1.001; sell raw ×.999. Commission
  defaults to0.00; each result retains the supplied policy and costs.
- Decimal products preserve source precision. A local context uses at least80
  digits and expands with input length, independent of ambient Decimal settings.
  Division rounds down; share sizing floors to6dp. Cash postings use explicit
  `ROUND_HALF_EVEN` cents. No cash/price/share calculation converts through float.
- Buy affordability first reserves commission, floors affordable shares, then
  verifies rounded debit cannot overdraw. Sells cannot exceed posted holdings.
  Check the minimum against unrounded executable notional after resizing,
  excluding commission: a sell notional4.995 is below5 even if cents round to5.
- Buys add the total debit to basis. Partial sales remove half-even cents of
  total basis ×sold/held; full sales remove all remaining basis. Realized P/L
  is net sale proceeds minus removed basis. No tax-lot claim is made.
- Affordability/holdings shortfalls are terminal skipped remainders, never
  phantom liquidity fills. Results conserve requested =filled +pending +skipped.

`simulate_batch` is a conditional chronological replay trace: sells first, then
buys, stable asset-ID order; duplicate order keys/assets fail. A missing sell
produces no proposed proceeds, so a subsequent buy cannot use them. **Durable
services must call `execute_order` against freshly read posted state and atomically
persist one effect before allowing its proceeds to fund the next order.** A
preview/replay result is not proof that a database posting happened.

## Corporate actions

`apply_action` requires the pinned calendar, explicit processing session and
observation time. The session must exist and its open must have arrived. Future
available/ingested evidence cannot affect a live step. Results retain the action,
calendar digest, session and observation time.

Splits apply on their effective session before trading. They scale shares exactly
and preserve total basis/cash. A result not representable at6dp stays pending
`UNSUPPORTED_SPLIT_PRECISION`; no cash-in-lieu or share rounding is invented.
Missed effective splits require chronological replay rather than applying a
ratio to a later holding without history.

Dividends capture an ex-session entitlement from then-posted shares, even when
the payable date is unavailable. Recognition requires a validated payable date,
retained entitlement, elapsed processing session and visible evidence. Selling
after ex-date does not remove entitlement. Missing history stays pending, never
reconstructs eligibility from today's holdings. Supplemental payable-date evidence
can mature a retained entitlement without changing its shares/amount.

Provider/event ID identifies an action. Retained semantic payload hashes prevent
reapplication; observation refreshes and equivalent decimal encodings do not
create another distribution. Substantive revisions conflict and require the
explicit correction policy owned by durable ledger services. Do not add dividend
cash to an already adjusted-return feature or benchmark path.

## Independent examples and verification

| Trace | Required result |
| --- | --- |
| FIX-03:1000 cash, buy2 at raw100 | Executed100.1; debit200.20; cash799.80 |
| Sell those2 later at raw100 | Credit199.80; cash999.60; basis0; realized−.40 |
| Cash100, request1 at raw100 | Fill.999000; debit100.00; skipped.001000 |
| Cash0, sell2 then buy1 at raw100 | Posted/proposed sell199.80 then debit100.10; conditional cash99.70 |
| Missing sell opening, same cash0 | Pending sell, no spendable proceeds, no buy fill |
| FIX-05:2 shares/basis200, split2:1 |4 shares, basis200; cash unchanged |
| Four entitled shares ×1.25, sold before payable |5.00 credit once on evidenced payable session |
| FIX-06:approval exactly at scheduled open | That open excluded; next strictly later opening |

Run `uv run --locked pytest backend/tests/portfolio -q`. Independent committed
FIX-03/05/06 values, half-even examples, price-gap/fee/long-only bounds, exact
band/minimum boundaries, mandatory concentration/cash corrections, empty/missing
states, future evidence/actions, preview separation and100 seeded conservation
cases cover the pure kernel. #44/#46 still own real PostgreSQL posting,
idempotency, locking, cancellation, crash/restart and replay guarantees; pure
arithmetic tests do not establish those durable guarantees. #39 owns integration
with the historical clock. No public trading flow is added here.
