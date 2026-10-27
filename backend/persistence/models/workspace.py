from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LocalWorkspace(Base):
    __tablename__ = "local_workspace"
    __table_args__ = (
        CheckConstraint("singleton = 1", name="ck_workspace_singleton"),
        UniqueConstraint("singleton", name="uq_workspace_singleton"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    singleton: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    default_benchmark: Mapped[str] = mapped_column(String(160), nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
