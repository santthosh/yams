"""Gate safety: failed, cancelled and unexpectedly skipped checks cannot go green."""

import pytest

from scripts.ci import docs_only, required


@pytest.mark.parametrize("runtime", ["true", "false"])
def test_required_rejects_incomplete_gates(runtime: str) -> None:
    results = {"scope": "success", "docs": "success", "quality": "success", "runtime": "success"}
    if runtime == "false":
        results.update(quality="skipped", runtime="skipped")
    assert required(results, runtime)
    for job in results:
        for failure in ("failure", "cancelled", "skipped", "unknown"):
            if failure != results[job]:
                assert not required({**results, job: failure}, runtime)
        assert not required({key: value for key, value in results.items() if key != job}, runtime)
    assert not required(results, "")
    assert not required({**results, "unexpected": "success"}, runtime)


def test_docs_applicability_is_explicit() -> None:
    assert docs_only(["README.md", "docs/development.md"])
    for paths in ([], ["docs/data.json"], [".github/workflows/ci.yml"], ["backend/api/main.py"]):
        assert not docs_only(paths)
