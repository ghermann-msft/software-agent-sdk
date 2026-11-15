import httpx
import pytest
from fastapi import HTTPException

from openhands.agent_server import integrations_router
from openhands.sdk.settings import AtlassianIntegrationRequest


@pytest.mark.parametrize(
    ("product", "expected_path"),
    [
        ("jira", "/rest/api/3/myself"),
        ("confluence", "/wiki/rest/api/user/current"),
    ],
)
async def test_validate_atlassian_cloud_checks_only_requested_product(
    monkeypatch,
    product,
    expected_path,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    async_client = httpx.AsyncClient

    def mock_client(**kwargs):
        return async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(integrations_router.httpx, "AsyncClient", mock_client)
    integration = AtlassianIntegrationRequest.model_validate(
        {
            "site_url": "https://example.atlassian.net",
            "email": "user@example.com",
            "api_token": "product-secret",
        }
    )

    await integrations_router._validate_atlassian_cloud(integration, product)

    assert [request.url.path for request in requests] == [expected_path]
    assert requests[0].headers["authorization"].startswith("Basic ")


async def test_validate_atlassian_cloud_rejects_invalid_credentials(monkeypatch):
    async_client = httpx.AsyncClient

    def mock_client(**kwargs):
        return async_client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(401)),
            **kwargs,
        )

    monkeypatch.setattr(integrations_router.httpx, "AsyncClient", mock_client)
    integration = AtlassianIntegrationRequest.model_validate(
        {
            "site_url": "https://example.atlassian.net",
            "email": "user@example.com",
            "api_token": "invalid-secret",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await integrations_router._validate_atlassian_cloud(integration, "jira")

    assert exc_info.value.status_code == 401
    assert "invalid-secret" not in exc_info.value.detail
