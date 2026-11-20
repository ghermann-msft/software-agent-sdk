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
            "openhands.agent_server.__main__.run_runtime_bootstrap"
        ) as run_runtime_bootstrap,
        patch(
            "openhands.sdk.mcp.azure_stdio_bridge.run_azure_workload_identity_bridge"
        ) as run_bridge,
    ):
        main()

    run_bridge.assert_called_once_with(
        url="https://foundry.example.com/mcp",
        scope="api://foundry/.default",
    )
    run_runtime_bootstrap.assert_not_called()


def test_agent_server_runs_packaged_oauth_mcp_bridge() -> None:
    seed_path = "C:\\workspace\\conversation\\acp\\oauth-seed.json"
    argv = [
        "openhands-agent-server",
        "--mcp-oauth-bridge",
        "--mcp-oauth-bridge-seed",
        seed_path,
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
        patch(
            "openhands.agent_server.__main__.run_runtime_bootstrap"
        ) as run_runtime_bootstrap,
        patch("openhands.agent_server.config.load_config") as load_config,
        patch(
            "openhands.agent_server.mcp_oauth_stdio_bridge.run_oauth_stdio_bridge"
        ) as run_bridge,
    ):
        main()

    run_bridge.assert_called_once_with(
        load_config.return_value,
        seed_path,
    )
    run_runtime_bootstrap.assert_not_called()


def test_agent_server_runs_hindsight_bridge_without_runtime_bootstrap() -> None:
    argv = [
        "openhands-agent-server",
        "--hindsight-mcp-bridge",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("openhands.agent_server.__main__._setup_crash_diagnostics"),
        patch(
            "openhands.agent_server.__main__.run_runtime_bootstrap"
        ) as run_runtime_bootstrap,
        patch(
            "openhands.agent_server.hindsight_mcp_bridge.run_hindsight_mcp_bridge"
        ) as run_bridge,
    ):
        main()

    run_bridge.assert_called_once_with()
    run_runtime_bootstrap.assert_not_called()


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
