"""Require an actual current-head MergeWatch result, not its neutral pending signal."""

import json
import os
import time
import urllib.request
from typing import Any

MERGEWATCH_APP_ID = 3052814


def reviewed(checks: list[dict[str, Any]], head: str, docs_only: bool) -> bool:
    matching = [
        check
        for check in checks
        if check.get("name") == "MergeWatch Review"
        and check.get("app", {}).get("id") == MERGEWATCH_APP_ID
        and check.get("head_sha") == head
    ]
    if not matching:
        return False
    check = max(matching, key=lambda entry: entry["id"])
    if check.get("status") != "completed":
        return False
    if check.get("conclusion") == "success":
        return True
    return (
        docs_only
        and check.get("conclusion") == "neutral"
        and check.get("output", {}).get("summary") == "Only docs changed"
    )


def main() -> None:
    head = os.environ["REVIEW_HEAD_SHA"]
    repository = os.environ["GITHUB_REPOSITORY"]
    runtime = os.environ["CI_RUNTIME"]
    if runtime not in {"true", "false"}:
        raise SystemExit("Missing CI applicability; review cannot be verified")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/commits/{head}/check-runs?per_page=100",
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    deadline = time.monotonic() + 120
    while True:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
        if reviewed(payload["check_runs"], head, runtime == "false"):
            print(f"Verified MergeWatch app {MERGEWATCH_APP_ID} on current head {head}")
            return
        if time.monotonic() >= deadline:
            raise SystemExit(
                "Current-head MergeWatch review missing, pending, skipped or unsuccessful"
            )
        time.sleep(5)


if __name__ == "__main__":
    main()
