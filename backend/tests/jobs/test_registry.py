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
        validate_payload("backtest", {"schema_version": 1, "work_units": 1})
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
