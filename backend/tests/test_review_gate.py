from typing import Any

from scripts.review_gate import MERGEWATCH_APP_ID, reviewed


def check(**overrides: Any) -> dict[str, Any]:
    return {
        "id": 1,
        "name": "MergeWatch Review",
        "app": {"id": MERGEWATCH_APP_ID},
        "head_sha": "current",
        "status": "completed",
        "conclusion": "success",
        "output": {"summary": "No issues detected"},
        **overrides,
    }


def test_only_current_actual_review_is_accepted() -> None:
    assert reviewed([check()], "current", False)
    assert not reviewed([], "current", False)
    for overrides in (
        {"app": {"id": 1}},
        {"head_sha": "stale"},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"conclusion": "skipped"},
        {"conclusion": "neutral", "output": {"summary": "MergeWatch is reviewing PR..."}},
    ):
        assert not reviewed([check(**overrides)], "current", False)
    assert not reviewed([check(), check(id=2, status="in_progress")], "current", False)


def test_only_explicit_docs_skip_is_accepted_for_docs() -> None:
    docs = check(conclusion="neutral", output={"summary": "Only docs changed"})
    assert reviewed([docs], "current", True)
    assert not reviewed([docs], "current", False)
    assert not reviewed([check(conclusion="neutral")], "current", True)
    assert not reviewed(
        [check(conclusion="neutral", output={"summary": "Draft PR"})], "current", True
    )
