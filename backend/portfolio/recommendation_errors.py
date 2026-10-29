"""Closed safe worker reason codes; payloads/prices/secrets are never log messages."""

SAFE_RECOMMENDATION_REASONS = frozenset(
    {
        "INPUT_FINGERPRINT_MISMATCH",
        "VALUATION_UNAVAILABLE",
        "WORKLOAD_LIMIT",
        "UNSUPPORTED_ACCOUNTING_SOURCE",
        "CALENDAR_UNAVAILABLE",
        "RECONCILIATION_REQUIRED",
    }
)


class RecommendationFailure(Exception):
    def __init__(self, reason: str):
        if reason not in SAFE_RECOMMENDATION_REASONS:
            raise ValueError("Unsupported recommendation failure")
        self.reason = reason
        super().__init__(reason)
