"""Alternative-template upgrade collisions, stable identities and real worker dispatch."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from uuid import uuid5

import pytest
from sqlalchemy import Engine

from backend.domain.registry import StrategyCreateRequest
from backend.jobs.queue import Queue
from backend.jobs.worker import Worker
from backend.persistence.bootstrap import bootstrap
from backend.strategies import registry
from backend.strategies.evaluations import admit_evaluation, read_evaluation
from backend.tests.integration.test_bootstrap import database as database
from backend.tests.integration.test_evaluations import prepare

pytestmark = pytest.mark.integration


def test_upgrade_names_preserve_user_records_and_published_versions(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as old:
        old.setattr("backend.persistence.bootstrap.seed_templates", registry.seed_default)
        bootstrap(database)
    users = []
    for name in ["Mean Reversion", "Mean Reversion (template 1)", "Low Volatility"]:
        users.append(
            registry.create_strategy(
                database, StrategyCreateRequest(name=name, config=registry.default_config())
            )
        )
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: bootstrap(database), range(4)))
    for user in users:
        assert registry.get_strategy(database, user.id) == user
    expected_names = {
        "mean_reversion": "Mean Reversion (template 2)",
        "low_volatility": "Low Volatility (template 1)",
    }
    for kind, name in expected_names.items():
        root = registry.get_strategy(database, registry.template_strategy_id(kind))
        assert root.name == name and root.template_key == f"{kind}_v1"
        assert root.published_version.id == uuid5(root.id, "1")
        assert root.published_version.config == registry.template_config(kind)
        appended = registry.publish_version(database, root.id, root.published_version.config)
        assert appended.version == 2 and appended.id != root.published_version.id
        bootstrap(database)
        assert registry.get_strategy(database, root.id).published_version == appended
        assert registry.list_versions(database, root.id).items[0] == root.published_version
    original = registry.list_versions(database, registry.DEFAULT_STRATEGY_ID).items[0]
    assert (
        original.id == registry.DEFAULT_VERSION_ID
        and original.config_sha256 == registry.DEFAULT_CONFIG_SHA256
    )


@pytest.mark.parametrize("kind", ["mean_reversion", "low_volatility"])
def test_supervised_worker_rerun_matches_independent_family_fixture(
    database: Engine, tmp_path: Path, kind: str
) -> None:
    base = prepare(database, tmp_path)
    request = base.model_copy(
        update={
            "strategy_version_id": uuid5(registry.template_strategy_id(kind), "1"),
            "as_of_session": date(2028, 7, 18),
        }
    )
    oracle = json.loads(
        (
            Path(__file__).resolve().parents[3] / "data/fixtures/template_extensions/case.json"
        ).read_text()
    )
    hashes = []
    for _ in range(2):
        accepted = admit_evaluation(database, tmp_path, request)
        assert Worker(Queue(database), artifact_root=tmp_path).run_once()
        result = read_evaluation(database, accepted.evaluation_id)
        assert result is not None and result.status == "completed" and result.result is not None
        assert result.strategy_config.signals.kind == kind
        assert list(result.result.selected_ids) == oracle["families"][kind]["ranks"]
        assert result.result.cash_target_weight == "0.4"
        assert all(
            row.features is None or getattr(row.features, "kind", None) == kind
            for row in result.result.candidates
        )
        hashes.append(result.result_sha256)
    assert hashes[0] == hashes[1]


def test_incompatible_template_identity_rolls_back_instead_of_renaming(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with monkeypatch.context() as old:
        old.setattr("backend.persistence.bootstrap.seed_templates", registry.seed_default)
        bootstrap(database)
    user = registry.create_strategy(
        database,
        StrategyCreateRequest(name="Conflicting identity", config=registry.default_config()),
    )
    with database.begin() as connection:
        connection.execute(
            text("UPDATE strategy SET template_key='low_volatility_v1' WHERE id=:id"),
            {"id": user.id},
        )
    before = registry.list_strategies(database)
    with pytest.raises(IntegrityError):
        bootstrap(database)
    assert registry.list_strategies(database) == before
    assert {row.id for row in before.items} == {registry.DEFAULT_STRATEGY_ID, user.id}
