"""Offline fixture adapter over an explicitly pinned manifest identity."""

from pathlib import Path

from backend.market_data.files import PinnedSnapshot, SnapshotIntegrityError
from backend.market_data.repository import MarketRepository


def fixture_repository(snapshot_root: Path, expected_manifest_hash: str) -> MarketRepository:
    snapshot = PinnedSnapshot.open(snapshot_root, expected_manifest_hash)
    if snapshot.manifest.mode != "synthetic_fixture":
        raise SnapshotIntegrityError("Fixture adapter refuses research data")
    return MarketRepository(snapshot)
