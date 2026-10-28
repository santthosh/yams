"""Filesystem publication primitive; #30 owns lease/lock and DB registration."""

import ctypes
import errno
import os
import sys
from pathlib import Path

from backend.market_data.files import PinnedSnapshot
from backend.market_data.repository import MarketRepository


def rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically move a sealed private directory, refusing any existing target.

    Supported local platforms: Linux renameat2 and macOS renamex_np. No copy or
    overwrite-capable fallback is permitted. The caller owns both parent paths.
    """
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "linux":
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    elif sys.platform == "darwin":
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(os.fsencode(source), os.fsencode(destination), 4)
    else:
        raise OSError(errno.ENOTSUP, "Atomic no-replace publication is unsupported")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def publish_sealed(stage: Path, store: Path, expected_hash: str) -> Path:
    """Validate and durably publish under an externally held digest/lease lock.

    Stage and store must be private, same-filesystem directories. Writers must have
    finished before entry and remain excluded until registration. No database row
    or current pointer is changed here. A post-rename failure leaves an orphan for
    #30's verified recovery; it must never trigger deletion or automatic adoption.
    """
    pinned = PinnedSnapshot.open(stage, expected_hash)
    with MarketRepository(pinned):
        pass
    destination = store / pinned.manifest.manifest_hash()
    # Keep validation descriptors and durable writes restricted to validated paths.
    for name in (*pinned.artifacts, "manifest.json"):
        descriptor = os.open(stage / name, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    descriptor = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        rename_no_replace(stage, destination)
    except FileExistsError:
        # Existing bytes must be verified, even when the directory name is trusted.
        PinnedSnapshot.open(destination, expected_hash)
    descriptor = os.open(store, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return destination
