# Paper account screens

Issue #47 adds `/portfolios` and `/portfolios/{id}` to the local application.
Accounts use synthetic USD capital and orders. The browser displays posted backend
state; it does not calculate balances, position values, weights, fees or fills.

## Create and inspect an account

Open **Paper portfolios** from navigation or the Dashboard. Enter a name, positive
starting capital (default $1,000), a published strategy version and source mode.
The selected published version and source remain bound to this account. Changes
to a strategy produce another version; they do not rewrite this binding.

Creation returns an independently funded cash account. It does not buy securities.
The detail page shows known cash, backend valuation/as-of, cash weight, posted
holdings, version/risk assumptions, reconciliation flag and immutable history.
A positive cash-only account has no holdings and displays the backend's 100% cash
weight. If total value is exactly zero and weights are undefined, the page shows
the explicit reason rather than inventing a percentage.

Synthetic fixtures are labeled and their calendar dates are not live coverage.
Market research accounts can hold synthetic cash without prices. Current real
providers remain diagnostic-only and unsupported for paper execution; an account
screen does not grant missing raw-price/action capabilities.

A creation request keeps its UUID key and original body until the outcome is
known. After connection loss or a server failure, fields remain locked and
**Retry same account creation** recovers the original command. Validation errors
return to an editable form. Account creation/retries never add a second opening
funding event under the same key. Inspect the account list after navigating away
from an unconfirmed submission before deliberately starting another account.

## Posted state and unavailable evidence

Refresh fetches current posted state through the same-origin, noncached API proxy.
Missing/stale marks retain known cash, shares and basis but show unavailable value
or weights with the backend reason. They are distinct from empty holdings and a
known zero value. Read failures show an error instead of a fabricated balance.
A reconciliation failure blocks financial work and needs the recovery procedure
in [ledger operations](paper-ledger.md); the UI never rebuilds or resets evidence.

Account and history reads are separate. If their sequence references differ,
the page asks for a refresh rather than implying the two reads were simultaneous.
History pages retain backend order and opaque cursors. A failed additional page
keeps displayed evidence and labels it partial. Source filters restart account
pagination so fixture and research pages cannot mix accidentally.

Cash/quantity/percentage formatting reuses exact decimal-string display helpers.
The ledger exposes actual raw/executed price strings, signed cash and position
changes, commission/slippage, removed basis and realized P/L. Expand an event to
inspect its identity, original effective/recorded time, strategy version, source
snapshot and correction lineage. No frontend return, target or forecast is inferred.
Tables are keyboard-focusable and scroll horizontally on narrow screens.

## Pending state and staged controls

[The private batch service](paper-batches.md) owns approval/cancellation/execution.
Public recommendation/apply/batch HTTP transport belongs to #49/#50 and the full
Decision Center to #52 in 0.0.5. This screen displays that boundary explicitly.
It offers no premature approval button or fake batch endpoint. A ledger approval
event is historical evidence, not a claim that its orders filled or remain active.

`OrderBatchState` is a presentational component over generated `PaperOrderBatchV1`.
Its pending, terminal partial and cancelled states display the backend's requested,
filled, pending and closed-shortfall quantities. Service-fixture browser tests
render it separately with production CSS and a visible `SYNTHETIC_DATA_ONLY` label;
application routes never import test fixtures. #50 can wire its real transport
without introducing client-owned financial calculations.

## Verification and handoff

`make test-e2e` runs the desktop 1280 px and mobile 360 px flows. Portfolio cases cover
keyboard creation, uncertain-response retry with the original key/body, server
validation, independent sources, posted holdings/fees/history pagination, missing
and stale marks, unknown accounts, long names, mobile table scrolling and Axe.
Authored browser fixtures are validated against the Python contracts and independent
FIX-03 cent/share/weight expectations in
`backend/tests/contracts/test_portfolio_browser_fixtures.py`.

`make smoke` owns a disposable full Docker project. The actual browser creates two
independent cash accounts through the real proxy, retries their original commands,
and inspects real private-service-seeded synthetic fills. Subsequent browser reads
and retries after database/application restart and rebuild retain identity, funding,
posted quantities and history. These checks use no mocked API and never access
user volumes. Screenshots/resource evidence are retained under ignored
`test-results/smoke/<project>/`; [the verification report](../verification/47-portfolios/README.md)
records the reviewed increment.

Implementation: `components/portfolios/PortfolioBrowser.tsx`, `PortfolioDetail.tsx`,
`HoldingsTable.tsx` and `OrderBatchState.tsx`, with generated API types and existing
formatters. This issue changes no financial runtime, migration or public contract.
The integrated 0.0.4 native packaged-release gate remains separate from this PR.
