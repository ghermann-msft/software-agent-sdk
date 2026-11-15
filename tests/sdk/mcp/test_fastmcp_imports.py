def test_fastmcp_runtime_imports() -> None:
    from fastmcp.mcp_config import MCPConfig, RemoteMCPServer

    assert MCPConfig is not None
    assert RemoteMCPServer is not None
