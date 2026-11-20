import os
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from acp.schema import McpServerStdio
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from openhands.agent_server.event_service import _with_hindsight_mcp_bridge
from openhands.agent_server.hindsight_mcp_bridge import (
    HINDSIGHT_MCP_SERVER_NAME,
    _bridge_command,
    create_bridge,
    create_hindsight_mcp_server,
    recall_memory,
    retain_memory,
)
from openhands.agent_server.hindsight_memory import HindsightMemorySpec
from openhands.sdk.agent import ACPAgent
from openhands.sdk.agent.acp_agent import _mcp_config_to_acp_servers
from openhands.sdk.context.memory_provider import (
    MemoryRecallResult,
    MemoryRetainResult,
    MemoryScope,
)


class _Provider:
    def __init__(self) -> None:
        self.recall_requests = []
        self.retain_requests = []

    def recall(self, request):
        self.recall_requests.append(request)
        return MemoryRecallResult.unavailable()

    def reflect(self, request):
        raise AssertionError("reflect was not requested")

    def retain(self, request):
        self.retain_requests.append(request)
        return MemoryRetainResult(
            event_id="retention-event-1",
            status="queued",
            duplicate=False,
        )


def _spec() -> HindsightMemorySpec:
    return HindsightMemorySpec(
        broker_url="http://memory-broker:8080",
        identity="signed-identity",
        scope=[
            MemoryScope(type="organization", id="org-halo-studios"),
            MemoryScope(type="private_user", id="user-1"),
        ],
    )


def test_bridge_command_preserves_packaged_windows_executable_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = r"C:\Program Files\OpenHands\agent-server.exe"
    monkeypatch.setattr(
        "openhands.agent_server.hindsight_mcp_bridge.sys.executable",
        executable,
    )
    monkeypatch.setattr(
        "openhands.agent_server.hindsight_mcp_bridge.sys.frozen",
        True,
        raising=False,
    )

    command, args = _bridge_command()

    assert command == executable
    assert args == ["--hindsight-mcp-bridge"]


def test_hindsight_bridge_is_forwarded_as_an_acp_stdio_server() -> None:
    conversation_id = uuid4()
    server = create_hindsight_mcp_server(_spec(), conversation_id)

    forwarded = _mcp_config_to_acp_servers(
        {HINDSIGHT_MCP_SERVER_NAME: server},
        SimpleNamespace(),
    )

    assert len(forwarded) == 1
    assert forwarded[0].name == HINDSIGHT_MCP_SERVER_NAME
    assert forwarded[0].command
    assert "--hindsight-mcp-bridge" in forwarded[0].args


@pytest.mark.asyncio
async def test_source_bridge_process_lists_memory_tools() -> None:
    server = create_hindsight_mcp_server(_spec(), uuid4())
    assert server.command is not None
    env = dict(os.environ)
    env.update(
        {name: value.get_secret_value() for name, value in (server.env or {}).items()}
    )
    transport = StdioTransport(
        command=server.command,
        args=server.args or [],
        env=env,
    )

    async with Client(transport) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == {"recall", "reflect", "retain"}


@pytest.mark.asyncio
async def test_bridge_tool_schemas_expose_only_semantic_arguments() -> None:
    mcp = create_bridge(_Provider(), uuid4())

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert set(tools) == {"recall", "reflect", "retain"}
    assert set(tools["recall"].parameters["properties"]) == {"query", "max_tokens"}
    assert set(tools["reflect"].parameters["properties"]) == {"query", "max_tokens"}
    assert set(tools["retain"].parameters["properties"]) == {"content"}
    forbidden = {"identity", "scope", "bank", "approval", "approval_token"}
    for tool in tools.values():
        assert forbidden.isdisjoint(tool.parameters["properties"])


def test_bridge_recall_remains_explicitly_untrusted_on_outage() -> None:
    provider = _Provider()

    result = recall_memory(
        provider,
        uuid4(),
        "How did we fix the timeout?",
        4096,
        source_event_id="mcp-request-1",
    )

    assert "Long-term memory is currently unavailable" in result
    assert provider.recall_requests[0].reason == "explicit"


def test_bridge_retain_keeps_content_verbatim_and_policy_fields_internal() -> None:
    provider = _Provider()
    conversation_id = uuid4()
    occurred_at = datetime(2026, 11, 19, tzinfo=UTC)
    content = "The reverse proxy idle timeout is 120 seconds."

    result = retain_memory(
        provider,
        conversation_id,
        content,
        source_event_id="mcp-request-1",
        occurred_at=occurred_at,
    )

    assert result == "Retention queued by the trusted broker."
    request = provider.retain_requests[0]
    assert request.conversation_id == conversation_id
    assert request.source_event_id == "mcp-request-1"
    assert request.occurred_at == occurred_at
    assert request.content == content
    assert not hasattr(request, "scope")
    assert not hasattr(request, "approval_token")


def test_acp_agent_receives_bridge_without_changing_original_config() -> None:
    agent = ACPAgent(acp_command=["copilot", "--acp"])

    configured = _with_hindsight_mcp_bridge(
        agent,
        spec=_spec(),
        conversation_id=uuid4(),
    )

    assert agent.mcp_config == {}
    assert HINDSIGHT_MCP_SERVER_NAME in configured.mcp_config


@pytest.mark.asyncio
async def test_windows_acp_agent_receives_launchable_hindsight_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = ACPAgent(acp_command=["copilot", "--acp"])

    with monkeypatch.context() as platform:
        platform.setattr("sys.platform", "win32")
        configured = _with_hindsight_mcp_bridge(
            agent,
            spec=_spec(),
            conversation_id=uuid4(),
        )

    assert agent.mcp_config == {}
    server = configured.mcp_config[HINDSIGHT_MCP_SERVER_NAME]
    assert server.command == sys.executable
    assert server.args == ["-m", "openhands.agent_server", "--hindsight-mcp-bridge"]
    forwarded = _mcp_config_to_acp_servers(
        {HINDSIGHT_MCP_SERVER_NAME: server},
        SimpleNamespace(),
    )
    assert len(forwarded) == 1
    stdio_server = forwarded[0]
    assert isinstance(stdio_server, McpServerStdio)
    assert stdio_server.command == server.command
    assert stdio_server.args == server.args

    env = dict(os.environ)
    env.update({item.name: item.value for item in stdio_server.env})
    transport = StdioTransport(
        command=stdio_server.command,
        args=stdio_server.args,
        env=env,
    )

    async with Client(transport) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == {"recall", "reflect", "retain"}
