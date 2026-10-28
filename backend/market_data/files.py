"""Contained descriptor reads; consumers query pinned bytes, never changing paths."""

import hashlib
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from backend.domain.market import SnapshotManifestV1


class SnapshotIntegrityError(ValueError):
    """The requested immutable evidence cannot be verified."""


def _directory(path: Path) -> int:
    """Open every component without following a symlink, including ancestors."""
    absolute = path.absolute()
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            if part in {".", ".."}:
                raise SnapshotIntegrityError("Noncanonical snapshot root")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read(root: int, relative: str, limit: int) -> bytes:
    parts = relative.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise SnapshotIntegrityError("Invalid snapshot path")
    directory = os.dup(root)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise SnapshotIntegrityError("Expected a bounded regular, singly linked artifact")
            content = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if len(content) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise SnapshotIntegrityError("Artifact changed while reading")
            return content
    finally:
        os.close(directory)


@dataclass(frozen=True)
class PinnedSnapshot:
    manifest: SnapshotManifestV1
    artifacts: Mapping[str, bytes]

    @classmethod
    def open(cls, root: Path, expected_manifest_hash: str) -> "PinnedSnapshot":
        """Validate a registered/trusted identity and retain a private byte snapshot.

        The bounded reader supports 64 MiB per artifact and 256 MiB total. Larger
        snapshots must be partitioned or use a separately budgeted reader; no
        silent truncation or unbounded read is allowed.
        """
        try:
            descriptor = _directory(root)
            try:
                manifest = SnapshotManifestV1.model_validate_json(
                    _read(descriptor, "manifest.json", 1024 * 1024)
                )
                if manifest.manifest_hash() != expected_manifest_hash:
                    raise SnapshotIntegrityError("Snapshot identity mismatch")
                if sum(item.size_bytes for item in manifest.artifacts) > 256 * 1024 * 1024:
                    raise SnapshotIntegrityError("Snapshot exceeds reader budget")
                content = {}
                for item in manifest.artifacts:
                    data = _read(descriptor, item.path, min(item.size_bytes, 64 * 1024 * 1024))
                    if (
                        len(data) != item.size_bytes
                        or hashlib.sha256(data).hexdigest() != item.sha256
                    ):
                        raise SnapshotIntegrityError("Artifact integrity mismatch")
                    content[item.path] = data
                return cls(manifest, MappingProxyType(content))
            finally:
                os.close(descriptor)
        except (OSError, ValueError) as error:
            if isinstance(error, SnapshotIntegrityError):
                raise
            raise SnapshotIntegrityError("Snapshot unavailable or invalid") from error
