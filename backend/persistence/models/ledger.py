"""Immutable economic evidence and separately mutable authorized-order lifecycles."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class RecommendationReference(Base):
    """Real linked envelope; #49 owns its production evaluator/content extensions."""

    __tablename__ = "recommendation"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT")
    )
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT")
    )
    as_of_session: Mapped[date] = mapped_column(Date)
    decision_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    portfolio_revision: Mapped[int] = mapped_column(BigInteger)
    source_mode: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_sha256: Mapped[str] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperOrderBatch(Base):
    __tablename__ = "paper_order_batch"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT")
    )
    recommendation_id: Mapped[UUID] = mapped_column(
        ForeignKey("recommendation.id", ondelete="RESTRICT")
    )
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT")
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    calendar_sha256: Mapped[str] = mapped_column(String(64))
    approved_revision: Mapped[int] = mapped_column(BigInteger)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decision_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    eligible_open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[UUID] = mapped_column()
    request_sha256: Mapped[str] = mapped_column(String(64))
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB)
    intent_sha256: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24))
    terminal: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperOrder(Base):
    __tablename__ = "paper_order"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("paper_order_batch.id", ondelete="RESTRICT"))
    ordinal: Mapped[int] = mapped_column(Integer)
    asset_id: Mapped[str] = mapped_column(String(160))
    sector: Mapped[str] = mapped_column()
    side: Mapped[str] = mapped_column(String(4))
    intent_key: Mapped[str] = mapped_column(String(256))
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    pending_quantity: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    closed_quantity: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    status: Mapped[str] = mapped_column(String(24))
    terminal: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(100))


class ActionEvidence(Base):
    __tablename__ = "paper_action_evidence"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT")
    )
    source_key: Mapped[str] = mapped_column(String(1024))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LedgerEvent(Base):
    __tablename__ = "ledger_event"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_portfolio.id", ondelete="RESTRICT")
    )
    sequence: Mapped[int] = mapped_column(BigInteger)
    portfolio_revision: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(40))
    event_key: Mapped[str] = mapped_column(String(256))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    order_id: Mapped[UUID | None] = mapped_column(ForeignKey("paper_order.id", ondelete="RESTRICT"))
    action_evidence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("paper_action_evidence.id", ondelete="RESTRICT")
    )
    correction_target_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ledger_event.id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT")
    )
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="RESTRICT")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class CashEntry(Base):
    __tablename__ = "cash_ledger_entry"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("ledger_event.id", ondelete="RESTRICT"))
    purpose: Mapped[str] = mapped_column(String(40))
    delta_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))


class PositionEvent(Base):
    __tablename__ = "position_event"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("ledger_event.id", ondelete="RESTRICT"))
    asset_id: Mapped[str] = mapped_column(String(160))
    sector: Mapped[str] = mapped_column()
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    basis_delta_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))


class PaperFill(Base):
    __tablename__ = "paper_fill"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("paper_order.id", ondelete="RESTRICT"))
    event_id: Mapped[UUID] = mapped_column(ForeignKey("ledger_event.id", ondelete="RESTRICT"))
    fill_event_key: Mapped[str] = mapped_column(String(256))
    execution_session: Mapped[date] = mapped_column(Date)
    raw_price: Mapped[Decimal] = mapped_column(Numeric)
    executed_price: Mapped[Decimal] = mapped_column(Numeric)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    gross_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    fee_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    slippage_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    cash_delta_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    removed_basis_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    realized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
