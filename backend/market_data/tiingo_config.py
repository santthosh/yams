"""Closed operator configuration; credentials never enter a job payload."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool

from backend.domain.types import Contract, SessionDate


class TiingoResearchConfigV1(Contract):
    schema_version: Literal[1]
    provider: Literal["tiingo_eod"]
    rights_verified_local_use: StrictBool
    rights_reference: Literal["https://www.tiingo.com/documentation/"] = (
        "https://www.tiingo.com/documentation/"
    )
    history_sessions: Annotated[int, Field(strict=True, ge=252, le=2000)] = 400
    max_assets: Annotated[int, Field(strict=True, ge=1, le=20)] = 20
    as_of_session: SessionDate | None = None
