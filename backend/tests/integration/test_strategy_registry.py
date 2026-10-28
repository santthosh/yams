"""Isolated real PostgreSQL identity, immutability, seeding and discovery proofs."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from backend.api.main import create_app
from backend.domain.registry import strategy_name
from backend.persistence.bootstrap import bootstrap
from backend.persistence.database import Settings
from backend.persistence.models.strategy import Strategy, StrategyVersion
from backend.strategies import registry
from backend.tests.integration.test_bootstrap import database as database

pytestmark = pytest.mark.integration


def test_concurrent_seed_and_immutable_default(database: Engine) -> None:
    workspace = bootstrap(database)
    first = registry.list_strategies(database)

    def seed(_: int) -> None:
        with database.begin() as connection:
            registry.seed_default(connection, workspace)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(seed, range(4)))
    assert registry.list_strategies(database) == first
    default = first.items[0]
    assert default.id == registry.DEFAULT_STRATEGY_ID and default.is_template
    assert default.template_key == registry.DEFAULT_TEMPLATE_KEY
    assert default.published_version.id == registry.DEFAULT_VERSION_ID
    assert default.published_version.version == 1
    assert default.published_version.config_sha256 == registry.DEFAULT_CONFIG_SHA256
    with Session(database) as session:
        assert len(session.scalars(select(Strategy)).all()) == 1
        assert len(session.scalars(select(StrategyVersion)).all()) == 1
    for sql in ["UPDATE strategy_version SET version=2", "DELETE FROM strategy_version"]:
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(sql))
    assert registry.list_strategies(database) == first


def add_strategy(
    database: Engine, workspace: UUID, name: str, config_hash: str | None = None
) -> UUID:
    now = datetime.now(UTC)
    identity = uuid4()
    config = registry.default_config()
    with Session(database) as session, session.begin():
        session.add(
            Strategy(
                id=identity,
                workspace_id=workspace,
                name=strategy_name(name),
                name_key=strategy_name(name).casefold(),
                template_key=None,
                created_at=now,
            )
        )
        session.flush()
        session.add(
            StrategyVersion(
                id=uuid4(),
                strategy_id=identity,
                version=1,
                status="published",
                config=config.model_dump(mode="json"),
                config_sha256=config_hash or config.config_hash(),
                published_at=now,
            )
        )
    return identity


def test_pagination_errors_and_no_execution_side_effects(database: Engine) -> None:
    workspace = bootstrap(database)
    identities = {registry.DEFAULT_STRATEGY_ID}
    identities |= {add_strategy(database, workspace, name) for name in ["Custom A", "Custom B"]}
    with TestClient(
        create_app(Settings(database.url.render_as_string(hide_password=False)))
    ) as client:
        found: list[UUID] = []
        cursor = None
        while True:
            params = {"limit": "1"}
            if cursor:
                params["cursor"] = cursor
            response = client.get("/api/v1/strategies", params=params)
            assert response.status_code == 200
            page = response.json()
            found.extend(UUID(row["id"]) for row in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert len(found) == 3 and set(found) == identities and found == sorted(found)
        assert client.get(f"/api/v1/strategies?cursor={uuid4()}").status_code == 422
        assert len(client.get("/api/v1/strategies?limit=100").json()["items"]) == 3
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM job")).scalar_one() == 0
    assert "portfolio" not in inspect(database).get_table_names()


def test_unicode_casefold_uniqueness_and_hash_integrity(database: Engine) -> None:
    workspace = bootstrap(database)
    add_strategy(database, workspace, "Straße")
    with pytest.raises(IntegrityError):
        add_strategy(database, workspace, "STRASSE")
    add_strategy(database, workspace, "Corrupt", "0" * 64)
    with TestClient(
        create_app(Settings(database.url.render_as_string(hide_password=False)))
    ) as client:
        response = client.get("/api/v1/strategies")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "NOT_READY"
        assert "Corrupt" not in response.text


def test_failed_default_load_rolls_back_fresh_bootstrap(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> None:
        raise ValueError("Invalid packaged default")

    monkeypatch.setattr(registry, "default_config", broken)
    with pytest.raises(ValueError, match="Invalid packaged"):
        bootstrap(database)
    assert inspect(database).get_table_names() == []
