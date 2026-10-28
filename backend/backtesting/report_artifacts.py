"""Fixed-role immutable report files with bounded, contained, hash-verified reads."""

import hashlib
import os
from pathlib import Path
from typing import Literal, Self
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, TypeAdapter, model_validator

from backend.backtesting.artifacts import _sync_directory
from backend.domain.common import ArtifactReference
from backend.domain.experiment_api import (
    ExperimentCurvePointV1,
    ExperimentReportSummaryV1,
    ExperimentReproducibilityV1,
    ExperimentTradeV1,
)
from backend.domain.types import Contract, Hash256, canonical_json, load_json
from backend.market_data.files import SnapshotIntegrityError, read_contained_file
from backend.market_data.publication import rename_no_replace

MAX_REPORT_BYTES = 64 * 1024 * 1024
Role = Literal["summary", "series", "trades", "reproducibility"]
ROLES: tuple[Role, ...] = ("summary", "series", "trades", "reproducibility")
FILENAMES = {
    "summary": "summary.json",
    "series": "series.jsonl",
    "trades": "trades.jsonl",
    "reproducibility": "reproducibility.json",
}


class ReportArtifact(Contract):
    role: Role
    reference: ArtifactReference
    size_bytes: int = Field(strict=True, ge=0, le=MAX_REPORT_BYTES)
    row_count: int = Field(strict=True, ge=0, le=2520000)


class ReportManifest(Contract):
    schema_version: Literal[1] = 1
    core_manifest_sha256: Hash256
    config_sha256: Hash256
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    engine_version: Hash256
    reporting_engine_version: Hash256
    artifacts: tuple[ReportArtifact, ...]

    @model_validator(mode="after")
    def fixed_roles(self) -> Self:
        if tuple(item.role for item in self.artifacts) != ROLES:
            raise ValueError("Report requires its exact ordered roles")
        if sum(item.size_bytes for item in self.artifacts) > MAX_REPORT_BYTES:
            raise ValueError("Report exceeds bounded artifact budget")
        return self

    def artifact(self, role: Role) -> ReportArtifact:
        return next(item for item in self.artifacts if item.role == role)


def encoded(value: Contract) -> bytes:
    return canonical_json(load_json(value.model_dump_json()))


def reference_for(role: Role, content: bytes) -> ArtifactReference:
    digest = hashlib.sha256(content).hexdigest()
    return ArtifactReference(
        id=uuid5(NAMESPACE_URL, f"yams:report:{role}:{digest}"), sha256=digest, schema_version=1
    )


def stage_report(
    stage: Path,
    summary: ExperimentReportSummaryV1,
    series: tuple[ExperimentCurvePointV1, ...],
    trades: tuple[ExperimentTradeV1, ...],
    reproducibility: ExperimentReproducibilityV1,
) -> str:
    contents: dict[Role, bytes] = {
        "summary": encoded(summary),
        "series": b"".join(encoded(item) + b"\n" for item in series),
        "trades": b"".join(encoded(item) + b"\n" for item in trades),
        "reproducibility": encoded(reproducibility),
    }
    counts = {"summary": 1, "series": len(series), "trades": len(trades), "reproducibility": 1}
    manifest = ReportManifest(
        core_manifest_sha256=reproducibility.core_manifest_sha256,
        config_sha256=reproducibility.config_sha256,
        snapshot_sha256=reproducibility.snapshot_sha256,
        calendar_sha256=reproducibility.calendar_sha256,
        engine_version=reproducibility.engine_version,
        reporting_engine_version=reproducibility.reporting_engine_version,
        artifacts=tuple(
            ReportArtifact(
                role=role,
                reference=reference_for(role, content),
                size_bytes=len(content),
                row_count=counts[role],
            )
            for role, content in contents.items()
        ),
    )
    manifest_bytes = encoded(manifest)
    stage.mkdir(mode=0o700, exist_ok=False)
    for name, content in [(FILENAMES[role], value) for role, value in contents.items()] + [
        ("manifest.json", manifest_bytes)
    ]:
        descriptor = os.open(
            stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    _sync_directory(stage)
    return hashlib.sha256(manifest_bytes).hexdigest()


def read_manifest(root: Path, digest: str) -> ReportManifest:
    TypeAdapter(Hash256).validate_python(digest)
    content = read_contained_file(root, "manifest.json", 1024 * 1024)
    if hashlib.sha256(content).hexdigest() != digest:
        raise SnapshotIntegrityError("Report manifest identity mismatch")
    return ReportManifest.model_validate_json(content)


def read_artifact(root: Path, manifest: ReportManifest, role: Role) -> bytes:
    artifact = manifest.artifact(role)
    content = read_contained_file(root, FILENAMES[role], artifact.size_bytes)
    if len(content) != artifact.size_bytes or reference_for(role, content) != artifact.reference:
        raise SnapshotIntegrityError("Report artifact identity mismatch")
    if role in {"series", "trades"} and (
        content.count(b"\n") != artifact.row_count or (content and not content.endswith(b"\n"))
    ):
        raise SnapshotIntegrityError("Report artifact row count mismatch")
    return content


def verify_report(root: Path, digest: str) -> ReportManifest:
    manifest = read_manifest(root, digest)
    for role in ROLES:
        read_artifact(root, manifest, role)
    return manifest


def publish_report(stage: Path, store: Path, digest: str) -> None:
    verify_report(stage, digest)
    try:
        rename_no_replace(stage, store / digest)
    except FileExistsError:
        verify_report(store / digest, digest)
    _sync_directory(store)
