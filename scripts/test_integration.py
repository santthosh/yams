"""Own a unique disposable Compose project; never access existing user volumes."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    exported = subprocess.check_output(
        [
            "uv",
            "export",
            "--locked",
            "--format",
            "requirements-txt",
            "--no-emit-project",
            "--no-header",
        ],
        cwd=ROOT,
        text=True,
    )
    committed = (ROOT / "infra/docker/integration-requirements.txt").read_text().splitlines()
    while committed and committed[0].startswith("#"):
        committed.pop(0)
    if exported.splitlines() != committed:
        raise SystemExit("Integration dependency drift: regenerate integration-requirements.txt")
    project = "yams-it-" + uuid4().hex[:12]
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(ROOT / "infra/docker/integration.compose.yaml"),
    ]
    configuration = json.loads(subprocess.check_output([*compose, "config", "--format", "json"]))
    if any(service.get("ports") for service in configuration["services"].values()):
        raise SystemExit("Integration services must not publish host ports")
    try:
        subprocess.run([*compose, "up", "-d", "--wait", "postgres"], check=True)
        subprocess.run([*compose, "run", "--build", "--rm", "test"], check=True)
        subprocess.run([*compose, "restart", "postgres"], check=True)
        subprocess.run([*compose, "up", "-d", "--wait", "postgres"], check=True)
        subprocess.run(
            [
                *compose,
                "run",
                "--rm",
                "test",
                "python",
                "-m",
                "pytest",
                "backend/tests/integration",
                "-m",
                "restart_verify",
                "-p",
                "no:cacheprovider",
            ],
            check=True,
        )
        print(f"PostgreSQL bootstrap/restart verified in isolated project {project}")
    finally:
        # Only resources created with this random project label are removed.
        subprocess.run([*compose, "down", "--volumes", "--remove-orphans"], check=True)


if __name__ == "__main__":
    main()
