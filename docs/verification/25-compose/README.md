# Issue #25 — integrated foundation verification

Status: implementation evidence, not a completed issue or release. Q14 approves
native web/API hot reload with a bounded Docker worker and PostgreSQL. No 0.0.2 work is
included. Operational commands are in [local-compose](../../operations/local-compose.md).

## Reproduction and observed scope

On 2026-10-27, `make smoke` passed in disposable project
`yams-smoke-b3228f375c6b`. [Raw evidence](evidence.json) records workspace/job IDs,
fixture hash, image IDs, actual container limits/ports, startup/load observations
and every HTTP sample. Only that project's volumes were removed. Existing unrelated
containers remained running and are identified in the record.

The test boots four services and one successful migration/seed with no provider
keys. It visits the actual Docker web/API/database/worker at 360px and 1280px,
checks labeled synthetic metadata and a real persisted completed diagnostic job,
and rejects external browser requests. API and worker have no external routing.
It verifies read-only fixtures, workspace/job/fixture/artifact preservation after
restart, cached-image startup without builds/pulls, rebuild/recreation, private
API/PostgreSQL ports and a loopback-only web port.

The [migration failure log](migration-failure.txt) records startup refusing an
invalid migration revision. The test inspects API/worker/web as not running,
repairs only its disposable revision, then verifies the same workspace after
recovery. This injection is never applied to operator data.

- [Mobile Dashboard](dashboard-360.png)
- [Desktop Settings and persisted job](settings-1280.png)

## Resource observations

Host: Docker Desktop Linux aarch64 VM, Engine 28.3.0, 16 reported CPUs and
8,217,190,400 bytes of memory. This is not an idle native four-core reference
machine. Concurrent host checks/builds and unrelated containers can affect timing.
The actual four-service allocation is capped at four CPUs and 4.5 GiB, with no
swap; migration runs before application services at 0.5 CPU/512 MiB.

One warm-up precedes three measured batches of twelve maximum-size registered
diagnostic jobs (one million integer work units each). The independent result is
`999999 * 1000000 / 2 = 499999500000`; every persisted effect matches. Payload
hashes, attempt CPU/RSS and raw health/workspace timings are retained. API reads
exercise PostgreSQL while the serial worker has pending/running work.

| Measured batch | Elapsed seconds | HTTP sample pairs | Max health seconds | Max workspace seconds |
|---|---:|---:|---:|---:|
| 1 | 4.822 | 65 | 0.029 | 0.009 |
| 2 | 4.794 | 65 | 0.012 | 0.024 |
| 3 | 4.784 | 65 | 0.043 | 0.018 |

Observed cgroup peaks after load: API 128,163,840 bytes; worker 107,667,456;
web 86,708,224; PostgreSQL 88,952,832. Fresh migration reported 0.740 seconds
wall time, 0.418 CPU seconds and a 51,613,696-byte cgroup peak. Process RSS and
cgroup memory are separate kernel observations; neither substitutes for the other.
Startup-only service peaks are also recorded before load.

These results prove the diagnostic foundation remains responsive under its caps.
They do not prove backtest/forecast throughput or justify larger admission limits.
The numerical probes in #16 and process/recovery tests in #23 retain their own
scope; future financial handlers must be measured when implemented.

## Other gates and corrections

Lint and strict Python/TypeScript typing passed. The current source passed 149
Python unit tests, 42 web tests, contract drift, all 23 fixture files, backend/web
builds and ten controlled-transport browser tests. Docker-specific browser checks
are additional to those ten tests. No GitHub Actions run is claimed before #26.
All 37 real PostgreSQL/process/resource/restart integration tests passed in disposable project yams-it-78c54d7048d2; its worker measurements remain under test-results/integration/.

Development failures were retained under ignored `test-results/smoke`: concurrent
exports to one backend image tag were corrected by giving migration sole build
ownership; internal-only web networking prevented host access; a later recreation
failed host access with two equal-priority networks. Explicit ingress gateway
priority and per-phase valid-port assertions passed the subsequent complete runs.
The latter is an evidence-backed correction, not proof of all Docker versions.
Docker builds select standalone Next output; local builds keep standard output so
`next start` works without the standalone warning.

The reset cancellation path was exercised with a nonmatching response and made no
resource changes. Destructive operator reset was not run. Developer verification is recorded below. Final issue completion
still requires current-head PR review and merged-state verification.

## Approved developer workflow

Q14 was approved by the user. On macOS arm64, the actual launcher started native
Uvicorn (8115) and Next development (3115) with project yams-dev-verify-q14.
The native API/web proxy returned ready with persisted workspace
`c5685340-60ee-4298-acf1-4ea95711e680`; the bounded container worker completed
diagnostic job `c4b6a053-a428-442e-81ec-d233cab2c56e`, read through the native web proxy.
Touching the API source triggered StatReload and replaced server PID 25197 with
25279; readiness recovered. The browser hot-reload probe changed a temporary
route from Reload before to Reload after without page.reload(), then removed
only its own temporary route. SIGTERM to the launcher stopped native processes
and its Compose project cleanly while retaining the development volumes.
Starting that same disposable project again recovered the identical workspace ID
and completed job from PostgreSQL. Both native ports were closed after shutdown.
Only the verification project's volumes were removed after this retention check.

`apps/web/tests/dev-reload.mjs <loopback-origin>` reproduces the web reload probe
against a running dev server. It refuses an existing probe directory and cleans
up its own source file. Next automatic agent-file generation is disabled to avoid
rewriting repository instructions during normal development.
