import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.domain.strategy import SignalConfig, StrategyConfigV1
from backend.domain.types import canonical_json

EXAMPLE = Path(__file__).parent / "examples" / "strategy.json"


def example() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(EXAMPLE.read_text())
    return value


def test_roundtrip_is_closed_and_preserves_financial_strings() -> None:
    config = StrategyConfigV1.from_json(EXAMPLE.read_bytes())
    output = json.loads(config.model_dump_json())
    assert output == example()
    assert output["portfolio"]["max_position_weight"] == "0.20"
    assert isinstance(config.signals, SignalConfig)
    assert config.signals.z_score_weights.momentum_long == Decimal("0.60")
    with pytest.raises(ValidationError):
        config.display_name = "mutated"


def test_canonical_bytes_normalize_only_declared_fields() -> None:
    config = StrategyConfigV1.from_json(EXAMPLE.read_bytes())
    other = example()
    other["universe"]["min_price_usd"] = "5"
    other["portfolio"]["max_position_weight"] = "0.2"
    other["display_name"] = "\u00a0Risk-Adjusted Momentum\u3000"
    reordered = dict(reversed(list(other.items())))
    assert StrategyConfigV1.model_validate(reordered).canonical_bytes() == config.canonical_bytes()
    assert b'"min_price_usd":"5"' in config.canonical_bytes()
    assert b'"momentum_long":0.6' in config.canonical_bytes()
    changed = example()
    changed["portfolio"]["min_cash_weight"] = "0.10"
    assert StrategyConfigV1.model_validate(changed).config_hash() != config.config_hash()
    other["display_name"] = "005.00"
    assert b'"display_name":"005.00"' in StrategyConfigV1.model_validate(other).canonical_bytes()


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("portfolio", "max_position_weight", "0"),
        ("portfolio", "max_sector_weight", "1.000001"),
        ("portfolio", "max_position_weight", 0.2),
        ("portfolio", "max_position_weight", "0.1234567"),
        ("portfolio", "max_positions", True),
        ("portfolio", "max_positions", 101),
        ("portfolio", "weighting", "execute_python"),
        ("portfolio", "min_cash_weight", "-0.1"),
        ("portfolio", "min_trade_usd", "1000000000000"),
        ("universe", "min_price_usd", "05.00"),
        ("universe", "min_price_usd", "5e0"),
        ("universe", "min_price_usd", "5.000"),
        ("universe", "min_price_usd", "NaN"),
        ("universe", "kind", "options"),
        ("universe", "min_history_sessions", 251),
        ("signals", "require_positive_trend", "true"),
        ("signals", "momentum_short_sessions", 126),
        ("signals", "momentum_long_sessions", 252),
        ("signals", "extra_expression", "__import__('os')"),
    ],
)
def test_invalid_config_is_rejected(section: str, field: str, value: object) -> None:
    data = example()
    data[section][field] = value
    with pytest.raises(ValidationError):
        StrategyConfigV1.model_validate(data)


@pytest.mark.parametrize("value", ["0.60", float("nan"), float("inf"), True, 0.6000001, -0.60])
def test_score_weights_are_finite_exact_bounded_numbers(value: object) -> None:
    data = example()
    data["signals"]["z_score_weights"]["momentum_long"] = value
    with pytest.raises(ValidationError):
        StrategyConfigV1.model_validate(data)


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_version_is_strict_integer(version: object) -> None:
    data = example()
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        StrategyConfigV1.model_validate(data)


@pytest.mark.parametrize("name", ["", "x" * 121, "a\u0000b", "a\ud800b"])
def test_invalid_names(name: str) -> None:
    data = example()
    data["display_name"] = name
    with pytest.raises(ValidationError):
        StrategyConfigV1.model_validate(data)


def test_duplicate_json_and_nonfinite_tokens_fail_before_validation() -> None:
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        StrategyConfigV1.from_json('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="Nonfinite JSON token"):
        StrategyConfigV1.from_json('{"x":NaN}')


def test_canonical_serialization_has_independent_exact_byte_oracles() -> None:
    assert canonical_json({"b": Decimal("0.60"), "a": "\n\t"}) == b'{"a":"\\u000a\\u0009","b":0.6}'
    assert canonical_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    assert canonical_json([Decimal("-0.000"), Decimal("1E+2"), True, None]) == b"[0,100,true,null]"
    with pytest.raises(ValueError, match="binary float"):
        canonical_json(0.6)
    with pytest.raises(ValueError, match="Unicode"):
        canonical_json("\ud800")
