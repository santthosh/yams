"""Exercise only a uniquely owned disposable full-application Compose project."""

import hashlib
import json
import os
import subprocess
import textwrap
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

    def python(code: str, *arguments: str) -> str:
        return compose("exec", "-T", "api", "python", "-c", code, *arguments).strip()

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
        assert len(strategies["items"]) == 3 and strategies["next_cursor"] is None
        default_version = next(
            row["published_version"]
            for row in strategies["items"]
            if row["template_key"] == "risk_adjusted_momentum_v1"
        )
        assert default_version["status"] == "published"
        assert default_version["config_sha256"] == (
            "2093c63d190815eba052508d6d42d8ae0c93400cf777602d2c5f759627f43f21"
        )
        assert default_version["config"]["portfolio"]["max_position_weight"] == "0.2"
        evidence["default_strategy"] = strategies
        evidence["workspace"] = workspace
        evidence["fixture_metadata"] = health["fixture_metadata"]
        evidence["checks"].append("clean boot and real same-origin API readiness")
        assert get("portfolios")["items"] == []
        portfolio_key = str(uuid4())
        portfolio_body = {
            "name": "SYNTHETIC_DATA_ONLY Docker account",
            "strategy_version_id": default_version["id"],
        }

        def create_paper_account() -> Any:
            request = urllib.request.Request(
                f"http://{address}/api/v1/portfolios",
                data=json.dumps(portfolio_body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{address}",
                    "Idempotency-Key": portfolio_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 201
                return json.load(response)

        paper_account = create_paper_account()
        assert (
            paper_account["cash_usd"] == paper_account["valuation"]["total_value_usd"] == "1000.00"
        )
        assert (
            paper_account["holdings"] == []
            and paper_account["valuation_mode"] == "synthetic_fixture"
        )
        assert paper_account["paper_only"] is True
        paper_history = get(f"portfolios/{paper_account['id']}/transactions")
        assert len(paper_history["items"]) == 1
        assert paper_history["items"][0]["kind"] == "opening_funding"
        assert paper_history["items"][0]["cash_delta_usd"] == "1000.00"
        assert paper_history["next_cursor"] is None

        def verify_paper_account() -> None:
            saved = get(f"portfolios/{paper_account['id']}")
            assert saved["cash_usd"] == "1000.00" and saved["holdings"] == []
            assert saved["created_at"] == paper_account["created_at"]
            assert saved["revision"] == saved["last_sequence"] == 1
            assert get(f"portfolios/{paper_account['id']}/transactions") == paper_history
            retried = create_paper_account()
            assert (
                retried["id"] == paper_account["id"]
                and retried["created_at"] == paper_account["created_at"]
            )
            assert get(f"portfolios/{paper_account['id']}/transactions") == paper_history

        verify_paper_account()
        evidence["paper_account"] = paper_account
        evidence["paper_history"] = paper_history
        evidence["checks"].append(
            "same-origin keyed paper account funding, exact retry and read-only ledger history"
        )
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
        publication = json.loads((destination / "strategy-publication.json").read_text())
        strategy_id = publication["created"]["body"]["id"]
        versions = get(f"strategies/{strategy_id}/versions")
        assert versions["items"] == [
            publication["created"]["body"]["published_version"],
            publication["appended"]["body"],
        ]
        strategies = get("strategies")
        assert len(strategies["items"]) == 6
        editor_versions = {
            json.loads(path.read_text())["fork"]["id"]: json.loads(path.read_text())["history"]
            for path in destination.glob("strategy-editor-*.json")
        }
        assert len(editor_versions) == 2
        evidence["strategy_publication"] = publication
        evidence["checks"].append(
            "real browser same-origin strategy creation, immutable append, conflict and pagination"
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
                len(matching) == 2 and matching[0]["result_sha256"] == matching[1]["result_sha256"]
            )
        evidence["strategy_evaluations"] = evaluations
        evidence["checks"].append(
            "real browser candidate/target reruns and cash-only cases via supervised worker"
        )
        subprocess.run(
            ["pnpm", "--filter", "@yams/web", "exec", "node", "tests/experiment-browser.mjs"],
            cwd=ROOT,
            env={
                **env,
                "YAMS_SMOKE_URL": f"http://{address}",
                "YAMS_SMOKE_EVIDENCE": str(destination),
            },
            check=True,
        )
        public_runs = json.loads((destination / "experiment-public.json").read_text())
        evidence["public_experiments"] = public_runs
        evidence["checks"].append(
            "real browser public experiment rerun, pages, cancellation and fingerprints"
        )

        subprocess.run(
            ["pnpm", "--filter", "@yams/web", "exec", "node", "tests/experiment-ui-browser.mjs"],
            cwd=ROOT,
            env={
                **env,
                "YAMS_SMOKE_URL": f"http://{address}",
                "YAMS_SMOKE_EVIDENCE": str(destination),
            },
            check=True,
        )
        ui_runs = json.loads((destination / "experiment-ui.json").read_text())
        # Browser JS objects cannot represent uint64 seeds. Preserve original
        # HTTP text in the recorder and decode here without binary rounding.
        for record in ui_runs["records"]:
            for role in ("original", "rerun", "cancelled", "fork_run"):
                raw_key = role + "_raw_json"
                if raw_key in record:
                    saved = json.loads(record.pop(raw_key))
                    assert saved["inputs"] == json.loads(saved["inputs_canonical_json"])
                    record[role] = saved
        evidence["experiment_ui"] = ui_runs
        evidence["checks"].append(
            "real mobile/desktop experiment form, charts/tables/Axe, exact uint64 rerun, "
            "original preservation and cancellation"
        )

        subprocess.run(
            ["pnpm", "--filter", "@yams/web", "exec", "node", "tests/comparison-browser.mjs"],
            cwd=ROOT,
            env={
                **env,
                "YAMS_SMOKE_URL": f"http://{address}",
                "YAMS_SMOKE_EVIDENCE": str(destination),
            },
            check=True,
        )
        comparison_runs = json.loads((destination / "comparison-ui.json").read_text())
        for record in comparison_runs["records"]:
            for role in ("source", "challenge", "mismatched"):
                record[role] = json.loads(record.pop(role + "_raw_json"))
                assert record[role]["inputs"] == json.loads(record[role]["inputs_canonical_json"])
            record["common"] = [json.loads(raw) for raw in record.pop("common_raw_json")]
            for saved in record["common"]:
                assert saved["inputs"] == json.loads(saved["inputs_canonical_json"])
        evidence["comparison_ui"] = comparison_runs
        evidence["checks"].append(
            "real mobile/desktop aligned and mismatched comparison, one-rule challenge, "
            "shared-setting exact-seed reruns and immutable source evidence"
        )

        # Challenge publication deliberately adds two immutable strategy roots.
        # Snapshot the registry after all writes, while proving the original six
        # rows and every old version are unchanged rather than weakening replay.
        original_strategy_rows = strategies["items"]
        strategies = get("strategies")
        original_strategy_ids = {row["id"] for row in original_strategy_rows}
        assert [
            row for row in strategies["items"] if row["id"] in original_strategy_ids
        ] == original_strategy_rows
        challenge_roots = [
            row for row in strategies["items"] if row["id"] not in original_strategy_ids
        ]
        assert len(challenge_roots) == 2 and len(strategies["items"]) == 8
        assert {row["published_version"]["id"] for row in challenge_roots} == {
            record["challenge"]["inputs"]["strategy_version_id"]
            for record in comparison_runs["records"]
        }
        challenge_versions = {
            row["id"]: get(f"strategies/{row['id']}/versions") for row in challenge_roots
        }
        for row in challenge_roots:
            assert challenge_versions[row["id"]]["items"] == [row["published_version"]]

        def verify_public_runs() -> None:
            for identity, history in challenge_versions.items():
                assert get(f"strategies/{identity}/versions") == history
            for saved in public_runs["runs"]:
                identity = saved["run"]["id"]
                assert get(f"experiments/{identity}") == saved["run"]
                assert get(f"experiments/{identity}/series?limit=2") == saved["first"]
                assert get(f"experiments/{identity}/trades") == saved["trades"]
            assert get(f"experiments/{public_runs['cancelled']['id']}") == public_runs["cancelled"]
            for record in ui_runs["records"]:
                for key in ("original", "rerun", "cancelled", "fork_run"):
                    if key in record:
                        saved = record[key]
                        assert get(f"experiments/{saved['id']}") == saved

            for record in comparison_runs["records"]:
                for saved in [
                    record["source"],
                    record["challenge"],
                    record["mismatched"],
                    *record["common"],
                ]:
                    assert get(f"experiments/{saved['id']}") == saved

        # Internal compatibility remains covered alongside the new public flow.
        core = json.loads(
            python(
                "import json\n"
                "from uuid import uuid5\n"
                "from sqlalchemy.orm import Session\n"
                "from backend.backtesting.service import admit_core\n"
                "from backend.domain.experiment import ExperimentRequest\n"
                "from backend.persistence.database import Settings, database_engine\n"
                "from backend.persistence.models.snapshot import CurrentSnapshot\n"
                "from backend.strategies.registry import template_strategy_id\n"
                "settings=Settings.from_environment()\n"
                "engine=database_engine(settings.database_url)\n"
                "with Session(engine) as session:\n"
                "    snapshot=session.get(CurrentSnapshot, 'synthetic_fixture').snapshot_id\n"
                "request=ExperimentRequest.model_validate(dict(\n"
                "    strategy_version_id=uuid5(template_strategy_id('mean_reversion'),'1'),\n"
                "    snapshot_id=snapshot,start_session='2028-07-18',\n"
                "    end_session_exclusive='2028-07-24',initial_capital_usd='1000.00',\n"
                "    benchmark_asset_id='SYN:SPY',execution_policy_id='us_eod_next_open_v1',\n"
                "    random_seed=42,evaluation_split=dict(kind='chronological',"
                "holdout_fraction=0.25)))\n"
                "accepted=admit_core(engine,settings.artifact_root,request)\n"
                "print(json.dumps(dict(experiment_id=str(accepted.experiment_id),job_id=str(accepted.job_id))))\n"
                "engine.dispose()"
            )
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            core_job = get(f"jobs/{core['job_id']}")
            if core_job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.1)
        assert core_job["status"] == "completed", core_job

        def core_state() -> Any:
            return json.loads(
                python(
                    "import json,sys\n"
                    "from uuid import UUID\n"
                    "from backend.backtesting.service import read_core_run\n"
                    "from backend.persistence.database import Settings,database_engine\n"
                    "settings=Settings.from_environment()\n"
                    "engine=database_engine(settings.database_url)\n"
                    "saved=read_core_run(engine,settings.artifact_root,UUID(sys.argv[1]))\n"
                    "assert saved is not None and saved.result is not None\n"
                    "print(json.dumps(dict(id=str(saved.id),manifest_sha256=saved.manifest_sha256,"
                    "result=saved.result.model_dump(mode='json'))))\n"
                    "engine.dispose()",
                    core["experiment_id"],
                )
            )

        core_result = core_state()
        oracle = json.loads((ROOT / "data/fixtures/backtesting/core-case.json").read_text())
        assert [row["nav_usd"] for row in core_result["result"]["points"]] == oracle[
            "daily_nav_usd"
        ]
        assert core_result["result"]["points"][1]["state"]["cash_usd"] == "392.84"
        evidence["backtest_core"] = core_result
        (destination / "backtest-core.json").write_text(json.dumps(core_result, indent=2))
        evidence["checks"].append(
            "internal core admission, actual supervised next-open replay and sealed artifact"
        )

        def metrics_report() -> Any:
            code = (
                "import sys\n"
                "from uuid import UUID\n"
                "from backend.backtesting.benchmark import build_report\n"
                "from backend.backtesting.service import read_core_run\n"
                "from backend.market_data.files import PinnedSnapshot\n"
                "from backend.market_data.repository import MarketRepository\n"
                "from backend.persistence.database import Settings,database_engine\n"
                "settings=Settings.from_environment()\n"
                "engine=database_engine(settings.database_url)\n"
                "saved=read_core_run(engine,settings.artifact_root,UUID(sys.argv[1]))\n"
                "snapshot=PinnedSnapshot.open(settings.artifact_root/'snapshots'/"
                "saved.payload.snapshot_sha256,saved.payload.snapshot_sha256)\n"
                "with MarketRepository(snapshot) as repository:\n"
                "    report=build_report(saved,repository)\n"
                "print(report.model_dump_json())\n"
                "engine.dispose()"
            )
            return json.loads(
                compose("exec", "-T", "worker", "python", "-c", code, core["experiment_id"])
            )

        report = metrics_report()
        golden_metrics = json.loads(
            (ROOT / "data/fixtures/metrics_extensions/case.json").read_text()
        )["core_report"]["expected"]
        metric_fields = {
            "cumulative_return_fraction": "cumulative_return",
            "annualized_return_fraction": "annualized_return",
            "annualized_volatility_fraction": "annualized_volatility",
            "max_drawdown_fraction": "max_drawdown",
            "sharpe_ratio": "sharpe",
            "turnover_fraction": "turnover",
        }
        for field, golden in metric_fields.items():
            observed = report["portfolio"]["total"]["metrics"][field]
            assert observed["unavailable_reason"] is None
            assert abs(observed["value"] - golden_metrics[golden]) <= 1e-12
        assert report["benchmark"]["available"]
        assert report["benchmark"]["nav_usd"] == ["1000.00", "1000.23", "1000.45", "1000.68"]
        assert report["cash_nav_usd"] == ["1000.00"] * 4
        assert report["portfolio"]["holdout"]["return_observations"] == 1
        evidence["backtest_metrics"] = report
        (destination / "backtest-metrics.json").write_text(json.dumps(report, indent=2))
        evidence["checks"].append(
            "worker-side Q12 metrics, aligned SPY/cash, continuing holdout and exposure"
        )
        # Explicit synthetic relational fixture exercises the private #46 service;
        # public recommendation/apply transport remains owned by #49/#50.
        paper_batch = json.loads(
            python(
                textwrap.dedent("""\
            import json
            from datetime import date,timedelta
            from uuid import uuid4
            from sqlalchemy.orm import Session
            from backend.market_data.catalog import verified_snapshot
            from backend.market_data.models import Calendar
            from backend.persistence.database import Settings,database_engine
            from backend.persistence.models.snapshot import CurrentSnapshot,DatasetSnapshot
            from backend.persistence.models.ledger import RecommendationReference
            from backend.persistence.readiness import read_workspace
            from backend.portfolio.batches import approve_batch
            from backend.portfolio.fills import enqueue_batch_attempt
            from backend.portfolio.ledger import create_portfolio,digest
            from backend.jobs.queue import Queue
            from backend.strategies.clock import decision_cutoff
            from backend.strategies.registry import DEFAULT_VERSION_ID
            settings=Settings.from_environment()
            engine=database_engine(settings.database_url)
            with Session(engine) as session:
                pointer=session.get(CurrentSnapshot,'synthetic_fixture')
                source=session.get(DatasetSnapshot,pointer.snapshot_id)
                pinned=verified_snapshot(source,settings.artifact_root)
            calendar=Calendar.model_validate_json(pinned.artifacts[pinned.manifest.calendar.artifact_path])
            decision=date(2028,7,17)
            cutoff=decision_cutoff(calendar,decision)
            owner,rec=uuid4(),uuid4()
            create_portfolio(engine,portfolio_id=owner,workspace_id=read_workspace(engine).id,
                strategy_version_id=DEFAULT_VERSION_ID,
                name='SYNTHETIC_DATA_ONLY execution smoke',created_at=cutoff)
            content={'label':'SYNTHETIC_DATA_ONLY','execution_intent':{
                'schema_version':1,'engine_version':'smoke-fixture-v1','orders':[{
                    'key':'BUY:SYN:AAA','asset_id':'SYN:AAA','sector':'Technology',
                    'side':'BUY','requested_quantity':'2.000000'}]}}
            with Session(engine) as session,session.begin():
                session.add(RecommendationReference(id=rec,portfolio_id=owner,
                    strategy_version_id=DEFAULT_VERSION_ID,snapshot_id=source.id,
                    as_of_session=decision,decision_cutoff=cutoff,portfolio_revision=1,
                    source_mode='synthetic_fixture',content=content,content_sha256=digest(content),
                    disposition='ready',created_at=cutoff))
            batch=approve_batch(engine,owner,rec,expected_revision=1,idempotency_key=uuid4(),
                pinned=pinned,approved_at=cutoff)
            eligible=next(row for row in calendar.sessions if row.open_at>cutoff)
            job=enqueue_batch_attempt(Queue(engine),batch,fixture_observed_at=eligible.close_at+timedelta(seconds=1))
            print(json.dumps({'portfolio_id':str(owner),'batch_id':str(batch),'job_id':str(job)}))
            engine.dispose()
            """)
            )
        )
        deadline = time.monotonic() + 60
        while get(f"jobs/{paper_batch['job_id']}")["status"] in {"queued", "running"}:
            if time.monotonic() >= deadline:
                raise AssertionError("Private paper batch worker did not complete")
            time.sleep(0.2)

        def verify_paper_batch() -> None:
            assert get(f"jobs/{paper_batch['job_id']}")["status"] == "completed"
            posted = get(f"portfolios/{paper_batch['portfolio_id']}")
            assert posted["cash_usd"] == "859.76" and posted["revision"] == 3
            assert posted["holdings"][0]["quantity"] == "2.000000"
            transactions = get(f"portfolios/{paper_batch['portfolio_id']}/transactions")
            assert {row["kind"] for row in transactions["items"]} == {
                "opening_funding",
                "batch_approval",
                "fill",
            }

        verify_paper_batch()
        evidence["paper_batch"] = paper_batch
        evidence["checks"].append("private explicit fixture approval and real worker atomic fill")
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
        assert core_state() == core_result
        assert metrics_report() == report
        verify_public_runs()
        verify_paper_batch()
        assert get("strategies") == strategies
        assert get(f"strategies/{strategy_id}/versions") == versions
        for editor_id, history in editor_versions.items():
            assert get(f"strategies/{editor_id}/versions") == history
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
        verify_paper_account()
        evidence["checks"].append(
            "restart retains paper account identity, funding and original creation retry"
        )
        evidence["checks"].append("restart preserves workspace, job, fixtures and artifact hash")
        compose("up", "--build", "--force-recreate", "-d", "--wait", "--wait-timeout", "120")
        address = web_address()
        assert get("workspace") == workspace
        assert core_state() == core_result
        assert metrics_report() == report
        verify_public_runs()
        verify_paper_batch()
        assert get("strategies") == strategies
        assert get(f"strategies/{strategy_id}/versions") == versions
        for editor_id, history in editor_versions.items():
            assert get(f"strategies/{editor_id}/versions") == history
        for saved in evaluations:
            assert get(f"strategy-evaluations/{saved['id']}") == saved
        assert (
            python(
                "from pathlib import Path; import hashlib; "
                "print(hashlib.sha256(Path('/artifacts/smoke.txt').read_bytes()).hexdigest())"
            )
            == expected
        )
        verify_paper_account()
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
        assert core_state() == core_result
        assert metrics_report() == report
        verify_public_runs()
        verify_paper_batch()
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
