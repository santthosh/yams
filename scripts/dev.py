"""Native web/API reload with a separately scoped, bounded Docker worker/database."""

import fcntl
import hashlib
import os
import re
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    project = os.environ.get("YAMS_DEV_PROJECT", "yams-dev")
    if not re.fullmatch(r"yams-dev(?:-[a-z0-9-]+)?", project):
        raise SystemExit("Development project must be yams-dev or yams-dev-<suffix>")
    api_port = int(os.environ.get("YAMS_DEV_API_PORT", "8000"))
    web_port = int(os.environ.get("YAMS_DEV_WEB_PORT", "3000"))
    for port in (api_port, web_port):
        if not 1 <= port <= 65535:
            raise SystemExit("Development ports must be between 1 and 65535")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    if api_port == web_port:
        raise SystemExit("API and web ports must differ")
    lock_name = "yams-dev-" + hashlib.sha256(project.encode()).hexdigest()[:16] + ".lock"
    with (Path(tempfile.gettempdir()) / lock_name).open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(
                "A development launcher is already running for this checkout"
            ) from None
        compose = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.dev.yaml")]
        processes: list[subprocess.Popen[bytes]] = []

        def stop(_signum: int, _frame: object) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        try:
            subprocess.run([*compose, "up", "--build", "-d", "--wait"], cwd=ROOT, check=True)
            address = subprocess.check_output(
                [*compose, "port", "postgres", "5432"], cwd=ROOT, text=True
            ).strip()
            if not address.startswith("127.0.0.1:") or int(address.rsplit(":", 1)[1]) == 0:
                raise RuntimeError("Development database must have a valid loopback port")
            env = {
                **os.environ,
                "DATABASE_URL": f"postgresql+psycopg://yams:yams_local_only@{address}/yams",
                "YAMS_FIXTURE_ROOT": str(ROOT / "data/fixtures"),
                "API_INTERNAL_ORIGIN": f"http://127.0.0.1:{api_port}",
                "NEXT_TELEMETRY_DISABLED": "1",
            }
            commands = [
                [
                    "uv",
                    "run",
                    "--locked",
                    "uvicorn",
                    "backend.api.main:app",
                    "--reload",
                    "--reload-dir",
                    "backend",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                ],
                [
                    "pnpm",
                    "--filter",
                    "@yams/web",
                    "exec",
                    "next",
                    "dev",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
            ]
            for command in commands:
                processes.append(
                    subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True)
                )
            print(
                f"Development UI: http://127.0.0.1:{web_port}; "
                "Ctrl-C stops services, retains volumes.",
                flush=True,
            )
            while all(process.poll() is None for process in processes):
                time.sleep(0.2)
            raise SystemExit("A native development process exited; stopping the development stack")
        except KeyboardInterrupt:
            pass
        finally:
            # Do not let a second interrupt prevent cleanup of processes owned by this launcher.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            for process in processes:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            subprocess.run([*compose, "down"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
