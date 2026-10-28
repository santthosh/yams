"""Closed backtest failure reasons safe for persisted diagnostics."""

SAFE_BACKTEST_REASONS = frozenset(
    {
        "INPUT_FINGERPRINT_MISMATCH",
        "UNSUPPORTED_ACCOUNTING_SOURCE",
        "SNAPSHOT_IDENTITY_MISMATCH",
        "UNCOVERED_EXPERIMENT_INTERVAL",
        "UNSUPPORTED_EXECUTION_POLICY",
        "AMBIGUOUS_ACTION_ORDER",
        "ORDER_ACTION_CONFLICT",
        "ACTION_NOT_DUE",
        "ACTION_NOT_AVAILABLE",
        "CHRONOLOGICAL_REPLAY_REQUIRED",
        "UNSUPPORTED_SPLIT_PRECISION",
        "MISSING_DIVIDEND_ENTITLEMENT",
        "PAYABLE_DATE_UNAVAILABLE",
        "UNRESOLVED_CORPORATE_ACTION",
        "MISSING_ELIGIBLE_OPEN",
        "MISSING_HELD_CLOSE",
        "MISSING_DECISION_CLOSE",
        "CANCELLED",
    }
)


class BacktestFailure(ValueError):
    def __init__(self, reason: str):
        if reason not in SAFE_BACKTEST_REASONS:
            raise ValueError("Unsupported backtest reason")
        self.reason = reason
        super().__init__(reason)
