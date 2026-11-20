import hashlib
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import openhands.agent_server.config as config_module
import openhands.agent_server.runtime_contract as runtime_contract
from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config, default_conversation_worktree_root
from openhands.sdk.settings.acp_install_catalog import (
    ACP_INSTALL_CATALOG,
    WINDOWS_PREINSTALLED_ACP_PROVIDERS,
)


def test_curated_resource_profiles_are_os_independent() -> None:
    profiles = {
        profile.id: profile.model_dump()
        for profile in runtime_contract.CURATED_RESOURCE_PROFILES
    }

    assert profiles == {
        "standard": {
            "id": "standard",
            "minimum": {"cpu": 2, "memory_gib": 4},
            "recommended": {"cpu": 4, "memory_gib": 8},
        },
        "high-memory": {
            "id": "high-memory",
            "minimum": {"cpu": 4, "memory_gib": 16},
            "recommended": {"cpu": 8, "memory_gib": 32},
        },
        "build": {
            "id": "build",
            "minimum": {"cpu": 4, "memory_gib": 8},
            "recommended": {"cpu": 8, "memory_gib": 16},
        },
    }


def test_windows_image_contract_is_reported_from_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(runtime_contract.platform, "machine", lambda: "AMD64")
    monkeypatch.setenv("OH_RUNTIME_SPEC_ID", "windows-server-2025-amd64")
    monkeypatch.setenv("OH_RUNTIME_CONTAINER_PLATFORM", "windows/amd64")
    monkeypatch.setenv("OH_RUNTIME_COMMAND_SHELL", "powershell.exe")
    monkeypatch.setenv("OH_RUNTIME_API_PORT", "8000")
    monkeypatch.setenv("OH_RUNTIME_WORKSPACE_MOUNT_PATH", r"C:\workspace")
    monkeypatch.setenv("OH_RUNTIME_DURABLE_STATE_PATH", r"C:\OpenHands")
    monkeypatch.setenv("OH_CONVERSATIONS_PATH", r"C:\OpenHands\conversations")
    monkeypatch.setenv("OH_BASH_EVENTS_DIR", r"C:\OpenHands\bash_events")
    monkeypatch.setenv("OH_PERSISTENCE_DIR", r"C:\OpenHands\persistence")

    app = create_app(
        Config(
            static_files_path=None,
            workspace_path=Path(r"C:\workspace\project"),
            conversation_worktree_root=Path(r"C:\workspace\worktrees"),
            conversations_path=tmp_path / "conversations",
        )
    )
    with TestClient(app) as client:
        payload = client.get("/server_info").json()

    assert "runtime_image_contract_v1" in payload["capabilities"]
    assert "native_windows_runtime_v1" in payload["capabilities"]
    assert payload["runtime_image"] == {
        "spec_id": "windows-server-2025-amd64",
        "os": "windows",
        "architecture": "amd64",
        "container_platform": "windows/amd64",
        "api_port": 8000,
        "liveness_paths": ["/alive", "/health"],
        "readiness_path": "/ready",
        "server_info_path": "/server_info",
        "workspace_mount_path": r"C:\workspace",
        "workspace_path": r"C:\workspace\project",
        "conversation_worktree_path": r"C:\workspace\worktrees",
        "durable_state_path": r"C:\OpenHands",
        "conversations_path": r"C:\OpenHands\conversations",
        "bash_events_path": r"C:\OpenHands\bash_events",
        "persistence_path": r"C:\OpenHands\persistence",
        "command_shell": "powershell.exe",
        "command_shell_args": ["-NoLogo", "-NoProfile"],
        "required_environment": ["OH_SESSION_API_KEYS_0", "OH_SECRET_KEY"],
        "resource_profiles": [
            profile.model_dump()
            for profile in runtime_contract.CURATED_RESOURCE_PROFILES
        ],
    }


def test_worktree_default_uses_host_temporary_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(config_module.tempfile, "gettempdir", lambda: str(tmp_path))

    assert default_conversation_worktree_root() == tmp_path / "conversation-worktrees"


