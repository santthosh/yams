# Initial resource sizing — #16

Measured 2026-10-27. [Raw observations](results.json) are labeled `SYNTHETIC_DATA_ONLY`. No result is an investment forecast, an engine validation or a throughput SLA.

## Reproduction

```sh
uv export --only-group benchmark --no-emit-project --format requirements-txt --output-file tools/benchmarks/requirements.txt
docker build -t yams-resource-probe:16 tools/benchmarks
docker run --rm --network none --read-only --cpus 2 --memory 2g --memory-swap 2g --pids-limit 64 yams-resource-probe:16
```

Python 3.13.12 / NumPy 2.5.4, PCG64 seed42, one numerical thread. Dependencies are hash-locked from `uv.lock`'s isolated benchmark group; the app does not acquire a NumPy runtime dependency from this probe. Image base: `python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8`. Measured final image ID: `sha256:babf34108f8f1699cf5877a229095172c3d3c8c46d823e391c6f681b400ec759` (local image, not a published application artifact).

Actual host: Docker Desktop / Linux arm64, Engine28.3.0, 16 reported CPUs, VM memory8,217,190,400 bytes. Other user containers remained running. The benchmark container used 2 CPUs/2 GiB, verified from cgroup values in the raw report. These are constrained-host observations within the proposed worker share of a 4-core/8-GB deployment, not an idle native reference-machine certification. No aggregate application performance was measured.

## Results and interpretation

Each of 15 cases ran in four fresh child processes (first marked warm-up, next three measured). All input/output hashes agreed across repetitions. The 27 measured bar cases covered 100/500/1,000 assets × 252/1,260/2,520 sessions; the 18 measured path cases covered 500/2,000/5,000 paths × 63/90 steps with 16 assets. The probe generates and validates dense synthetic numerical inputs, computes representative window operations or block-shaped sampling, and hashes output. It does not perform actual source normalization, Decimal ledger accounting, disk snapshots, portfolio forecasts or database jobs.

| Observation | Result |
|---|---:|
| Largest measured bar numerical section | 0.120262 seconds |
| Largest measured path numerical section | 0.016586 seconds |
| Largest bar process peak RSS | 178,440 KiB |
| Largest path process peak RSS | 160,324 KiB |
| Container memory peak before process probes | 186,028,032 bytes |
| Numeric matrix OOM events | 0 |
| Oversized admission probes rejected before allocation | 2 |
| Maximum supervisor polling gap during CPU-bound child | 0.106044 seconds |
| Child termination latency | 0.002493 seconds |
| Blocked-I/O child timeout (requested0.2s) | 0.201278 seconds |

The elapsed numerical sections exclude Python/NumPy process startup; peak RSS includes the child process. Raw measurements retain CPU time, exit status, dimensions and hashes. Supervisor observations measure OS process behavior, not DB heartbeat/lease semantics. They justify headroom and an independent supervisor but cannot prove exactly-once financial effects.

A separate disposable container ran this deliberate memory-failure probe:

```sh
docker run --name yams-resource-oom16 --network none --read-only --cpus 1 --memory 64m --memory-swap 64m --pids-limit 16 --entrypoint python yams-resource-probe:16 -c 'x = bytearray(512 * 1024 * 1024)'
docker inspect yams-resource-oom16 --format '{{json .State}}'
docker rm yams-resource-oom16
```

Observed exit137, `OOMKilled=true`, started `2026-10-27T17:21:34.468581344Z`, finished `2026-10-27T17:21:34.525813761Z`. The container was removed afterward. This used the immediately preceding image with an eight-asset numerical probe; the memory-failure command overrides the entrypoint and imports no NumPy, so its enforced allocation is independent of that matrix width. It produced no application output or mounted files. #23 must prove an actual worker converts resource failure into a durable failed attempt with no sealed partial result.

## Ratified scope and remaining gates

[ADR-005](../../adr/0005-worker-queue.md) chooses one handler, 2 CPUs/2 GiB and the tested dimension ceilings. A 300-second attempt deadline is a conservative operational ceiling, not extrapolated execution time. Heartbeat/lease/cancellation settings leave margin above measured process polling delays; they still require real PostgreSQL tests. Forecast default5,000 paths is preserved; oversized union/history requests fail explicitly rather than silently changing model parameters.

#23 owns claim races, expiry fencing, durable cancellation, timeout/OOM failure publication, idle/CPU/I/O handler tests and real-clock recovery. #25 owns API/DB responsiveness, startup peaks and full-stack resource caps within the reference profile. Later financial engines must repeat representative whole-job measurements before claiming throughput or raising limits. These are required downstream gates, not work falsely marked passed in this report.
