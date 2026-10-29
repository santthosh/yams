# Paper account API

Issue [#45](https://github.com/santthosh/yams/issues/45) adds account create/list/detail
and immutable transaction pages to the source checkout for planned 0.0.4. This does
not publish that release. All capital and orders are synthetic. Startup creates no
accounts or recommendations. The portfolio UI belongs to #47; approval/cancellation
and scheduled execution belong to #46; public recommendation apply remains #50
in 0.0.5. See the [ledger guarantees](paper-ledger.md).

## Create an independent cash account

Start the source application with `docker compose up --build -d --wait`. The web
proxy is the only published default interface, at `http://127.0.0.1:3000`.

```sh
curl http://127.0.0.1:3000/api/v1/portfolios \
  -H 'Origin: http://127.0.0.1:3000' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 11111111-1111-4111-8111-111111111111' \
  --data '{"name":"Local paper account","strategy_version_id":"184f4ef7-c542-5387-a5aa-9bd4d162efde","mode":"synthetic_fixture","opening_cash_usd":"1000.00"}'
```

This uses the immutable seeded momentum version. Alternatively select a published
version from `GET /api/v1/strategies`. The response is `201 PaperPortfolioV1`, with
a UUID, `state=active`, `cash_usd="1000.00"`, no holdings and a known all-cash value.
A cash account does not imply a recommendation or a purchase.

Use a new UUID key for each deliberate account creation. Reuse the original key
and semantic body after a lost response; retry returns the same account identity
and current posted state, preserving original funding and creation time. Reusing
the key with changed inputs returns `409 IDEMPOTENCY_CONFLICT`, including when the
new body supplies an unknown strategy or snapshot. No duplicate funding occurs.
Different keys create independent capital, even with identical names.

The closed input contains `name` (trimmed, 1–120 characters, no controls),
`strategy_version_id`, optional `opening_cash_usd` (default `"1000.00"`, positive,
maximum 22 whole digits and two decimal places), `mode` (default
`synthetic_fixture`) and optional `snapshot_id`. Floats, zero/negative funding,
excess scale and unknown fields are rejected. A selected snapshot must exist,
match the source mode, be unblocked and pass hash/file verification before the
funding transaction. Its ID is retained on the immutable opening event. Omitting
it is valid because cash-only funding needs no market price.

Source mode and opening funding remain immutable. This API has no deposit,
withdrawal, direct fill, source-change or arbitrary strategy-execution endpoint.
The configured risk policy comes from the bound immutable strategy version;
the v1 benchmark label remains SPY. Selecting a research source does not authorize
accounting with a diagnostic-only provider.

## Read posted state and history

Use the returned UUID in these paths:

| Route | Response / pagination |
|---|---|
| `GET /api/v1/portfolios` | `Page[PaperPortfolioV1]`; `limit` default 25/max 100, UUID `cursor`, optional `mode` |
| `GET /api/v1/portfolios/{id}` | Posted cash/holdings, bound strategy/risk, valuation evidence and revision |
| `GET /api/v1/portfolios/{id}/transactions` | Newest immutable events first; `limit` default 25/max 100 and UUID `cursor` |

List cursors belong to the selected source filter. Transaction cursors belong to
one account. Invalid/cross-account cursors return `422 VALIDATION_ERROR`; unknown
accounts return `404 NOT_FOUND`. Reads never enqueue jobs, post financial events,
clear reconciliation flags or rebuild projections. A failed ledger boundary
check returns `409 STATE_CONFLICT` requiring explicit reconciliation. This can
fail a page rather than serve unverified balances. Database/schema failures
return sanitized `503 NOT_READY`.

Each transaction carries original sequence/revision, effective and recorded UTC
times, strategy/snapshot references, signed cash and position/basis effects, and
an actual fill only for a fill event. Corrections retain their target event.
Metadata-only events have a real zero cash delta; a pending order is not a fill.
Pages expose source mode, paper-only status and synthetic warnings. Private
command payloads, file paths and provider credentials are not returned.

## Valuation and unavailable data

The documented summary names remain `state`, `total_value_usd`, `valuation_mode`
and `valuation_as_of_session`. Holdings expose `mark_price_usd` and
`price_as_of_session`. The additional `valuation` envelope contains status,
reason, pinned snapshot/hash, checked time, cash weight, missing assets and
warnings. Its value/session must agree with the summary.

A cash-only account has an exactly known value without a market snapshot:
`total_value_usd=cash_usd`, cash weight 1 and `reason=CASH_ONLY`; market session is
null. At zero total capital, value 0 is known but the undefined cash percentage is
null with `ZERO_PORTFOLIO_VALUE`. No market date is invented for cash.

Held accounts use the latest published same-mode source, or their selected
opening snapshot before another publication exists. Hash-verified raw closes
share one completed pinned session and retain availability/ingestion checks.
Inactive holdings remain accounting inputs when their historical bars exist.
Read-only valuation does not require a future trading session. The synthetic
clock comes from the selected fixture session's actual bar observations, and is
always labeled `SYNTHETIC_DATA_ONLY`; it is not the current real exchange date.
Real sources use actual observation time and verified accounting capabilities.
Existing real feeds remain diagnostic-only where raw/action support is absent.

Missing, blocked, stale, unsupported or corrupt price evidence yields explicit
unavailable/stale status, null totals/marks/weights and a reason, never a fake
zero-valued holding. Posted cash and quantities remain visible. Shared exact
Fraction/Decimal valuation computes totals; display money rounds half-even to
cents and weights to 18 decimal places. Independently rounded holding amounts may
differ from the once-rounded aggregate by a cent. None of this rounding changes
the cash ledger or a strategy allocation. Price inputs retain their source
precision. Source reads are cached within one response so a bounded account page
does not repeatedly open the same analytical snapshot.

## Verification

Run the real repository targets: `make lint`, `make typecheck`, `make test`,
`make contracts-check`, `make fixtures-check`, `make test-integration` and
`make smoke`. Integration uses uniquely owned disposable PostgreSQL resources,
never the operator's volumes. Tests cover strict keys/capital/lineage, concurrent
creation/retry with the two-connection pool, independently derived source values,
missing files, account/source-scoped pages, read-only row counts and actual restart.
The Docker smoke creates an explicit fixture cash account through the same-origin
proxy and verifies its original identity, funding and retry after restart/rebuild.

Independent valuation example: the committed fixture's January 4, 2030 raw open 89
produces a two-share debit 178.18 under the shared 10bps policy; cash 821.82 remains.
Its December 31 raw close 101.800 values two shares at 203.60, total 1025.42. These are
repository-authored synthetic inputs, not market returns or an investment signal.
