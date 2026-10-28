# Paper ledger persistence

Issue [#44](https://github.com/santthosh/yams/issues/44) implements private backend
ledger services in `backend/portfolio/ledger.py` and the additive
`0006_paper_ledger` migration. These services support synthetic capital and
orders only. This source increment does not publish 0.0.4 or expose a portfolio
HTTP route. Account transport belongs to #45; approval/cancellation and worker
orchestration belong to #46. Production startup creates no accounts or
recommendations. The 0.0.5 recommendation producer remains #49.

## Funding and evidence

`create_portfolio` takes explicit account/workspace/published-strategy UUIDs,
a trimmed name and a UTC creation timestamp. Opening USD cash defaults to
`"1000.00"`, must be positive and fit 22 whole digits/two decimal places, and
creates no holdings. The account UUID identifies the creation command: exact
semantic retry returns the existing account, including after later activity;
changing its original opening intent is a `LedgerConflict`. Retried observation
timestamps do not change the original creation time. Funding is the first event,
not an extra balance added during replay. Separate accounts never share cash.

`post_order` requires a real applied recommendation reference, authorized batch
and original order. The calling backend worker must preload the complete
validated calendar, raw bars and corporate actions from the pinned market
repository outside the SQL transaction. These arguments are private trusted
backend evidence, never an HTTP price input. The ledger binds snapshot hash,
calendar, source mode, strategy, recommendation, cutoff and approval lineage
before recomputing with the shared `execute_order` kernel on locked holdings.
It does not establish provider rights or verify artifact files a second time.
The caller remains responsible for repository verification, source capabilities
and freshness; existing real-provider historical/accounting limitations remain.

Orders execute in sell-first, asset/ordinal order using posted cash. A pending
sell cannot finance a buy. A missing eligible open stays pending. A positive
cash-constrained partial fill closes its shortfall and is terminal; it cannot
be resubmitted automatically at another open. A skipped order receives a
terminal rejection and creates no fill. Cancellation already recorded by its
owning service cannot be resurrected by this writer. Batch reservation is a
partial unique index allowing one nonterminal batch per account.

## Transaction and retry guarantees

Every writer locks the portfolio before batch/order rows. The stable execution
identity hashes the immutable order UUID, policy ID, eligible session and logical
fill ordinal zero; worker attempts and observation time cannot create another
fill. Retry returns the original event; changed economic evidence conflicts.
A fill commits its event, fill, cash entry, position event, projections, order,
batch and revision together. There is no notification before commit. Deferred
PostgreSQL checks reject incomplete accounting tuples, inconsistent event chains
or late child entries that would alter a sealed transition. Immutable evidence
and authorized intent reject update/delete; referenced rows use restrictive
foreign keys. Projections alone are replaceable.

Money/basis are finite exact cents, quantities have at most six decimal places,
and raw/executed prices retain decimal precision. Inputs reject excess precision
before SQL can round them. The shared kernel owns average-cost basis, fees,
slippage and affordability; persistence does not implement a second quant engine.

Independent authored acceptance trace (all `SYNTHETIC_DATA_ONLY`, exact equality):

| Operation | Cash USD | Shares | Total basis USD |
|---|---:|---:|---:|
| Opening funding | 1000.00 | 0 | 0.00 |
| Buy two at raw 100, executed 100.10 | 799.80 | 2.000000 | 200.20 |
| Sell both at raw 100, executed 99.90 | 999.60 | 0 | 0.00 |

With opening cash 100.00 and a one-share request, the same buy posts 0.999000
shares, debits 100.00 and closes the remaining 0.001000 shares. Duplicate delivery
adds no rows or revision. Prices here are authored fixtures, not market returns.

## Corporate actions and corrections

`post_action` invokes the existing split/dividend kernel on locked state. Stable
provider/event identities distinguish distributions from refreshed observations.
A split preserves total basis. Dividend entitlement is persisted on the effective
session even when payable recognition is pending, and survives a subsequent sale.
A due payment credits that captured quantity once; repeated deliveries return the
original payment. Revised economic evidence requires an explicit correction.
An active batch needing a split adjustment is blocked for reevaluation rather
than silently changing its authorized share quantities.

`correct_dividend` supports an explicit cash-only amount correction with a target
event, unique command UUID, revised verified action and reason. It retains the
original entry and appends compensation. Four entitled shares originally paid
1.25 per share receive 5.00; correcting to 1.00 appends -1.00. A second correction
must target the current correction, not compensate the original again. Exact
retry adds nothing. Different identity/session or unsupported trade/split
corrections and negative resulting cash require explicit reconciliation and mark
the account blocked. These services do not implement arbitrary trade repair.

## Replay, reconciliation and operations

`read_portfolio` returns durable projections. `reconcile` locks the account and
folds signed cash/quantity/basis entries from zero in event order, checking hashes,
contiguity and each immutable before/after boundary. Metadata retains captured
entitlements and applied action identities. A mismatch sets
`reconciliation_failed` durably and raises `ReconciliationFailure`. New posting
also checks the immutable projection boundary and refuses a mismatch.
`reconcile(..., rebuild=True)` explicitly replaces projections only after the full
evidence chain validates; it never edits event/fill/action evidence. Unsupported
correction requests require operator investigation before clearing that block.

Normal bootstrap applies the additive migration under the existing migration
lock. It preserves workspace identity/preferences, strategy versions, existing
experiments and jobs. Destructive downgrade is refused; use a verified backup or
reviewed forward repair. Do not reset volumes to recover a ledger.

Run `make test-integration` for isolated PostgreSQL proofs: empty/prior upgrade,
concurrent funding/fill retry, independent SQL sums, fault injection after each
write, process exit after commit before acknowledgment, corporate actions,
correction/FK retention, reconciliation/rebuild and an actual database restart.
Canonical expectations are FIX-03/04/05/09 and ADR-004; no float tolerance applies.
Test-only recommendation records are explicitly labeled and fully linked. They
are never seeded into a production workspace.

## Handoff to account and approval owners

The staged batch `intent` envelope contains an `orders` array of shared
`OrderIntent` objects in persisted ordinal order. Posting validates every
immutable order against that envelope; caller-supplied prices cannot redefine
intent. Recommendation content is an immutable object/hash envelope for the
later producer, not a fabricated completed `RecommendationV1`.

Approval increments revision by appending a metadata-only `batch_approval` event
with unchanged financial state in the same transaction as batch/order creation.
Cancellation may use `batch_cancel`/`order_closed` metadata events. The schema
supports these event kinds; #46 implements their authorization/idempotency and
state transitions. A strategy change uses `strategy_binding`, requires no active
batch, and records the new UUID as `command.new_strategy_version_id`. Financial
revisions must retain a corresponding immutable event so boundary checks and
replay remain valid. These are private persistence handoffs, not new public APIs.
