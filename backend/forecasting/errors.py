"""Closed reasons safe for job diagnostics; never persist arbitrary exception text."""

SAFE_FORECAST_REASONS = frozenset(
    {"INPUT_FINGERPRINT_MISMATCH", "DECISION_CUTOFF_MISMATCH", "UNSUPPORTED_NUMERICAL_VERSION"}
)


class ForecastFailure(ValueError):
    def __init__(self, reason: str):
        if reason not in SAFE_FORECAST_REASONS:
            raise ValueError("Unsupported forecast failure reason")
        self.reason = reason
        super().__init__(reason)
