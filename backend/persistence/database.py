"""Bounded PostgreSQL connections. Never log connection URLs or parameters."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Settings:
    database_url: str | None = field(default=None, repr=False)
    fixture_root: Path = Path(__file__).resolve().parents[2] / "data/fixtures"

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL"),
            fixture_root=Path(os.environ.get("YAMS_FIXTURE_ROOT", str(cls.fixture_root))),
        )


def database_engine(url: str) -> Engine:
    try:
        parsed = make_url(url)
        if parsed.drivername != "postgresql+psycopg":
            raise ValueError("Unsupported database driver")
        return create_engine(
            parsed,
            echo=False,
            hide_parameters=True,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            pool_timeout=2,
            connect_args={
                "connect_timeout": 2,
                "options": "-c statement_timeout=5000 -c lock_timeout=5000",
            },
        )
    except Exception:
        raise ValueError("Invalid PostgreSQL configuration") from None
