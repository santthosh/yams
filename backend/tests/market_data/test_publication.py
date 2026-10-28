from pathlib import Path

import pytest

from backend.market_data.files import SnapshotIntegrityError
from backend.market_data.publication import publish_sealed, rename_no_replace
from backend.tests.market_data.test_files import IDENTITY, copy_snapshot


def test_existing_empty_destination_cannot_be_replaced(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    destination = tmp_path / "existing"
    stage.mkdir()
    destination.mkdir()
    (stage / "marker").write_text("retained")
    with pytest.raises(FileExistsError):
        rename_no_replace(stage, destination)
    assert not (destination / "marker").exists()
    assert (stage / "marker").read_text() == "retained"


def test_publish_retry_and_corrupt_existing_destination(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    stage = copy_snapshot(tmp_path)
    published = publish_sealed(stage, store, IDENTITY)
    assert published.name == IDENTITY
    assert not stage.exists()
    retry = copy_snapshot(tmp_path)
    assert publish_sealed(retry, store, IDENTITY) == published
    assert retry.exists()
    (published / "bars.parquet").write_bytes(b"corrupt")
    with pytest.raises(SnapshotIntegrityError):
        publish_sealed(retry, store, IDENTITY)
    assert (published / "bars.parquet").read_bytes() == b"corrupt"
