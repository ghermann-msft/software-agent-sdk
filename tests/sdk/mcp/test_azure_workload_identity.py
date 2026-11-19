from unittest.mock import Mock, call, patch

import httpx2
import mcp.types
import pytest
from azure.core.credentials import AccessToken
from fastmcp import Client, FastMCP
from fastmcp.mcp_config import RemoteMCPServer
from pydantic import ValidationError

from openhands.sdk.mcp.azure import AzureWorkloadIdentityAuth
from openhands.sdk.mcp.azure_stdio_bridge import (
    _create_stdio_proxy,
    create_azure_workload_identity_bridge,
    run_azure_workload_identity_bridge,
)
from openhands.sdk.mcp.config import (
    AZURE_AI_SCOPE,
    MCPAzureWorkloadIdentityAuthCredential,
    MCPServer,
    coerce_mcp_config,
    dump_mcp_config,
)
from openhands.sdk.mcp.utils import _prepare_mcp_config, create_mcp_tools


FOUNDRY_MCP_URL = (
    "https://account.services.ai.azure.com/api/projects/project/toolboxes/"
    "web-search/versions/1/mcp?api-version=v1"
)


def _authenticate(
    auth: AzureWorkloadIdentityAuth,
    url: str = FOUNDRY_MCP_URL,
) -> httpx2.Request:
    flow = auth.sync_auth_flow(httpx2.Request("POST", url))
    return next(flow)


def test_credential_is_publicly_importable_from_config() -> None:
    credential = MCPAzureWorkloadIdentityAuthCredential(
        strategy="azure_workload_identity"
    )

    assert credential.scope == AZURE_AI_SCOPE


def test_azure_workload_identity_auth_is_lazy_cached_and_refreshed() -> None:
    now = [0.0]
    credential = Mock()
    credential.get_token.side_effect = [
        AccessToken("first-token", 1000),
        AccessToken("refreshed-token", 2000),
    ]
    credential_factory = Mock(return_value=credential)
    auth = AzureWorkloadIdentityAuth(
        FOUNDRY_MCP_URL,
        AZURE_AI_SCOPE,
        credential_factory=credential_factory,
        time_fn=lambda: now[0],
    )

    assert credential_factory.call_count == 0
    assert _authenticate(auth).headers["Authorization"] == "Bearer first-token"

    now[0] = 600
    assert _authenticate(auth).headers["Authorization"] == "Bearer first-token"

    now[0] = 701
    assert _authenticate(auth).headers["Authorization"] == "Bearer refreshed-token"

    credential_factory.assert_called_once_with()
    assert credential.get_token.call_args_list == [
        call(AZURE_AI_SCOPE),
        call(AZURE_AI_SCOPE),
    ]


def test_azure_workload_identity_auth_propagates_token_failure() -> None:
    credential = Mock()
    credential.get_token.side_effect = RuntimeError("identity unavailable")
    auth = AzureWorkloadIdentityAuth(
        FOUNDRY_MCP_URL,
        AZURE_AI_SCOPE,
        credential_factory=Mock(return_value=credential),
    )
    request = httpx2.Request("POST", FOUNDRY_MCP_URL)

    with pytest.raises(RuntimeError, match="identity unavailable"):
        next(auth.sync_auth_flow(request))

    assert "Authorization" not in request.headers


def test_azure_workload_identity_auth_does_not_follow_another_origin() -> None:
    credential_factory = Mock()
    auth = AzureWorkloadIdentityAuth(
        FOUNDRY_MCP_URL,
        AZURE_AI_SCOPE,
        credential_factory=credential_factory,
    )

    request = _authenticate(auth, "https://redirected.example.com/mcp")

    assert "Authorization" not in request.headers
    credential_factory.assert_not_called()


def test_azure_workload_identity_auth_drops_token_on_cross_origin_redirect() -> None:
    credential = Mock()
    credential.get_token.return_value = AccessToken("redirect-token", 1000)
    auth = AzureWorkloadIdentityAuth(
        FOUNDRY_MCP_URL,
        AZURE_AI_SCOPE,
        credential_factory=Mock(return_value=credential),
        time_fn=lambda: 0,
    )
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx2.Response(
                302,
                headers={"Location": "https://redirected.example.com/mcp"},
            )
        return httpx2.Response(200)

    with httpx2.Client(
        auth=auth,
        transport=httpx2.MockTransport(handle),
        follow_redirects=True,
    ) as client:
        client.post(FOUNDRY_MCP_URL)

    assert requests[0].headers["Authorization"] == "Bearer redirect-token"
    assert "Authorization" not in requests[1].headers


@pytest.mark.asyncio
async def test_azure_workload_identity_auth_injects_async_transport_header() -> None:
    credential = Mock()
    credential.get_token.return_value = AccessToken("async-token", 1000)
    auth = AzureWorkloadIdentityAuth(
        FOUNDRY_MCP_URL,
        AZURE_AI_SCOPE,
        credential_factory=Mock(return_value=credential),
        time_fn=lambda: 0,
    )
    flow = auth.async_auth_flow(httpx2.Request("POST", FOUNDRY_MCP_URL))

    request = await anext(flow)

    assert request.headers["Authorization"] == "Bearer async-token"


