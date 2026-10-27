"""Explicit operator-only destructive reset; never called during startup or tests."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    config = json.loads(
        subprocess.check_output(
            ["docker", "compose", "config", "--format", "json"], cwd=ROOT, text=True
        )
    )
    project = config["name"]
    volumes = sorted(value["name"] for value in config.get("volumes", {}).values())
    print(f"This permanently deletes local data for Compose project {project}.")
    print("Volumes: " + ", ".join(volumes))
    if input(f"Type 'delete {project}' to proceed: ") != f"delete {project}":
        raise SystemExit("Reset cancelled; no resources changed.")
    subprocess.run(
        ["docker", "compose", "-p", project, "down", "--volumes", "--remove-orphans"],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
