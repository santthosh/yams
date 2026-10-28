"""Validated defaults and immutable strategy publication; never computes returns."""

import json
from datetime import UTC, datetime
from importlib.resources import files
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Connection, Engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.domain.common import Page
from backend.domain.registry import (
    StrategyCreateRequest,
    StrategyV1,
    StrategyVersionV1,
    strategy_name,
)
from backend.domain.strategy import StrategyConfigV1
from backend.persistence.models.strategy import Strategy, StrategyVersion
from backend.persistence.models.workspace import LocalWorkspace

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
            items.append(strategy_view(session, row))
        return Page[StrategyV1](
            items=tuple(items), next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None
        )


class StrategyNotFound(LookupError):
    pass


class StrategyNameConflict(ValueError):
    pass


def strategy_view(session: Session, row: Strategy) -> StrategyV1:
    version = session.scalar(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == row.id)
        .order_by(StrategyVersion.version.desc())
        .limit(1)
    )
    if version is None:
        raise ValueError("Strategy has no published version")
    return StrategyV1(
        id=row.id,
        name=row.name,
        is_template=row.template_key is not None,
        template_key=row.template_key,
        created_at=row.created_at,
        published_version=version_view(version),
    )


def new_version(strategy_id: UUID, ordinal: int, config: StrategyConfigV1) -> StrategyVersion:
    # Round-trip validation also guards callers outside the HTTP boundary.
    config = StrategyConfigV1.from_json(config.canonical_bytes())
    return StrategyVersion(
        id=uuid4(),
        strategy_id=strategy_id,
        version=ordinal,
        status="published",
        config=json.loads(config.canonical_bytes()),
        config_sha256=config.config_hash(),
        published_at=datetime.now(UTC),
    )


def create_strategy(engine: Engine, request: StrategyCreateRequest) -> StrategyV1:
    request = StrategyCreateRequest.model_validate(request.model_dump())
    try:
        with Session(engine) as session, session.begin():
            workspace = session.scalar(select(LocalWorkspace))
            if workspace is None:
                raise ValueError("Workspace is not initialized")
            row = Strategy(
                id=uuid4(),
                workspace_id=workspace.id,
                name=request.name,
                name_key=request.name.casefold(),
                template_key=None,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            session.flush()
            session.add(new_version(row.id, 1, request.config))
            session.flush()
            result = strategy_view(session, row)
        return result
    except IntegrityError as error:
        if (
            getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            == "uq_strategy_name"
        ):
            raise StrategyNameConflict("Strategy name already exists") from error
        raise


def get_strategy(engine: Engine, strategy_id: UUID) -> StrategyV1:
    with Session(engine) as session:
        row = session.get(Strategy, strategy_id)
        if row is None:
            raise StrategyNotFound("Unknown strategy")
        return strategy_view(session, row)


def list_versions(
    engine: Engine, strategy_id: UUID, limit: int = 25, cursor: UUID | None = None
) -> Page[StrategyVersionV1]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Page limit must be between 1 and 100")
    with Session(engine) as session:
        if session.get(Strategy, strategy_id) is None:
            raise StrategyNotFound("Unknown strategy")
        statement = select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
        if cursor is not None:
            preceding = session.get(StrategyVersion, cursor)
            if preceding is None or preceding.strategy_id != strategy_id:
                raise LookupError("Unknown version cursor")
            statement = statement.where(StrategyVersion.version > preceding.version)
        rows = session.scalars(statement.order_by(StrategyVersion.version).limit(limit + 1)).all()
        return Page[StrategyVersionV1](
            items=tuple(version_view(row) for row in rows[:limit]),
            next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
        )


def publish_version(
    engine: Engine, strategy_id: UUID, config: StrategyConfigV1
) -> StrategyVersionV1:
    with Session(engine) as session, session.begin():
        # Lock the stable identity, not the latest version: concurrent appends must
        # serialize even when they began with the same latest-version observation.
        row = session.scalar(select(Strategy).where(Strategy.id == strategy_id).with_for_update())
        if row is None:
            raise StrategyNotFound("Unknown strategy")
        previous = strategy_view(session, row).published_version
        version = new_version(strategy_id, previous.version + 1, config)
        session.add(version)
        session.flush()
        result = version_view(version)
    return result


ALTERNATIVE_CONFIG_HASHES = {
    "mean_reversion": "10904787385cca66062bcb1b27d264799b3cc954ee7fed62a91d11339295d81b",
    "low_volatility": "133492a4ad378dff7e0ef2b96e3d6efe9f5a55fc3c286b440a32cb6a4c76fdcf",
}


def template_config(kind: str) -> StrategyConfigV1:
    if kind not in ALTERNATIVE_CONFIG_HASHES:
        raise ValueError("Unsupported alternative template")
    config = StrategyConfigV1.from_json(
        files("backend.strategies").joinpath(f"default_{kind}.json").read_bytes()
    )
    if config.signals.kind != kind or config.config_hash() != ALTERNATIVE_CONFIG_HASHES[kind]:
        raise ValueError("Packaged template differs from its ratified independent configuration")
    return config


def template_strategy_id(kind: str) -> UUID:
    if kind not in ALTERNATIVE_CONFIG_HASHES:
        raise ValueError("Unsupported alternative template")
    return uuid5(NAMESPACE_URL, f"https://yams.local/strategies/{kind.replace('_', '-')}")


def seed_templates(connection: Connection, workspace_id: UUID) -> None:
    """One atomic bootstrap owns all seeds; never rename a user's conflicting identity."""
    configs = [template_config(kind) for kind in sorted(ALTERNATIVE_CONFIG_HASHES)]
    seed_default(connection, workspace_id)
    for config in configs:
        kind = config.signals.kind
        identity = template_strategy_id(kind)
        version_id = uuid5(identity, "1")
        key = f"{kind}_v1"
        now = datetime.now(UTC)
        # Same advisory transaction lock as bootstrap/seed_default is held. A
        # concurrent ordinary create is still protected by the DB name constraint.
        existing = connection.execute(select(Strategy.id).where(Strategy.id == identity)).scalar()
        if existing is None:
            count = connection.execute(select(func.count()).select_from(Strategy)).scalar_one()
            for number in range(count + 2):
                name = (
                    config.display_name
                    if number == 0
                    else f"{config.display_name} (template {number})"
                )
                inserted = connection.execute(
                    insert(Strategy)
                    .values(
                        id=identity,
                        workspace_id=workspace_id,
                        name=name,
                        name_key=strategy_name(name).casefold(),
                        template_key=key,
                        created_at=now,
                    )
                    .on_conflict_do_nothing(constraint="uq_strategy_name")
                    .returning(Strategy.id)
                ).scalar()
                if inserted is not None:
                    break
            else:
                raise ValueError("Unable to reserve a compatible template identity")
            connection.execute(
                insert(StrategyVersion).values(
                    id=version_id,
                    strategy_id=identity,
                    version=1,
                    status="published",
                    config=json.loads(config.canonical_bytes()),
                    config_sha256=config.config_hash(),
                    published_at=now,
                )
            )
        with Session(bind=connection) as session:
            row = session.get(Strategy, identity)
            version = session.get(StrategyVersion, version_id)
            if (
                row is None
                or version is None
                or row.workspace_id != workspace_id
                or row.template_key != key
                or row.name_key != strategy_name(row.name).casefold()
                or version.strategy_id != identity
                or version.version != 1
                or version_view(version).config.canonical_bytes() != config.canonical_bytes()
            ):
                raise ValueError(
                    "Existing template identity or immutable configuration is incompatible"
                )
