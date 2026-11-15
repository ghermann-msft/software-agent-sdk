"""Azure workload identity authentication for remote MCP transports."""

import asyncio
import threading
import time
from collections.abc import AsyncGenerator, Callable, Generator

import httpx2
from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential


TOKEN_REFRESH_BUFFER_SECONDS = 300


def _origin(url: httpx2.URL) -> tuple[str, str, int | None]:
    default_port = {"http": 80, "https": 443}.get(url.scheme)
    return url.scheme, url.host, url.port or default_port


class AzureWorkloadIdentityAuth(httpx2.Auth):
    """Inject cached Azure bearer tokens only on the configured MCP origin."""

    def __init__(
        self,
        url: str,
        scope: str,
        *,
        credential_factory: Callable[[], DefaultAzureCredential] | None = None,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self._origin = _origin(httpx2.URL(url))
        self._scope = scope
        self._credential_factory = credential_factory or DefaultAzureCredential
        self._time_fn = time_fn
        self._credential: DefaultAzureCredential | None = None
        self._token: AccessToken | None = None
        self._lock = threading.Lock()

    def _authorization_header(self) -> str:
        with self._lock:
            token = self._token
            if (
                token is None
                or token.expires_on <= self._time_fn() + TOKEN_REFRESH_BUFFER_SECONDS
            ):
                credential = self._credential
                if credential is None:
                    credential = self._credential_factory()
                    self._credential = credential
                token = credential.get_token(self._scope)
                self._token = token
            return f"Bearer {token.token}"

    def _applies_to(self, request: httpx2.Request) -> bool:
        return _origin(request.url) == self._origin

    def sync_auth_flow(
        self, request: httpx2.Request
    ) -> Generator[httpx2.Request, httpx2.Response]:
        if self._applies_to(request):
            request.headers["Authorization"] = self._authorization_header()
        yield request

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        if self._applies_to(request):
            request.headers["Authorization"] = await asyncio.to_thread(
                self._authorization_header
            )
        yield request

    def close(self) -> None:
        with self._lock:
            credential = self._credential
            self._credential = None
            self._token = None
        if credential is not None:
            credential.close()
