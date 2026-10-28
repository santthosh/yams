"""Real PostgreSQL publication races, atomicity and pinned-reference protection."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.exc import DBAPIError

from backend.api.main import create_app
from backend.domain.registry import StrategyCreateRequest
from backend.domain.strategy import StrategyConfigV1
from backend.persistence.bootstrap import bootstrap
from backend.persistence.database import Settings
from backend.strategies import registry
from backend.strategies.evaluations import admit_evaluation, read_evaluation
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_evaluations import prepare

pytestmark = pytest.mark.integration


def test_create_append_paginate_and_preserve_canonical_config(database: Engine) -> None:
    bootstrap(database)
    config = registry.default_config()
    original = config.model_dump(mode="json")
    url = database.url.render_as_string(hide_password=False)
    with TestClient(create_app(Settings(url))) as client:
        response = client.post(
            "/api/v1/strategies", json={"name": "  My fork  ", "config": original}
        )
        assert response.status_code == 201
        root = response.json()
        assert (
            root["name"] == "My fork" and not root["is_template"] and root["template_key"] is None
        )
        first = root["published_version"]
        assert (
            first["config"] == original and first["config_sha256"] == registry.DEFAULT_CONFIG_SHA256
        )
        path = f"/api/v1/strategies/{root['id']}"
        # A rule change appends; equal config publication also allocates a new identity.
        changed = config.model_dump(mode="json")
        changed["portfolio"]["max_position_weight"] = "0.15"
        expected_hash = StrategyConfigV1.model_validate(changed).config_hash()
        for ordinal in [2, 3]:
            published = client.post(path + "/versions", json=changed)
            assert published.status_code == 201
            version = published.json()
            assert version["version"] == ordinal and version["id"] != first["id"]
            assert version["config_sha256"] == expected_hash != first["config_sha256"]
        latest = client.get(path).json()
        assert latest["published_version"] == version
        page1 = client.get(path + "/versions?limit=1").json()
        assert page1["items"] == [first]
        page2 = client.get(
            path + "/versions", params={"limit": 1, "cursor": page1["next_cursor"]}
        ).json()
        page3 = client.get(path + "/versions", params={"cursor": page2["next_cursor"]}).json()
        assert page2["items"][0]["version"] == 2
        assert page3["items"] == [version] and page3["next_cursor"] is None
        for cursor in [str(uuid4()), str(registry.DEFAULT_VERSION_ID)]:
            assert client.get(path + "/versions", params={"cursor": cursor}).status_code == 422
        assert client.post(path + "/versions", json={"config": changed}).status_code == 422
        for method, suffix, payload in [
            ("get", "", None),
            ("get", "/versions", None),
            ("post", "/versions", original),
        ]:
            missing = f"/api/v1/strategies/{uuid4()}{suffix}"
            result = client.get(missing) if method == "get" else client.post(missing, json=payload)
            assert result.status_code == 404 and result.json()["error"]["code"] == "NOT_FOUND"
    # Repeated startup validates version one without replacing any appended version.
    bootstrap(database)
    assert registry.get_strategy(database, UUID(root["id"])).model_dump(mode="json") == latest
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM job")).scalar_one() == 0


def test_concurrent_publication_and_unicode_name_conflict(database: Engine) -> None:
    bootstrap(database)
    request = StrategyCreateRequest(name="Straße", config=registry.default_config())

    def create(_: int) -> int:
        with TestClient(
            create_app(Settings(database.url.render_as_string(hide_password=False)))
        ) as client:
            return int(
                client.post("/api/v1/strategies", json=request.model_dump(mode="json")).status_code
            )

    with ThreadPoolExecutor(max_workers=4) as executor:
        statuses = list(executor.map(create, range(4)))
    assert sorted(statuses) == [201, 409, 409, 409]
    root = next(row for row in registry.list_strategies(database).items if row.name == "Straße")
    with TestClient(
        create_app(Settings(database.url.render_as_string(hide_password=False)))
    ) as client:
        assert (
            client.post(
                "/api/v1/strategies",
                json={"name": " STRASSE ", "config": request.config.model_dump(mode="json")},
            ).status_code
            == 409
        )
    with ThreadPoolExecutor(max_workers=4) as executor:
        versions = list(
            executor.map(
                lambda _: registry.publish_version(database, root.id, request.config), range(8)
            )
        )
    assert sorted(version.version for version in versions) == list(range(2, 10))
    assert len({version.id for version in versions}) == 8
    assert {version.config_sha256 for version in versions} == {registry.DEFAULT_CONFIG_SHA256}
    assert registry.list_versions(database, root.id).items[0] == root.published_version


def test_initial_version_failure_rolls_back_root(database: Engine) -> None:
    bootstrap(database)

    def fail_insert(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        many: bool,
    ) -> None:
        if statement.startswith("INSERT INTO strategy_version"):
            raise RuntimeError("injected publication fault")

    event.listen(database, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="publication fault"):
            registry.create_strategy(
                database,
                StrategyCreateRequest(name="Must roll back", config=registry.default_config()),
            )
    finally:
        event.remove(database, "before_cursor_execute", fail_insert)
    assert {row.id for row in registry.list_strategies(database).items} == {
        registry.DEFAULT_STRATEGY_ID,
        registry.template_strategy_id("mean_reversion"),
        registry.template_strategy_id("low_volatility"),
    }
    assert len(registry.list_versions(database, registry.DEFAULT_STRATEGY_ID).items) == 1


def test_published_reference_stays_pinned_after_append(database: Engine, tmp_path: Path) -> None:
    request = prepare(database, tmp_path)
    accepted = admit_evaluation(database, tmp_path, request)
    before = read_evaluation(database, accepted.evaluation_id)
    assert before is not None
    config = registry.default_config().model_dump(mode="json")
    config["portfolio"]["max_position_weight"] = "0.15"
    new = registry.publish_version(
        database, registry.DEFAULT_STRATEGY_ID, StrategyConfigV1.model_validate(config)
    )
    assert new.id != request.strategy_version_id and new.config_sha256 != before.config_sha256
    assert read_evaluation(database, accepted.evaluation_id) == before
    original = registry.list_versions(database, registry.DEFAULT_STRATEGY_ID).items[0]
    assert (
        original.id == before.inputs.strategy_version_id
        and original.config_sha256 == before.config_sha256
    )
    for sql in [
        "UPDATE strategy_version SET config_sha256 = 'bad'",
        "DELETE FROM strategy_version",
        "DELETE FROM strategy",
    ]:
        with pytest.raises(DBAPIError), database.begin() as connection:
            connection.execute(text(sql))
    assert read_evaluation(database, accepted.evaluation_id) == before
