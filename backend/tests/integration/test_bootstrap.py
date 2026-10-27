"""Requires the uniquely scoped, unexposed Postgres service created by the harness."""

import json
import os
import shutil
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from backend.api.main import create_app
from backend.persistence.bootstrap import MIGRATIONS, bootstrap
from backend.persistence.database import Settings, database_engine
from backend.persistence.readiness import read_workspace, readiness

pytestmark = pytest.mark.integration


def isolated_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if (
        os.environ.get("YAMS_TEST_ISOLATED") != "1"
        or parsed.host != "postgres"
        or parsed.database != "yams_test"
    ):
        raise RuntimeError("Run make test-integration in its disposable Compose project")
    return url


@pytest.fixture
def database() -> Iterator[Engine]:
    root = database_engine(isolated_url())
    name = "test_" + uuid4().hex
    with root.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(isolated_url()).set(database=name).render_as_string(hide_password=False)
    engine = database_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
        with root.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        root.dispose()


def test_fresh_repeat_and_concurrent_bootstrap_preserves_identity_and_preferences(
    database: Engine,
) -> None:
    assert readiness(database, Settings.fixture_root).migration.status == "failed"
    with ThreadPoolExecutor(max_workers=2) as executor:
        fresh = list(executor.map(lambda _: bootstrap(database), range(2)))
    assert fresh[0] == fresh[1]
    first = fresh[0]
    with database.begin() as connection:
        connection.execute(
            text("UPDATE local_workspace SET preferences = :prefs, locale = 'fr-CA'"),
            {"prefs": json.dumps({"theme": "dark", "retained": True})},
        )
    with ThreadPoolExecutor(max_workers=2) as executor:
        identities = list(executor.map(lambda _: bootstrap(database), range(2)))
    assert identities == [first, first]
    workspace = read_workspace(database)
    assert workspace.locale == "fr-CA"
    assert workspace.preferences == {"theme": "dark", "retained": True}
    assert set(inspect(database).get_table_names()) == {"alembic_version", "local_workspace"}
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM local_workspace")).scalar_one() == 1
    for singleton in (1, 2):
        with pytest.raises(IntegrityError), database.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO local_workspace SELECT :id, :singleton, locale, "
                    "default_benchmark, preferences FROM local_workspace"
                ),
                {"id": uuid4(), "singleton": singleton},
            )
    health = readiness(database, Settings.fixture_root)
    assert health.status == "ready"


def test_api_workspace_and_readiness_failures(database: Engine, tmp_path: Path) -> None:
    identity = bootstrap(database)
    url = database.url.render_as_string(hide_password=False)
    with TestClient(create_app(Settings(url))) as client:
        assert client.get("/api/v1/health").status_code == 200
        response = client.get("/api/v1/workspace")
        assert response.status_code == 200 and response.json()["id"] == str(identity)
        with database.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'unknown_revision'"))
        bad = client.get("/api/v1/health")
        assert bad.status_code == 503
        assert bad.json()["migration"]["reason"] == "MIGRATION_MISMATCH"
        assert client.get("/api/v1/workspace").status_code == 503
        assert "disposable_test_only" not in bad.text
    with database.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '0001_workspace'"))
    with TestClient(create_app(Settings(url, tmp_path))) as client:
        missing = client.get("/api/v1/health")
        assert missing.status_code == 503
        assert missing.json()["database"]["status"] == "ready"
        assert missing.json()["migration"]["status"] == "ready"
        assert missing.json()["fixtures"]["status"] == "failed"
    unreachable = make_url(url).set(host="127.0.0.1", port=1).render_as_string(hide_password=False)
    with TestClient(create_app(Settings(unreachable))) as client:
        failed = client.get("/api/v1/health")
        assert failed.status_code == 503
        assert failed.json()["database"]["status"] == "failed"
        assert "disposable_test_only" not in failed.text


def test_failed_migration_rolls_back_and_does_not_reseed(database: Engine, tmp_path: Path) -> None:
    identity = bootstrap(database)
    before = read_workspace(database)
    migrations = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, migrations)
    (migrations / "versions/0002_failure.py").write_text(
        "from alembic import op\n"
        "revision = '0002_failure'\ndown_revision = '0001_workspace'\n"
        "def upgrade():\n"
        "    op.execute('CREATE TABLE must_rollback (id integer)')\n"
        "    raise RuntimeError('deliberate migration failure')\n"
    )
    with pytest.raises(RuntimeError, match="deliberate migration failure"):
        bootstrap(database, migrations)
    assert "must_rollback" not in inspect(database).get_table_names()
    assert read_workspace(database) == before
    assert bootstrap(database) == identity
    with database.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0001_workspace"
        )


def test_prepare_real_container_restart() -> None:
    engine = database_engine(isolated_url())
    try:
        identity = bootstrap(engine)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE local_workspace SET preferences = :prefs"),
                {"prefs": json.dumps({"restart_marker": "retained"})},
            )
        Path("/evidence/workspace.json").write_text(json.dumps({"id": str(identity)}))
    finally:
        engine.dispose()


@pytest.mark.restart_verify
def test_workspace_survives_actual_postgres_container_restart() -> None:
    expected = json.loads(Path("/evidence/workspace.json").read_text())
    engine = database_engine(isolated_url())
    try:
        assert str(bootstrap(engine)) == expected["id"]
        assert read_workspace(engine).preferences == {"restart_marker": "retained"}
        assert readiness(engine, Settings.fixture_root).status == "ready"
    finally:
        engine.dispose()
