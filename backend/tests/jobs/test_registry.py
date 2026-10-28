import pytest
from pydantic import ValidationError

from backend.jobs.registry import JobLimits, validate_payload, validate_workload


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 1, "work_units": -1},
        {"schema_version": 1, "work_units": 1000001},
        {"schema_version": 1, "work_units": True},
        {"schema_version": 1, "work_units": 1, "function": "os.system"},
        {"schema_version": 2, "work_units": 1},
    ],
)
def test_closed_diagnostic_admission(payload: object) -> None:
    with pytest.raises(ValidationError):
        validate_payload("diagnostic", payload)


def test_unknown_kind_and_initial_limits() -> None:
    with pytest.raises(ValueError, match="Unregistered"):
        validate_payload("forecast", {"schema_version": 1, "work_units": 1})
    limits = JobLimits()
    assert (limits.wall_seconds, limits.heartbeat_seconds, limits.lease_seconds) == (300, 5, 30)
    assert (limits.max_attempts, limits.memory_mib, limits.cpu_count, limits.pids) == (
        3,
        2048,
        2,
        64,
    )
    with pytest.raises(ValidationError):
        JobLimits(memory_mib=2049)
    with pytest.raises(ValidationError):
        JobLimits(heartbeat_seconds=5, lease_seconds=5)
    with pytest.raises(ValidationError):
        JobLimits(max_attempts=4)


def test_workload_ceiling_is_enforced_without_registering_future_handlers() -> None:
    validate_workload(assets=1000, sessions=2520, paths=5000, steps=90, union_assets=16)
    for values in (
        {"assets": 1001},
        {"sessions": 2521},
        {"paths": 5001},
        {"steps": 91},
        {"union_assets": 17},
        {"assets": -1},
        {"steps": True},
    ):
        with pytest.raises(ValueError):
            validate_workload(**values)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "null",
        "[]",
        '{"memory_mib":-1}',
        '{"cpu_count":3}',
        '{"wall_seconds":"3"}',
        '{"unknown":1}',
        '{"version":true}',
        '{"numerical_threads":true}',
        '{"heartbeat_seconds":2,"lease_seconds":2}',
    ],
)
def test_invalid_environment_limits_fail_without_echoing_input(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv("YAMS_JOB_LIMITS", raw)
    with pytest.raises(ValueError, match="^Invalid YAMS_JOB_LIMITS configuration$"):
        JobLimits.from_environment()


def test_lowered_environment_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YAMS_JOB_LIMITS", '{"wall_seconds":30,"memory_mib":512}')
    limits = JobLimits.from_environment()
    assert limits.wall_seconds == 30 and limits.memory_mib == 512
    assert limits.max_attempts == 3
