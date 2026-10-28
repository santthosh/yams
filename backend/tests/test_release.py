import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts import release as release_script
from scripts.release import image_ref, passed_main, release_available, verified_platforms


def test_only_exact_successful_main_ci_allows_release() -> None:
    good: dict[str, Any] = {
        "head_sha": "source",
        "head_branch": "main",
        "event": "push",
        "path": ".github/workflows/ci.yml",
        "status": "completed",
        "conclusion": "success",
    }
    assert passed_main([good], "source")
    assert not passed_main([], "source")
    for field, wrong in (
        ("head_sha", "other"),
        ("head_branch", "feature"),
        ("event", "pull_request"),
        ("path", "other.yml"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("conclusion", "cancelled"),
        ("conclusion", "neutral"),
    ):
        assert not passed_main([{**good, field: wrong}], "source")


def test_published_or_conflicting_version_cannot_be_replaced() -> None:
    assert release_available(None, "source")
    assert release_available({"draft": True, "target_commitish": "source"}, "source")
    assert not release_available({"draft": False, "target_commitish": "source"}, "source")
    assert not release_available({"draft": True, "target_commitish": "other"}, "source")


def test_candidate_image_must_be_immutable_and_in_owned_namespace() -> None:
    assert image_ref("backend", "sha256:" + "a" * 64).endswith("@sha256:" + "a" * 64)
    for name, digest in (("web", "latest"), ("other", "sha256:" + "a" * 64), ("web", "sha256:bad")):
        with pytest.raises(ValueError):
            image_ref(name, digest)


def test_both_native_installations_must_pass_for_exact_images_and_source() -> None:
    provenance = {
        "source_sha": "source",
        "images": {"backend": "backend-digest", "web": "web-digest"},
    }
    records = [
        {
            "native_host": host,
            "source_sha": "source",
            "passed": True,
            "backend": {"image": "backend-digest", "architecture": arch},
            "web": {"image": "web-digest", "architecture": arch},
        }
        for host, arch in (("x86_64", "amd64"), ("aarch64", "arm64"))
    ]
    assert verified_platforms(records, provenance)
    assert not verified_platforms(records[:1], provenance)
    assert not verified_platforms([records[0], records[0]], provenance)
    for field, value in (("passed", False), ("source_sha", "other"), ("native_host", "unknown")):
        changed = deepcopy(records)
        changed[0][field] = value
        assert not verified_platforms(changed, provenance)
    changed = deepcopy(records)
    changed[1]["web"] = {"image": "wrong", "architecture": "amd64"}
    assert not verified_platforms(changed, provenance)


def test_tag_source_outside_main_is_rejected_before_api_or_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.name", "Local release guard test")
    git("config", "user.email", "release-test@example.invalid")
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "main fixture")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("switch", "-c", "outside-main")
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "undelivered fixture")
    monkeypatch.setattr(release_script, "ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v0.0.1")
    monkeypatch.setenv("GITHUB_REPOSITORY", "santthosh/yams")

    def unexpected_api(path: str) -> Any:
        raise AssertionError("Invalid source must fail before network or publication")

    monkeypatch.setattr(release_script, "api", unexpected_api)
    with pytest.raises(subprocess.CalledProcessError):
        release_script.preflight()
