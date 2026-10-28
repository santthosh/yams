"""Read-only registry metadata, separate from immutable strategy configuration."""

import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, StrictBool, StrictStr

from backend.domain.strategy import WHITE_SPACE, StrategyConfigV1
from backend.domain.types import Contract, Hash256, UTCTimestamp


def strategy_name(value: str) -> str:
    value = value.strip(WHITE_SPACE)
    if not 1 <= len(value) <= 120 or any(
        unicodedata.category(char) in {"Cc", "Cs"} for char in value
    ):
        raise ValueError("Strategy name must contain 1–120 characters without controls")
    return value


StrategyName = Annotated[StrictStr, AfterValidator(strategy_name)]


class StrategyVersionV1(Contract):
    id: UUID
    strategy_id: UUID
    version: Annotated[int, Field(strict=True, ge=1)]
    status: Literal["published"]
    config: StrategyConfigV1
    config_sha256: Hash256
    published_at: UTCTimestamp


class StrategyV1(Contract):
    id: UUID
    name: StrategyName
    is_template: StrictBool
    template_key: StrictStr | None
    created_at: UTCTimestamp
    published_version: StrategyVersionV1
