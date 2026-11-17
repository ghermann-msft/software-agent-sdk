from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhands.sdk.context.memory_provider import (
    MemoryProvider,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemoryReflectRequest,
    MemoryReflectResult,
    MemoryScope,
)
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


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
    def __init__(self, spec: HindsightMemorySpec) -> None:
        self._spec = spec

    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
        try:
            response = self._post("recall", request.model_dump(mode="json"))
            return MemoryRecallResult.model_validate(response)
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "Hindsight recall unavailable; continuing without memory",
                exc_info=True,
            )
            return MemoryRecallResult.unavailable()

    def reflect(self, request: MemoryReflectRequest) -> MemoryReflectResult:
        try:
            response = self._post("reflect", request.model_dump(mode="json"))
            return MemoryReflectResult.model_validate(response)
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "Hindsight reflect unavailable; continuing without memory",
                exc_info=True,
            )
            return MemoryReflectResult.unavailable()

    def _post(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "identity": self._spec.identity,
            "scope": [item.model_dump(mode="json") for item in self._spec.scope],
            **payload,
        }
        url = f"{str(self._spec.broker_url).rstrip('/')}/api/v1/hindsight/{operation}"
        response = httpx.post(
            url,
            json=payload,
            timeout=self._spec.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Hindsight broker response must be a JSON object")
        return body