def test_server_info_reports_configured_storage_paths(tmp_path: Path) -> None:
    config = Config(
        static_files_path=None,
        conversations_path=tmp_path / "conversations",
        bash_events_dir=tmp_path / "bash-events",
    )

    with TestClient(create_app(config)) as client:
        runtime_image = client.get("/server_info").json()["runtime_image"]

    assert runtime_image["conversations_path"] == str(config.conversations_path)
    assert runtime_image["bash_events_path"] == str(config.bash_events_dir)


def test_windows_dockerfile_declares_immutable_interface() -> None:
    dockerfile = (
        Path(__file__).parents[2]
        / "openhands-agent-server"
        / "openhands"
        / "agent_server"
        / "docker"
        / "Dockerfile.windows"
    ).read_text(encoding="utf-8")

    assert "windowsservercore-ltsc2025@sha256:" in dockerfile
    assert "servercore:ltsc2025@sha256:" in dockerfile
    assert "ARG MINGIT_URL=https://github.com/git-for-windows/" in dockerfile
    assert "MINGIT_SHA256=" in dockerfile
    assert "ARG P4_VERSION=2025.2" in dockerfile
    assert "ARG P4_BUILD=3086021" in dockerfile
    assert (
        "ARG P4_SHA256="
        "b40445fd623b885326d88f27d894b5078cda02a87589dd514925fc031ab2875b" in dockerfile
    )
    assert (
        "ARG P4_MCP_URL=https://github.com/perforce/p4mcp-server/releases/"
        "download/v2026.4.3126709/p4-mcp-server-win.zip" in dockerfile
    )
    assert "ARG P4_MCP_VERSION=2026.4.3126709" in dockerfile
    assert (
        "ARG P4_MCP_SHA256="
        "7e88b9c244616d5548f8939cb165136883ca3967c3726a7d47a7d963cc9ce879" in dockerfile
    )
    copilot_version = re.search(
        r"(?m)^ARG COPILOT_CLI_VERSION=(\d+\.\d+\.\d+)$", dockerfile
    )
    assert copilot_version
    assert (
        "ARG COPILOT_CLI_URL=https://github.com/github/copilot-cli/releases/"
        f"download/v{copilot_version.group(1)}/copilot-win32-x64.zip" in dockerfile
    )
    assert re.search(r"(?m)^ARG COPILOT_CLI_SHA256=[0-9a-f]{64}$", dockerfile)
    assert re.search(r"(?m)^ARG COPILOT_CLI_LICENSE_SHA256=[0-9a-f]{64}$", dockerfile)
    assert "ARG NODE_VERSION=24.22.2" in dockerfile
    assert (
        "ARG NODE_SHA256="
        "ca1bff5d8ead13c9f2ea404a176db46bd430704d5b5113734049fa365e7799e2" in dockerfile
    )
    assert "ARG NPM_VERSION=12.2.2" in dockerfile
    assert (
        "ARG ACP_NPM_ALLOW_SCRIPTS="
        "@moonshot-ai/kimi-code,opencode-ai,@github/keytar,node-pty,"
        "@google/genai,protobufjs" in dockerfile
    )
    assert (
        "ARG INSTALL_ACP_PROVIDERS=" + ",".join(WINDOWS_PREINSTALLED_ACP_PROVIDERS)
        in dockerfile
    )
    assert WINDOWS_PREINSTALLED_ACP_PROVIDERS == tuple(ACP_INSTALL_CATALOG)
    assert "--format json" in dockerfile
    assert "$env:Path = 'C:\\Node;' + $env:Path" in dockerfile
    assert "('--allow-scripts=' + $env:ACP_NPM_ALLOW_SCRIPTS)" in dockerfile
    assert "$binary + '.cmd'" in dockerfile
    assert "ARG POWERSHELL_VERSION=7.7.0" in dockerfile
    assert (
        "ARG POWERSHELL_SHA256="
        "7c74e03b20a75b59715847439d046a6214b1863ee79b187872980f139bb4a05f" in dockerfile
    )
    assert (
        "COPY openhands-agent-server\\openhands\\agent_server\\docker\\vendor\\"
        "perforce\\p4-2025.2.3086021.exe C:\\Perforce\\p4.exe" in dockerfile
    )
    assert "$env:P4_URL" not in dockerfile
    assert "throw 'p4.exe SHA256 verification failed'" in dockerfile
    assert "throw ('Unexpected p4.exe version: ' + $p4Version)" in dockerfile
    assert "throw 'p4-mcp-server SHA256 verification failed'" in dockerfile
    assert "throw 'Copilot CLI SHA256 verification failed'" in dockerfile
    assert "throw 'Copilot CLI license SHA256 verification failed'" in dockerfile
    assert "throw 'PowerShell SHA256 verification failed'" in dockerfile
    assert "C:\\PowerShell\\pwsh.exe -NoLogo -NoProfile -Version" in dockerfile
    assert "C:\\PowerShell\\pwsh.exe -NoLogo -NoProfile -Command" not in dockerfile
    assert "$versionText = ($version -join ' ').Trim()" in dockerfile
    assert "$version -notmatch" not in dockerfile
    assert '-join "`n"' not in dockerfile
    assert "C:\\Perforce\\p4.exe" in dockerfile
    assert "C:\\Perforce\\p4mcp\\p4-mcp-server.exe" in dockerfile
    assert "C:\\Perforce\\p4mcp\\logs" in dockerfile
    assert "C:\\Copilot\\copilot.exe --no-auto-update help acp" in dockerfile
    assert "C:\\PowerShell\\pwsh.exe" in dockerfile
    assert "'*S-1-5-93-2-1:(OI)(CI)RX'" in dockerfile
    assert "'*S-1-5-93-2-1:(OI)(CI)M'" in dockerfile
    assert (
        'ENV PATH="C:\\Copilot;C:\\ACP;C:\\Node;C:\\PowerShell;'
        "C:\\Perforce;C:\\Perforce\\p4mcp;"
        "C:\\MinGit\\cmd;C:\\MinGit\\mingw64\\bin;"
        "C:\\Windows\\System32;C:\\Windows;C:\\Windows\\System32\\Wbem;"
        'C:\\Windows\\System32\\WindowsPowerShell\\v1.0"' in dockerfile
    )
    assert "PERFORCE_NOTICES.md" in dockerfile
    assert "Perforce-p4-legal.txt" in dockerfile
    assert "$uri =" not in dockerfile
    assert "OH_RUNTIME_SPEC_ID=windows-server-2025-amd64" in dockerfile
    assert "OH_WORKSPACE_PATH=C:\\workspace\\project" in dockerfile
    assert "OH_RUNTIME_WORKSPACE_MOUNT_PATH=C:\\workspace" in dockerfile
    assert "OH_PERSISTENCE_DIR=C:\\OpenHands\\persistence" in dockerfile
    assert "OH_CONVERSATION_WORKTREE_ROOT=C:\\workspace\\worktrees" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "http://127.0.0.1:8000/ready" in dockerfile
    assert (
        'ENTRYPOINT ["C:\\\\AgentServer\\\\openhands-agent-server.exe"]' in dockerfile
    )


