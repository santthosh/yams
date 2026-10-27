# Issue #23 verification checkpoint

This is an implementation checkpoint, not a delivery or release claim. The owning
issue remains open until the remaining evidence, operational documentation and
current-head PR review are complete.

## Exercised behavior

`make test-integration` ran on 2026-10-27 in disposable Compose project
`yams-it-23e58543f477`: 21 tests passed before PostgreSQL restart and one passed
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

## Remaining before delivery

- Validate deployment-supplied lower limits at startup and document configuration.
- Retain measured heartbeat/reclaim/cancellation timing, CPU and peak memory evidence.
- Complete failure-path audit, including malformed persisted payloads and process
  startup failure, and operational handoff examples.
- Review complete diff and current-head MergeWatch findings, merge, verify merged
  state and reassess dependent issues. No application Compose or release claim is
  made here; those are later 0.0.1 deliverables.

The integration suite currently emits the upstream Starlette/httpx deprecation
warning. It is not suppressed and did not fail the tests.
