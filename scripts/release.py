"""Validate, package and publish an immutable local Docker prerelease."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = "santthosh/yams"
VERSION = re.compile(r"0\.0\.[1-9][0-9]*(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def api(path: str) -> Any:
    return json.loads(command("gh", "api", path))


def existing_release(tag: str) -> Any:
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/releases/tags/{tag}"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    if "HTTP 404" in result.stderr:
        # Drafts are not consistently exposed by the tag endpoint; write-scoped
        # publication credentials can see them in the releases listing.
        return next(
            (
                release
                for release in api(f"repos/{REPO}/releases?per_page=100")
                if release["tag_name"] == tag
            ),
            None,
        )
    raise RuntimeError(result.stderr)


def wait_for_draft(tag: str, sha: str) -> Any:
    """Bound GitHub's read-after-create lag without recreating or replacing a release."""
    for attempt in range(10):
        release = existing_release(tag)
        if release is not None:
            if not release_available(release, sha) or release.get("draft") is not True:
                raise SystemExit("Refusing to modify a published release or conflicting draft")
            return release
        if attempt < 9:
            time.sleep(1)
    raise SystemExit("Release draft is not visible; retry publication without rebuilding images")


def passed_main(runs: list[dict[str, Any]], sha: str) -> bool:
    return any(
        run.get("head_sha") == sha
        and run.get("head_branch") == "main"
        and run.get("event") == "push"
        and run.get("path") == ".github/workflows/ci.yml"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        for run in runs
    )


def release_available(release: dict[str, Any] | None, sha: str) -> bool:
    return release is None or (
        release.get("draft") is True and release.get("target_commitish") == sha
    )


def image_ref(name: str, digest: str) -> str:
    if name not in {"backend", "web"} or not DIGEST.fullmatch(digest):
        raise ValueError("Expected a verified YAMS image digest")
    return f"ghcr.io/santthosh/yams-{name}@{digest}"


def emit(**values: str) -> None:
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def manifest_digest(reference: str) -> str:
    output = command("docker", "buildx", "imagetools", "inspect", reference)
    match = re.search(r"^Digest:\s+(sha256:[0-9a-f]{64})$", output, re.M)
    if not match:
        raise ValueError("Registry inspection did not return an immutable digest")
    return match[1]


def indexes() -> None:
    records = [json.loads(path.read_text()) for path in (ROOT / "digests").glob("*.json")]
    expected = {(name, arch) for name in ("backend", "web") for arch in ("amd64", "arm64")}
    if len(records) != 4 or {(r["component"], r["arch"]) for r in records} != expected:
        raise SystemExit("Missing or duplicate platform candidate")
    outputs = {}
    for name in ("backend", "web"):
        selected = [r for r in records if r["component"] == name]
        if any(r["source_sha"] != os.environ["RELEASE_SHA"] for r in selected):
            raise SystemExit("Candidate source mismatch")
        tag = f"ghcr.io/santthosh/yams-{name}:candidate-{os.environ['GITHUB_RUN_ID']}"
        command(
            "docker",
            "buildx",
            "imagetools",
            "create",
            "--tag",
            tag,
            *(image_ref(name, r["digest"]) for r in selected),
        )
        outputs[name + "_digest"] = manifest_digest(tag)
    emit(**outputs)


