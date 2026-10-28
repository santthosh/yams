"""Snapshot diagnostics: immutable requests, complete results and async lifecycle."""

import hashlib
from fractions import Fraction
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from backend.domain.common import ErrorDetail, JobStatus
from backend.domain.strategy import StrategyConfigV1
from backend.domain.types import (
    AssetId,
    Contract,
    FractionString,
    Hash256,
    Reason,
    SessionDate,
    SourceMode,
    UTCTimestamp,
    canonical_json,
    load_json,
)
from backend.portfolio.allocation import AllocationExclusion
from backend.portfolio.risk import AllocationTarget, RiskReport, assess_targets
from backend.strategies.momentum import CandidateEvidence, DataDiagnosticEvidence


class StrategyEvaluationRequest(Contract):
    strategy_version_id: UUID
    snapshot_id: UUID
    as_of_session: SessionDate


class StrategyEvaluationAccepted(Contract):
    job_id: UUID
    evaluation_id: UUID


class EvaluationCandidateV1(CandidateEvidence):
    """Shared engine fields, uniquely named in the generated public schema."""


class EvaluationReproducibilityV1(Contract):
    strategy_version_id: UUID
    snapshot_id: UUID
    config_sha256: Hash256
    snapshot_sha256: Hash256
    calendar_sha256: Hash256
    engine_version: Hash256


class StrategyEvaluationResultV1(Contract):
    schema_version: Literal[1] = 1
    as_of_session: SessionDate
    decision_cutoff_utc: UTCTimestamp
    mode: SourceMode
    warnings: tuple[Reason, ...]
    candidates: tuple[EvaluationCandidateV1, ...]
    selected_ids: tuple[AssetId, ...]
    target_weights: tuple[AllocationTarget, ...]
    cash_target_weight: FractionString
    constraint_evidence: RiskReport
    allocation_reasons: tuple[Reason, ...]
    allocation_exclusions: tuple[AllocationExclusion, ...]
    data_diagnostics: tuple[DataDiagnosticEvidence, ...]
    reproducibility: EvaluationReproducibilityV1

    @model_validator(mode="after")
    def complete_evidence(self) -> Self:
        ids = [row.asset_id for row in self.candidates]
        target_ids = [row.asset_id for row in self.target_weights]
        if len(ids) != len(set(ids)) or len(target_ids) != len(set(target_ids)):
            raise ValueError("Duplicate diagnostic candidate/target identity")
        if len(self.selected_ids) != len(set(self.selected_ids)):
            raise ValueError("Duplicate selected identity")
        if not set(target_ids) <= set(self.selected_ids) <= set(ids):
            raise ValueError("Diagnostic targets require selected candidate evidence")
        total = sum((Fraction(row.weight) for row in self.target_weights), Fraction(0))
        if total + Fraction(self.cash_target_weight) != 1:
            raise ValueError("Diagnostic allocation must conserve complete capital")
        if (
            not self.constraint_evidence.compliant
            or Fraction(self.constraint_evidence.cash_weight) != Fraction(self.cash_target_weight)
            or Fraction(self.constraint_evidence.invested_weight) != total
        ):
            raise ValueError("Constraint evidence disagrees with targets")
        return self

    def canonical_bytes(self) -> bytes:
        # Convert the engine's finite JSON statistics back to exact decimal tokens
        # for canonical serialization, without asking canonical_json to accept floats.
        return canonical_json(load_json(self.model_dump_json()))

    def result_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class StrategyEvaluationV1(Contract):
    id: UUID
    job_id: UUID
    status: JobStatus
    inputs: StrategyEvaluationRequest
    mode: SourceMode
    provider: Annotated[str, Field(strict=True, min_length=1)]
    config_sha256: Hash256
    snapshot_sha256: Hash256
    engine_version: Hash256
    created_at: UTCTimestamp
    strategy_config: StrategyConfigV1
    result: StrategyEvaluationResultV1 | None
    result_sha256: Hash256 | None
    error: ErrorDetail | None

    @model_validator(mode="after")
    def lifecycle(self) -> Self:
        if self.strategy_config.config_hash() != self.config_sha256:
            raise ValueError("Diagnostic strategy rules differ from pinned config hash")
        if self.result is not None:
            for candidate in self.result.candidates:
                if (
                    candidate.features is not None
                    and getattr(candidate.features, "kind", "risk_adjusted_momentum")
                    != self.strategy_config.signals.kind
                ):
                    raise ValueError("Diagnostic evidence family differs from pinned config")
        if self.status == "completed":
            if self.result is None or self.result_sha256 != self.result.result_hash():
                raise ValueError("Completed diagnostics require sealed, hash-verified evidence")
            repro = self.result.reproducibility
            verified_risk = assess_targets(
                self.result.target_weights,
                self.result.cash_target_weight,
                self.strategy_config.portfolio,
            )
            if verified_risk != self.result.constraint_evidence or not verified_risk.compliant:
                raise ValueError("Diagnostic constraints fail the pinned strategy policy")
            selected = {
                row.asset_id: row
                for row in self.result.candidates
                if row.eligible
                and row.allocation_eligible
                and row.features is not None
                and row.features.volatility > 0
            }
            if len(
                self.result.selected_ids
            ) > self.strategy_config.portfolio.max_positions or not set(
                self.result.selected_ids
            ) <= set(selected):
                raise ValueError("Selected diagnostics are not allocation eligible")
            if (
                self.result.as_of_session != self.inputs.as_of_session
                or self.result.mode != self.mode
                or repro.strategy_version_id != self.inputs.strategy_version_id
                or repro.snapshot_id != self.inputs.snapshot_id
                or repro.config_sha256 != self.config_sha256
                or repro.snapshot_sha256 != self.snapshot_sha256
                or repro.engine_version != self.engine_version
            ):
                raise ValueError("Diagnostic result lineage differs from immutable inputs")
        elif self.result is not None or self.result_sha256 is not None:
            raise ValueError("Incomplete diagnostics cannot expose completed evidence")
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Only failed diagnostics have a terminal error")
        return self


class StrategyEvaluationPayload(Contract):
    schema_version: Literal[1] = 1
    evaluation_id: UUID
    inputs: StrategyEvaluationRequest
    source_mode: SourceMode
    snapshot_sha256: Hash256
    config_sha256: Hash256
    calendar_sha256: Hash256
    engine_version: Hash256
    decision_cutoff_utc: UTCTimestamp
    config_canonical_json: Annotated[str, Field(strict=True, min_length=1, max_length=16384)]
