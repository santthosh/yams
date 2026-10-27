"""Export implemented routes plus contract-only components, never fake endpoints."""

import argparse
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from backend.domain.common import ErrorEnvelope, JobV1, PageRequest
from backend.domain.experiment import ExperimentRequest, ExperimentRunV1
from backend.domain.forecast import ForecastV1
from backend.domain.market import AssetV1, MarketBarV1, SnapshotManifestV1
from backend.domain.orders import PaperOrderBatchV1
from backend.domain.recommendation import RecommendationV1
from backend.domain.strategy import StrategyConfigV1

MODELS: tuple[type[BaseModel], ...] = (
    StrategyConfigV1,
    MarketBarV1,
    AssetV1,
    SnapshotManifestV1,
    RecommendationV1,
    ForecastV1,
    PaperOrderBatchV1,
    ExperimentRequest,
    ExperimentRunV1,
    JobV1,
    ErrorEnvelope,
    PageRequest,
)


def build_openapi(app: FastAPI) -> dict[str, Any]:
    document = get_openapi(title=app.title, version=app.version, routes=app.routes)
    _, bundle = models_json_schema(
        [(model, mode) for model in MODELS for mode in ("validation", "serialization")],
        ref_template="#/components/schemas/{model}",
    )
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
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
    for model in MODELS:
        for mode in ("validation", "serialization"):
            outputs[root / f"contracts/schemas/{model.__name__}.{mode}.json"] = json_bytes(
                model.model_json_schema(mode=mode)
            )
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
