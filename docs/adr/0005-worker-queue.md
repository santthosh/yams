# ADR-005: Durable jobs, resource budgets and restart scheduling

Status: Proposed for final review under #16; accepted when this PR merges. Q04 resource measurements are recorded in [the evidence report](../verification/16-resource-budgets/README.md). Reference profile: 4 CPU cores / 8 GB RAM. No throughput or latency guarantee is claimed.

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

## Measured initial budgets and Q04 validation

The actual inspected Docker host on 2026-10-27 is Linux arm64 through Docker Desktop, Engine 28.3.0, 16 reported CPUs and 8,217,190,400 bytes of VM memory, with other containers running. This is **not** an idle native 4-core/8-GB reference machine. Do not relabel host observations as reference-profile measurements. Run an isolated, resource-limited test project without stopping unrelated user containers; record interference and the aggregate limits of web/API/worker/Postgres. Use no user data volumes.

The committed harness ran 15 synthetic workload combinations, each with one warm-up and three measured processes, under 2 CPUs / 2 GiB with network disabled. All repeated input/output hashes matched. Peak process RSS was 178,440 KiB; the largest bar case took 0.121 seconds or less in its measured numerical section. These are sizing probes, not whole-job benchmarks. Detailed raw timings, process probes and the deliberately enforced OOM result are in the evidence report. #23 must prove the real queue transitions and resource enforcement; #25 must validate aggregate application responsiveness before release. This ADR does not pretend those later proofs ran.

| Setting | Initial default / hard admission ceiling | Rationale and implementation obligation |
|---|---|---|
| Active handlers | 1 | Single bounded worker, separate supervisor; one numerical thread per handler |
| Worker resources | 2 CPUs, 2 GiB, no swap, 64 PIDs | Measured probe envelope; leaves room within the reference profile for other services |
| Attempt wall deadline | 300 seconds | Operational ceiling with substantial probe headroom, not promised latency; includes handler I/O; terminate on expiry, never publish partial result |
| Heartbeat / lease | Every 5 seconds / expire after 30 seconds | Six heartbeat intervals; separate supervisor poll gap measured <0.107 seconds; actual DB heartbeat recovery remains #23 verification |
| Supervisor poll / cancel grace | 0.1 seconds / 5 seconds | Measured process termination <0.003 seconds; tolerate slower graceful cleanup, then kill and invalidate publication |
| Attempts / backoff | 3 total; 1 then 2 seconds; maximum provider retry-after 30 seconds | Bounded recovery; permanent errors, OOM and timeout do not retry automatically |
| Catch-up enqueue / tick | 100 occurrences / 5 seconds | Bounded administrative batch, not measured financial throughput; preserve remaining backlog |
| Bar workload | <=1,000 assets and <=2,520 scheduled sessions, <=2,520,000 asset-session cells | Largest tested dense matrix; includes requested warm-up/coverage, not only reported output period |
| Forecast workload | <=5,000 paths, <=90 sampled exchange steps, <=16 union assets, <=7,200,000 path-step-asset cells | Includes two disjoint default eight-position portfolios; model horizon remains 90 calendar days, not 90 trading days |

Reject over-budget work with `422 WORKLOAD_LIMIT` before enqueue/allocation, including individually legal dimensions whose product exceeds the ceiling. A wider current/proposed asset union is explicitly unavailable under the initial forecast budget; do not drop holdings or sample fewer paths silently. Runtime memory exhaustion is `RESOURCE_EXHAUSTED`; deadline expiry is `TIME_LIMIT`; neither output is complete. Reject malformed/negative limit configuration at startup. Configuration can lower limits; raising validated workload ceilings requires repeat measurements and versioned job limits. Resource ceilings never override domain minimum-history or forecast-method requirements.

For #25's aggregate test, allocate at most worker 2 CPUs/2 GiB, web 1 CPU/1 GiB, API 0.5 CPU/512 MiB and PostgreSQL 0.5 CPU/1 GiB: 4 CPUs and 4.5 GiB total, leaving host/VM headroom within the 8-GB reference. These are initial deployment caps to verify under integrated load, not independent performance claims. Startup/migration peak use also needs measurement. No unrelated running containers were stopped for the probe.

Benchmark procedure:

1. Record CPU architecture, Docker/runtime/library versions and image digests, host/container limits, available memory, other workload interference and exact commands. Use a test allocation within the 4-core/8-GB target; do not claim CPU quotas reproduce the speed of every four-core machine.
2. Use labeled synthetic arrays and a harmless queue handler, not invented portfolio performance. Measure contiguous daily-bar validation/feature-window work at 100, 500 and 1,000 tickers with 252, 1,260 and 2,520 sessions; record accepted coverage versus resource failures. Measure bootstrap-shaped numerical work at 500, 2,000 and 5,000 paths with a 16-asset union and 63/90 steps, plus deliberately oversized rejected requests. The committed numerical probe covers these combinations; real queue and full-engine checks remain with implementation owners.
3. Repeat each supported workload at least three times after one warm-up; retain elapsed wall time, process CPU time, peak RSS/cgroup memory, exit status and deterministic input hash. Measure sequential workloads and, in #25, API/DB responsiveness concurrently with the worker. Record raw observations, not only an average.
4. The initial probe exercises sustained CPU, blocked-I/O timeout and termination. In #23 exercise an idle handler, crash-after-claim and cancel race. Record actual DB heartbeat gaps, reclaim delay, cancellation delay and maximum attempts. Use explicit injected clocks for deterministic state-machine tests as well as real-clock integration measurements.
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
