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


def test_interrupted_draft_resumes_only_identical_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    bundle = tmp_path / "release-bundle"
    bundle.mkdir()
    verification = tmp_path / "verification"
    verification.mkdir()
    images = {name: image_ref(name, "sha256:" + "a" * 64) for name in ("backend", "web")}
    (bundle / "provenance.json").write_text(json.dumps({"source_sha": "source", "images": images}))
    (bundle / "INSTALL.md").write_text("Installation fixture")
    for host, arch in (("x86_64", "amd64"), ("aarch64", "arm64")):
        directory = verification / arch
        directory.mkdir()
        (directory / "evidence.json").write_text(
            json.dumps(
                {
                    "native_host": host,
                    "source_sha": "source",
                    "passed": True,
                    **{
                        name: {"image": image, "architecture": arch}
                        for name, image in images.items()
                    },
                }
            )
        )
    monkeypatch.setattr(release_script, "ROOT", tmp_path)
    monkeypatch.setenv("RELEASE_VERSION", "0.0.1")
    monkeypatch.setenv("RELEASE_SHA", "source")
    state: dict[str, Any] = {"release": None, "assets": {}, "interrupt": True}

    def current_release(tag: str) -> Any:
        if state["release"] is None:
            return None
        return {
            "draft": state["release"] == "draft",
            "target_commitish": "source",
            "assets": [{"name": name, "id": name} for name in state["assets"]],
        }

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "api", "repos/santthosh/yams/git/ref/tags/v0.0.1"]:
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"object": {"type": "commit", "sha": "source"}}), ""
            )
        if args[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            return subprocess.CompletedProcess(args, 0, "existing verified alias", "")
        if args == ["sha256sum", "--check", "SHA256SUMS"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    def command(*args: str) -> str:
        if args[:3] == ("gh", "release", "create"):
            state["release"] = "draft"
        elif args[:3] == ("gh", "release", "upload"):
            path = Path(args[4])
            if state["interrupt"] and state["assets"]:
                raise RuntimeError("Simulated interrupted upload")
            assert path.name not in state["assets"]
            state["assets"][path.name] = path.read_bytes()
        elif args[:3] == ("gh", "release", "edit"):
            assert "--draft=false" in args
            state["release"] = "published"
        else:
            raise AssertionError(args)
        return ""

    def download(args: list[str], **kwargs: Any) -> bytes:
        assert args[:2] == ["gh", "api"]
        return bytes(state["assets"][args[-1].rsplit("/", 1)[1]])

    monkeypatch.setattr(release_script, "existing_release", current_release)
    monkeypatch.setattr(release_script, "manifest_digest", lambda reference: "sha256:" + "a" * 64)
    monkeypatch.setattr(release_script, "command", command)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "check_output", download)
    with pytest.raises(RuntimeError, match="interrupted"):
        release_script.publish()
    assert state["release"] == "draft" and len(state["assets"]) == 1
    name = next(iter(state["assets"]))
    original = state["assets"][name]
    state["assets"][name] = b"conflicting partial upload"
    state["interrupt"] = False
    with pytest.raises(SystemExit, match="Conflicting draft asset"):
        release_script.publish()
    assert state["release"] == "draft"
    state["assets"][name] = original
    release_script.publish()
    assert state["release"] == "published"
    assert set(state["assets"]) == {path.name for path in bundle.iterdir()}
    with pytest.raises(SystemExit, match="published version"):
        release_script.publish()
