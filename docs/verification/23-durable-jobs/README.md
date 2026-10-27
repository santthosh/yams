# Issue #23 durable-job verification

The implementation and verification below are complete locally. PR review, merge
and merged-state verification are tracked in #23; this report is not a milestone
release claim. Operational examples are in [worker operations](../../operations/durable-jobs.md).

## Exercised behavior

`make test-integration` ran on 2026-10-27 in disposable Compose project
`yams-it-cacb6b6b3761`: 36 tests passed before PostgreSQL restart and one passed
after restart. The runner removed only its own database/evidence volumes and
network. Test supervisor and child share enforced limits of 2 CPUs, 2 GiB memory,
zero swap and 64 PIDs. Python is 3.13.12; the pinned PostgreSQL/Python image digests
are in `infra/docker/integration.compose.yaml` and `integration.Dockerfile`.
These are local Docker Desktop Linux arm64 observations, not an idle native
four-core reference-machine benchmark or throughput guarantee.

- Upgrade from populated workspace schema preserves UUID and preferences.
- Concurrent enqueue deduplicates identical inputs; conflicting key reuse fails.
  PostgreSQL rejects mutations of immutable job and schedule inputs.
- Concurrent claims and held-row contention exercise real `SKIP LOCKED` behavior.
- Injected-clock recovery rejects stale tokens, retains abandoned attempts and
  stops at three attempts. Retry-after is capped; resource errors do not retry.
- Cancel-before-completion seals no output; completion-before-cancel remains
  completed. Queued cancellation prevents claim. GET is read-only; public POST
  cancellation is not exposed in this milestone.
- Concurrent scheduler catch-up preserves original due times, bounded batches,
  unique occurrences and a restart-safe cursor. Later target jobs wait for both
  queued earlier occurrences and earlier occurrences not yet materialized.
- The supervisor renews a two-second lease while an idle child runs for 2.5 seconds.
- Deadline termination, memory allocation failure and abrupt handler exit fail
  without a sealed diagnostic effect. An unresponsive cancelled handler is killed.
- A real supervisor SIGKILL terminates its child via Linux parent-death protection.
  The live lease cannot be reclaimed early; recovery completes on attempt two,
  leaving exactly one durable diagnostic effect with integer value 45.
- A separate supervisor exits immediately after committing completion. A subsequent
  worker observes terminal state, does not replay, and retains one effect/attempt.

The harmless diagnostic sums integers `0..work_units-1`; this is not market data
or investment output. Expected value 45 for ten integers is independently fixed
in tests. Only the diagnostic kind is registered. Schedules currently express
fixed-second diagnostic intervals, not exchange calendars or financial policies.

## Retained measurements and quality gates

Raw observations: [worker.json](worker.json). Idle and CPU-bound cases each ran
once as warm-up and three measured times, with a one-second heartbeat and
two-second lease. Each test runs a new child process. Elapsed values include
process startup, supervision and database work; CPU time includes child startup.
The CPU-bound/idle bodies last 2.5 seconds and both return the fixed diagnostic
result. This does not measure financial throughput.

| Case (three measured runs) | Wall seconds | Child CPU seconds | Largest heartbeat gap, seconds | Peak RSS, KiB |
|---|---:|---:|---:|---:|
| idle_handler | 3.145–3.188 | 0.632–0.640 | 1.090–1.109 | 113516–114028 |
| busy_handler | 3.089–3.096 | 3.088–3.096 | 1.081–1.097 | 113516–114668 |

Unresponsive-child cancellation completed in 1.174 seconds with
a one-second grace. Recovery after supervisor SIGKILL completed in
2.799 seconds using the two-second lease and one-second backoff;
it used two attempts and produced one effect. Crash-after-commit remained complete
with one attempt and one effect. Injected-clock tests independently prove the
three-attempt ceiling, 1/2-second backoff and 30-second retry-after cap.

Resource/error records include TIME_LIMIT, RESOURCE_EXHAUSTED, JOB_FAILED and
VALIDATION_ERROR, all without a completed partial result. The worker also passed
process-start allocation failure and a deliberately stalled supervisor read: the
child's independent kernel wall timer killed it before the read returned. The
wall timer uses [Python's Unix interval timer](https://docs.python.org/3.13/library/signal.html#signal.setitimer)
with the default SIGALRM action, not a delayed Python signal callback.

`make lint typecheck test contracts-check fixtures-check build test-integration`
passed: 149 Python unit tests, four web tests, all 23 fixture files, generated
contracts, strict Python/TypeScript checks and Python/Next production builds.
The final invalid-output change additionally passed lint, strict Python typing
and the full 37-check PostgreSQL suite (36 before restart plus one afterward).
Startup validation rejects malformed/larger limits; accepted jobs preserve their
old limits after deployment defaults change. Poisoned payloads fail without
starving the next job. Concurrent cancel/complete and concurrent recovery tests
verify one legal state transition.

## Limitations

Only diagnostic execution and fixed-second synthetic schedules are implemented.
Financial/calendar handlers and public cancellation remain with their owning
issues. Application Compose, aggregate responsiveness and dual-architecture
release installation remain later 0.0.1 gates. No user volumes or unrelated
containers were stopped. Whole-service limits were enforced; the shared host is
not an isolated native four-core machine. Peak RSS for forcibly terminated
children is sampled and can miss a final spike; successful-child RSS also uses
the kernel high-water measurement. Measurements may be absent for an attempt
that loses authority or dies before its metrics transaction commits.

The integration suite currently emits the upstream Starlette/httpx deprecation
warning. It is not suppressed and did not fail the tests.
