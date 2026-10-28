"""Atomic, serialized migration plus idempotent singleton initialization."""

from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert

from backend.persistence.database import Settings, database_engine
from backend.persistence.models.workspace import LocalWorkspace
from backend.strategies.registry import seed_templates

MIGRATIONS = Path(__file__).parent / "migrations"


def migration_config(path: Path = MIGRATIONS) -> Config:
    config = Config()
    config.set_main_option("script_location", str(path))
    return config


def expected_revision(path: Path = MIGRATIONS) -> str:
    heads = ScriptDirectory.from_config(migration_config(path)).get_heads()
    if len(heads) != 1:
        raise RuntimeError("Expected one linear migration head")
    return heads[0]


def bootstrap(engine: Engine, migrations: Path = MIGRATIONS) -> UUID:
    config = migration_config(migrations)
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(1497451859)"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.execute(
            insert(LocalWorkspace)
            .values(
                id=uuid4(),
                singleton=1,
                locale="en-US",
                default_benchmark="SPY",
                preferences={"theme": "system"},
            )
            .on_conflict_do_nothing(index_elements=["singleton"])
        )
        identity = connection.execute(select(LocalWorkspace.id)).scalar_one()
        seed_templates(connection, identity)
        return identity


def main() -> None:
    settings = Settings.from_environment()
    engine = None
    try:
        if not settings.database_url:
            raise ValueError("Missing database configuration")
        engine = database_engine(settings.database_url)
        identity = bootstrap(engine)
    except Exception as error:
        raise SystemExit(
            f"Bootstrap failed error_type={type(error).__name__}; "
            "check database access and migration compatibility."
        ) from None
    finally:
        if engine is not None:
            engine.dispose()
    print(f"Workspace ready: {identity}")


if __name__ == "__main__":
    main()
