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
    expected_files = {
        "compose.yaml",
        "compose.research.yaml",
        "env.example",
        "INSTALL.md",
        "RESEARCH.md",
        "provenance.json",
    }
    checksum_names = []
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if name not in expected_files:
            raise SystemExit("Unexpected checksum path")
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
        checksum_names.append(name)
    assert len(checksum_names) == len(expected_files) and set(checksum_names) == expected_files
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
    # Render the packaged opt-in path with a synthetic token, without starting it
    # or making provider calls. Never expose actual runner credentials.
    synthetic_token = "SYNTHETIC_DATA_ONLY_not_a_provider_key"
    research = json.loads(
        subprocess.check_output(
            [
                "docker",
                "compose",
                "-f",
                str(bundle / "compose.yaml"),
                "-f",
                str(bundle / "compose.research.yaml"),
                "config",
                "--format",
                "json",
            ],
            env={**os.environ, "TIINGO_API_TOKEN": synthetic_token},
            text=True,
        )
    )
    assert research["networks"]["research-egress"].get("internal", False) is False
    for name, service in research["services"].items():
        assert service["image"] == config["services"][name]["image"]
        token = service.get("environment", {}).get("TIINGO_API_TOKEN")
        assert token == (synthetic_token if name == "worker" else None)
        assert ("research-egress" in service.get("networks", {})) == (name == "worker")
        if name != "web":
            assert not service.get("ports")
    for section in ("networks", "volumes"):
        assert all(not value.get("external") for value in research[section].values())
    project = "yams-release-smoke-" + uuid4().hex[:12]
    destination = ROOT / "test-results" / "release" / expected_arch
    destination.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {
        "project": project,
        "native_host": platform.machine(),
        "source_sha": provenance["source_sha"],
        "checks": ["packaged research override: worker-only synthetic token and egress"],
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
            evaluations = [
                row
                for path in sorted(destination.glob("candidate-runs-*.json"))
                for row in json.loads(path.read_text())
            ]
            assert len(evaluations) == 10
            for kind in ("mean_reversion", "low_volatility"):
                matching = [
                    row for row in evaluations if row["strategy_config"]["signals"]["kind"] == kind
                ]
                assert (
                    len(matching) == 2
                    and matching[0]["result_sha256"] == matching[1]["result_sha256"]
                )
            publication = json.loads((destination / "strategy-publication.json").read_text())
            strategy_id = publication["created"]["body"]["id"]
            versions = get(f"strategies/{strategy_id}/versions")
            editor_versions = {
                json.loads(path.read_text())["fork"]["id"]: json.loads(path.read_text())["history"]
                for path in destination.glob("strategy-editor-*.json")
            }
            assert len(editor_versions) == 2
            evidence["strategy_evaluations"] = evaluations
            evidence["checks"].append(
                "native real-worker candidate rerun hashes and explicit cash-only results"
            )
            original_strategies = get("strategies")
            assert len(original_strategies["items"]) == 6
            for script in (
                "experiment-browser.mjs",
                "experiment-ui-browser.mjs",
                "comparison-browser.mjs",
            ):
                subprocess.run(
                    ["pnpm", "--filter", "@yams/web", "exec", "node", "tests/" + script],
                    cwd=ROOT,
                    env=browser_env,
                    check=True,
                )
            public_runs = json.loads((destination / "experiment-public.json").read_text())
            ui_runs = json.loads((destination / "experiment-ui.json").read_text())
            for record in ui_runs["records"]:
                for role in ("original", "rerun", "cancelled", "fork_run"):
                    if role + "_raw_json" in record:
                        record[role] = json.loads(record.pop(role + "_raw_json"))
                        assert record[role]["inputs"] == json.loads(
                            record[role]["inputs_canonical_json"]
                        )
            comparisons = json.loads((destination / "comparison-ui.json").read_text())
            for record in comparisons["records"]:
                for role in ("source", "challenge", "mismatched"):
                    record[role] = json.loads(record.pop(role + "_raw_json"))
                    assert record[role]["inputs"] == json.loads(
                        record[role]["inputs_canonical_json"]
                    )
                record["common"] = [json.loads(raw) for raw in record.pop("common_raw_json")]
                for saved in record["common"]:
                    assert saved["inputs"] == json.loads(saved["inputs_canonical_json"])
            evidence.update(
                public_experiments=public_runs, experiment_ui=ui_runs, comparison_ui=comparisons
            )
            strategies = get("strategies")
            original_ids = {row["id"] for row in original_strategies["items"]}
            assert [
                row for row in strategies["items"] if row["id"] in original_ids
            ] == original_strategies["items"]
            challenges = [row for row in strategies["items"] if row["id"] not in original_ids]
            assert len(strategies["items"]) == 8 and len(challenges) == 2
            assert {row["published_version"]["id"] for row in challenges} == {
                record["challenge"]["inputs"]["strategy_version_id"]
                for record in comparisons["records"]
            }
            challenge_versions = {
                row["id"]: get(f"strategies/{row['id']}/versions") for row in challenges
            }
            for row in challenges:
                assert challenge_versions[row["id"]]["items"] == [row["published_version"]]
            evidence["checks"].append(
                "native real editor/version/experiment/report/challenge/fair-comparison journey, "
                "exact uint64 seeds, backend fingerprints, keyboard/Axe/tables "
                "and immutable originals"
            )

            def verify_reports() -> None:
                for record in public_runs["runs"]:
                    identity = record["run"]["id"]
                    assert get(f"experiments/{identity}") == record["run"]
                    assert get(f"experiments/{identity}/series?limit=2") == record["first"]
                    assert get(f"experiments/{identity}/trades") == record["trades"]
                assert (
                    get(f"experiments/{public_runs['cancelled']['id']}") == public_runs["cancelled"]
                )
                for record in ui_runs["records"]:
                    for role in ("original", "rerun", "cancelled", "fork_run"):
                        if role in record:
                            assert get(f"experiments/{record[role]['id']}") == record[role]
                for record in comparisons["records"]:
                    for saved in [
                        record["source"],
                        record["challenge"],
                        record["mismatched"],
                        *record["common"],
                    ]:
                        assert get(f"experiments/{saved['id']}") == saved
                for identity, history in challenge_versions.items():
                    assert get(f"strategies/{identity}/versions") == history

            verify_reports()
            run("down")
            run("up", "-d", "--wait", "--wait-timeout", "120", "--pull", "never")
            assert get("workspace")["id"] == workspace["id"]
            verify_reports()
            assert get("strategies") == strategies
            assert get(f"strategies/{strategy_id}/versions") == versions
            for editor_id, history in editor_versions.items():
                assert get(f"strategies/{editor_id}/versions") == history
            assert get(f"jobs/{job}")["status"] == "completed"
            for saved in evaluations:
                assert get(f"strategy-evaluations/{saved['id']}") == saved
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
                "cached restart preserves workspace/job/artifact, exact experiment reports "
                "and challenge "
                "versions with only loopback web published"
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
