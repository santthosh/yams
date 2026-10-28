"""Strategy identity is distinct from append-only published configuration."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class Strategy(Base):
    __tablename__ = "strategy"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name_key", name="uq_strategy_name"),
        UniqueConstraint("workspace_id", "template_key", name="uq_strategy_template"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("local_workspace.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_key: Mapped[str] = mapped_column(String(360), nullable=False)
    template_key: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategyVersion(Base):
    __tablename__ = "strategy_version"
    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    strategy_id: Mapped[UUID] = mapped_column(ForeignKey("strategy.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
