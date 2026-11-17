"""LocalConversation lazily resolves persistent memory (``AgentContext.load_memory``).

Memory resolution mirrors project skills: AgentContext cannot read the
workspace at validation time, so LocalConversation loads the MEMORY.md indexes
on the first ``send_message()`` and the result lands in the SystemPromptEvent.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.context.memory import MEMORY_INDEX_RELPATH
from openhands.sdk.context.memory_provider import (
    ADAPTIVE_RECALL_TOKEN_BUDGET,
    AUTOMATIC_RECALL_TOKEN_BUDGET,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemoryRecord,
)
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import MessageEvent, SystemPromptEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep the user memory tier (``~/.openhands/memory/``) off the host home."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # USERPROFILE is what Path.home() reads on Windows, where HOME is a no-op.
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _agent(agent_context: AgentContext) -> Agent:
    return Agent(
        llm=TestLLM.from_messages(
            [Message(role="assistant", content=[TextContent(text="ok")])],
            model="test-model",
        ),
        tools=[],
        include_default_tools=[],
        agent_context=agent_context,
    )


def _write_memory_index(workspace: Path, text: str) -> None:
    index = workspace / MEMORY_INDEX_RELPATH
    index.parent.mkdir(parents=True)
    index.write_text(text)


def _system_prompt_event(
    tmp_path: Path, agent_context: AgentContext
) -> SystemPromptEvent:
    conversation = LocalConversation(
        agent=_agent(agent_context),
        workspace=tmp_path / "workspace",
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    try:
        conversation.send_message("hi")
        return next(
            e for e in conversation.state.events if isinstance(e, SystemPromptEvent)
        )
    finally:
        conversation.close()


def test_load_memory_flag_injects_memory_into_system_prompt(tmp_path: Path):
    workspace = tmp_path / "workspace"
    _write_memory_index(workspace, "- SENTINEL_MEMORY_789\n")

    event = _system_prompt_event(tmp_path, AgentContext(load_memory=True))

    assert event.dynamic_context is not None
    assert "<MEMORY_CONTEXT>" in event.dynamic_context.text
    assert "SENTINEL_MEMORY_789" in event.dynamic_context.text
    assert "persistent memory that survives across sessions" in event.system_prompt.text


def test_load_memory_flag_off_ignores_memory_files(tmp_path: Path):
    workspace = tmp_path / "workspace"
    _write_memory_index(workspace, "- SENTINEL_MEMORY_789\n")

    event = _system_prompt_event(tmp_path, AgentContext())

    dynamic = event.dynamic_context.text if event.dynamic_context else ""
    assert "SENTINEL_MEMORY_789" not in dynamic
    assert "<MEMORY_CONTEXT>" not in dynamic
    assert "Use `AGENTS.md` under the repository root" in event.system_prompt.text


def test_load_memory_without_memory_files_is_noop(tmp_path: Path):
    (tmp_path / "workspace").mkdir()

    event = _system_prompt_event(tmp_path, AgentContext(load_memory=True))

    dynamic = event.dynamic_context.text if event.dynamic_context else ""
    assert "<MEMORY_CONTEXT>" not in dynamic


def test_load_memory_failure_does_not_prevent_startup(tmp_path: Path):
    workspace = tmp_path / "workspace"
    _write_memory_index(workspace, "- SENTINEL_MEMORY_789\n")

    with patch(
        "openhands.sdk.conversation.impl.local_conversation.load_memory",
        side_effect=OSError("disk error"),
    ):
        event = _system_prompt_event(tmp_path, AgentContext(load_memory=True))

    dynamic = event.dynamic_context.text if event.dynamic_context else ""
    assert "<MEMORY_CONTEXT>" not in dynamic


def test_broker_memory_recalls_at_task_boundaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Provider:
        def __init__(self) -> None:
            self.requests: list[MemoryRecallRequest] = []

        def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
            self.requests.append(request)
            return MemoryRecallResult(
                memories=(
                    MemoryRecord(
                        source_memory_id=f"memory-{len(self.requests)}",
                        source_event_id="source-event",
                        source_conversation_id="source-conversation",
                        date=datetime(2026, 11, 17, tzinfo=UTC),
                        scope=(),
                        relevance=0.9,
                        uncertainty=0.1,
                        content=f"recalled for {request.reason}",
                    ),
                )
            )

        def reflect(self, request):
            raise AssertionError("reflect should not be called")

    monkeypatch.setattr(
        "openhands.sdk.conversation.impl.local_conversation.sys.platform",
        "linux",
    )
    provider = Provider()
    conversation = LocalConversation(
        agent=_agent(AgentContext()),
        workspace=tmp_path / "workspace",
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
        memory_provider=provider,
    )
    try:
        conversation.send_message("Fix the authentication timeout in the API")
        conversation.send_message("Fix the authentication timeout in the API please")
        conversation.send_message(
            "Now redesign the database migration rollback strategy"
        )

        user_events = [
            event
            for event in conversation.state.events
            if isinstance(event, MessageEvent) and event.source == "user"
        ]
        tool_names = set(conversation.agent.tools_map)
    finally:
        conversation.close()

    assert [request.reason for request in provider.requests] == [
        "new_task",
        "material_change",
    ]
    assert [request.max_tokens for request in provider.requests] == [
        AUTOMATIC_RECALL_TOKEN_BUDGET,
        ADAPTIVE_RECALL_TOKEN_BUDGET,
    ]
    assert "recalled for new_task" in user_events[0].extended_content[0].text
    assert user_events[1].extended_content == []
    assert "recalled for material_change" in user_events[2].extended_content[0].text
    assert {"recall_memory", "reflect_memory"} <= tool_names


def test_broker_memory_outage_does_not_block_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Provider:
        def recall(self, request):
            raise OSError("broker unavailable")

        def reflect(self, request):
            raise AssertionError("reflect should not be called")

    monkeypatch.setattr(
        "openhands.sdk.conversation.impl.local_conversation.sys.platform",
        "linux",
    )
    conversation = LocalConversation(
        agent=_agent(AgentContext()),
        workspace=tmp_path / "workspace",
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
        memory_provider=Provider(),
    )
    try:
        conversation.send_message("Investigate the production deployment failure")
        event = next(
            event
            for event in conversation.state.events
            if isinstance(event, MessageEvent) and event.source == "user"
        )
    finally:
        conversation.close()

    assert "Long-term memory is currently unavailable" in event.extended_content[0].text


def test_broker_memory_is_disabled_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Provider:
        def recall(self, request):
            raise AssertionError("Windows conversations must not call memory")

        def reflect(self, request):
            raise AssertionError("Windows conversations must not call memory")

    monkeypatch.setattr(
        "openhands.sdk.conversation.impl.local_conversation.sys.platform",
        "win32",
    )
    conversation = LocalConversation(
        agent=_agent(AgentContext()),
        workspace=tmp_path / "workspace",
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
        memory_provider=Provider(),
    )
    try:
        conversation.send_message("Investigate the production deployment failure")
        event = next(
            event
            for event in conversation.state.events
            if isinstance(event, MessageEvent) and event.source == "user"
        )
        tool_names = set(conversation.agent.tools_map)
    finally:
        conversation.close()

    assert event.extended_content == []
    assert "recall_memory" not in tool_names
    assert "reflect_memory" not in tool_names


def test_fork_preserves_broker_memory_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Provider:
        def __init__(self) -> None:
            self.requests: list[MemoryRecallRequest] = []

        def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult:
            self.requests.append(request)
            return MemoryRecallResult()

        def reflect(self, request):
            raise AssertionError("reflect should not be called")

    monkeypatch.setattr(
        "openhands.sdk.conversation.impl.local_conversation.sys.platform",
        "linux",
    )
    provider = Provider()
    conversation = LocalConversation(
        agent=_agent(AgentContext()),
        workspace=tmp_path / "workspace",
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
        memory_provider=provider,
    )
    fork = None
    try:
        conversation.send_message("Investigate the production deployment failure")
        fork = conversation.fork()
        fork.send_message("Continue the production deployment investigation")
    finally:
        if fork is not None:
            fork.close()
        conversation.close()

    assert len(provider.requests) == 2
    assert provider.requests[0].conversation_id != provider.requests[1].conversation_id
    assert provider.requests[1].reason == "new_task"
