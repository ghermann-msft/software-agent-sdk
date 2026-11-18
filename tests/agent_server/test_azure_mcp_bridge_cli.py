import sys
from unittest.mock import patch

from openhands.agent_server.__main__ import main


def test_agent_server_runs_packaged_azure_mcp_bridge() -> None:
    argv = [
        "openhands-agent-server",
        "--mcp-azure-workload-identity-bridge",
        "--mcp-azure-bridge-url",
        "https://foundry.example.com/mcp",
        "--mcp-azure-bridge-scope",
        "api://foundry/.default",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
        patch(
            "openhands.sdk.mcp.azure_stdio_bridge.run_azure_workload_identity_bridge"
        ) as run_bridge,
    ):
        main()

    run_bridge.assert_called_once_with(
        url="https://foundry.example.com/mcp",
        scope="api://foundry/.default",
    )
