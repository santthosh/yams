"""Durable paper accounts and derivable exact-cent/six-decimal projections."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolio"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("local_workspace.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3))
    source_mode: Mapped[str] = mapped_column(String(32))
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="RESTRICT")
    )
    opening_cash_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    opening_event_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "ledger_event.id",
            name="fk_portfolio_opening",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        )
    )
    opening_sha256: Mapped[str] = mapped_column(String(64))
    cash_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    revision: Mapped[int] = mapped_column(BigInteger)
    last_sequence: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24))
    reconciliation_failed: Mapped[bool] = mapped_column(Boolean)
    state_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperPosition(Base):
    __tablename__ = "paper_position"

    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    sector: Mapped[str] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    total_basis_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    last_sequence: Mapped[int] = mapped_column(BigInteger)