def test_vendored_p4_binary_matches_pinned_hash() -> None:
    binary = (
        Path(__file__).parents[2]
        / "openhands-agent-server"
        / "openhands"
        / "agent_server"
        / "docker"
        / "vendor"
        / "perforce"
        / "p4-2025.2.3086021.exe"
    )

    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()

    assert digest == "b40445fd623b885326d88f27d894b5078cda02a87589dd514925fc031ab2875b"


def test_windows_workflow_smokes_every_acp_shim_and_two_acp_transports() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "server.yml"
    ).read_text(encoding="utf-8")
    smoke_script = (
        Path(__file__).parents[2] / ".github" / "scripts" / "test_windows_acp.mjs"
    ).read_text(encoding="utf-8")

    for spec in ACP_INSTALL_CATALOG.values():
        executable = (
            "copilot.exe" if spec.key == "copilot-cli" else f"{spec.binary_name}.cmd"
        )
        assert f"Get-Command {executable} -ErrorAction Stop" in workflow

    assert "C:\\test_windows_acp.mjs `\n                        codex" in workflow
    assert "C:\\test_windows_acp.mjs `\n                        copilot" in workflow
    assert "throw 'Codex ACP initialize smoke failed.'" in workflow
    assert "throw 'Copilot ACP initialize smoke failed.'" in workflow
    assert 'method: "initialize"' in smoke_script
    assert "90_000" in smoke_script
    assert r"C:\ACP\codex-acp.cmd" in smoke_script
    assert r"C:\Copilot\copilot.exe" in smoke_script


