# ADR-001: Market clock and synthetic execution

Status: proposed for review in [#12](https://github.com/santthosh/yams/issues/12); accepted when this ADR's PR merges. Implements approved Q01 from [#72](https://github.com/santthosh/yams/issues/72).

## Decision and inputs

Use policy ID `us_eod_next_open_v1` across backtests, paper portfolios and Arena. All capital, orders and fills are synthetic. A pure execution kernel receives an immutable calendar schedule/version, source snapshot, decision cutoff, approval instant, portfolio state, intended orders and policy; it returns proposed effects and reasons. It performs no network/database I/O. ADR-004 owns atomic posting and reservation, not different arithmetic.

The initial calendar is the U.S. primary-equity session calendar (`XNYS`, exchange timezone `America/New_York`). A calendar artifact contains session date, UTC open/close and a content digest used as `calendar_version`; retain the generator/library and timezone-data versions. No unversioned “latest calendar” lookup may change a stored run. #13 verifies provider/session alignment; #21 supplies explicit synthetic calendars for edge fixtures. Calendar/library installation and production schedule validation belong to subsequent implementation, not this document-only PR.

Store event timestamps as timezone-aware RFC3339 UTC `Z`; session dates are exchange-local dates, not UTC dates inferred by truncation. A schedule explicitly contains holidays, early closes and DST changes. Reject a missing/out-of-range/unvalidated calendar instead of assuming every weekday is a session.

## Decision cutoff and next open

A close-derived decision is made only after the session's closing bar is complete, validated and available. Record `decision_cutoff_utc` and require every input's `available_at <= decision_cutoff_utc`; this cutoff is at or after that session's scheduled close. Data downloaded later is not automatically evidence that it was historically available (ADR-002 owns availability proxies and disclosures).

Given `decision_cutoff_utc`, `approved_at` and the pinned schedule, choose the first session whose opening instant is **strictly greater than both timestamps**. Equality is too late for that open. For a deterministic historical backtest, the simulated approval instant is the decision cutoff; it is not the wall-clock time when the backtest ran. A live-like approval always uses the actual recorded approval time and cannot fill at a past opening. Preserve these timestamps through restart.

Eligibility of a session does not imply a usable execution price. Require a validated raw opening price and coherent corporate-action evidence. Partial/unvalidated opening quotes, absent bars, provider errors or unsafe stale evidence leave the order unfilled/pending with a reason; never use adjusted close, a previous close, zero or an inferred quote. A later-arriving validated bar for the originally eligible session may support that session's synthetic fill if its open was after approval; retain both execution-session and ingestion/posting timestamps. Do not silently substitute a different day's price for a missing scheduled opening.

## Amounts, costs and cash

- Use Decimal for raw/executed prices, quantities and cash. No float conversion at API or ledger boundaries.
- Apply adverse 10 bps per side: buy price = raw open × 1.001; sell price = raw open × 0.999. Default commission is USD 0.00. Record the configured policy with every run/batch.
- Keep executed price precision through multiplication; round each completed cash posting to USD cents with `ROUND_HALF_EVEN`. Quantity has at most six decimal places. Sell at most the posted position; truncate affordable buy quantity downward to six decimals, then verify the rounded debit cannot exceed available cash.
- Plan feasible sells before buys. **Q01:** executed/posted sale proceeds are immediately available for subsequent buys in the same synthetic rebalance. There is no settlement delay. Approval, a preview or an unfilled sell does not create spendable proceeds. Disclose the lack of settlement realism.
- Preserve the USD 5 minimum trade and 0.02 absolute-weight rebalance band. Evaluate the minimum against executable notional after cash/quantity adjustment (excluding commission); below-minimum trades are skipped with a reason. A weight delta below the band is HOLD unless correcting a mandatory risk breach; equality reaches the threshold. Risk corrections still obey affordability, minimum trade and long-only rules.
- A price gap may reduce a buy to an affordable quantity; record requested versus executable/filled quantity and the shortfall reason. This is cash-constrained sizing, not a model of market liquidity. Zero feasible quantity or a below-minimum remainder is not a fabricated fill. Do not borrow cash or sell a short position to satisfy the requested quantity.

## Pending intent and cancellation

Approval creates a durable authorized intent, not holdings. Public statuses follow API §7.2; `waiting_for_eligible_open`/`PENDING_DATA` describe why a pending order cannot yet post. Any partially executed state records actual filled and unfilled quantities; it must never imply the full request was filled. ADR-004 specifies the reservation and residual-intent representation, preserving these cash and quantity invariants.

Cancellation affects only unposted intent. Serialize cancel and posting at the same portfolio/order transaction boundary: cancellation winning first prevents that posting; posting winning first is reported as a fill, never reversed to pretend cancellation. Previously posted portions remain immutable; cancel only the remainder. Exact retry returns the durable outcome. Use the original approval/cutoff during lease recovery and deduplicate every fill/action event; restart is not new authorization.

## Corporate actions

Raw execution/ledger prices and adjusted feature-return prices have separate roles. A split scales posted shares and inversely scales unit basis on the declared effective session, before affected session trading; preserve total basis. A cash dividend credits eligible holdings once on the provider's validated payable/recognition date under ADR-002, not a guessed date. Preserve entitlement evidence so a subsequent sale does not erase an earned distribution. Do not add dividends a second time to an adjusted-return feature/benchmark series. Missing reliable raw prices/event dates blocks a realism claim and is disclosed; use explicit synthetic action fixtures to prove arithmetic.

## Independent fixture traces and verification

Implementation handoff (#35): [shared paper execution kernel](../operations/paper-execution-kernel.md)
documents the executable pure interfaces and numerical boundaries. Decimal precision
expands with input length; buys divide/quantize downward to6dp and postings use
explicit half-even cents. Hypothetical quote/preview transitions have no execution
timestamp and cannot create spendable proceeds. Corporate-action processing requires
the pinned session opening to have arrived; an exactly unrepresentable split remains
pending rather than inventing fractional-share rounding or cash-in-lieu. Durable
posting/recovery remains #44/#46, with action-before-trade chronology owned by consumers.

The times below are **synthetic fixture schedule inputs**, not claims about an actual exchange's historical calendar. Expected results are hand-derived, never produced by the implementation under test.

| Fixture | Inputs / action | Required result |
|---|---|---|
| FIX-06 before open | T close/cutoff `2030-01-03T21:00:00Z`; next fixture open `2030-01-04T14:30:00Z`; approval `14:29:59Z` that day | Next open eligible; no fill before validated opening evidence |
| FIX-06 equality/late | Same schedule; approval at `14:30:00Z` or `14:30:01Z` | That opening is ineligible; choose the next strictly later scheduled opening |
| FIX-06 holiday/gap | Schedule contains no session between Jan 4 and Jan 8; Jan 8 open missing | Do not invent Jan 5–7 sessions; Jan 8 remains pending data, no substituted price |
| FIX-03 accounting | Start 1000.00; buy 2.000000 at raw 100.00; later sell both at raw 100.00 | Buy price 100.10000, debit 200.20, cash 799.80; sell price 99.90000, credit 199.80, cash 999.60 |
| FIX-03 affordable reduction | Available cash 100.00; request 1.000000 at raw 100.00, no fee | Executed-price bound 100.10; max downward-quantized quantity 0.999000; rounded debit 100.00, cash 0.00; shortfall recorded |
| FIX-05 split | Two shares at unit basis 100.00; declared 2:1 split before next fixture open | Four shares at unit basis 50.00; total basis 200.00; no cash created |
| FIX-05 dividend | Entitlement: four shares, declared 1.25/share; payable date later than ex-date | Single 5.00 cash credit at validated recognition date; none before; replay does not duplicate |
| FIX-09 cancel/restart | Duplicate delivery around approval, cancellation or cash posting | One durable outcome per key; cancel-first leaves zero fill effects; fill-first retains exact posted amounts; recovery preserves approval time |

Cash assertions are exact cents and quantity assertions exact six-decimal values; timestamp/session selection is exact. #21 commits these fixture inputs/oracles; #35 implements the pure kernel; #44/#46 prove transaction, concurrency and replay behavior with real PostgreSQL. #39 reuses the kernel under a historical clock. #50 supplies the public cancel/idempotency transport. This ADR does not claim those components exist yet.
