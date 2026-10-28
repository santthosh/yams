import json
import os
import shutil
from pathlib import Path

import pytest

from backend.market_data.files import PinnedSnapshot, SnapshotIntegrityError

FIXTURES = Path(__file__).resolve().parents[3] / "data/fixtures"
IDENTITY = json.loads((FIXTURES / "manifest.json").read_text())["snapshot_sha256"]


def copy_snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "snapshot"
    shutil.copytree(FIXTURES / "snapshot", root)
    return root


def test_pin_survives_external_change_but_new_reader_rejects_it(tmp_path: Path) -> None:
    root = copy_snapshot(tmp_path)
    pinned = PinnedSnapshot.open(root, IDENTITY)
    original = pinned.artifacts["bars.parquet"]
    (root / "bars.parquet").write_bytes(b"corrupt replacement")
    assert pinned.artifacts["bars.parquet"] == original
    with pytest.raises(SnapshotIntegrityError, match="integrity"):
        PinnedSnapshot.open(root, IDENTITY)
    with pytest.raises(TypeError):
        pinned.artifacts["bars.parquet"] = b"mutation"  # type: ignore[index]


@pytest.mark.parametrize(
    "kind", ["file_symlink", "root_symlink", "ancestor_symlink", "hardlink", "fifo"]
)
def test_rejects_indirection_and_nonregular_artifacts(tmp_path: Path, kind: str) -> None:
    root = copy_snapshot(tmp_path)
    original = root / "bars.parquet"
    if kind in {"file_symlink", "hardlink", "fifo"}:
        outside = tmp_path / "outside.json"
        original.rename(outside)
        if kind == "file_symlink":
            original.symlink_to(outside)
        elif kind == "hardlink":
            os.link(outside, original)
        else:
            os.mkfifo(original)
    elif kind == "root_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    else:
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        root = alias / "snapshot"
    with pytest.raises(SnapshotIntegrityError):
        PinnedSnapshot.open(root, IDENTITY)


def test_identity_is_pinned_and_portable(tmp_path: Path) -> None:
    root = copy_snapshot(tmp_path)
    assert PinnedSnapshot.open(root, IDENTITY).manifest.manifest_hash() == IDENTITY
    with pytest.raises(SnapshotIntegrityError, match="identity"):
        PinnedSnapshot.open(root, "0" * 64)
