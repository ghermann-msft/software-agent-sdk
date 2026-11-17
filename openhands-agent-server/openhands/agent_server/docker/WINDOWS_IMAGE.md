# Windows Server 2025 Agent Server image

The native Windows image runs the existing Agent Server API in a Windows Server
2025 process-isolated container. It does not run a nested Windows guest.

## Immutable build contract

Build on a Windows Server 2025 container host:

```powershell
docker build `
  --file openhands-agent-server\openhands\agent_server\docker\Dockerfile.windows `
  --build-arg OPENHANDS_BUILD_GIT_SHA=(git rev-parse HEAD) `
  --build-arg OPENHANDS_BUILD_GIT_REF=(git symbolic-ref -q HEAD) `
  --tag ghcr.io/openhands/agent-server:$(git rev-parse --short HEAD)-windows-ltsc2025-amd64 `
  .
```

The Dockerfile pins the Python builder and Windows Server Core runtime by
manifest digest. It also pins MinGit, the official Helix Core command-line
client, and the official P4 MCP Server Windows release by URL and SHA-256.
Updating any of these inputs is an explicit image-contract change. Production
deployments must pin the resulting image digest rather than a mutable tag.

Linux and hosted Windows CI validate the Dockerfile contract, build the Windows
PyInstaller executable, and exercise the Windows terminal/file behavior. A real
image build requires a Docker host configured for Windows containers with a
Windows Server 2025-compatible kernel.

Dispatch the `Agent Server` workflow with `windows_image_only=true` to build,
smoke-test, and publish a commit-addressed image without creating or replacing
the Linux image aliases:

```text
ghcr.io/openhands/agent-server:<commit-sha>-windows-ltsc2025-amd64
```

The existing public Agent Server package permits anonymous AKS pulls. A workflow
running outside `OpenHands/software-agent-sdk` needs an
`OPENHANDS_GHCR_TOKEN` secret with `write:packages` access and OpenHands
organization authorization; a fork's `GITHUB_TOKEN` cannot publish this image.

The workflow first attempts GitHub's `windows-2025` runner. If that runner does
not expose a Windows Docker daemon, dispatch it with
`windows_runner_mode=self-hosted`. The fallback runner must have Docker
configured for Windows containers and all of these labels:

```text
self-hosted, Windows, X64, windows-server-2025, windows-containers
```

## Consumer interface

| Property | Value |
|---|---|
| Image tag suffix | `windows-ltsc2025-amd64` |
| OS/spec identifier | `windows-server-2025-amd64` |
| Container platform | `windows/amd64` |
| API port | `8000/tcp` |
| Liveness | `GET /alive` or `GET /health` |
| Readiness | `GET /ready` |
| Discovery | `GET /server_info` |
| Workspace mount | `C:\workspace` |
| Default working directory | `C:\workspace\project` |
| Worktree root | `C:\workspace\worktrees` |
| Durable state mount | `C:\OpenHands` |
| Command shell | `powershell.exe -NoLogo -NoProfile` |
| Required environment | `OH_SESSION_API_KEYS_0`, `OH_SECRET_KEY` |

Mount `C:\workspace` for project files; conversations start in
`C:\workspace\project` and git worktrees live in `C:\workspace\worktrees`.
Mount `C:\OpenHands` for conversations, settings, and bash events. This keeps
high-I/O checkout data separate from easily mounted durable metadata. Git for
Windows, `p4.exe`, and `p4-mcp-server.exe` are on `PATH` for `ContainerUser`.
The MCP server's log directory is writable without granting write access to the
executables. Browser and VSCode capabilities are intentionally absent from this
first minimal slice.

The image includes:

| Tool | Version/source | SHA-256 |
|---|---|---|
| `p4.exe` | [Helix Core CLI 2025.2 Windows x64](https://cdist2.perforce.com/perforce/r25.2/bin.ntx64/p4.exe) | `b40445fd623b885326d88f27d894b5078cda02a87589dd514925fc031ab2875b` |
| `p4-mcp-server.exe` | [P4 MCP Server 2026.4.3126709 Windows release](https://github.com/perforce/p4mcp-server/releases/download/v2026.4.3126709/p4-mcp-server-win.zip) | `7e88b9c244616d5548f8939cb165136883ca3967c3726a7d47a7d963cc9ce879` |

Perforce redistribution and dependency notices are stored at
`C:\AgentServer\licenses`. The checked-in source notice is
[`PERFORCE_NOTICES.md`](PERFORCE_NOTICES.md); the image build also records the
client's complete `p4 help -l legal` output as `Perforce-p4-legal.txt`.

The Linux image follows the same split: `/workspace`, `/workspace/project`, and
`/workspace/worktrees` are high-performance workspace paths; `/openhands`,
`/openhands/conversations`, `/openhands/bash_events`, and
`/openhands/persistence` are durable paths.

`/server_info` advertises `runtime_image_contract_v1` and
`native_windows_runtime_v1`. Its `runtime_image.resource_profiles` list is the
authoritative curated performance-class catalog:

| Profile | Minimum | Recommended |
|---|---|---|
| `standard` | 2 CPU, 4 GiB | 4 CPU, 8 GiB |
| `high-memory` | 4 CPU, 16 GiB | 8 CPU, 32 GiB |
| `build` | 4 CPU, 8 GiB | 8 CPU, 16 GiB |

The profile identifier is independent of OS. Orchestrators choose a curated
profile and enforce its resources; the SDK does not accept arbitrary CPU or
memory values.