def test_azure_workload_identity_auth_closes_and_clears_credentials() -> None:
    first = Mock()
    first.get_token.return_value = AccessToken("first-token", 1000)
    second = Mock()
    second.get_token.return_value = AccessToken("second-token", 1000)
    auth = AzureWorkloadIdentityAuth(
        FOUNDRY_MCP_URL,
        AZURE_AI_SCOPE,
        credential_factory=Mock(side_effect=[first, second]),
        time_fn=lambda: 0,
    )

    assert _authenticate(auth).headers["Authorization"] == "Bearer first-token"
    auth.close()
    assert _authenticate(auth).headers["Authorization"] == "Bearer second-token"

    first.close.assert_called_once_with()
    second.close.assert_not_called()


@pytest.mark.parametrize(
    "server",
    [
        {
            "url": "https://example.com/sse",
            "transport": "sse",
            "auth": {"strategy": "azure_workload_identity"},
        },
        {
            "url": "http://example.com/mcp",
            "transport": "streamable-http",
            "auth": {"strategy": "azure_workload_identity"},
        },
    ],
)
def test_azure_workload_identity_rejects_inapplicable_transport(server: dict) -> None:
    with pytest.raises(ValidationError):
        MCPServer.model_validate(server)


@patch("openhands.sdk.mcp.azure.DefaultAzureCredential")
def test_azure_workload_identity_is_runtime_only_transport_auth(
    credential_class: Mock,
) -> None:
    credential = Mock()
    credential.get_token.return_value = AccessToken("runtime-token", 2000)
    credential_class.return_value = credential
    config = coerce_mcp_config(
        {
            "foundry": {
                "url": FOUNDRY_MCP_URL,
                "transport": "streamable-http",
                "headers": {"X-Static": "static-value"},
                "auth": {"strategy": "azure_workload_identity"},
            }
        }
    )

    prepared = _prepare_mcp_config(config)
    server = prepared.mcpServers["foundry"]

    assert isinstance(server, RemoteMCPServer)
    assert server.headers == {"X-Static": "static-value"}
    assert isinstance(server.auth, AzureWorkloadIdentityAuth)
    request = _authenticate(server.auth)
    assert request.headers["Authorization"] == "Bearer runtime-token"
    assert dump_mcp_config(config) == {
        "foundry": {
            "url": FOUNDRY_MCP_URL,
            "transport": "streamable-http",
            "headers": {"X-Static": "static-value"},
            "auth": {"strategy": "azure_workload_identity"},
        }
    }
    assert "runtime-token" not in config["foundry"].model_dump_json()


@patch("openhands.sdk.mcp.utils.MCPClient")
def test_azure_workload_identity_credential_is_closed_with_client(
    client_class: Mock,
) -> None:
    config = coerce_mcp_config(
        {
            "foundry": {
                "url": FOUNDRY_MCP_URL,
                "transport": "streamable-http",
                "auth": {"strategy": "azure_workload_identity"},
            }
        }
    )

    create_mcp_tools(config)

    prepared = client_class.call_args.args[0]
    server = prepared.mcpServers["foundry"]
    assert isinstance(server, RemoteMCPServer)
    runtime_auth = server.auth
    assert isinstance(runtime_auth, AzureWorkloadIdentityAuth)
    cleanup = client_class.return_value._add_cleanup_callback.call_args.args[0]
    assert cleanup.__self__ is runtime_auth
    assert cleanup.__func__ is AzureWorkloadIdentityAuth.close


@pytest.mark.asyncio
async def test_stdio_proxy_discovers_and_invokes_upstream_tool() -> None:
    upstream = FastMCP("upstream")

    @upstream.tool
    def echo(value: str) -> str:
        return value

    bridge = _create_stdio_proxy(upstream)
    async with Client(bridge) as client:
        tools = await client.list_tools()
        result = await client.call_tool("echo", {"value": "through-bridge"})

    assert [tool.name for tool in tools] == ["echo"]
    content = result.content[0]
    assert isinstance(content, mcp.types.TextContent)
    assert content.text == "through-bridge"


def test_bridge_builder_contains_no_token_or_authorization() -> None:
    bridge, auth = create_azure_workload_identity_bridge(
        FOUNDRY_MCP_URL,
        AZURE_AI_SCOPE,
    )

    assert bridge is not None
    assert isinstance(auth, AzureWorkloadIdentityAuth)
    assert "Authorization" not in repr(bridge)
    assert "Bearer" not in repr(bridge)


def test_bridge_closes_auth_when_stdio_server_stops() -> None:
    bridge = Mock()
    auth = Mock()
    with patch(
        "openhands.sdk.mcp.azure_stdio_bridge.create_azure_workload_identity_bridge",
        return_value=(bridge, auth),
    ):
        run_azure_workload_identity_bridge(FOUNDRY_MCP_URL)

    bridge.run.assert_called_once_with(transport="stdio", show_banner=False)
    auth.close.assert_called_once_with()
