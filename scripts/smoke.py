"""Exercise only a uniquely owned disposable full-application Compose project."""

import hashlib
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    exported = subprocess.check_output(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
        text=True,
    )
    if exported != (ROOT / "infra/docker/backend-requirements.txt").read_text():
        raise SystemExit("Backend image dependency drift: regenerate backend-requirements.txt")
    project = "yams-smoke-" + uuid4().hex[:12]
    env = {**os.environ, "YAMS_WEB_PORT": "0", "YAMS_JOB_LIMITS": "{}"}
    command = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yaml")]
    evidence: dict[str, Any] = {"project": project, "checks": []}
    destination = ROOT / "test-results" / "smoke" / project
    destination.mkdir(parents=True, exist_ok=True)

    def compose(*args: str) -> str:
        return subprocess.check_output([*command, *args], cwd=ROOT, env=env, text=True)

    def python(code: str) -> str:
        return compose("exec", "-T", "api", "python", "-c", code).strip()

    def web_address() -> str:
        value = compose("port", "web", "3000").strip()
        evidence.setdefault("web_addresses", []).append(value)
        assert value.startswith("127.0.0.1:") and int(value.rsplit(":", 1)[1]) > 0, value
        return value

    config = json.loads(compose("config", "--format", "json"))
    assert set(config["services"]) == {"web", "api", "worker", "postgres", "migrate"}
    assert config["networks"]["private"]["internal"] is True
    for name, service in config["services"].items():
        if name != "web":
            assert not service.get("ports"), name
    assert config["services"]["web"]["ports"][0]["host_ip"] == "127.0.0.1"
    started = time.monotonic()
    try:
        compose("up", "--build", "-d", "--wait", "--wait-timeout", "120")
        evidence["startup_seconds"] = time.monotonic() - started
        migration_records = [
            json.loads(line)
            for line in compose("logs", "--no-log-prefix", "migrate").splitlines()
            if line.startswith('{"event": "bootstrap_resources"')
        ]
        assert len(migration_records) == 1 and migration_records[0]["succeeded"]
        assert 0 < migration_records[0]["cgroup_memory_peak_bytes"] <= 512 * 1024 * 1024
        evidence["migration_startup"] = migration_records[0]
        evidence["startup_cgroup_memory_peak_bytes"] = {
            service: int(compose("exec", "-T", service, "cat", "/sys/fs/cgroup/memory.peak"))
            for service in ("api", "worker", "web", "postgres")
        }
        address = web_address()
        evidence["web_address"] = address

        def get(path: str) -> Any:
            with urllib.request.urlopen(f"http://{address}/api/v1/{path}", timeout=5) as response:
                return json.load(response)

        health = get("health")
        assert health["status"] == "ready"
        workspace = get("workspace")
        strategies = get("strategies")
        assert len(strategies["items"]) == 1 and strategies["next_cursor"] is None
        default_version = strategies["items"][0]["published_version"]
        assert default_version["status"] == "published"
        assert default_version["config_sha256"] == (
            "2093c63d190815eba052508d6d42d8ae0c93400cf777602d2c5f759627f43f21"
        )
        assert default_version["config"]["portfolio"]["max_position_weight"] == "0.2"
        evidence["default_strategy"] = strategies
        evidence["workspace"] = workspace
        evidence["fixture_metadata"] = health["fixture_metadata"]
        evidence["checks"].append("clean boot and real same-origin API readiness")
        artifact = b"SYNTHETIC_DATA_ONLY: durable smoke artifact\n"
        python(f"from pathlib import Path; Path('/artifacts/smoke.txt').write_bytes({artifact!r})")
        expected = hashlib.sha256(artifact).hexdigest()
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
            time.sleep(0.1)
        assert result["status"] == "completed", result
        evidence["job"] = result
        evidence["checks"].append("real persisted diagnostic job completed by bounded worker")
        evidence["load_runs"] = []
        # One warm-up and three measured batches of the only registered handler.
        # Each batch keeps the serial worker busy while health/workspace reads hit PostgreSQL.
        for repetition in range(4):
            ids = json.loads(
                python(
                    "import json; from uuid import uuid4; from backend.jobs.queue import Queue; "
                    "from backend.persistence.database import Settings,database_engine; "
                    "q=Queue(database_engine(Settings.from_environment().database_url)); "
                    "print(json.dumps([str(q.enqueue('diagnostic', "
                    "{'schema_version':1,'work_units':1000000},uuid4())) for _ in range(12)]))"
                )
            )
            samples = []
            batch_started = time.monotonic()
            observed_pending = False
            while time.monotonic() - batch_started < 60:
                last = get(f"jobs/{ids[-1]}")
                if last["status"] == "completed":
                    break
                assert last["status"] in {"queued", "running"}, last
                observed_pending = True
                sample_started = time.monotonic()
                assert get("health")["status"] == "ready"
                health_seconds = time.monotonic() - sample_started
                sample_started = time.monotonic()
                assert get("workspace") == workspace
                samples.append(
                    {
                        "health_seconds": health_seconds,
                        "workspace_seconds": time.monotonic() - sample_started,
                        "last_job_status": last["status"],
                    }
                )
                time.sleep(0.05)
            assert last["status"] == "completed" and observed_pending
            elapsed = time.monotonic() - batch_started
            records = json.loads(
                python(
                    "import json; from sqlalchemy import text; "
                    "from backend.persistence.database import Settings,database_engine; "
                    "e=database_engine(Settings.from_environment().database_url); c=e.connect(); "
                    "r=c.execute(text('SELECT j.id,j.status,j.payload_hash,a.diagnostics,d.value "
                    "FROM job j JOIN job_attempt a ON a.job_id=j.id "
                    "JOIN job_diagnostic_effect d ON d.job_id=j.id "
                    "WHERE j.id = ANY(CAST(:ids AS uuid[]))'), "
                    f"{{'ids':{ids!r}}}); "
                    "print(json.dumps([dict(x) for x in r.mappings()],default=str))"
                )
            )
            assert len(records) == 12
            assert all(r["status"] == "completed" and r["value"] == 499999500000 for r in records)
            evidence["load_runs"].append(
                {
                    "warmup": repetition == 0,
                    "batch_seconds": elapsed,
                    "api_samples": samples,
                    "jobs": records,
                }
            )
        evidence["cgroup_memory_peak_bytes"] = {
            service: int(compose("exec", "-T", service, "cat", "/sys/fs/cgroup/memory.peak"))
            for service in ("api", "worker", "web", "postgres")
        }
        evidence["docker_host"] = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "info",
                    "--format",
                    '{"architecture":"{{.Architecture}}","cpus":{{.NCPU}},'
                    '"memory":{{.MemTotal}},"version":"{{.ServerVersion}}"}',
                ],
                text=True,
            )
        )
        evidence["other_containers"] = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}"], text=True
        ).splitlines()
        evidence["checks"].append(
            "warm-up plus three diagnostic batches with concurrent API/DB reads"
        )
        subprocess.run(
            ["pnpm", "--filter", "@yams/web", "exec", "node", "tests/compose-browser.mjs"],
            cwd=ROOT,
            env={
                **env,
                "YAMS_SMOKE_URL": f"http://{address}",
                "YAMS_SMOKE_JOB": job,
                "YAMS_SMOKE_EVIDENCE": str(destination),
            },
            check=True,
        )
        evidence["checks"].append("real Docker browser Dashboard/Settings/job at both widths")
        evaluations = [
            row
            for path in sorted(destination.glob("candidate-runs-*.json"))
            for row in json.loads(path.read_text())
        ]
        assert len(evaluations) == 6
        evidence["strategy_evaluations"] = evaluations
        evidence["checks"].append(
            "real browser candidate/target reruns and cash-only cases via supervised worker"
        )
        for service in ("api", "worker"):
            blocked = compose(
                "exec",
                "-T",
                service,
                "python",
                "-c",
                "import socket; s=socket.socket(); s.settimeout(1); "
                "print(s.connect_ex(('1.1.1.1',443))); s.close()",
            ).strip()
            assert blocked != "0", f"{service} unexpectedly has external routing"
        evidence["checks"].append("API and worker external routing blocked")
        # Read-only root protects the baked, repository-owned fixture directory.
        readonly = python(
            "from pathlib import Path\n"
            "try: Path('/app/data/fixtures/smoke-write').write_text('invalid')\n"
            "except OSError: print('read-only')\n"
            "else: raise SystemExit('fixture write unexpectedly succeeded')"
        )
        assert readonly == "read-only"
        compose("restart", "postgres", "api", "worker", "web")
        compose("up", "-d", "--wait", "--wait-timeout", "120", "--pull", "never", "--no-build")
        address = web_address()
        assert get("workspace") == workspace
        assert get("strategies") == strategies
        for saved in evaluations:
            assert get(f"strategy-evaluations/{saved['id']}") == saved
        assert get("health")["fixture_metadata"] == health["fixture_metadata"]
        assert get(f"jobs/{job}")["status"] == "completed"
        actual = python(
            "from pathlib import Path; import hashlib; "
            "print(hashlib.sha256(Path('/artifacts/smoke.txt').read_bytes()).hexdigest())"
        )
        assert actual == expected
        evidence["artifact_sha256"] = actual
        evidence["checks"].append("restart preserves workspace, job, fixtures and artifact hash")
        compose("up", "--build", "--force-recreate", "-d", "--wait", "--wait-timeout", "120")
        address = web_address()
        assert get("workspace") == workspace
        assert get("strategies") == strategies
        for saved in evaluations:
            assert get(f"strategy-evaluations/{saved['id']}") == saved
        assert (
            python(
                "from pathlib import Path; import hashlib; "
                "print(hashlib.sha256(Path('/artifacts/smoke.txt').read_bytes()).hexdigest())"
            )
            == expected
        )
        evidence["checks"].append("rebuild/recreate preserves named-volume state")
        ids = compose("ps", "-q").split()
        inspect = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True))
        evidence["containers"] = [
            {
                "service": item["Config"]["Labels"]["com.docker.compose.service"],
                "image": item["Image"],
                "memory": item["HostConfig"]["Memory"],
                "nano_cpus": item["HostConfig"]["NanoCpus"],
                "ports": item["NetworkSettings"]["Ports"],
            }
            for item in inspect
        ]
        budgets = {
            "api": (0.5, 512),
            "postgres": (0.5, 1024),
            "worker": (2, 2048),
            "web": (1, 1024),
        }
        assert len(inspect) == 4
        for item in inspect:
            service = item["Config"]["Labels"]["com.docker.compose.service"]
            cpu, memory = budgets[service]
            host = item["HostConfig"]
            assert host["NanoCpus"] == int(cpu * 1_000_000_000)
            assert host["Memory"] == memory * 1024 * 1024
            assert host["MemorySwap"] == host["Memory"]
            if service != "web":
                assert not host["PortBindings"]
            else:
                assert list(host["PortBindings"]) == ["3000/tcp"]
                assert host["PortBindings"]["3000/tcp"][0]["HostIp"] == "127.0.0.1"
        evidence["checks"].append("actual private ports and aggregate 4 CPU/4.5 GiB caps")
        # Corrupt only the disposable project's revision, then prove startup gating.
        revision = python(
            "from sqlalchemy import text; "
            "from backend.persistence.database import Settings,database_engine; "
            "e=database_engine(Settings.from_environment().database_url); "
            "c=e.connect(); "
            "print(c.execute(text('SELECT version_num FROM alembic_version')).scalar())"
        )
        assert revision.replace("_", "").isalnum()
        python(
            "from sqlalchemy import text; "
            "from backend.persistence.database import Settings,database_engine; "
            "e=database_engine(Settings.from_environment().database_url); "
            "c=e.connect(); "
            "c.execute(text(\"UPDATE alembic_version SET version_num='invalid_smoke'\")); "
            "c.commit()"
        )
        compose("down")
        failure = subprocess.run(
            [*command, "up", "-d", "--wait", "--wait-timeout", "60"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        assert failure.returncode != 0, "Migration failure incorrectly permitted startup"
        (destination / "migration-failure.log").write_text(failure.stdout + failure.stderr)
        failed_ids = compose("ps", "-a", "-q").split()
        failed = json.loads(subprocess.check_output(["docker", "inspect", *failed_ids], text=True))
        for item in failed:
            service = item["Config"]["Labels"]["com.docker.compose.service"]
            if service in {"api", "worker", "web"}:
                assert not item["State"]["Running"], service
            if service == "migrate":
                assert item["State"]["ExitCode"] != 0
        compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "yams",
            "-d",
            "yams",
            "-c",
            f"UPDATE alembic_version SET version_num='{revision}'",
        )
        compose("up", "-d", "--wait", "--wait-timeout", "120")
        address = web_address()
        assert get("workspace") == workspace
        evidence["checks"].append(
            "failed migration blocks application startup; repair preserves workspace"
        )
        evidence["passed"] = True
    finally:
        (destination / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        try:
            (destination / "compose.log").write_text(compose("logs", "--no-color"))
        finally:
            # The random project above is the only resource ownership scope for cleanup.
            compose("down", "--volumes", "--remove-orphans")
        print(f"Smoke evidence: {destination}")


if __name__ == "__main__":
    main()
