# Public paper controls (#50)

All funds, holdings, intent and fills are synthetic. Current provider tokens do not
enable real-market accounting. This is the 0.0.5 source increment; published0.0.4
assets retain their original staged controls. The Decision Center screen and
portfolio scheduling remain #52/#51.

The API uses the real recommendation publication from #49 and delegates every
financial transition to the existing shared approval/cancellation/fill services.
No route accepts a trade price, amount, quantity or operation timestamp.

| Operation under `/api/v1` | Input | Result |
|---|---|---|
| `POST /recommendations/{id}/apply` | `{"expected_revision":1}` and UUID `Idempotency-Key` | 202 `PaperApprovalAccepted` |
| `GET /recommendations/{id}/apply-result` | Original UUID key header | 200 original immutable approval |
| `GET /order-batches/{id}` | None | 200 actual batch, quantities, clock and latest fill job |
| `POST /recommendations/{id}/dismiss` | `{}` | 200 disposition; no financial mutation |
| `POST /order-batches/{id}/cancel` | `{}` | 200 actual pending-cancel/partial/filled outcome |
| `POST /order-batches/{id}/advance-fixture` | `{}` and new UUID key | 202 original job/observation identity |

Apply uses the current posted revision from the original decision. Exact retry
with the original key/body returns the original approval before freshness, state
or source-file checks; changing inputs under that key gives409
`IDEMPOTENCY_CONFLICT`. Persist the key locally before submission so a lost response
can be recovered through the read-only lookup. Unknown keys/resources give404.
Approval reserves intent and increments the audit revision; cash and holdings do
not change. Use batch GET for subsequent state instead of treating an old202
response as current order state. HOLD/cash-only decisions have no executable batch
and return422. Stale state/disposition returns409 `STATE_CONFLICT`, stale source409
`STALE_DATA`, and unavailable integrity/storage503. Errors omit private diagnostics.

Dismissal changes only ready/expired disposition and retains immutable content;
repeating dismissal succeeds, applying an already dismissed decision conflicts.
An applied recommendation cannot be dismissed to undo approval. Cancellation
closes outstanding quantities under the same portfolio lock as posting. It retains
already committed fills, returns the actual partial/filled outcome when posting
wins, and creates no extra event on terminal retry. It requires no market files.

## Synthetic time and worker execution

`clock_mode="synthetic_replay"`, `data_status="synthetic_fixture"` and `paper_only`
identify replay. `approved_at`/`fixture_clock_at` are logical synthetic instants;
`operator_recorded_at` records actual UTC separately in immutable ledger details.
Legacy private records without that metadata return null rather than invented
audit time. The durable replay floor includes accepted fill observation clocks,
even when an attempt fails or is cancelled. New approvals/cancellations cannot
rewind that clock. Private trusted fixture seams remain compatible.

An approval never automatically invents a future fixture clock. Explicit advance
chooses the next close in a verified pinned execution calendar and queues one
bounded existing fill attempt. A new key means another explicit step; retry keeps
the original job and time, even after cancellation or source removal. Active jobs
block overlapping new steps. Original eligible opening and next-open arithmetic
never change. A daily bar published after close can leave the first step pending;
advance later explicitly to expose that same opening evidence. Missing openings
remain pending rather than using a different day's price.

The step's recovery key is namespaced to its batch and retained in the job's
immutable correlation identity. Its work uses the existing semantic idempotency
key, so the scheduler reuses the same attempt instead of adding duplicate work.
The worker can continue remaining orders at the same persisted observation
instant, spending only durably posted sale proceeds. Restart retains pending jobs,
original keys, approval/eligibility and audit evidence; it does not advance time.
Monitoring runs only while Docker is active.

The Next.js proxy forwards only these scoped methods, valid keys and same-origin
JSON. Recovery GET forwards only its explicit key; cookies and authorization are
not forwarded. Generated types preserve exact expected-revision integer bounds
and all existing route/schema definitions. [ADR-015](../adr/0015-public-paper-controls.md)
records the ratification and required verification.
