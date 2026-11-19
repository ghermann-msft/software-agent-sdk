"""Local stdio proxy for settings-backed OAuth MCP servers."""

from __future__ import annotations

from fastmcp.mcp_config import RemoteMCPServer
from fastmcp.server import create_proxy

from openhands.agent_server.config import Config
from openhands.agent_server.mcp_oauth_store import MCPSettingsOAuthTokenStore
from openhands.agent_server.persistence import ServerStores
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.mcp.exceptions import MCPError
from openhands.sdk.mcp.oauth import NonInteractiveMCPOAuth
from openhands.sdk.mcp.utils import _prepare_mcp_config


def _find_oauth_server(
    mcp_config: dict[str, MCPServer],
    name: str,
    url: str,
) -> tuple[str, MCPServer]:
    named = mcp_config.get(name)
    if named is not None and named.url == url and named.oauth_auth is not None:
        return name, named

    matches = [
        (server_name, server)
        for server_name, server in mcp_config.items()
        if server.url == url and server.oauth_auth is not None
    ]
    if len(matches) == 1:
        return matches[0]
    raise MCPError(
        f"OAuth MCP server {name!r} at {url!r} is not available in Agent Server "
        "settings. Authorize the connection again before starting the conversation."
    )


def create_oauth_stdio_bridge(
    config: Config,
    name: str,
    url: str,
):
    settings_store = ServerStores.from_config(config).settings
    settings = settings_store.load()
    mcp_config = settings.agent_settings.mcp_config if settings else {}
    stored_name, server = _find_oauth_server(mcp_config, name, url)
    token_store = MCPSettingsOAuthTokenStore(
        settings_store,
        seed_mcp_config={stored_name: server},
        cipher=config.cipher,
        write_back_webhooks=config.webhooks,
        session_api_key=(
            config.session_api_keys[0] if config.session_api_keys else None
        ),
    )
    prepared = _prepare_mcp_config(
        {stored_name: server},
        mcp_oauth_token_storage=token_store,
        mcp_oauth_class=NonInteractiveMCPOAuth,
    )
    remote = prepared.mcpServers[stored_name]
    if not isinstance(remote, RemoteMCPServer):
        raise TypeError("OAuth MCP bridge requires a remote MCP server")
    if not isinstance(remote.auth, NonInteractiveMCPOAuth):
        raise TypeError("OAuth MCP bridge requires noninteractive OAuth")
    return create_proxy(remote.to_transport(), name="OpenHands OAuth MCP Bridge")


def run_oauth_stdio_bridge(config: Config, name: str, url: str) -> None:
    bridge = create_oauth_stdio_bridge(config, name, url)
    bridge.run(transport="stdio", show_banner=False)
