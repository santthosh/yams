"""Tamper, orphan and path safety around authored synthetic core artifacts."""

import hashlib
import os
from pathlib import Path

import pytest

from backend.backtesting.artifacts import publish_core, read_core, stage_core
from backend.market_data.files import SnapshotIntegrityError, read_contained_file
from backend.tests.backtesting.test_core import pinned, run


def test_deterministic_stage_no_overwrite_and_verified_orphan_reuse(tmp_path: Path) -> None:
    result = run(pinned(tmp_path))
    stage = tmp_path / "stage"
    digest = stage_core(stage, result)
    assert read_core(stage, digest) == result
    assert digest == hashlib.sha256((stage / "manifest.json").read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        stage_core(stage, result)
    store = tmp_path / "store"
    store.mkdir()
    destination = publish_core(stage, store, digest)
    assert not stage.exists() and destination.name == digest
    assert read_core(destination, digest) == result
    # Fresh recomputation, not arbitrary adoption of a directory with a trusted name.
    retry = tmp_path / "retry"
    assert stage_core(retry, result) == digest
    assert publish_core(retry, store, digest) == destination
    (destination / "core.json").write_bytes(b"corrupt")
    with pytest.raises(SnapshotIntegrityError):
        publish_core(retry, store, digest)


@pytest.mark.parametrize(
    "mutation", ["core", "manifest", "symlink", "hardlink", "missing", "ancestor"]
)
def test_incomplete_or_unsafe_artifact_cannot_be_read(tmp_path: Path, mutation: str) -> None:
    result = run(pinned(tmp_path))
    stage = tmp_path / "stage"
    digest = stage_core(stage, result)
    if mutation in {"core", "manifest"}:
        (stage / ("core.json" if mutation == "core" else "manifest.json")).write_bytes(b"{}")
    elif mutation == "symlink":
        (stage / "core.json").rename(tmp_path / "outside")
        (stage / "core.json").symlink_to(tmp_path / "outside")
    elif mutation == "hardlink":
        os.link(stage / "core.json", tmp_path / "linked")
    elif mutation == "missing":
        (stage / "core.json").unlink()
    else:
        (tmp_path / "alias").symlink_to(stage, target_is_directory=True)
        stage = tmp_path / "alias"
    with pytest.raises(SnapshotIntegrityError):
        read_core(stage, digest)


def test_reader_and_digest_reject_traversal_and_unbounded_budget(tmp_path: Path) -> None:
    for path, budget in [
        ("../secret", 100),
        ("core.json", 64 * 1024 * 1024 + 1),
        ("core.json", -1),
    ]:
        with pytest.raises(SnapshotIntegrityError):
            read_contained_file(tmp_path, path, budget)
    with pytest.raises(ValueError):
        read_core(tmp_path, "../secret")
