# ADR-004: Atomic paper ledger and revision control

Status: Accepted for implementation under #15. Date: 2026-10-27. Consumes [ADR-001](0001-execution-semantics.md), [ADR-002](0002-data-normalization.md) and approved Q01. All funds and trades are synthetic. #44/#46 own executable PostgreSQL proofs; this ADR is not a claim those services exist.

## Records and numerical boundaries

Use UUID primary/foreign keys, timezone-aware UTC timestamps, explicit exchange-session dates and immutable source/policy hashes. Financial API values are decimal strings. Reject excess scale before database assignment rather than relying on implicit rounding. Persist finite Decimal values only, never binary floats or PostgreSQL special numeric values.

| Record | Required payload / constraints |
|---|---|
| `paper_portfolio` | workspace ID, USD currency, immutable opening-funding reference, bound strategy version, revision bigint >=0, projected cash, lifecycle status; opening funding is a ledger event, not an extra balance added on replay |
| `ledger_event` | portfolio ID, strictly increasing per-portfolio sequence, event kind, semantic event key, payload hash, recorded/effective timestamps, policy/source references, optional correction target; unique `(portfolio_id, sequence)` and `(portfolio_id, event_key)` |
| `cash_entry` | event ID, signed USD delta, purpose; unique `(event_id, purpose)`; every cash change references an immutable event |
| `position_event` | event ID, asset ID, signed quantity delta, signed total-cost-basis delta, reason; unique `(event_id, asset_id)` |
| `position` projection | unique `(portfolio_id, asset_id)`, nonnegative quantity and total cost basis, last applied event sequence; zero quantity implies zero basis |
| `recommendation` reference | portfolio/strategy-version/snapshot IDs, as-of/cutoff, portfolio revision, immutable content/hash and provenance mode, disposition; foreign keys target real rows, no placeholder IDs |
| `paper_order_batch` | portfolio/recommendation IDs, immutable approved intent/hash, approval time/revision/idempotency key, pinned execution policy/calendar/snapshot, eligible session, status and terminal reason; unique recommendation ID and `(portfolio_id, idempotency_key)` |
| `paper_order` | batch/asset ID, stable ordinal, side, requested quantity, filled quantity, cancelled/skipped remainder, state/reason; requested = filled + cancelled/skipped + still pending |
| `paper_fill` | order/event IDs, stable fill-event key, raw/executed prices, quantity, gross, fee, cash delta, execution session and posting timestamp; unique `(order_id, fill_event_key)` and event ID |
| action evidence | source action ID/version, entitlement/effective/payable facts and payload hash; applied identity unique per portfolio/action/version, with explicit correction links between revisions |

Cash, gross, fees and total cost basis use `NUMERIC(24,2)` with exact cents. Quantities/deltas use `NUMERIC(30,6)`; positive quantities for fills and nonnegative projections. Prices use unconstrained `NUMERIC` with application validation of finite positive decimals, retaining source precision through ADR-001 multiplication. Average unit basis is derived as total basis / quantity, not independently rounded and accumulated. Account/API input values must fit storage bounds; overflow fails the whole command.

Use average-cost accounting for the position projection: purchase basis increases by the exact cash debit including fees; sale removes `ROUND_HALF_EVEN(total_basis × sold_qty / held_qty, cents)`, with a full sale removing the entire remaining basis. Sales credit actual proceeds separately; realized P/L is proceeds minus removed basis. Splits preserve total basis while changing quantity; dividend cash does not alter basis. No tax-lot or tax reporting claim. Arithmetic for division must use sufficient precision and verify the resulting cent/quantity invariants; never independently round average unit basis before computing removed basis.

All referenced records use restrictive deletion. Immutable event/fill/entry payloads cannot be updated or deleted by ordinary application paths; enforce this in persistence and integration tests, with database protections for ledger tables. Mutable projections and lifecycle dispositions are distinct from immutable event content.

## Approval, reservation and locking

Use PostgreSQL portfolio-row locking plus a client revision token. Every approval, cancellation, fill, funding/action posting, correction and strategy-binding change locks that portfolio row first. Within a portfolio, acquire batch/order rows in stable ID order after the portfolio lock. No network I/O occurs while holding locks; revalidate preloaded evidence and current state inside the transaction.

The minimal reservation policy is **one active execution batch per portfolio**. A partial unique index enforces one nonterminal batch. Approval reserves exclusive use of the portfolio's available cash and sellable holdings for that batch, without changing economic balances or inventing sell proceeds. A second distinct approval while a batch is active returns `409 STATE_CONFLICT`; the operator must wait or cancel the remaining intent, then reevaluate. This avoids multiple speculative cash reservations at unknown future opens. Independent portfolios do not share reservations.

