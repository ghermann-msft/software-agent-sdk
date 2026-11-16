import sys
from pathlib import Path

from fastapi.testclient import TestClient

import openhands.agent_server.config as config_module
import openhands.agent_server.runtime_contract as runtime_contract
from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config, default_conversation_worktree_root


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
    assert "MINGIT_SHA256=" in dockerfile
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
    assert (
        "${{ inputs.windows_image }}:${{ github.sha }}"
        "-windows-ltsc2025-amd64"
    ) in workflow
    assert "default: ghcr.io/openhands/agent-server" in workflow
    assert "OPENHANDS_GHCR_TOKEN" in workflow
    assert "Verify anonymous manifest pull" in workflow
    assert "windows-server-2025, windows-containers" in workflow
    assert "latest-windows" not in workflow
