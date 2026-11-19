"""Local stdio proxy for settings-backed OAuth MCP servers."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from fastmcp.mcp_config import RemoteMCPServer
from fastmcp.server import create_proxy
from pydantic import ValidationError

from openhands.agent_server.config import Config
from openhands.agent_server.mcp_oauth_store import MCPSettingsOAuthTokenStore
from openhands.agent_server.persistence import ServerStores
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.mcp.oauth import NonInteractiveMCPOAuth
from openhands.sdk.mcp.utils import _prepare_mcp_config
from openhands.sdk.utils.pydantic_secrets import client_context


def _load_seed(seed_path: str | Path) -> tuple[str, MCPServer]:
    path = Path(seed_path)
    if not path.is_absolute():
        raise ValueError("OAuth MCP bridge seed path must be absolute")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("OAuth MCP bridge seed file must be owner-only")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        name = payload["name"]
        if not isinstance(name, str) or not name:
            raise ValueError
        server = MCPServer.model_validate(
            payload["server"],
            context=client_context("plaintext"),
        )
    except (OSError, KeyError, TypeError, ValueError, ValidationError):
        raise ValueError("OAuth MCP bridge seed file is invalid") from None
    if server.url is None or server.oauth_auth is None:
        raise ValueError("OAuth MCP bridge seed requires a remote OAuth server")
    return name, server


def create_oauth_stdio_bridge(
    config: Config,
    seed_path: str | Path,
):
    name, server = _load_seed(seed_path)
    settings_store = ServerStores.from_config(config).settings
    token_store = MCPSettingsOAuthTokenStore(
        settings_store,
        seed_mcp_config={name: server},
        cipher=config.cipher,
        write_back_webhooks=config.webhooks,
        session_api_key=(
            config.session_api_keys[0] if config.session_api_keys else None
        ),
        prefer_seed=True,
    )
    prepared = _prepare_mcp_config(
        {name: server},
        mcp_oauth_token_storage=token_store,
        mcp_oauth_class=NonInteractiveMCPOAuth,
    )
    remote = prepared.mcpServers[name]
    if not isinstance(remote, RemoteMCPServer):
        raise TypeError("OAuth MCP bridge requires a remote MCP server")
    if not isinstance(remote.auth, NonInteractiveMCPOAuth):
        raise TypeError("OAuth MCP bridge requires noninteractive OAuth")
    return create_proxy(remote.to_transport(), name="OpenHands OAuth MCP Bridge")


def run_oauth_stdio_bridge(config: Config, seed_path: str | Path) -> None:
    bridge = create_oauth_stdio_bridge(config, seed_path)
    bridge.run(transport="stdio", show_banner=False)
