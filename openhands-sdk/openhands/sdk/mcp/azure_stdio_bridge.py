"""Local stdio proxy for Azure workload-identity MCP servers."""

import argparse
from collections.abc import Sequence

from fastmcp.mcp_config import RemoteMCPServer
from fastmcp.server import create_proxy

from openhands.sdk.mcp.azure import AzureWorkloadIdentityAuth
from openhands.sdk.mcp.config import AZURE_AI_SCOPE, coerce_mcp_config
from openhands.sdk.mcp.utils import _prepare_mcp_config


def _create_stdio_proxy(target):
    return create_proxy(target, name="OpenHands Azure MCP Bridge")


def create_azure_workload_identity_bridge(
    url: str,
    scope: str = AZURE_AI_SCOPE,
):
    config = coerce_mcp_config(
        {
            "upstream": {
                "url": url,
                "transport": "streamable-http",
                "auth": {
                    "strategy": "azure_workload_identity",
                    "scope": scope,
                },
            }
        }
    )
    prepared = _prepare_mcp_config(config)
    server = prepared.mcpServers["upstream"]
    if not isinstance(server, RemoteMCPServer):
        raise TypeError("Azure workload identity bridge requires a remote MCP server")
    auth = server.auth
    if not isinstance(auth, AzureWorkloadIdentityAuth):
        raise TypeError("Azure workload identity bridge requires Azure transport auth")
    return _create_stdio_proxy(server.to_transport()), auth


def run_azure_workload_identity_bridge(
    url: str,
    scope: str = AZURE_AI_SCOPE,
) -> None:
    bridge, auth = create_azure_workload_identity_bridge(url, scope)
    try:
        bridge.run(transport="stdio", show_banner=False)
    finally:
        auth.close()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--scope", default=AZURE_AI_SCOPE)
    args = parser.parse_args(argv)
    run_azure_workload_identity_bridge(args.url, args.scope)


if __name__ == "__main__":
    main()