Under the lock, resolve exact idempotent retries first: same portfolio/key/payload returns the original durable batch even if the revision has since advanced; different payload returns `409 IDEMPOTENCY_CONFLICT`. For a new approval verify expected revision, current strategy/snapshot/recommendation references, freshness and recommendation disposition. An obsolete token returns `409 STATE_CONFLICT`; a stale input returns `409 STALE_DATA`. Reserve, create orders, mark recommendation applied and increment revision in one transaction. Unique recommendation identity prevents another key from authorizing it again.

The active batch may consume only posted cash. Post feasible sells before buys in stable order (asset_id then order ordinal); missing sell evidence leaves proceeds unavailable. Buys dependent on those proceeds wait until the sell stage resolves. A rejected/skipped sell creates no cash; after sells resolve, size buys against actual remaining posted cash under ADR-001. No settlement delay applies to posted sales (Q01). Corporate actions may post while a batch is active under the same lock, incrementing revision; the worker revalidates holdings and quantities rather than rejecting its own valid approved batch solely because an earlier fill advanced revision. An external strategy change requires no active batch.

## Atomic posting and recovery

For each proposed fill: begin transaction; lock portfolio; check stable event key/payload and batch authorization/cancellation; validate original approval/cutoff/eligible session and raw/action evidence; recompute affordability and sellable quantity against locked projections; insert ledger event, fill, cash entry and position event; update projections, order/batch state and portfolio revision; commit. Database constraints and final invariant checks enforce nonnegative cash/shares and complete row relationships. No partial commit or external notification before commit. A commit acknowledgment lost in transit is handled by exact retry, not another fill.

The event key is derived from immutable order ID plus the original execution event identity (policy version, eligible session and logical fill ordinal), never worker attempt, lease ID or current time. A changed payload under the same event key is a conflict. Action identity uses stable source action/version plus portfolio. Store enough evidence to recreate the intended effects and diagnose conflicts without credentials. A lease grants scheduling ownership, not financial uniqueness.

Cash-constrained sizing may post less than requested once. Record filled quantity and close the shortfall as skipped with `INSUFFICIENT_CASH` or `BELOW_MIN_TRADE`; do not automatically resubmit it at another day's open. An order with a positive fill and closed shortfall remains `partially_filled` with `terminal=true`; a fully filled order is `filled`; a zero fill is rejected/skipped with a reason. Batch output includes `terminal` and remaining quantities so a terminal partial result is distinguishable from waiting orders. A missing eligible open remains nonterminal/pending. Cancellation closes only outstanding intent, releases exclusive reservation when all orders are terminal and retains all posted fills. Cancel-first prevents posting; fill-first retains its posted portion. Retry returns that recorded outcome.

Replay folds events in per-portfolio sequence order from zero balances, including opening funding exactly once. Projections are rebuildable; their last sequence identifies the replay boundary. On mismatch, block new financial posting and report reconciliation failure; do not silently overwrite evidence. Rebuild in isolation and atomically replace verified projections under the portfolio lock. Restart preserves original approval timestamps and event identities.

## Corrections and actions

Never edit a posted fill to repair it. Append a correction event with target event ID, reason, evidence and a unique correction-command key. A correction contains compensating deltas and, if needed, replacement effects as one atomic event group; validate the resulting cash, shares and basis before committing. It must not masquerade as a new operator trade. If compensation would create negative balances, unsupported fractional action units or inconsistent subsequent state, reject it and leave the portfolio blocked for explicit reconciliation; never delete intervening trades or create unexplained funding. One correction may supersede a prior correction through explicit lineage, not duplicate the original reversal.

Apply supported splits before affected trading and post dividends only from preserved entitlement and reliable payable/recognition evidence, as ADR-002 requires. Replays/duplicate action deliveries cannot double credit. Revised provider evidence creates an explicit correction request; it does not repost the full revised action automatically. Corporate-action transformations of pending orders must preserve original authorized economic intent with an auditable adjustment record; if the action cannot be represented under the policy, block execution pending reevaluation instead of guessing.

## Migration ownership and order

One Alembic history, one head. Reserve the following unique revision identifiers; these are future ownership assignments, not existing migrations. Each implementation sets `down_revision` to the then-current merged head and verifies dependency tables exist. The table lists required artifact order, not permission to implement later milestones now.

