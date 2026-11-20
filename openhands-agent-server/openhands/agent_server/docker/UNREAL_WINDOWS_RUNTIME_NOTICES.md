# Unreal Windows runtime notices

The Windows Agent Server image includes runtime prerequisites adapted from
Epic's Unreal Engine Windows container sample under
`Engine/Extras/Containers/Dockerfiles/windows/runtime`. The implementation
retains the OpenHands image, executable, and startup contract; it does not
redistribute the Epic sample image or its entrypoint. Use of the adapted
scaffolding requires an applicable Unreal Engine license.

## Microsoft Windows and DirectX components

The image copies selected Windows system DLLs from the digest-pinned
`mcr.microsoft.com/windows/server:ltsc2025` image into the matching
Windows Server Core LTSC 2025 runtime. These files remain subject to the
Microsoft container image and Windows license terms.

The legacy DirectX runtime DLLs come from Microsoft's **DirectX End-User
Runtimes (June 2010)**, version 9.29.1974.1, published July 15, 2024:

- URL:
  `https://download.microsoft.com/download/8/4/A/84A35BF1-DAFE-4AE8-82AF-AD2AE20B6B14/directx_Jun2010_redist.exe`
- SHA-256:
  `053f76dcbb28802e23341b6a787e3b0791c0fa5c8d4d011b1044172dbf89c73b`

The Visual C++ 2015-2022 x64 runtime is installed from Microsoft's immutable
Visual Studio download URL:

- Version: 14.44.35211.0
- SHA-256:
  `cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b`

Redistribution of the Visual C++ runtime is limited to licensed Visual Studio
users and is governed by the Microsoft Software License Terms.

## DirectX Shader Compiler

`dxcompiler.dll` and `dxil.dll` come from Microsoft's DirectX Shader Compiler
release `v1.6.2104`, published April 20, 2021:

- URL:
  `https://github.com/microsoft/DirectXShaderCompiler/releases/download/v1.6.2104/dxc_2021_04-20.zip`
- SHA-256:
  `ee5e96d58134957443ded04be132e2e19240c534d7602e3ab8fd5adc5156014a`

The archive's license is copied to
`C:\AgentServer\licenses\DirectXShaderCompiler-LICENSE.txt`.

## Python and Azure tools

The usable Python runtime is copied from the same digest-pinned official
`python:3.13.17-windowsservercore-ltsc2025` image that builds the frozen Agent
Server. Python 3.13.17 was published October 21, 2026.

Azure CLI `2.92.0` was published November 3, 2026. The official x64 archive is
older than the repository's seven-day dependency observation window:

- URL:
  `https://github.com/Azure/azure-cli/releases/download/azure-cli-2.92.0/azure-cli-2.92.0-x64.zip`
- SHA-256:
  `2cbd2c10e4b2ec4de2ab98eaa69f51fa4c9dfc4922b5116ada88091663d92af2`

The archive's `CLI_LICENSE.rtf` is copied to
`C:\AgentServer\licenses\Azure-CLI-LICENSE.rtf`.

AzCopy `10.34.1` was published October 22, 2026:

- URL:
  `https://github.com/Azure/azure-storage-azcopy/releases/download/v10.34.1/azcopy_windows_amd64_10.34.1.zip`
- SHA-256:
  `6d299fdf2dbf466167e9806576d15cb0de3c4ce8769caf5d1c1110877e5f66ff`

The archive's third-party notice is copied to
`C:\AgentServer\licenses\AzCopy-NOTICE.txt`.
