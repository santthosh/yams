"""Synthetic sizing probes, not a financial engine or queue implementation."""

import argparse
import hashlib
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np


def measure(kind: str, size: int, sessions: int) -> dict[str, object]:
    if kind == "bars" and not (1 <= size <= 1000 and 252 <= sessions <= 2520):
        raise ValueError("WORKLOAD_LIMIT before allocation")
    if kind == "paths" and not (1 <= size <= 5000 and 1 <= sessions <= 90):
        raise ValueError("WORKLOAD_LIMIT before allocation")
    rng = np.random.Generator(np.random.PCG64(42))
    start, cpu = time.perf_counter(), time.process_time()
    if kind == "bars":
        returns = rng.normal(0, 0.01, (sessions, size))
        prices = 100 * np.exp(np.cumsum(returns, axis=0))
        volume = rng.integers(1000, 1000000, (sessions, size), dtype=np.int64)
        inputs = hashlib.sha256(prices.tobytes() + volume.tobytes()).hexdigest()
        if not (np.isfinite(prices).all() and (prices > 0).all() and (volume >= 0).all()):
            raise ValueError("Invalid synthetic inputs")
        features = np.stack(
            [
                prices[-1] / prices[-127] - 1,
                prices[-1] / prices[-64] - 1,
                np.std(np.diff(np.log(prices[-61:]), axis=0), axis=0, ddof=1),
                np.mean(prices[-200:], axis=0),
                np.median(prices[-20:] * volume[-20:], axis=0),
            ]
        )
        output = features
    else:
        # Two disjoint default eight-position portfolios need a 16-asset union.
        history = rng.normal(0, 0.01, (252, 16))
        starts = rng.integers(0, 248, (size, (sessions + 4) // 5))
        indices = (starts[:, :, None] + np.arange(5)).reshape(size, -1)[:, :sessions]
        inputs = hashlib.sha256(history.tobytes() + indices.tobytes()).hexdigest()
        shocks = history[indices]
        weights = np.full(16, 0.95 / 16)
        output = np.prod(1 + np.sum(shocks * weights, axis=2), axis=1)
        if not np.isfinite(output).all():
            raise ValueError("Nonfinite synthetic output")
    return {
        "kind": kind,
        "size": size,
        "sessions": sessions,
        "wall_seconds": time.perf_counter() - start,
        "cpu_seconds": time.process_time() - cpu,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "input_sha256": inputs,
        "output_sha256": hashlib.sha256(output.tobytes()).hexdigest(),
    }


def supervision_probe() -> dict[str, object]:
    # A separate CPU-bound child tests supervisor responsiveness, not DB heartbeats.
    child = subprocess.Popen(
        [sys.executable, "-c", "while True: sum(range(100000))"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    gaps = []
    last = time.monotonic()
    try:
        for _ in range(20):
            time.sleep(0.1)
            now = time.monotonic()
            gaps.append(now - last)
            last = now
        start = time.monotonic()
        child.terminate()
        child.wait(timeout=5)
        latency = time.monotonic() - start
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    timeout_start = time.monotonic()
    try:
        subprocess.run([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.2)
    except subprocess.TimeoutExpired:
        timeout_elapsed = time.monotonic() - timeout_start
    else:
        raise AssertionError("Timeout was not enforced")
    return {
        "supervisor_max_poll_gap_seconds": max(gaps),
        "termination_seconds": latency,
        "blocked_io_timeout_seconds": timeout_elapsed,
        "note": "Process probes only; no PostgreSQL lease/cancel claim",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["bars", "paths"])
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--sessions", type=int, default=252)
    args = parser.parse_args()
    if args.case:
        print(json.dumps(measure(args.case, args.size, args.sessions)))
        return
    records = []
    cases = [("bars", n, s) for n in (100, 500, 1000) for s in (252, 1260, 2520)]
    cases += [("paths", n, s) for n in (500, 2000, 5000) for s in (63, 90)]
    for kind, size, sessions in cases:
        for run in range(4):
            result = subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "--case",
                    kind,
                    "--size",
                    str(size),
                    "--sessions",
                    str(sessions),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            record = json.loads(result.stdout)
            record.update(run=run, warmup=run == 0, exit_code=result.returncode)
            records.append(record)
    for kind, size, sessions in (("bars", 1001, 2520), ("paths", 5001, 90)):
        try:
            measure(kind, size, sessions)
        except ValueError as error:
            assert str(error) == "WORKLOAD_LIMIT before allocation"
        else:
            raise AssertionError("Oversized request accepted")
    cgroup = {}
    for name in ("cpu.max", "memory.max", "memory.peak", "memory.events"):
        path = Path("/sys/fs/cgroup") / name
        cgroup[name] = path.read_text().strip() if path.exists() else "unavailable"
    print(
        json.dumps(
            {
                "mode": "SYNTHETIC_DATA_ONLY",
                "python": platform.python_version(),
                "platform": platform.platform(),
                "numpy": np.__version__,
                "seed": 42,
                "rng": "PCG64",
                "cgroup": cgroup,
                "records": records,
                "oversized_requests_rejected": 2,
                "process_probe": supervision_probe(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