| Revision ID | Owner / milestone | Owned schema and prerequisite |
|---|---|---|
| `0001_workspace` | #22 / 0.0.1 | Singleton workspace and migration infrastructure; no financial feature tables |
| `0002_jobs` | #23 / 0.0.1 | Durable job/attempt/lease tables after workspace |
| `0003_snapshots` | #30 / 0.0.2 | Asset/snapshot metadata and immutable artifact references |
| `0004_strategies` | #71 / 0.0.2 | Strategy/version registry after workspace; #36 extends it later |
| `0005_experiments` | #39 / 0.0.3; #41 consumes it | Initial experiment persistence after delivered snapshot/strategy tables |
| `0006_paper_ledger` | #44 / 0.0.4 | Portfolio, recommendation-reference schema, batch/order/fill, ledger/action and projection tables after snapshot/strategy schemas |
| `0007_recommendation_content` | #49 / 0.0.5 | Additive recommendation computation/content extensions, preserving #44 IDs and foreign keys |

The 0.0.3 sequencing amendment under #39 assigns initial experiment persistence
and the reserved `0005_experiments` migration to the backtest-core owner #39.
Its scope already includes the experiment model and core worker handler; downstream
#41 depends on #39/#40 and therefore cannot be an undelivered schema prerequisite
for the core. #39 supplies immutable strategy/snapshot/config/policy/seed inputs,
job relationships and fenced sealed-output persistence under the existing domain,
queue and artifact contracts. #40 owns metrics/benchmark calculations. #41 owns
public experiment creation/detail/windowed-series/trades and cooperative job
cancellation transport over those delivered services. It must not create a second
experiment aggregate, replay financial logic in transport or reuse this revision.

This is an ownership/order correction, not a new table or handler implementation,
financial policy, public endpoint or definition of completed state. #39 must first
verify the actual merged schema head (currently `0004a_evaluations`), contract
compatibility, immutable references and independent transaction/artifact recovery
proofs. Join that actual head linearly; the reserved ID does not authorize skipping
intervening delivered migrations. Completion still requires all owned outputs to
be sealed under a valid lease; cancelled/failed/partial artifacts cannot appear
complete. Later public responses must satisfy the complete versioned API contract;
no scaffold placeholder metrics or future-only dependencies are introduced.

Other feature migrations receive distinct IDs at their owning PR and join the actual merged head; never reuse these reserved identifiers or create an unreviewed second head. #44 creates the real recommendation reference/content envelope before batch foreign keys, in the same migration sequence. Service integration tests may insert fully linked `synthetic_fixture` recommendation rows with explicit test evidence; production startup seeds no recommendations. #49 later produces valid recommendation content through the real evaluator. Thus 0.0.4 can persist/test execution infrastructure without a dependency on the 0.0.5 producer. Earlier migrations never import later application code.

Use additive forward migrations, versioned envelopes and explicit backfills with validation. Migration failure must abort startup readiness, preserving the last usable schema/data. Test upgrades from empty and previous release schemas, repeat startup, FK restrictions and backup/restore. Normal startup never drops/reseeds portfolios. Destructive downgrade/reset is not a routine recovery strategy; use reviewed forward repair or verified backup restoration. #22 owns migration runner serialization; feature owners own data-specific backfills and compatibility.

## Independent FIX-03/04/05/09 acceptance traces

| Trace | Expected durable result (exact cents/6dp, no tolerance) |
|---|---|
| Funding/buy/sell | Funding +1000.00, buy 2 at executed100.10: cash799.80, shares2, basis200.20. Sell both at99.90: cash999.60, shares0, basis0, realized loss0.40. Replay gives the same values. |
| Sale-funded buy | Cash0, posted sell credit199.80, then buy1 at100.10: cash99.70. Before the sale commits available cash remains0; preview alone cannot fund the buy. |
| Competing approvals | A and B both submit revision7. A locks, approves and commits revision8. B acquires the lock and receives409; exactly one active batch, unchanged cash/holdings. A's exact retry returns its batch. |
| Duplicate fill | Workers A/B submit identical fill key. A commits one event/fill/cash-entry/position-event tuple; B returns that tuple with no revision increment or extra rows. Changed amount under same key is a conflict. |
| Crash matrix | Inject failure after each insert/projection/state update, before commit: no event/fill/cash/share/status/revision change survives. Crash after commit before response: retry returns exactly the committed result. |
| Split/dividend | Two shares, basis200.00 become four, basis200.00 (unit basis50). Entitlement4 × dividend1.25 credits5.00 once. Duplicate delivery and restart retain one action event and one cash credit. |
| Correction | Erroneous standalone dividend5.00 credited to cash100.00 gives105.00; a supported correction to4.00 appends−1.00, giving104.00. Original+5.00 remains immutable; correction retry adds nothing. |
| Partial/cancel | Request1 at100.10 with cash100.00: fill0.999000, debit100.00, terminal skipped remainder0.001000. Cancel after posting cannot undo it. For an unposted pending order, cancel-first leaves zero fill tuples. |

#21 materializes oracles; #44/#46 run real PostgreSQL fault injection, concurrent transactions and independent event-fold comparison. SQLite mocks or a passing arithmetic example cannot establish these transactional guarantees.
