"""Bounded, hash-verified, filesystem-before-database core publication."""

import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter

from backend.backtesting.runner import BacktestCoreResult
from backend.domain.types import Contract, Hash256, canonical_json, load_json
from backend.market_data.files import SnapshotIntegrityError, read_contained_file
from backend.market_data.publication import rename_no_replace

MAX_CORE_BYTES = 64 * 1024 * 1024


class CoreManifest(Contract):
    schema_version: Literal[1] = 1
    core_sha256: Hash256
    core_size_bytes: int = Field(strict=True, ge=1, le=MAX_CORE_BYTES)
    config_sha256: Hash256
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    engine_version: str
    policy_version: Literal["walk_forward_v1"] = "walk_forward_v1"


def manifest_for(result: BacktestCoreResult, content: bytes) -> CoreManifest:
    return CoreManifest(
        core_sha256=hashlib.sha256(content).hexdigest(),
        core_size_bytes=len(content),
        config_sha256=result.config_sha256,
        snapshot_sha256=result.snapshot_sha256,
        calendar_sha256=result.calendar_sha256,
        engine_version=result.engine_version,
    )


def _canonical(result: BacktestCoreResult | CoreManifest) -> bytes:
    return canonical_json(load_json(result.model_dump_json()))


def stage_core(stage: Path, result: BacktestCoreResult) -> str:
    content = _canonical(result)
    manifest = _canonical(manifest_for(result, content))
    stage.mkdir(mode=0o700, exist_ok=False)
    for name, value in (("core.json", content), ("manifest.json", manifest)):
        descriptor = os.open(
            stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    _sync_directory(stage)
    return hashlib.sha256(manifest).hexdigest()


def read_core(root: Path, digest: str) -> BacktestCoreResult:
    digest = TypeAdapter(Hash256).validate_python(digest)
    manifest_bytes = read_contained_file(root, "manifest.json", 1024 * 1024)
    if hashlib.sha256(manifest_bytes).hexdigest() != digest:
        raise SnapshotIntegrityError("Core manifest identity mismatch")
    manifest = CoreManifest.model_validate_json(manifest_bytes)
    content = read_contained_file(root, "core.json", manifest.core_size_bytes)
    if (
        len(content) != manifest.core_size_bytes
        or hashlib.sha256(content).hexdigest() != manifest.core_sha256
    ):
        raise SnapshotIntegrityError("Core artifact integrity mismatch")
    result = BacktestCoreResult.model_validate_json(content)
    if manifest_for(result, content) != manifest:
        raise SnapshotIntegrityError("Core manifest lineage mismatch")
    return result


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_core(stage: Path, store: Path, digest: str) -> Path:
    """Caller owns digest/lease lock; arbitrary preexisting orphans are not adopted."""
    read_core(stage, digest)
    destination = store / digest
    for name in ("core.json", "manifest.json"):
        descriptor = os.open(stage / name, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    _sync_directory(stage)
    try:
        rename_no_replace(stage, destination)
    except FileExistsError:
        read_core(destination, digest)
    _sync_directory(store)
    return destination