def test_openapi_exports_runtime_image_contract() -> None:
    schema = create_app(Config(static_files_path=None)).openapi()
    components = schema["components"]["schemas"]
    server_info = components["ServerInfo"]
    runtime_image = components["RuntimeImageContract"]

    assert server_info["properties"]["runtime_image"] == {
        "$ref": "#/components/schemas/RuntimeImageContract"
    }
    assert {
        "spec_id",
        "container_platform",
        "workspace_mount_path",
        "workspace_path",
        "conversation_worktree_path",
        "durable_state_path",
        "conversations_path",
        "bash_events_path",
        "persistence_path",
        "command_shell",
        "resource_profiles",
    } <= runtime_image["properties"].keys()


def test_linux_dockerfile_declares_the_same_storage_split() -> None:
    dockerfile = (
        Path(__file__).parents[2]
        / "openhands-agent-server"
        / "openhands"
        / "agent_server"
        / "docker"
        / "Dockerfile"
    ).read_text(encoding="utf-8")

    assert "OH_RUNTIME_WORKSPACE_MOUNT_PATH=/workspace" in dockerfile
    assert "OH_WORKSPACE_PATH=/workspace/project" in dockerfile
    assert "OH_CONVERSATION_WORKTREE_ROOT=/workspace/worktrees" in dockerfile
    assert "OH_RUNTIME_DURABLE_STATE_PATH=/openhands" in dockerfile
    assert "OH_CONVERSATIONS_PATH=/openhands/conversations" in dockerfile
    assert "OH_BASH_EVENTS_DIR=/openhands/bash_events" in dockerfile
    assert "OH_PERSISTENCE_DIR=/openhands/persistence" in dockerfile


def test_windows_image_workflow_publishes_only_commit_addressed_tag() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "server.yml"
    ).read_text(encoding="utf-8")

    assert "windows_image_only:" in workflow
    assert "windows_image:" in workflow
    assert "windows_visibility_only:" in workflow
    assert "windows_existing_reference:" in workflow
    assert (
        "${{ inputs.windows_image }}:${{ github.sha }}-windows-ltsc2025-amd64"
    ) in workflow
    assert "default: ghcr.io/openhands/agent-server" in workflow
    assert "OPENHANDS_GHCR_TOKEN" in workflow
    assert "Verify anonymous manifest pull" in workflow
    assert "/user/packages/container/${PACKAGE_NAME}" in workflow
    assert "windows-server-2025, windows-containers" in workflow
    assert "Get-Command p4.exe -ErrorAction Stop" in workflow
    assert "Get-Command p4-mcp-server.exe -ErrorAction Stop" in workflow
    assert "Get-Command copilot.exe -ErrorAction Stop" in workflow
    assert "Get-Command pwsh.exe -ErrorAction Stop" in workflow
    assert "p4.exe -V" in workflow
    assert "p4-mcp-server.exe --help" in workflow
    assert "copilot.exe --no-auto-update help acp" in workflow
    assert "Select-Object -First 1" not in workflow
    assert "latest-windows" not in workflow
