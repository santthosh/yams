# Decision Center source verification — #52

Planned 0.0.5 source increment. The published 0.0.4 release is unchanged; #53 owns
the final fresh-install/core/native release gate. Financial inputs are
`SYNTHETIC_DATA_ONLY`. Recorded application output is evidence, not an independent
oracle or real investment performance.

## Independent paper ledger example

This calculation reads the committed synthetic fixture values and uses ordinary
Decimal arithmetic; it does not call the production planner, executor or forecast.
The authored equal 20% security targets on a $1,000 cash account imply $200 per
security. The 2028-07-17 closes are $70, $70 and $67, producing six-place truncated
quantities 2.857142, 2.857142 and 2.985074. These are the same independently authored
planner expectations documented in `backend/tests/recommendations/expected_cases.json`.

Under ADR-001's zero commission and 10-basis-point adverse buy slippage, the actual
2028-07-18 raw openings in `data/fixtures/snapshot/bars.json` produce:

| Asset | Quantity | Raw open | Executed price (open × 1.001) | Cent-rounded debit |
| --- | --- | --- | --- | --- |
| SYN:AAA | 2.857142 | 70.050 | 70.120050 | 200.34 |
| SYN:BBB | 2.857142 | 70.050 | 70.120050 | 200.34 |
| SYN:CCC | 2.985074 | 65.040 | 65.105040 | 194.34 |

Each debit rounds half-even to cents. Total debit595.02; remaining cash404.98.
Approval alone leaves cash1000.00 and holdings empty. Daily fixture bars arrive
one second after their close, so the first explicitly observed close remains
pending. A later explicit close exposes the original opening; bounded worker
attempts may pass through partial state before all three quantities post. A single
completed attempt is not batch completion. The browser asserts terminal filled
status, every original quantity, no pending/closed shortfall and exact cash.

Posted account marks can use a later available fixture session; the screen labels
them separately from the frozen historical decision/forecast as-of. Those later
marks never enter the historical decision.

## Verification and limits

- `make test-integration`:188 actual PostgreSQL cases plus11 actual restart checks
  passed in uniquely owned project `yams-it-499973af07d5`; resources cleaned.
- Backend unit/contract suite:472 passed. Web suite:84 passed, including explicit
  unavailable/cash-only/no-order/stale views, exact large money/canonical uint64
  inputs, corrupted-storage guards and accessible same-key response-loss retry.
- Lint/format, strict Python/TypeScript, prior route/shared-schema compatibility,
  generated contract drift,30 fixture checks and wheel/source package build pass.
- Final fresh production Docker run `yams-smoke-e49d653619fa`:30 checks pass,
  including all prior restart/rebuild/migration/port/resource proofs and the real
  Decision Center at360/1280. Owned resources are cleaned. Prototype failures
  remain in local logs and are not passed gates.
- Local native macOS Turbopack subprocess port binding is unavailable in this
  environment. Production Docker and required GitHub Actions verify build/runtime;
  no setting or assertion is weakened to claim local native execution.

Operational behavior: [Decision Center](../../operations/decision-center.md).


## Final browser and source evidence

[Recorded safe evidence](evidence.json) retains both real browser journeys: keyboard
confirmation/focus restoration, same-key lost-response recovery after reload at360px,
double-click suppression at1280px, unchanged1000cash at approval, two explicit fixture
observations, terminal complete quantities and404.98cash. A subsequent genuine HOLD
review is dismissed through the UI with an unchanged ledger. Both widths have zero
Axe violations and document width equals viewport width. Prior immutable actions and
scenario output remain identical after fills; the dashboard reads actual account state.

Screenshots: [mobile confirmation](decision-confirm-360.png),
[desktop confirmation](decision-confirm-1280.png),
[mobile filled state](decision-filled-360.png),
[desktop filled state](decision-filled-1280.png).

The accessible approval-error placement, unbroken engine-hash overflow and stale
queued-history display were reproduced against prior UI builds and corrected without
weakening assertions. Focused regression tests pass. Every prior OpenAPI route and
shared schema remains JSON-value compatible; only two readonly paths/models are added.
All158 production Python source files match both final PostgreSQL integration and
production application images, whose immutable local image IDs are recorded. The final
frontend production build was made after its last source change. Required current-head
GitHub Actions and actual MergeWatch review remain PR gates, not assumed from local tests.
