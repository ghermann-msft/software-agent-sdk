import os
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


def test_agent_server_runs_packaged_oauth_mcp_bridge() -> None:
    argv = [
        "openhands-agent-server",
        "--mcp-oauth-bridge",
        "--mcp-oauth-bridge-name",
        "atlassian-rovo",
        "--mcp-oauth-bridge-url",
        "https://mcp.atlassian.com/v1/mcp",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
        patch("openhands.agent_server.config.load_config") as load_config,
        patch(
            "openhands.agent_server.mcp_oauth_stdio_bridge.run_oauth_stdio_bridge"
        ) as run_bridge,
    ):
        main()

    run_bridge.assert_called_once_with(
        load_config.return_value,
        "atlassian-rovo",
        "https://mcp.atlassian.com/v1/mcp",
    )


def test_agent_server_bridge_mode_suppresses_sdk_banner(capsys) -> None:
    argv = [
        "openhands-agent-server",
        "--mcp-azure-workload-identity-bridge",
        "--mcp-azure-bridge-url",
        "https://foundry.example.com/mcp",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch.dict(os.environ, {"OPENHANDS_SUPPRESS_BANNER": "1"}),
        patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
        patch(
            "openhands.sdk.mcp.azure_stdio_bridge.run_azure_workload_identity_bridge"
        ),
    ):
        main()

    assert capsys.readouterr().out == ""
