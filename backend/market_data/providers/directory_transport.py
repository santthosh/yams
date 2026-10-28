"""Bounded acquisition from fixed public directory endpoints; disabled without rights."""

import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from backend.market_data.providers.directory import DirectorySnapshot, parse_directory
from backend.market_data.providers.yahoo import ProviderFailure, ResearchPermission

ENDPOINTS = {
    "nasdaqlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "otherlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}
MAX_BYTES = 8 * 1024 * 1024


class DirectoryDownloader(Protocol):
    def fetch(self, url: str, *, timeout: float, limit: int) -> bytes: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise ProviderFailure("DIRECTORY_REDIRECT_UNSUPPORTED")


class HTTPSDirectoryDownloader:
    def fetch(self, url: str, *, timeout: float, limit: int) -> bytes:
        if url not in ENDPOINTS.values():
            raise ProviderFailure("DIRECTORY_ENDPOINT_UNSUPPORTED")
        opener = urllib.request.build_opener(NoRedirect())
        request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
        try:
            with opener.open(request, timeout=timeout) as response:
                if (
                    response.status != 200
                    or response.headers.get("Content-Encoding", "identity") != "identity"
                ):
                    raise ProviderFailure("DIRECTORY_RESPONSE_UNSUPPORTED")
                content = response.read(limit + 1)
                if not isinstance(content, bytes):
                    raise ProviderFailure("DIRECTORY_RESPONSE_UNSUPPORTED")
        except urllib.error.HTTPError as error:
            reason = (
                "DIRECTORY_RATE_LIMITED"
                if error.code == 429
                else "DIRECTORY_UNAVAILABLE"
                if 500 <= error.code < 600
                else "DIRECTORY_REQUEST_FAILED"
            )
            raise ProviderFailure(reason) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderFailure("DIRECTORY_UNAVAILABLE") from None
        if len(content) > limit:
            raise ProviderFailure("DIRECTORY_SIZE_LIMIT")
        return content


@dataclass(frozen=True)
class AcquiredDirectory:
    content: bytes
    observed_at: datetime
    source_url: str
    snapshot: DirectorySnapshot


def acquire_directory(
    kind: Literal["nasdaqlisted", "otherlisted"],
    permission: ResearchPermission,
    downloader: DirectoryDownloader | None = None,
) -> AcquiredDirectory:
    permission.require_verified()
    if kind not in ENDPOINTS:
        raise ProviderFailure("DIRECTORY_ENDPOINT_UNSUPPORTED")
    source_url = ENDPOINTS[kind]
    content = (downloader or HTTPSDirectoryDownloader()).fetch(
        source_url, timeout=10.0, limit=MAX_BYTES
    )
    observed_at = datetime.now(UTC)
    return AcquiredDirectory(content, observed_at, source_url, parse_directory(content, kind))
