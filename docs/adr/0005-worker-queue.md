# ADR-005: Durable jobs, resource budgets and restart scheduling

Status: Draft under #16. Queue design below is proposed for review; workload defaults remain unratified until the Q04 benchmark is run. Reference profile: 4 CPU cores / 8 GB RAM. No throughput or latency guarantee is claimed.

## Queue and persisted envelope

Use direct PostgreSQL `FOR UPDATE SKIP LOCKED` claiming, one worker supervisor and one executing handler at a time. Do not add Redis or a queue-library dependency. Keep the implementation small and test its transactional behavior against real PostgreSQL. A handler subprocess may isolate CPU/memory/time limits; it is part of the worker container, not a fifth service. The supervisor owns heartbeat and cancellation so a CPU-bound handler cannot starve lease renewal.

Persist `job_id`, `schema_version`, allowlisted `kind`, validated immutable payload and payload hash, idempotency key, source mode, correlation ID, status, created/scheduled/available timestamps, attempt count and maximum, progress, cancel-request time, lease owner/token/expiry, heartbeat time, attempt deadline, result references and structured error. `job_attempt` retains attempt number/token, start/end, outcome and bounded diagnostics. `schedule` retains stable schedule/version, target, next due occurrence and enabled state. Unique `(schedule_id, schedule_version, occurrence_at)` prevents repeated catch-up enqueue. No arbitrary import path, executable expression or shell command is a payload.

Each kind owns a closed versioned payload schema with immutable IDs rather than embedded datasets or credentials. Future kinds are `refresh_market_data`, `backtest`, `forecast`, `evaluate_portfolio`, `apply_scheduled_fills`, `evaluate_arena` and `mature_journal`. Foundation registers only a harmless synthetic test/diagnostic handler; it must not fabricate investment output or expose unavailable later handlers. Unknown kind/version fails validation without enqueue. API cancellation and status transport follow the endpoint ownership matrix.

Validate resource admission before enqueue and again at claim. Store effective limits with the job; changing deployment defaults does not change an already accepted job's reproducibility inputs. A semantic idempotency key plus identical payload returns the original job; key reuse with different payload returns `409 IDEMPOTENCY_CONFLICT`. Progress is advisory and bounded 0–100; only a committed successful result establishes completion.

## Claim, fencing and transitions

Use database time for lease deadlines and due ordering. A short transaction selects one due queued job ordered by `available_at`, `created_at`, then ID, locks with `SKIP LOCKED`, verifies attempts/admission, increments attempt number, creates a new unpredictable lease token, records the attempt and changes status to running. Commit before executing work. Never hold a queue-row lock through computation or network calls.

Heartbeat, progress, retries and completion update only when job ID, attempt and lease token still match and the lease has not expired. A stale worker must not renew or publish. Completion checks cancellation and lease ownership under the job lock in the same transaction that seals result references. Artifact writes use attempt-local temporary paths; only a fenced publication can expose them. Financial writes also require ADR-004 event identity and portfolio locking: queue ownership never replaces ledger idempotency. Any handler side effect must be idempotent or fenced before retries are permitted.

| From / trigger | To / durable effect |
|---|---|
| queued + due claim | running; new attempt and token, original input unchanged |
| queued + cancel | cancelled; no handler starts |
| running + cancel request | cancel_requested; record request, signal handler |
| running + successful sealed output | completed only if token current, lease valid and cancellation absent |
| running + permanent error | failed with safe code/details; no retry |
| running + retryable error | queued with backoff if attempts remain; otherwise failed |
| running + lease expiry | revoke token, mark attempt abandoned; queue a bounded retry or fail exhausted job |
| cancel_requested + handler acknowledgement/expiry | cancelled after invalidating publication authority; partial artifacts remain unsealed |
| terminal + retry/cancel delivery | return durable state; no resurrection or second output |

Cancel-versus-complete is decided under the same job lock. Completion committed first stays completed; cancellation committed first prevents completion. The supervisor checks for cancel and terminates an unresponsive handler after the configured grace period. Cancellation cannot undo a previously committed ledger event; expose its durable effects and cancel only remaining work. Expiry with a recorded cancellation never requeues the work. Explicit reruns after terminal failure use a new job referencing the failed job, not mutation of its immutable history.

## Retry classification and recovery

Bound total attempts, including abandoned claims. Retry only documented transient errors: provider timeout/temporary unavailability or throttling, temporary database connectivity and safely rolled-back serialization/deadlock failures. Respect bounded provider retry-after hints. Permanent invalid config, unsupported source/schema, missing rights, malformed input, accounting invariant failure and resource-budget exhaustion fail without automatic retry. Generic uncaught errors are not presumed transient. A poison job must eventually become failed and allow other jobs to proceed.

