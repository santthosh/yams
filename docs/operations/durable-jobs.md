# Durable job operations

The foundation `diagnostic` handler remains a labeled synthetic integer sum, not
a financial calculation. Unknown kinds and payload fields fail before enqueue.
The typed payload is `{"schema_version":1,"work_units":10}`; work units must be
an integer from zero through one million. Ten units produce the independent
integer sum 45. The sealed result has kind `diagnostic`, no financial resource ID,
and a fixed synthetic message; its durable effect lives in `job_diagnostic_effect`.

The current source also registers `refresh_market_data`, `evaluate_strategy`,
`backtest_core`, `backtest`, `evaluate_portfolio`, `forecast` and
`apply_scheduled_fills`. Their owning admission services pin validated immutable
inputs and own fenced publication; the diagnostic example below cannot enqueue
arbitrary financial work. See [market refresh](market-refresh.md),
[candidate inspection](strategy-evaluations.md), [experiments](experiment-api.md),
[recommendations](recommendations.md), [forecasts](scenario-forecasts.md) and
[private paper batches](paper-batches.md). Public job cancellation is implemented;
paper approval/dismissal/batch transport remains #50. The optional
[Tiingo workflow](tiingo-research.md) remains diagnostic-only for accounting.

## Startup and configuration

Apply `make db-bootstrap` before starting API or worker. Migration `0002_jobs`
adds `job`, `job_attempt`, `schedule` and `job_diagnostic_effect`; it preserves the
workspace. Standalone worker startup does not migrate; application Compose runs
its migration service before API/worker readiness. `DATABASE_URL` must use the
private `postgresql+psycopg://` service described in README. Never publish its port.

Run `python -m backend.jobs.worker` in the installed Linux worker environment.
The worker refuses unbounded cgroup-v2 CPU/memory/PID settings or nonzero swap:
maximum 2 CPUs, 2 GiB memory and 64 PIDs. It is intentionally not a native macOS
worker. Application image/Compose wiring is delivered by #25; `make dev` uses
the approved native web/API plus Docker worker/database workflow. The isolated
integration harness remains the resource-enforced test path.

`YAMS_JOB_LIMITS` is an optional JSON object of lower defaults, for example
`{"wall_seconds":60,"memory_mib":1024}`. Missing fields retain ADR-005 defaults;
unknown fields, nonintegers, negatives, over-ceiling settings and heartbeat >=
lease are rejected. Worker startup fails with a safe message, without echoing
configuration. Queue construction also validates it. `.env` is not loaded
implicitly: export settings in the service environment.

Defaults are three attempts, 300-second wall deadline, 5-second heartbeat,
30-second lease, 100-ms status poll, 5-second cancellation grace, one numerical
thread, catch-up of 100 occurrences per 5-second tick, and the resource ceilings
above. Effective limits are persisted with each accepted job. Changing defaults
only affects new admissions; it does not rewrite existing job/schedule inputs.
Server-owned callers may supply a validated `JobLimits` explicitly within the
same ADR hard ceilings. Lower per-job memory uses Linux address-space limits;
lower CPU count restricts affinity. The container ceiling still bounds the whole
supervisor/child service. Do not shrink deployment resources below accepted job
requirements without draining or cancelling those jobs first.

## Internal service example

Run this from the installed backend environment with the private database URL
set, after bootstrap. Reuse the same idempotency UUID for retries of this request;
choose a new UUID for a genuinely new job. Reusing a key with changed inputs raises
`IdempotencyConflict` rather than silently changing the first job.

```python
from uuid import UUID
from backend.jobs.queue import Queue
from backend.persistence.database import Settings, database_engine

settings = Settings.from_environment()
assert settings.database_url is not None
engine = database_engine(settings.database_url)
try:
    queue = Queue(engine)
    job_id = queue.enqueue(
        "diagnostic",
        {"schema_version": 1, "work_units": 10},
        UUID("8a296977-f34d-4a35-a877-eb600975eab3"),
    )
    print(job_id)
    print(queue.get(job_id))
    # Internal cancellation, when intended: queue.cancel(job_id)
finally:
    engine.dispose()
```

`GET /api/v1/jobs/<printed-UUID>` returns the same public status view; missing jobs
return `404 NOT_FOUND`, unavailable storage returns `503 NOT_READY`. GET never
claims, recovers or cancels. The public cancellation POST is deliberately absent
until #41. Errors preserve the originating correlation ID, with safe messages.

For a fixed-second synthetic schedule, use `queue.create_schedule("diagnostic",
payload, target="diagnostic-example", first_due_at=<UTC datetime>,
interval_seconds=60)`. The worker calls `catch_up` while active, preserving each
original due time and atomically advancing the cursor. Batches defer remaining
backlog. Schedule definitions are immutable; changes require a new schedule ID,
with the old schedule disabled through an authorized administrative transaction.
Existing occurrence identities and job inputs remain unchanged. The current application
has no schedule UI or financial/calendar scheduler. No monitoring occurs while
Docker is stopped. Inspect `schedule.next_due_at` and queued job timestamps for
backlog; no public schedule-status endpoint is claimed.

## Recovery and diagnostics

Claims use short PostgreSQL row locks with `SKIP LOCKED`; computation holds no job
row lock. Attempt/token/unexpired-lease checks fence heartbeat and publication.
Completion and cancellation serialize under the same job lock. Diagnostic effect
and completed result commit together. A killed supervisor cannot leave its child
executing: the child sets Linux parent-death SIGKILL and checks the expected parent.
The worker also uses a session advisory lock to prevent duplicate supervisors
from claiming concurrently during normal operation.

Only explicitly transient provider failures request immediate retries, with
1/2-second exponential backoff and retry-after capped at 30 seconds. A database
operation failure stops the child and publication; the abandoned lease is recovered
after connectivity returns, subject to the same three-attempt bound. Transaction
rollback also applies to serialization/deadlock failures. Generic exceptions,
invalid input, timeout and memory/resource failures are permanent. A poisoned
payload is marked failed and does not starve the next claim. A queued cancel is
terminal immediately; running cancellation signals the child, then kills it after
grace. Cancellation winning the lock prevents sealed output.

Inspect `job_attempt` for start/end, outcome, backoff, elapsed time, largest observed
heartbeat gap, child CPU time and peak RSS in KiB. Successful child RSS includes
its kernel high-water value; terminated children use sampled `/proc` high-water
values, which may miss a final spike. Metrics can be absent if a supervisor dies
or loses its lease before recording them. They are observations, not completion
proof. Only a committed terminal state and sealed result establish success.

The unit suite tests contracts without a database; `make test-integration` uses a
fresh isolated PostgreSQL project and real Linux processes. It removes only its
own resources and retains measured JSON outside the containers. See the linked
verification report before interpreting resource measurements as performance.
