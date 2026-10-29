# Monthly portfolio reviews and restart catch-up (#51)

This is the0.0.5 source increment. It schedules analysis, never approval or trades.
The Decision Center screen remains #52 and the packaged core release #53; published
0.0.4 assets retain their original behavior. All current portfolio accounting is
`SYNTHETIC_DATA_ONLY`; real providers remain diagnostic-only for accounting.

## Time and explicit observation

The immutable strategy policy is monthly. A review anchor is the last pinned
trading session before the first pinned session in the next month; its intended
cutoff is that next opening minus one hour. Truncated calendars cannot invent a
month end, following opening or review opportunity. The opportunity stays current
until a later decision session's canonical cutoff elapses. Older opportunities
are recorded as missed, rather than recommendations supposedly made while the
application was stopped.

Synthetic time advances through explicit observations: original ledger chronology,
accepted fixture-fill steps and an explicitly requested manual review's selected
canonical cutoff. A cash-only account needs no fake order to select a later
synthetic review session. For example, the existing manual route accepts:

```text
POST /api/v1/portfolios/{id}/recommendations
```

```json
{"as_of_session":"2028-07-31","clock_mode":"synthetic_replay","seed":42}
```

The date must be covered by the selected verified snapshot. Selecting a later
session advances the durable synthetic review observation; it changes no cash,
holding, order or approval. The accepted run is immutable and a target projection
retains the maximum explicit cutoff. A rejected/rolled-back admission advances
nothing. Once accepted, cancelling/failing its computation does not rewind the
chosen observation. Exact key retry recovers that original request. Older manual
inspection cannot rewind time or make a newly computed result appear to have
been created at the older logical cutoff. Actual admission/history and computation
UTC remain separate from synthetic request/creation time.

The scheduler must prove a cutoff is already due under that prior clock. It never
updates the explicit observation itself. A GET, forecast, newer future-dated
fixture publication, worker restart or passage of wall time cannot move synthetic
time forward. Existing approved fills retain their original eligibility and
observation; catch-up does not backdate a new authorization.

## Bounded execution and persistence

The single supervisor scans active targets fairly within the existing catch-up
budget, processes the oldest observed occurrence first and preserves strict
per-portfolio order. Up to one review is admitted per tick. Missed metadata uses
the remaining bounded allowance; remaining work stays deferred. Heavy source
verification/admission runs between handlers so it cannot block their heartbeat.
Lightweight supervisor observations continue during handler heartbeats.

Each due occurrence retains its intended session/cutoff, original observation and
source, outcome and linked immutable job/recommendation. Missing source/coverage
waits with a reason while the opportunity remains current. Later compatible data
can satisfy it; a passed window becomes missed. Posted state after the original
cutoff is skipped, never rewritten into historical holdings. Stored calendar
cutoffs cannot silently move after a publication change. An active approved batch
or unresolved earlier review defers state-dependent review; unrelated work can
continue. No source error fabricates a price, score or scenario.

Admission freezes current posted state through the existing shared service. The
job/run, occurrence link and handled checkpoint commit together. Manual-first,
scheduled-first and concurrent equivalent requests reuse one original resource
when revision, config/version, resolved source/calendar/build, session/mode and
seed match. Existing independent manual reruns without a scheduled association
retain their behavior. Failed/cancelled/dismissed/expired results are not silently
resurrected. A new explicit request key that reuses a result gets its own immutable
canonical-input alias; changed input under that key still conflicts and exact
retry precedes source-file/freshness checks. Resolved snapshot equivalence does
not rewrite an original request's input bytes.

Migration0009 adds review targets/occurrences, request aliases and observed
supervisor gaps. It backfills explicit manual cutoffs from existing runs without
changing their payloads, original statistics, funds or jobs. Database guards keep
explicit clock/checkpoints monotonic and handled occurrences/aliases immutable.
Normal startup/migration never resets user volumes. Original completed artifacts
remain original; an accepted numerical job cannot silently run under a different
engine build merely because software was upgraded.

## Readonly status

`GET /api/v1/portfolios/{id}/schedule` returns `PortfolioScheduleV1`. It performs
no enqueue, repair, checkpoint update or time advance. Unknown accounts return404,
invalid IDs422 and unavailable storage/integrity503.

- `clock_at` is the current durable replay clock (actual UTC for real mode);
  `observed_clock_at`/`last_observed_at` describe the last supervisor target scan.
  `last_explicit_review_cutoff` records the latest accepted manual selection.
- `next_review_session` and `next_review_due_at` are paired or null with an honest
  reason. `due_backlog` is nullable when the next opportunity is not yet known;
  unknown backlog is never represented as zero work.
- `recent_occurrences` contains at most25 latest records. Full occurrence history
  remains in PostgreSQL. Each admitted record exposes its real job state and
  original recommendation; waiting, missed and skipped have explicit reasons.
- `active_order_batch_id` identifies outstanding authorized intent. The separate
  controls-available flag distinguishes public recommendations from legacy private
  diagnostic batches; status never invents public controls for such a fixture.
- `supervisor` distinguishes fresh, stale and unobserved actual heartbeats. The
  last unobserved interval starts at the last observed heartbeat, not a claimed
  exact shutdown instant. Its limitation is explicit in the response.

Monitoring runs only while Docker is active; closing the browser alone does not
stop Docker. Show `Monitoring paused while YAMS was closed` with the observed
interval and Docker qualification. Never promise24/7 monitoring or infer the exact
shutdown time from a heartbeat gap. The [ADR](../adr/0016-portfolio-review-scheduler.md)
records this boundary; #52 owns its accessible screen presentation.
