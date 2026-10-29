"""Bounded Linux numerical-workload probe, not securities data or investment results."""

import json
import os
import platform
import resource
import sys
import time


def main() -> None:
    if sys.platform != "linux":
        raise SystemExit(
            "Run this owned diagnostic in a Linux container with two CPUs and 2GiB RAM"
        )
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    resource.setrlimit(resource.RLIMIT_AS, (2048 * 1024 * 1024, 2048 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    import numpy as np

    from backend.forecasting.bootstrap import draw_starts, simulate

    # A neutral authored array exercises every dimension without inventing market returns.
    history = np.zeros((252, 16), dtype=np.float64)
    weights = np.full((2, 16), 0.05, dtype=np.float64)
    began = time.perf_counter()
    sampling = draw_starts(90, 42)
    paths = simulate(history, sampling.starts, weights, 90)
    elapsed = time.perf_counter() - began
    assert paths.shape == (2, 5000, 91) and np.array_equal(paths, np.ones_like(paths))
    print(
        json.dumps(
            {
                "label": "SYNTHETIC_DATA_ONLY",
                "probe": "NUMERICAL_DIMENSION_STRESS_NOT_MARKET_PERFORMANCE",
                "native_host": platform.machine(),
                "numpy_version": np.__version__,
                "assets": 16,
                "paths": 5000,
                "future_sessions": 90,
                "history_returns": 252,
                "path_shape": list(paths.shape),
                "computation_seconds": elapsed,
                "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "address_space_limit_mib": 2048,
                "cpu_seconds_limit": 10,
                "cpu_affinity_count": len(os.sched_getaffinity(0)),
                "passed": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
