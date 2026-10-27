"""Database-independent API bootstrap; readiness belongs to the persistence layer."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from backend.api.errors import register_error_handlers
from backend.api.openapi import ContractAPI
from backend.api.routing import ContractRoute


class Liveness(BaseModel):
    status: Literal["alive"] = "alive"
    paper_only: Literal[True] = True


def create_app() -> FastAPI:
    app = ContractAPI(title="YAMS", version="0.0.1")
    app.router.route_class = ContractRoute
    register_error_handlers(app)

    @app.get("/livez", response_model=Liveness, tags=["operations"])
    def liveness() -> Liveness:
        """Process liveness only: not database, fixture or worker readiness."""
        return Liveness()

    return app


app = create_app()
