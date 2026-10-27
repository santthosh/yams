"""Closed payloads and persisted ADR-005 limits; never import code from payloads."""

import os
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from backend.domain.types import Contract


class JobLimits(Contract):
    version: Literal[1] = 1
    max_attempts: Annotated[int, Field(strict=True, ge=1, le=3)] = 3
    wall_seconds: Annotated[int, Field(strict=True, ge=1, le=300)] = 300
    heartbeat_seconds: Annotated[int, Field(strict=True, ge=1, le=5)] = 5
    lease_seconds: Annotated[int, Field(strict=True, ge=2, le=30)] = 30
    cancel_grace_seconds: Annotated[int, Field(strict=True, ge=1, le=5)] = 5
    poll_milliseconds: Annotated[int, Field(strict=True, ge=1, le=100)] = 100
    memory_mib: Annotated[int, Field(strict=True, ge=64, le=2048)] = 2048
    cpu_count: Annotated[int, Field(strict=True, ge=1, le=2)] = 2
    pids: Annotated[int, Field(strict=True, ge=2, le=64)] = 64
    numerical_threads: Literal[1] = 1
    catchup_batch: Annotated[int, Field(strict=True, ge=1, le=100)] = 100
    scheduler_tick_seconds: Annotated[int, Field(strict=True, ge=1, le=5)] = 5

    @field_validator("version", "numerical_threads", mode="before")
    @classmethod
    def strict_one(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version and numerical threads must be integers")
        return value

    @classmethod
    def from_environment(cls) -> "JobLimits":
        raw = os.environ.get("YAMS_JOB_LIMITS", "{}")
        try:
            if len(raw) > 8192:
                raise ValueError("Oversized limits")
            return cls.model_validate_json(raw)
        except ValueError:
            # Configuration is operator input; never echo arbitrary values into logs.
            raise ValueError("Invalid YAMS_JOB_LIMITS configuration") from None

    @model_validator(mode="after")
    def coherent_timing(self) -> Self:
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("Heartbeat must be shorter than lease")
        return self


class DiagnosticPayload(Contract):
    schema_version: Literal[1]
    # A deterministic integer exercise, not fabricated financial work.
    work_units: Annotated[int, Field(strict=True, ge=0, le=1000000)]


def validate_payload(kind: str, payload: object) -> DiagnosticPayload:
    if kind != "diagnostic":
        raise ValueError("Unregistered job kind")
    return DiagnosticPayload.model_validate(payload)


def validate_workload(
    *, assets: int = 0, sessions: int = 0, paths: int = 0, steps: int = 0, union_assets: int = 0
) -> None:
    """Shared hard admission ceilings for future typed handlers, not registration."""
    values = (assets, sessions, paths, steps, union_assets)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Invalid workload dimensions")
    if (
        assets > 1000
        or sessions > 2520
        or assets * sessions > 2520000
        or paths > 5000
        or steps > 90
        or union_assets > 16
        or paths * steps * union_assets > 7200000
    ):
        raise ValueError("WORKLOAD_LIMIT")


class AttemptMetrics(Contract):
    elapsed_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    max_heartbeat_gap_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    cpu_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    peak_rss_kib: Annotated[int, Field(strict=True, ge=0)] | None
