"""Run the normal bootstrap and report bounded startup resource observations."""

import json
import resource
import runpy
import time
from pathlib import Path


def main() -> None:
    started = time.monotonic()
    succeeded = False
    try:
        runpy.run_module("backend.persistence.bootstrap", run_name="__main__")
        succeeded = True
    finally:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        try:
            peak: int | None = int(Path("/sys/fs/cgroup/memory.peak").read_text())
        except (OSError, ValueError):
            peak = None
        print(
            json.dumps(
                {
                    "event": "bootstrap_resources",
                    "succeeded": succeeded,
                    "wall_seconds": time.monotonic() - started,
                    "cpu_seconds": usage.ru_utime + usage.ru_stime,
                    "peak_rss_kib": usage.ru_maxrss,
                    "cgroup_memory_peak_bytes": peak,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