def verified_platforms(records: list[dict[str, Any]], provenance: dict[str, Any]) -> bool:
    hosts = {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    return (
        len(records) == 2
        and set(provenance["images"]) == {"backend", "web"}
        and {hosts.get(record.get("native_host", "")) for record in records} == {"amd64", "arm64"}
        and all(
            record.get("passed") is True
            and record.get("source_sha") == provenance["source_sha"]
            and all(
                record.get(name, {}).get("architecture") == hosts.get(record.get("native_host", ""))
                for name in ("backend", "web")
            )
            and all(
                record.get(name, {}).get("image") == image
                for name, image in provenance["images"].items()
            )
            for record in records
        )
    )


def validate_application_version(version: str) -> None:
    base = version.split("-", 1)[0]
    versions = {
        tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        json.loads((ROOT / "apps/web/package.json").read_text())["version"],
        json.loads((ROOT / "contracts/openapi.json").read_text())["info"]["version"],
    }
    if versions != {base}:
        raise SystemExit("Release version differs from package/API versions")


def preflight() -> None:
    event = os.environ["GITHUB_EVENT_NAME"]
    ref = os.environ["GITHUB_REF"]
    if os.environ["GITHUB_REPOSITORY"] != REPO:
        raise SystemExit("Release repository mismatch")
    if event == "workflow_dispatch" and ref == "refs/heads/main":
        version = os.environ["VERSION_INPUT"]
    elif event == "push" and ref.startswith("refs/tags/v"):
        version = ref.removeprefix("refs/tags/v")
    else:
        raise SystemExit("Release must use main dispatch or a version tag")
    if not VERSION.fullmatch(version):
        raise SystemExit("Expected a 0.0.x semver version, optionally prerelease-qualified")
    sha = command("git", "rev-parse", "HEAD")
    subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"], cwd=ROOT, check=True)
    runs = api(f"repos/{REPO}/actions/workflows/ci.yml/runs?event=push&head_sha={sha}&per_page=100")
    if not passed_main(runs["workflow_runs"], sha):
        raise SystemExit("Exact release SHA has no successful main CI run")
    validate_application_version(version)
    release = existing_release("v" + version)
    if not release_available(release, sha):
        raise SystemExit("Published version or conflicting draft already exists; never overwrite")
    emit(version=version, sha=sha)
    print(f"Validated v{version} at exact main-tested SHA {sha}")


def recovery_preflight() -> None:
    # The recovery implementation itself must be reviewed and pass main CI.
    if os.environ["GITHUB_REPOSITORY"] != REPO:
        raise SystemExit("Recovery repository mismatch")
    if (
        os.environ["GITHUB_EVENT_NAME"] != "workflow_dispatch"
        or os.environ["GITHUB_REF"] != "refs/heads/main"
    ):
        raise SystemExit("Recovery must be dispatched from main")
    current = command("git", "rev-parse", "HEAD")
    runs = api(
        f"repos/{REPO}/actions/workflows/ci.yml/runs?event=push&head_sha={current}&per_page=100"
    )
    if not passed_main(runs["workflow_runs"], current):
        raise SystemExit("Recovery implementation has no successful main CI")
    version, run_id = os.environ["VERSION_INPUT"], os.environ["RECOVERY_RUN"]
    if not VERSION.fullmatch(version) or not run_id.isdecimal():
        raise SystemExit("Invalid recovery version/run")
    run = api(f"repos/{REPO}/actions/runs/{run_id}")
    jobs = api(f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100")["jobs"]
    if not recoverable_run(run, jobs, version):
        raise SystemExit("Recovery requires a failed tag publication with all native gates passed")
    sha = run["head_sha"]
    target = api(f"repos/{REPO}/git/ref/tags/v{version}")["object"]
    if target["type"] != "commit" or target["sha"] != sha:
        raise SystemExit("Recovery tag/source mismatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"], cwd=ROOT, check=True)
    source_runs = api(
        f"repos/{REPO}/actions/workflows/ci.yml/runs?event=push&head_sha={sha}&per_page=100"
    )
    if not passed_main(source_runs["workflow_runs"], sha):
        raise SystemExit("Recovery requires passing source CI")
    emit(version=version, sha=sha)


def recoverable_run(run: dict[str, Any], jobs: list[dict[str, Any]], version: str) -> bool:
    expected = {
        "validate",
        "package",
        "build (backend, amd64, ubuntu-24.04)",
        "build (backend, arm64, ubuntu-24.04-arm)",
        "build (web, amd64, ubuntu-24.04)",
        "build (web, arm64, ubuntu-24.04-arm)",
        "verify (amd64, ubuntu-24.04)",
        "verify (arm64, ubuntu-24.04-arm)",
    }
    results = {job["name"]: job["conclusion"] for job in jobs}
    return (
        run.get("event") == "push"
        and run.get("head_branch") == "v" + version
        and run.get("path") == ".github/workflows/release.yml"
        and run.get("status") == "completed"
        and run.get("conclusion") == "failure"
        and len(jobs) == len(expected) + 1
        and set(results) == expected | {"publish"}
        and all(results[name] == "success" for name in expected)
        and results["publish"] == "failure"
    )


def release_summary(version: str) -> tuple[str, str]:
    if version == "0.0.1":
        return (
            "offline foundation",
            "Local paper-only foundation. Download all assets, verify SHA256SUMS and follow "
            "INSTALL.md. No financial engine or live provider execution is included.",
        )
    if version == "0.0.2":
        return (
            "market data and candidate diagnostics",
            "Local paper-only research prerelease: immutable market snapshots, published "
            "strategy versions and reproducible candidate/target diagnostics. Offline "
            "synthetic examples and optional personal-use Tiingo acquisition are included. "
            "Download all assets, verify SHA256SUMS and follow INSTALL.md. See RESEARCH.md "
            "for user-owned credentials, source quotas and timing. No backtests, forecasts "
            "or durable paper accounts/orders/fills are included. Real source data is not "
            "redistributed; complete corporate-action accounting remains unsupported.",
        )
    if version == "0.0.3":
        return (
            "Strategy Lab and historical experiments",
            "Local paper-only research prerelease: immutable strategy versions, momentum/"
            "mean-reversion/low-volatility templates, bounded walk-forward experiments, "
            "separate development/holdout metrics, aligned SPY/cash comparisons and "
            "controlled one-rule challenges. Historical accounting examples use explicitly "
            "labeled synthetic data; real provider acquisition remains diagnostic-only. "
            "Download all assets, verify SHA256SUMS and follow INSTALL.md. Native amd64 "
            "and arm64 packaged installations verify the actual editor/worker/report/"
            "comparison journey and retained state. No forecasts or durable paper accounts/"
            "orders/fills are included; no real money or brokerage is involved.",
        )
    if version == "0.0.4":
        return (
            "Paper Portfolios",
            "Local paper-only prerelease: independent cash accounts, posted holdings, "
            "exact-cent immutable ledger history and backend valuations, with idempotent "
            "authorization and fenced synthetic fill/action processing. Native amd64 and "
            "arm64 installations verify browser-created $1,000 accounts and explicitly "
            "service-seeded synthetic fills through the real worker, including cached "
            "restart. Public recommendation/apply controls and forecasts remain staged "
            "for 0.0.5. Real feeds remain diagnostic-only; financial examples are labeled "
            "SYNTHETIC_DATA_ONLY. Download all assets, verify SHA256SUMS and follow INSTALL.md. "
            "No real money or brokerage is involved.",
        )
    return (
        "local paper research prerelease",
        "Local paper-only research prerelease. Download all assets, verify SHA256SUMS "
        "and follow INSTALL.md for delivered capabilities and limits. No real-money trading.",
    )


def package() -> None:
    version, sha = os.environ["RELEASE_VERSION"], os.environ["RELEASE_SHA"]
    images = {
        name: image_ref(name, os.environ[name.upper() + "_DIGEST"]) for name in ("backend", "web")
    }
    env = {**os.environ, "YAMS_WEB_PORT": "3000", "YAMS_JOB_LIMITS": "{}"}
    env.update(YAMS_BACKEND_IMAGE=images["backend"], YAMS_WEB_IMAGE=images["web"])
    config = json.loads(
        subprocess.check_output(
            [
                "docker",
                "compose",
                "-f",
                "compose.yaml",
                "-f",
                "compose.release.yaml",
                "config",
                "--format",
                "json",
            ],
            cwd=ROOT,
            env=env,
            text=True,
        )
    )
    config = {key: value for key, value in config.items() if not key.startswith("x-")}
    # Rendered names would defeat -p isolation and could touch an operator's volumes.
    for section in ("networks", "volumes"):
        for value in config[section].values():
            if value.get("external"):
                raise SystemExit("Release resources must remain project-scoped")
            value.pop("name", None)
    for name, service in config["services"].items():
        if "build" in service or "@sha256:" not in service["image"]:
            raise SystemExit(f"Release service {name} is not a prebuilt pinned image")
        if name in {"api", "worker", "migrate"}:
            service["environment"]["YAMS_JOB_LIMITS"] = "${YAMS_JOB_LIMITS:-{}}"
    config["services"]["web"]["ports"][0]["published"] = "${YAMS_WEB_PORT:-3000}"
    destination = ROOT / "release-bundle"
    destination.mkdir(exist_ok=True)
    (destination / "compose.yaml").write_text(json.dumps(config, indent=2) + "\n")
    (destination / "env.example").write_text(
        "# Offline paper-only default\nYAMS_WEB_PORT=3000\n# YAMS_JOB_LIMITS={}\n"
        "# Optional local research only; see RESEARCH.md. Never publish your token.\n"
        "# TIINGO_API_TOKEN=\n"
    )
    shutil.copyfile(ROOT / "docs/releases.md", destination / "INSTALL.md")
    shutil.copyfile(ROOT / "compose.research.yaml", destination / "compose.research.yaml")
    research = (ROOT / "docs/operations/tiingo-research.md").read_text()
    research = research.replace(
        "../adr/0010-free-research-provider.md",
        f"https://github.com/{REPO}/blob/{sha}/docs/adr/0010-free-research-provider.md",
    )
    (destination / "RESEARCH.md").write_text(research)
    provenance = {
        "repository": REPO,
        "version": version,
        "source_sha": sha,
        "workflow_run": f"https://github.com/{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
        "images": images,
        "platforms": ["linux/amd64", "linux/arm64"],
        "fixture_manifest_sha256": hashlib.sha256(
            (ROOT / "data/fixtures/manifest.json").read_bytes()
        ).hexdigest(),
        "build_provenance": "BuildKit provenance and SBOM attached to image manifests",
    }
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    names = (
        "compose.yaml",
        "compose.research.yaml",
        "env.example",
        "INSTALL.md",
        "RESEARCH.md",
        "provenance.json",
    )
    (destination / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((destination / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names
        )
    )


def publish() -> None:
    version, sha = os.environ["RELEASE_VERSION"], os.environ["RELEASE_SHA"]
    tag = "v" + version
    release = existing_release(tag)
    # Drafts require write-scoped API visibility; validate them here before any mutation.
    if os.environ.get("RECOVERY_RUN") and not release:
        raise SystemExit("Recovery requires an existing unpublished draft")
    if not release_available(release, sha):
        raise SystemExit("Refusing to replace a published version or conflicting draft")
    destination = ROOT / "release-bundle"
    provenance = json.loads((destination / "provenance.json").read_text())
    records = [
        json.loads(path.read_text()) for path in (ROOT / "verification").rglob("evidence.json")
    ]
    if not verified_platforms(records, provenance) or provenance["source_sha"] != sha:
        raise SystemExit("Both exact native platform installations must pass before publication")
    for record in records:
        arch = record["backend"]["architecture"]
        if arch not in {"amd64", "arm64"}:
            raise SystemExit("Unknown verified platform")
        (destination / f"evidence-{arch}.json").write_text(json.dumps(record, indent=2) + "\n")
    files = sorted(
        path for path in destination.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    (destination / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files)
    )
    # Tag creation is restricted separately from immutable update/deletion rules.
    tag_result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/git/ref/tags/{tag}"], capture_output=True, text=True
    )
    if tag_result.returncode == 0:
        target = json.loads(tag_result.stdout)["object"]
        for _ in range(5):
            if target["type"] != "tag":
                break
            target = api(f"repos/{REPO}/git/tags/{target['sha']}")["object"]
        if target["type"] != "commit" or target["sha"] != sha:
            raise SystemExit("Existing version tag does not match the verified source")
    elif "HTTP 404" in tag_result.stderr:
        raise SystemExit("Administrator must create the verified immutable version tag first")
    else:
        raise RuntimeError(tag_result.stderr)
    for name, image in provenance["images"].items():
        alias = f"ghcr.io/santthosh/yams-{name}:{version}"
        existing = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", alias], capture_output=True, text=True
        )
        if existing.returncode == 0:
            if manifest_digest(alias) != image.split("@", 1)[1]:
                raise SystemExit("Existing version image differs; never overwrite")
        elif "not found" in existing.stderr.lower():
            command("docker", "buildx", "imagetools", "create", "--tag", alias, image)
            if manifest_digest(alias) != image.split("@", 1)[1]:
                raise SystemExit("Version alias digest mismatch")
        else:
            raise RuntimeError(existing.stderr)
    subprocess.run(["sha256sum", "--check", "SHA256SUMS"], cwd=destination, check=True)
    if not release:
        command(
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            REPO,
            "--verify-tag",
            "--target",
            sha,
            "--draft",
            "--prerelease",
            "--title",
            f"YAMS {tag} — {release_summary(version)[0]}",
            "--notes",
            release_summary(version)[1],
        )
    # Resume only identical draft assets; never clobber an existing asset.
    release = wait_for_draft(tag, sha)
    allowed_assets = {path.name for path in destination.iterdir() if path.is_file()}

    def logical_name(name: str) -> str:
        # GitHub sanitizes a leading-dot upload name. Keep the original verified
        # bytes/checksums for legacy bundles; future bundles use env.example.
        if name == "default.env.example" and ".env.example" in allowed_assets:
            return ".env.example"
        return name

    assets = {logical_name(asset["name"]): asset for asset in release["assets"]}
    for path in sorted(destination.iterdir()):
        if not path.is_file():
            continue
        if path.name in assets:
            content = subprocess.check_output(
                [
                    "gh",
                    "api",
                    "-H",
                    "Accept: application/octet-stream",
                    f"repos/{REPO}/releases/assets/{assets[path.name]['id']}",
                ]
            )
            if content != path.read_bytes():
                raise SystemExit(f"Conflicting draft asset: {path.name}")
        else:
            command("gh", "release", "upload", tag, str(path), "--repo", REPO)
    uploaded = existing_release(tag)
    allowed_assets = {path.name for path in destination.iterdir() if path.is_file()}
    with tempfile.TemporaryDirectory(prefix="yams-draft-download-") as temporary:
        downloaded = Path(temporary)
        for asset in uploaded["assets"]:
            name = logical_name(asset["name"])
            if name not in allowed_assets:
                raise SystemExit("Unexpected draft asset")
            local = destination / name
            content = subprocess.check_output(
                [
                    "gh",
                    "api",
                    "-H",
                    "Accept: application/octet-stream",
                    f"repos/{REPO}/releases/assets/{asset['id']}",
                ]
            )
            if content != local.read_bytes():
                raise SystemExit("Uploaded draft asset checksum mismatch")
            (downloaded / name).write_bytes(content)
        if len(uploaded["assets"]) != len(allowed_assets):
            raise SystemExit("Missing release asset")
        # Exercise the complete installer command against fresh draft downloads,
        # including both platform evidence files added after native smoke tests.
        subprocess.run(["sha256sum", "--check", "SHA256SUMS"], cwd=downloaded, check=True)
    notes = release_summary(version)[1]
    if ".env.example" in allowed_assets:
        notes += (
            "\n\n**0.0.1 installation prerequisite:** GitHub names the configuration asset "
            "`default.env.example`. After downloading all assets, run "
            "`cp default.env.example .env.example` **before** the checksum command in INSTALL.md. "
            "This restores the original verified filename without changing its bytes."
        )
    command(
        "gh",
        "release",
        "edit",
        tag,
        "--repo",
        REPO,
        "--draft=false",
        "--prerelease",
        "--notes",
        notes,
    )


if __name__ == "__main__":
    {
        "preflight": preflight,
        "recovery-preflight": recovery_preflight,
        "indexes": indexes,
        "package": package,
        "publish": publish,
    }[sys.argv[1]]()
