import os
import platform
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ResourceSize(BaseModel):
    cpu: int = Field(gt=0)
    memory_gib: int = Field(gt=0)


class RuntimeResourceProfile(BaseModel):
    id: Literal["standard", "high-memory", "build"]
    minimum: ResourceSize
    recommended: ResourceSize


CURATED_RESOURCE_PROFILES = [
    RuntimeResourceProfile(
        id="standard",
        minimum=ResourceSize(cpu=2, memory_gib=4),
        recommended=ResourceSize(cpu=4, memory_gib=8),
    ),
    RuntimeResourceProfile(
        id="high-memory",
        minimum=ResourceSize(cpu=4, memory_gib=16),
        recommended=ResourceSize(cpu=8, memory_gib=32),
    ),
    RuntimeResourceProfile(
        id="build",
        minimum=ResourceSize(cpu=4, memory_gib=8),
        recommended=ResourceSize(cpu=8, memory_gib=16),
    ),
]


class RuntimeImageContract(BaseModel):
    spec_id: str
    os: Literal["linux", "windows", "macos", "unknown"]
    architecture: str
    container_platform: str
    api_port: int = Field(gt=0, le=65535)
    liveness_paths: list[str]
    readiness_path: str
    server_info_path: str
    workspace_mount_path: str
    workspace_path: str
    conversation_worktree_path: str
    durable_state_path: str | None
    conversations_path: str
    bash_events_path: str
    persistence_path: str | None
    command_shell: str
    command_shell_args: list[str]
    required_environment: list[str]
    resource_profiles: list[RuntimeResourceProfile]


def _runtime_os() -> Literal["linux", "windows", "macos", "unknown"]:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def _architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "amd64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or "unknown"


def build_runtime_image_contract(
    workspace_path: Path,
    conversation_worktree_path: Path,
    conversations_path: Path = Path("workspace/conversations"),
    bash_events_path: Path = Path("workspace/bash_events"),
) -> RuntimeImageContract:
    runtime_os = _runtime_os()
    architecture = _architecture()
    default_shell = "powershell.exe" if runtime_os == "windows" else "/bin/bash"
    shell_args = (
        ["-NoLogo", "-NoProfile"]
        if runtime_os == "windows"
        else ["--noprofile", "--norc"]
    )
    persistence_path = os.environ.get("OH_PERSISTENCE_DIR")

    return RuntimeImageContract(
        spec_id=os.environ.get(
            "OH_RUNTIME_SPEC_ID", f"{runtime_os}-native-{architecture}"
        ),
        os=runtime_os,
        architecture=architecture,
        container_platform=os.environ.get(
            "OH_RUNTIME_CONTAINER_PLATFORM", f"{runtime_os}/{architecture}"
        ),
        api_port=int(os.environ.get("OH_RUNTIME_API_PORT", "8000")),
        liveness_paths=["/alive", "/health"],
        readiness_path="/ready",
        server_info_path="/server_info",
        workspace_mount_path=os.environ.get(
            "OH_RUNTIME_WORKSPACE_MOUNT_PATH", str(workspace_path)
        ),
        workspace_path=str(workspace_path),
        conversation_worktree_path=str(conversation_worktree_path),
        durable_state_path=os.environ.get("OH_RUNTIME_DURABLE_STATE_PATH"),
        conversations_path=os.environ.get(
            "OH_CONVERSATIONS_PATH", str(conversations_path)
        ),
        bash_events_path=os.environ.get(
            "OH_BASH_EVENTS_DIR", str(bash_events_path)
        ),
        persistence_path=persistence_path,
        command_shell=os.environ.get("OH_RUNTIME_COMMAND_SHELL", default_shell),
        command_shell_args=shell_args,
        required_environment=["OH_SESSION_API_KEYS_0", "OH_SECRET_KEY"],
        resource_profiles=CURATED_RESOURCE_PROFILES,
    )
