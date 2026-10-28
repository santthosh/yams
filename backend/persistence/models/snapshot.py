"""Snapshot metadata: immutable content, separate local publication audit/pointer."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models.workspace import Base


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshot"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    manifest_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="ck_snapshot_digest"),
        CheckConstraint(
            "source_mode IN ('synthetic_fixture','research_market_data')",
            name="ck_snapshot_source_mode",
        ),
        CheckConstraint(
            "quality IN ('usable','usable_with_warnings','blocked')", name="ck_snapshot_quality"
        ),
    )


class SnapshotArtifactReference(Base):
    __tablename__ = "snapshot_artifact"
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT"), primary_key=True
    )
    path: Mapped[str] = mapped_column(String(512), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_snapshot_artifact_size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_snapshot_artifact_digest"),
    )


class SnapshotPublication(Base):
    __tablename__ = "snapshot_publication"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("job.id", ondelete="RESTRICT"), primary_key=True
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_token: Mapped[UUID] = mapped_column(nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CurrentSnapshot(Base):
    __tablename__ = "current_snapshot"
    # Mode-specific pointers prevent a fixture refresh replacing research evidence.
    source_mode: Mapped[str] = mapped_column(String(32), primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshot.id", ondelete="RESTRICT"), nullable=False
    )
    publication_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("snapshot_publication.job_id", ondelete="RESTRICT"), nullable=False
    )
    __table_args__ = (UniqueConstraint("source_mode", name="uq_current_snapshot_mode"),)
