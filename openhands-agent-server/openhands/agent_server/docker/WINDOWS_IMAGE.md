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

The Dockerfile pins the Python builder, Windows Server Core runtime, and
matching full Windows Server DLL source by manifest digest. MinGit, the
official P4 MCP Server, DirectX Shader Compiler, Azure CLI, AzCopy, and the
legacy DirectX redist use versioned URLs and SHA-256 verification. The Visual
C++ runtime uses Microsoft's immutable content-addressed URL. The official
Helix Core command-line client is vendored as a Perforce-signed,
SHA-256-pinned binary because Perforce's release-line download URL is mutable.
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
Windows, Python, Azure CLI (`az`), AzCopy, `p4.exe`, and `p4-mcp-server.exe`
are on `PATH` for `ContainerUser`. The MCP server's log directory is writable
without granting write access to the executables. Browser and VSCode
capabilities are intentionally absent from this first minimal slice.

The image also contains the Windows multimedia, legacy DirectX, DXC/DXR, and
Visual C++ runtime files required by Unreal Engine Windows applications. Before
the Agent Server starts, its existing executable runs the configured GPU
bootstrap script. The script copies NVIDIA or AMD user-mode API DLLs from
`HostDriverStore` into the writable, image-local `C:\AgentServer\gpu` directory
on `PATH` when the container was started with GPU support. Each DLL is staged
under a unique temporary name and atomically moved into place, so repeated or
concurrent startup cannot expose a partial copy. If `HostDriverStore` is absent,
the script exits successfully and normal headless Agent Server operation is
unchanged.

To expose a compatible GPU to a process-isolated Windows container, use the
device class documented by Microsoft:

```powershell
docker run `
  --isolation process `
  --device class/5B45201D-F2F2-4F3B-85BB-30FF1F953599 `
  ghcr.io/openhands/agent-server:<commit-sha>-windows-ltsc2025-amd64
```

The image includes:

| Tool | Version/source | SHA-256 |
|---|---|---|
| `python.exe` | Python 3.13.17 from the digest-pinned official Windows builder image | Image digest pinned in `Dockerfile.windows` |
| `az.cmd` | [Azure CLI 2.92.0 x64 archive](https://github.com/Azure/azure-cli/releases/download/azure-cli-2.92.0/azure-cli-2.92.0-x64.zip) | `2cbd2c10e4b2ec4de2ab98eaa69f51fa4c9dfc4922b5116ada88091663d92af2` |
| `azcopy.exe` | [AzCopy 10.34.1 Windows x64 archive](https://github.com/Azure/azure-storage-azcopy/releases/download/v10.34.1/azcopy_windows_amd64_10.34.1.zip) | `6d299fdf2dbf466167e9806576d15cb0de3c4ce8769caf5d1c1110877e5f66ff` |
| `p4.exe` | Helix Core CLI 2025.2 build 3086021 Windows x64, vendored from the [official Perforce distribution](https://cdist2.perforce.com/perforce/r25.2/bin.ntx64/p4.exe) | `b40445fd623b885326d88f27d894b5078cda02a87589dd514925fc031ab2875b` |
| `p4-mcp-server.exe` | [P4 MCP Server 2026.4.3126709 Windows release](https://github.com/perforce/p4mcp-server/releases/download/v2026.4.3126709/p4-mcp-server-win.zip) | `7e88b9c244616d5548f8939cb165136883ca3967c3726a7d47a7d963cc9ce879` |

Perforce redistribution and dependency notices are stored at
`C:\AgentServer\licenses`. The checked-in source notice is
[`PERFORCE_NOTICES.md`](PERFORCE_NOTICES.md); the image build also records the
client's complete `p4 help -l legal` output as `Perforce-p4-legal.txt`.
Unreal runtime, DirectX, Python, Azure CLI, AzCopy, and Visual C++ provenance is
recorded in
[`UNREAL_WINDOWS_RUNTIME_NOTICES.md`](UNREAL_WINDOWS_RUNTIME_NOTICES.md).

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
