"""Content fingerprint works identically in a checkout, wheel and Docker image."""

import hashlib
import platform
import re
import tomllib
from importlib.metadata import requires, version
from pathlib import Path

from backend.domain.types import canonical_json


def engine_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    sources = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
        if "tests" not in path.relative_to(root).parts
    }
    manifest = root.parent / "pyproject.toml"
    if manifest.is_file():
        project = tomllib.loads(manifest.read_text())["project"]
        if project["name"] != "yams":
            raise ValueError("Engine manifest identity mismatch")
        requirements = project["dependencies"]
    else:
        # Wheels carry distribution metadata; images carry the project manifest.
        requirements = requires("yams") or []
    dependencies = {}
    for requirement in requirements:
        if ";" in requirement and re.search(r"\bextra\b", requirement.split(";", 1)[1]):
            continue  # Optional acquisition extras are not the shared quant runtime.
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
        if match is None:
            raise ValueError("Unsupported engine dependency metadata")
        name = match.group().lower().replace("_", "-")
        dependencies[name] = version(name)
    architecture = platform.machine().lower()
    architecture = {"aarch64": "arm64", "amd64": "x86_64"}.get(architecture, architecture)
    return hashlib.sha256(
        canonical_json(
            {
                "python": platform.python_version(),
                "architecture": architecture,
                "dependencies": dependencies,
                "sources": sources,
            }
        )
    ).hexdigest()
