"""Export implemented routes plus contract-only components, never fake endpoints."""

import argparse
import json
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from backend.domain.common import ErrorEnvelope, JobV1, PageRequest
from backend.domain.data import AssetPageV1, DataHealthV1, SnapshotV1
from backend.domain.evaluation import (
    StrategyEvaluationAccepted,
    StrategyEvaluationRequest,
    StrategyEvaluationResultV1,
    StrategyEvaluationV1,
)
from backend.domain.experiment import ExperimentRequest, ExperimentRunV1
from backend.domain.experiment_api import (
    ExperimentAccepted,
    ExperimentDetailV1,
    ExperimentPageV1,
    ExperimentReproducibilityV1,
    ExperimentSeriesPageV1,
    ExperimentSummaryV1,
    ExperimentTradesPageV1,
    JobCancelRequest,
)
from backend.domain.forecast import ForecastV1
from backend.domain.market import AssetV1, MarketBarV1, SnapshotManifestV1
from backend.domain.orders import PaperOrderBatchV1
from backend.domain.recommendation import RecommendationV1
from backend.domain.registry import StrategyCreateRequest, StrategyV1, StrategyVersionV1
from backend.domain.strategy import StrategyConfigV1
from backend.domain.workspace import HealthV1, WorkspaceV1

MODELS: tuple[type[BaseModel], ...] = (
    StrategyConfigV1,
    StrategyCreateRequest,
    StrategyV1,
    StrategyVersionV1,
    StrategyEvaluationRequest,
    StrategyEvaluationAccepted,
    StrategyEvaluationResultV1,
    StrategyEvaluationV1,
    SnapshotV1,
    DataHealthV1,
    AssetPageV1,
    MarketBarV1,
    AssetV1,
    SnapshotManifestV1,
    RecommendationV1,
    ForecastV1,
    PaperOrderBatchV1,
    ExperimentRequest,
    ExperimentRunV1,
    ExperimentAccepted,
    ExperimentDetailV1,
    ExperimentSummaryV1,
    ExperimentPageV1,
    ExperimentSeriesPageV1,
    ExperimentTradesPageV1,
    ExperimentReproducibilityV1,
    JobCancelRequest,
    JobV1,
    ErrorEnvelope,
    PageRequest,
    HealthV1,
    WorkspaceV1,
)


def build_openapi(app: FastAPI) -> dict[str, Any]:
    document = get_openapi(title=app.title, version=app.version, routes=app.routes)
    _, bundle = models_json_schema(
        [(model, mode) for model in MODELS for mode in ("validation", "serialization")],
        ref_template="#/components/schemas/{model}",
    )
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    # FastAPI suffixes duplicated input/output definitions even when Pydantic's
    # combined bundle proves they share a schema. Normalize only known aliases;
    # compare definitions below rather than overwriting a genuine conflict.
    aliases = {
        "StrategyConfigV1-Input": "StrategyConfigV1",
        "StrategyConfigV1-Output": "StrategyConfigV1",
        "ExecutionPolicy-Input": "backend__domain__strategy__ExecutionPolicy",
    }

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str) and value.startswith("#/components/schemas/"):
            name = value.rsplit("/", 1)[-1]
            return "#/components/schemas/" + aliases.get(name, name)
        return value

    document = cast(dict[str, Any], normalize(document))
    schemas = document["components"]["schemas"]
    for alias, name in aliases.items():
        if alias in schemas:
            if schemas[alias] != bundle["$defs"][name]:
                raise ValueError(f"Conflicting OpenAPI alias: {alias}")
            schemas.pop(alias)
    # FastAPI's OpenAPI numeric-bound DTO coerces the uint64 ceiling to float.
    # Restore the exact integer constraint from the authoritative typed request.
    request_schema = schemas.get("ExperimentRequest")
    if request_schema is not None:
        seed = request_schema["properties"]["random_seed"]
        exact_seed = bundle["$defs"]["ExperimentRequest"]["properties"]["random_seed"]
        if seed != exact_seed:
            if seed != {**exact_seed, "maximum": float(exact_seed["maximum"])}:
                raise ValueError("Conflicting experiment random-seed schema")
            request_schema["properties"]["random_seed"] = exact_seed
    for name, definition in bundle["$defs"].items():
        if name in schemas and schemas[name] != definition:
            raise ValueError(f"Conflicting OpenAPI schema: {name}")
        schemas[name] = definition
    document["info"]["description"] = (
        "Only paths listed here are implemented. Components include versioned contracts "
        "for later feature owners; their presence does not activate endpoints."
    )
    return document


class ContractAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        if self.openapi_schema is None:
            self.openapi_schema = build_openapi(self)
        return self.openapi_schema


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode()


def export(root: Path, check: bool) -> None:
    from backend.api.main import create_app

    outputs = {root / "contracts/openapi.json": json_bytes(create_app().openapi())}
    goldens = {}
    for model in MODELS:
        for mode in ("validation", "serialization"):
            goldens[f"{model.__name__}.{mode}"] = model.model_json_schema(mode=mode)
    outputs[root / "contracts/schemas.json"] = json_bytes(goldens)
    drift = []
    for path, content in outputs.items():
        if check:
            if not path.exists() or path.read_bytes() != content:
                drift.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if drift:
        raise SystemExit("Contract drift: " + ", ".join(drift) + "; run make contracts")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    export(args.output_root, args.check)


if __name__ == "__main__":
    main()
