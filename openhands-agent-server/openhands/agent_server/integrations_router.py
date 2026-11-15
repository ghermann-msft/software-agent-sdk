from __future__ import annotations

from typing import cast

import httpx
from fastapi import APIRouter, HTTPException, Request, status

from openhands.agent_server._secrets_exposure import get_config
from openhands.agent_server.persistence import PersistedSettings, get_settings_store
from openhands.agent_server.persistence.models import SettingsUpdatePayload
from openhands.agent_server.settings_router import _apply_settings_update
from openhands.sdk.settings import (
    AtlassianIntegrationRequest,
    AtlassianIntegrationResponse,
    AtlassianProductConnection,
)
from openhands.sdk.settings.api_models import (
    ATLASSIAN_MCP_SERVER_KEYS,
    AtlassianProduct,
)


atlassian_router = APIRouter(prefix="/v1/integrations", tags=["Integrations"])


def _site_url(integration: AtlassianIntegrationRequest) -> str:
    return str(integration.site_url).rstrip("/").removesuffix("/wiki")


def _product_response(
    settings: PersistedSettings,
    product: AtlassianProduct,
) -> AtlassianProductConnection:
    server = settings.agent_settings.mcp_config.get(ATLASSIAN_MCP_SERVER_KEYS[product])
    if server is None or server.env is None:
        return AtlassianProductConnection(connected=False)
    prefix = product.upper()
    url = server.env.get(f"{prefix}_URL")
    email = server.env.get(f"{prefix}_USERNAME")
    token = server.env.get(f"{prefix}_API_TOKEN")
    if url is None or email is None or token is None:
        return AtlassianProductConnection(connected=False)
    site_url = url.get_secret_value().rstrip("/").removesuffix("/wiki")
    return AtlassianProductConnection(
        connected=bool(token.get_secret_value()),
        site_url=site_url,
        email=email.get_secret_value(),
    )


def _atlassian_response(settings: PersistedSettings) -> AtlassianIntegrationResponse:
    return AtlassianIntegrationResponse(
        jira=_product_response(settings, "jira"),
        confluence=_product_response(settings, "confluence"),
    )


async def _validate_atlassian_cloud(
    integration: AtlassianIntegrationRequest,
    product: AtlassianProduct,
) -> None:
    site_url = _site_url(integration)
    auth = httpx.BasicAuth(
        integration.email,
        integration.api_token.get_secret_value(),
    )
    url = (
        f"{site_url}/rest/api/3/myself"
        if product == "jira"
        else f"{site_url}/wiki/rest/api/user/current"
    )
    try:
        async with httpx.AsyncClient(
            auth=auth,
            follow_redirects=False,
            timeout=10.0,
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Atlassian Cloud validation failed",
        ) from None
    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Atlassian credentials were rejected",
        )
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Atlassian Cloud validation failed",
        )


@atlassian_router.get(
    "/atlassian",
    response_model=AtlassianIntegrationResponse,
)
async def get_atlassian_integration(request: Request) -> AtlassianIntegrationResponse:
    """Return the authenticated user's Atlassian connection status."""
    config = get_config(request)
    settings = get_settings_store(config).load() or PersistedSettings()
    return _atlassian_response(settings)


@atlassian_router.put(
    "/atlassian/{product}",
    response_model=AtlassianIntegrationResponse,
)
async def put_atlassian_integration(
    request: Request,
    product: AtlassianProduct,
    integration: AtlassianIntegrationRequest,
) -> AtlassianIntegrationResponse:
    """Validate and configure one per-user Atlassian product."""
    await _validate_atlassian_cloud(integration, product)
    server_data = integration.to_mcp_server(product).model_dump(
        mode="python",
        context={"expose_secrets": "plaintext"},
        exclude_none=True,
        exclude_defaults=True,
    )
    update_data = cast(
        SettingsUpdatePayload,
        {
            "agent_settings_diff": {
                "mcp_config": {ATLASSIAN_MCP_SERVER_KEYS[product]: server_data}
            }
        },
    )
    _apply_settings_update(request, update_data)
    config = get_config(request)
    settings = get_settings_store(config).load() or PersistedSettings()
    return _atlassian_response(settings)


@atlassian_router.delete(
    "/atlassian/{product}",
    response_model=AtlassianIntegrationResponse,
)
async def delete_atlassian_integration(
    request: Request,
    product: AtlassianProduct,
) -> AtlassianIntegrationResponse:
    """Disconnect one Atlassian product without affecting the other."""
    update_data = cast(
        SettingsUpdatePayload,
        {
            "agent_settings_diff": {
                "mcp_config": {ATLASSIAN_MCP_SERVER_KEYS[product]: None}
            }
        },
    )
    _apply_settings_update(request, update_data)
    config = get_config(request)
    settings = get_settings_store(config).load() or PersistedSettings()
    return _atlassian_response(settings)
