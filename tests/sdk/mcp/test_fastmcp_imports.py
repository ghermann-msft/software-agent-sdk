def test_sdk_fastmcp_runtime_imports() -> None:
    from openhands.sdk.mcp.config import FastMCPConfig
    from openhands.sdk.mcp.utils import (
        FastMCPConfig as UtilsFastMCPConfig,
        RemoteMCPServer,
    )
    from openhands.sdk.skills.utils import MCPConfig as SkillsMCPConfig

    assert UtilsFastMCPConfig is FastMCPConfig
    assert SkillsMCPConfig is FastMCPConfig
    assert RemoteMCPServer is not None
