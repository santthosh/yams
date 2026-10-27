"""Raw JSON parsing that preserves exact score numbers and rejects duplicate keys."""

import json
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from backend.domain.types import load_json


class ContractRequest(Request):
    async def json(self) -> Any:
        try:
            return load_json(await self.body())
        except ValueError as error:
            # FastAPI treats JSONDecodeError as a normal request validation failure.
            raise json.JSONDecodeError("Invalid JSON payload", "", 0) from error


class ContractRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            return await original(ContractRequest(request.scope, request.receive))

        return handler
