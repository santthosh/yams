"""Database-independent API bootstrap; readiness belongs to the persistence layer."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class Liveness(BaseModel):
    status: Literal["alive"] = "alive"
    paper_only: Literal[True] = True


def create_app() -> FastAPI:
    app = FastAPI(title="YAMS", version="0.0.1")

    @app.get("/livez", response_model=Liveness, tags=["operations"])
    def liveness() -> Liveness:
        """Process liveness only: not database, fixture or worker readiness."""
        return Liveness()

    return app


app = create_app()
