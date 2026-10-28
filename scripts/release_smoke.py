"""Anonymous fresh installation of the packaged manifest on a native runner."""

import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    bundle = ROOT / "release-bundle"
    provenance = json.loads((bundle / "provenance.json").read_text())
    checksum_names = []
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if name not in {"compose.yaml", ".env.example", "INSTALL.md", "provenance.json"}:
            raise SystemExit("Unexpected checksum path")
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
        checksum_names.append(name)
    assert len(checksum_names) == 4 and set(checksum_names) == {
        "compose.yaml",
        ".env.example",
        "INSTALL.md",
        "provenance.json",
    }
    expected_arch = os.environ["RELEASE_ARCH"]
    assert expected_arch in {"amd64", "arm64"}
    assert (
        platform.machine()
        in {"amd64": ("x86_64", "AMD64"), "arm64": ("aarch64", "arm64")}[expected_arch]
    )
    config = json.loads((bundle / "compose.yaml").read_text())
    for section in ("volumes", "networks"):
        assert all(
            not value.get("external") and not value.get("name")
            for value in config[section].values()
        )
    project = "yams-release-smoke-" + uuid4().hex[:12]
    destination = ROOT / "test-results" / "release" / expected_arch
    destination.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {
        "project": project,
        "native_host": platform.machine(),
        "source_sha": provenance["source_sha"],
        "checks": [],
    }
    with tempfile.TemporaryDirectory(prefix="yams-anonymous-") as docker_config:
        env = {
            **os.environ,
            "DOCKER_CONFIG": docker_config,
            "YAMS_WEB_PORT": "0",
            "YAMS_JOB_LIMITS": "{}",
        }
        compose = ["docker", "compose", "-p", project, "-f", str(bundle / "compose.yaml")]

        def run(*args: str) -> str:
            return subprocess.check_output([*compose, *args], env=env, text=True).strip()

        def python(code: str) -> str:
            return run("exec", "-T", "worker", "python", "-c", code)

        def address() -> str:
            value = run("port", "web", "3000")
            assert value.startswith("127.0.0.1:") and int(value.split(":")[-1]) > 0
            return value

        def get(path: str) -> Any:
            with urllib.request.urlopen(f"http://{address()}/api/v1/{path}", timeout=5) as response:
                return json.load(response)

        try:
            # No registry login or inherited Docker auth is available in this directory.
            run("pull")
            evidence["checks"].append("anonymous digest pulls")
            for name, image in provenance["images"].items():
                inspected = json.loads(
                    subprocess.check_output(
                        ["docker", "image", "inspect", image], env=env, text=True
                    )
                )[0]
                assert inspected["Architecture"] == expected_arch and inspected["Os"] == "linux"
                assert (
                    inspected["Config"]["Labels"]["org.opencontainers.image.revision"]
                    == provenance["source_sha"]
                )
                evidence[name] = {
                    "image": image,
                    "architecture": inspected["Architecture"],
                    "id": inspected["Id"],
                }
            run("up", "-d", "--wait", "--wait-timeout", "120", "--pull", "never")
            health = get("health")
            assert health["status"] == "ready"
            workspace = get("workspace")
            actual_fixture_hash = python(
                "import hashlib; from pathlib import Path; "
                "print(hashlib.sha256(Path('/app/data/fixtures/manifest.json')"
                ".read_bytes()).hexdigest())"
            )
            assert actual_fixture_hash == provenance["fixture_manifest_sha256"]
            artifact = "SYNTHETIC_DATA_ONLY: release retention proof"
            python(
                "from pathlib import Path; "
                f"Path('/artifacts/release-smoke.txt').write_text({artifact!r})"
            )
            job = python(
                "from uuid import uuid4; from backend.jobs.queue import Queue; "
                "from backend.persistence.database import Settings,database_engine; "
                "q=Queue(database_engine(Settings.from_environment().database_url)); "
                "print(q.enqueue('diagnostic', {'schema_version':1,'work_units':1000000},uuid4()))"
            )
            for _ in range(100):
                result = get(f"jobs/{job}")
                if result["status"] in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(0.2)
            assert result["status"] == "completed"
            evidence.update(
                workspace=workspace, job=result, fixture_manifest_sha256=actual_fixture_hash
            )
            browser_env = {
                **env,
                "YAMS_SMOKE_URL": f"http://{address()}",
                "YAMS_SMOKE_JOB": job,
                "YAMS_SMOKE_EVIDENCE": str(destination),
            }
            subprocess.run(
                ["pnpm", "--filter", "@yams/web", "exec", "node", "tests/compose-browser.mjs"],
                cwd=ROOT,
                env=browser_env,
                check=True,
            )
            evidence["checks"].append(
                "native image/source/fixture identity and offline browser/API/worker journey"
            )
            run("down")
            run("up", "-d", "--wait", "--wait-timeout", "120", "--pull", "never")
            assert get("workspace")["id"] == workspace["id"]
            assert get(f"jobs/{job}")["status"] == "completed"
            assert (
                python(
                    "from pathlib import Path; "
                    "print(Path('/artifacts/release-smoke.txt').read_text())"
                )
                == artifact
            )
            rendered = json.loads(run("config", "--format", "json"))
            assert all(
                not service.get("ports")
                for name, service in rendered["services"].items()
                if name != "web"
            )
            evidence["checks"].append(
                "cached restart preserves workspace/job/artifact with only loopback web published"
            )
            evidence["passed"] = True
        finally:
            (destination / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
            try:
                (destination / "compose.log").write_text(run("logs", "--no-color"))
            finally:
                run("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