Backoff is exponential with a cap, recorded per attempt. A database outage means a worker cannot prove lease ownership: stop publishing immediately, stop the handler at the safe boundary and allow recovery to revalidate after connectivity returns. Recover expired jobs with row locks; two recoverers cannot create two active attempts. Do not reset attempts or original financial authorization times on restart.

## Chronological scheduling

Scheduling runs only while Docker is active. Persist intended due instants and business-session identity; restart is not an excuse to call every missed action “now.” Generate due occurrences oldest first with a bounded catch-up batch. Each handler uses the original cutoff, pinned data/calendar and approval policy. Deduplicate occurrences even if multiple schedulers race. Maintain per-target ordering: a later occurrence cannot overtake an unresolved earlier one when it depends on its state.

Historical catch-up may process previously authorized fills or matured evidence only with eligible original chronology and idempotent posting. It must not backdate a new approval or retrospectively generate supposedly prospective Arena decisions using subsequently observed facts. If required point-in-time evidence is missing, record that occurrence as missed/unavailable with its reason; do not fabricate a result. A future schedule's explicit policy determines whether stateless refresh occurrences may coalesce; coalescing is never applied to financial events by default. Catch-up limits defer remaining occurrences rather than silently deleting them. Expose downtime and backlog in status; promise no monitoring while stopped.

## Q04 benchmark and budget ratification gate

The actual inspected Docker host on 2026-10-27 is Linux arm64 through Docker Desktop, Engine 28.3.0, 16 reported CPUs and 8,217,190,400 bytes of VM memory, with other containers running. This is **not** an idle native 4-core/8-GB reference machine. Do not relabel host observations as reference-profile measurements. Run an isolated, resource-limited test project without stopping unrelated user containers; record interference and the aggregate limits of web/API/worker/Postgres. Use no user data volumes.

Before closing #16, commit measured results and ratify numeric worker CPU/memory, attempt timeout, heartbeat/lease, cancellation grace, retry/backoff, catch-up, ticker/history and forecast path/horizon limits. Until then #23 remains blocked on this ADR. #19 is independent and supplies the runtime/locked numerical dependencies needed for a representative harness. This does not create a #23→#16 prerequisite cycle.

Benchmark procedure:

1. Record CPU architecture, Docker/runtime/library versions and image digests, host/container limits, available memory, other workload interference and exact commands. Use a test allocation within the 4-core/8-GB target; do not claim CPU quotas reproduce the speed of every four-core machine.
2. Use labeled synthetic arrays and a harmless queue handler, not invented portfolio performance. Measure contiguous daily-bar validation/feature-window work at 100, 500 and 1,000 tickers with 252, 1,260 and 2,520 sessions; record accepted coverage versus resource failures. Measure bootstrap-shaped numerical work at 500 and 2,000 paths with 8 assets and 63 steps, plus one deliberately oversized rejected request. These are workload candidates, not accepted production limits.
3. Repeat each supported workload at least three times after one warm-up; retain elapsed wall time, process CPU time, peak RSS/cgroup memory, exit status and deterministic input hash. Measure sequential workloads and API/DB responsiveness concurrently with the worker. Record raw observations, not only an average.
4. Exercise an idle handler, sustained CPU handler, blocked-I/O handler, crash-after-claim and cancel race. Record heartbeat gaps, reclaim delay, cancellation delay and maximum attempts. Use explicit injected clocks for deterministic state-machine tests as well as real-clock integration measurements.
5. Choose defaults with documented headroom within the total profile; distinguish hard admission limits from measured performance and operational lease timing. Demonstrate over-limit rejection, timeout termination and memory-limit failure without partially published results. Record unsupported combinations rather than extrapolating from a tiny workload.
6. Revalidate chosen defaults with the actual #23 worker and #25 integrated Compose deployment before release. Microbenchmarks guide admission budgets but cannot establish full backtest/forecast throughput; later feature implementations rerun representative workloads before expanding limits.

## FIX-09 implementation acceptance matrix

- Two claimers race one queued job: one running attempt/token; the loser gets no claim.
- Worker dies after claim: before expiry no reclaim; after expiry one new token/attempt, prior token cannot heartbeat, publish or complete.
- Cancellation wins completion lock: terminal cancelled with no sealed result. Completion wins: terminal completed with one sealed result. Partial temporary output is never presented as completed.
- Transient failure retries to the bounded maximum; invalid input and budget exhaustion do not retry. Poison job does not starve the next due job.
- Two schedulers enqueue the same occurrence: one durable job. Restart preserves occurrence/cutoff and cannot create a past approval.
- Financial handler replay around commit: ADR-004 event key yields one durable posting even if a lease expires; cancelled jobs disclose any already committed effects.

Use a harmless synthetic handler for foundation queue proofs. Real PostgreSQL integration, process termination and resource evidence are required; a mocked in-memory queue does not prove claim/lease safety.
