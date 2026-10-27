"""Fail-closed CI applicability, local documentation checks and aggregate gate."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def docs_only(paths: list[str]) -> bool:
    return bool(paths) and all(
        p in {"README.md", "AGENTS.md"} or (p.startswith("docs/") and p.endswith(".md"))
        for p in paths
    )


def required(results: dict[str, str], runtime: str) -> bool:
    expected = {"scope": "success", "docs": "success"}
    if runtime not in {"true", "false"}:
        return False
    expected.update(
        dict.fromkeys(("quality", "runtime"), "success" if runtime == "true" else "skipped")
    )
    return results == expected


def check_docs() -> None:
    errors = []
    files = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for path in files:
        content = path.read_text()
        if not content.strip() or "<<<<<<< " in content or "\x00" in content:
            errors.append(f"{path.relative_to(ROOT)}: empty or conflicted content")
        # Check Markdown inline local file links, not external URLs or illustrative code blocks.
        prose = re.sub(r"```.*?```", "", content, flags=re.S)
        for target in re.findall(r"\]\(([^\s)]+)\)", prose):
            link = urlsplit(target.strip("<>"))
            if link.scheme or link.netloc or not link.path:
                continue
            local = (path.parent / unquote(link.path)).resolve()
            if not local.is_relative_to(ROOT) or not local.exists():
                errors.append(f"{path.relative_to(ROOT)}: missing local link {target}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Content and local file links checked in {len(files)} Markdown documents")


def main() -> None:
    command = sys.argv[1]
    if command == "scope":
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        head = git("rev-parse", "HEAD")
        if "pull_request" in event:
            base = event["pull_request"]["base"]["sha"]
        else:
            base = event.get("before", "")
        if not re.fullmatch(r"[0-9a-f]{40}", base) or base == "0" * 40:
            paths = []  # Unknown base requires all runtime gates.
        else:
            paths = git("diff", "--name-only", "-z", base, head).rstrip("\0").split("\0")
        runtime = str(not docs_only(paths)).lower()
        evidence = ROOT / "test-results/ci"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "scope.json").write_text(
            json.dumps(
                {"tested_sha": head, "base_sha": base, "paths": paths, "runtime": runtime}, indent=2
            )
            + "\n"
        )
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write(f"runtime={runtime}\n")
        print(f"Tested SHA: {head}; runtime applicable: {runtime}")
    elif command == "docs":
        check_docs()
    elif command == "required":
        needs = json.loads(os.environ["CI_NEEDS"])
        results = {key: value["result"] for key, value in needs.items()}
        runtime = needs.get("scope", {}).get("outputs", {}).get("runtime", "")
        print(json.dumps({"results": results, "runtime_applicable": runtime}, indent=2))
        if not required(results, runtime):
            raise SystemExit("Required CI gates did not all pass")
    else:
        raise SystemExit(f"Unknown CI command: {command}")


if __name__ == "__main__":
    main()
