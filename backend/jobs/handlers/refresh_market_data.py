"""Prepare private sealed artifacts; only the supervisor can register them."""

import os
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

from backend.jobs.registry import RefreshPayload
from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository
from backend.market_data.research import acquire_research_snapshot
from backend.persistence.database import Settings


def refresh_market_data(payload: dict[str, Any], cancelled: Event, *, stage: Path) -> str:
    config = RefreshPayload.model_validate(payload)
    if config.source_mode == "research_market_data":
        assert config.research_config is not None
        pinned = acquire_research_snapshot(config.research_config, cancelled=cancelled.is_set)
    else:
        assert config.expected_manifest_hash is not None
        pinned = PinnedSnapshot.open(
            Settings.from_environment().fixture_root / "snapshot", config.expected_manifest_hash
        )
    with MarketRepository(pinned):
        pass
    stage.mkdir(mode=0o700)
    content = {**pinned.artifacts, "manifest.json": pinned.manifest.canonical_bytes()}
    for name, data in content.items():
        if cancelled.is_set():
            raise RuntimeError("Refresh cancelled before sealing")
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return pinned.manifest.manifest_hash()
