from __future__ import annotations

import os
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhands.sdk.context.memory_provider import (
    MemoryProvider,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemoryReflectRequest,
    MemoryReflectResult,
    MemoryRetainRequest,
    MemoryRetainResult,
    MemoryScope,
)
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)
_SESSION_API_KEY_ENV_NAMES = ("OH_SESSION_API_KEYS_0", "SESSION_API_KEY")


class HindsightMemorySpec(BaseModel):
    """Deployment-owned connection details for the trusted memory broker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_url: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    scope: list[MemoryScope] = Field(
        default_factory=list,
        description=(
            "Ordered authorized hierarchy supplied by the trusted control plane. "
            "It contains the active organization scope and is never extended from "
            "conversation or agent input."
        ),
    )
    timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @field_validator("broker_url")
    @classmethod
    def validate_broker_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("broker_url must be an absolute HTTP(S) URL")
        return value

    @model_validator(mode="after")
    def validate_active_organization(self) -> HindsightMemorySpec:
        organization_scopes = [
            scope for scope in self.scope if scope.type == "organization"
        ]
        if len(organization_scopes) > 1:
            raise ValueError("scope may contain only one active organization")
        return self

    @property
    def organization_id(self) -> str | None:
        return next(
            (scope.id for scope in self.scope if scope.type == "organization"),
            None,
        )


class HindsightBrokerMemoryProvider(MemoryProvider):
    def __init__(
        self,
        spec: HindsightMemorySpec,
        *,
        session_api_key: str | None = None,
    ) -> None:
        self._spec = spec
        self._session_api_key = session_api_key

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        try:
            response = self._post_read("recall", request.model_dump(mode="json"))
            return MemoryRecallResult.model_validate(response)
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "Hindsight recall unavailable; continuing without memory",
                exc_info=True,
            )
            return MemoryRecallResult.unavailable()

    def reflect(self, request: MemoryReflectRequest) -> MemoryReflectResult:
        try:
            response = self._post_read("reflect", request.model_dump(mode="json"))
            return MemoryReflectResult.model_validate(response)
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "Hindsight reflect unavailable; continuing without memory",
                exc_info=True,
            )
            return MemoryReflectResult.unavailable()

    def retain(self, request: MemoryRetainRequest) -> MemoryRetainResult:
        private_scope = next(
            (scope for scope in self._spec.scope if scope.type == "private_user"),
            None,
        )
        if private_scope is None:
            return MemoryRetainResult(
                status="denied",
                message="No trusted private-user retention scope is configured.",
            )
        session_api_key = self._session_api_key or next(
            (
                value
                for name in _SESSION_API_KEY_ENV_NAMES
                if (value := os.getenv(name))
            ),
            None,
        )
        if not session_api_key:
            logger.warning(
                "Hindsight retain unavailable: no session API key is configured"
            )
            return MemoryRetainResult.unavailable()

        try:
            payload = {
                **request.model_dump(mode="json"),
                "scope": private_scope.model_dump(mode="json"),
            }
            response = self._post_payload(
                "retain",
                payload,
                headers={"X-Session-API-Key": session_api_key},
            )
            broker_result = _BrokerRetainResult.model_validate(response)
            return MemoryRetainResult(
                event_id=broker_result.event_id,
                status=broker_result.status,
                duplicate=broker_result.duplicate,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                return MemoryRetainResult(
                    status="denied",
                    message="Retention was denied by trusted broker policy.",
                )
            logger.warning(
                "Hindsight retain unavailable; continuing without memory retention",
                exc_info=True,
            )
            return MemoryRetainResult.unavailable()
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "Hindsight retain unavailable; continuing without memory retention",
                exc_info=True,
            )
            return MemoryRetainResult.unavailable()

    def _post_read(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "identity": self._spec.identity,
            "scope": [item.model_dump(mode="json") for item in self._spec.scope],
            **payload,
        }
        return self._post_payload(operation, payload)

    def _post_payload(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{str(self._spec.broker_url).rstrip('/')}/api/v1/hindsight/{operation}"
        request_kwargs: dict[str, Any] = {
            "json": payload,
            "timeout": self._spec.timeout_seconds,
        }
        if headers is not None:
            request_kwargs["headers"] = headers
        response = httpx.post(url, **request_kwargs)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Hindsight broker response must be a JSON object")
        return body


class _BrokerRetainResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    status: Literal["queued", "delivered", "dead_letter"]
    duplicate: bool
