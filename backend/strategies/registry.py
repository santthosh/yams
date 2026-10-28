"""Validated default parameters and read-only registry; never computes returns."""

import json
from datetime import UTC, datetime
from importlib.resources import files
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.domain.common import Page
from backend.domain.registry import StrategyV1, StrategyVersionV1, strategy_name
from backend.domain.strategy import StrategyConfigV1
from backend.persistence.models.strategy import Strategy, StrategyVersion

DEFAULT_TEMPLATE_KEY = "risk_adjusted_momentum_v1"
DEFAULT_STRATEGY_ID = uuid5(NAMESPACE_URL, "https://yams.local/strategies/risk-adjusted-momentum")
DEFAULT_VERSION_ID = uuid5(DEFAULT_STRATEGY_ID, "1")
DEFAULT_CONFIG_SHA256 = "2093c63d190815eba052508d6d42d8ae0c93400cf777602d2c5f759627f43f21"


def default_config() -> StrategyConfigV1:
    config = StrategyConfigV1.from_json(
        files("backend.strategies").joinpath("default_momentum.json").read_bytes()
    )
    if config.config_hash() != DEFAULT_CONFIG_SHA256:
        raise ValueError("Packaged default does not match the ratified momentum configuration")
    return config


def seed_default(connection: Connection, workspace_id: UUID) -> None:
    """Caller owns atomic bootstrap transaction; serialize independent seed calls too."""
    config = default_config()  # Invalid/missing defaults fail before any registry write.
    connection.execute(text("SELECT pg_advisory_xact_lock(1497451859)"))
    now = datetime.now(UTC)
    name = strategy_name(config.display_name)
    connection.execute(
        insert(Strategy)
        .values(
            id=DEFAULT_STRATEGY_ID,
            workspace_id=workspace_id,
            name=name,
            name_key=name.casefold(),
            template_key=DEFAULT_TEMPLATE_KEY,
            created_at=now,
        )
        .on_conflict_do_nothing()
    )
    connection.execute(
        insert(StrategyVersion)
        .values(
            id=DEFAULT_VERSION_ID,
            strategy_id=DEFAULT_STRATEGY_ID,
            version=1,
            status="published",
            config=json.loads(config.canonical_bytes()),
            config_sha256=config.config_hash(),
            published_at=now,
        )
        .on_conflict_do_nothing()
    )
    with Session(bind=connection) as session:
        strategy = session.get(Strategy, DEFAULT_STRATEGY_ID)
        version = session.get(StrategyVersion, DEFAULT_VERSION_ID)
        if (
            strategy is None
            or version is None
            or strategy.workspace_id != workspace_id
            or strategy.template_key != DEFAULT_TEMPLATE_KEY
            or strategy.name_key != name.casefold()
            or version.strategy_id != DEFAULT_STRATEGY_ID
            or version.version != 1
            or version.status != "published"
            or version.config_sha256 != config.config_hash()
            or StrategyConfigV1.model_validate(version.config).canonical_bytes()
            != config.canonical_bytes()
        ):
            raise ValueError("Existing default registry identity or configuration is incompatible")


def version_view(row: StrategyVersion) -> StrategyVersionV1:
    config = StrategyConfigV1.model_validate(row.config)
    if config.config_hash() != row.config_sha256 or row.status != "published":
        raise ValueError("Published strategy config hash mismatch")
    return StrategyVersionV1(
        id=row.id,
        strategy_id=row.strategy_id,
        version=row.version,
        status="published",
        config=config,
        config_sha256=row.config_sha256,
        published_at=row.published_at,
    )


def list_strategies(
    engine: Engine, limit: int = 25, cursor: UUID | None = None
) -> Page[StrategyV1]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Page limit must be between 1 and 100")
    with Session(engine) as session:
        statement = select(Strategy)
        if cursor is not None:
            if session.get(Strategy, cursor) is None:
                raise LookupError("Unknown strategy cursor")
            statement = statement.where(Strategy.id > cursor)
        rows = session.scalars(statement.order_by(Strategy.id).limit(limit + 1)).all()
        items = []
        for row in rows[:limit]:
            version = session.scalar(
                select(StrategyVersion)
                .where(StrategyVersion.strategy_id == row.id)
                .order_by(StrategyVersion.version.desc())
                .limit(1)
            )
            if version is None:
                raise ValueError("Strategy has no published version")
            items.append(
                StrategyV1(
                    id=row.id,
                    name=row.name,
                    is_template=row.template_key is not None,
                    template_key=row.template_key,
                    created_at=row.created_at,
                    published_version=version_view(version),
                )
            )
        return Page[StrategyV1](
            items=tuple(items), next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None
        )
