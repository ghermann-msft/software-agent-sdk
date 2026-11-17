from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from openhands.agent_server.event_service import EventService
from openhands.agent_server.hindsight_memory import (
    HindsightBrokerMemoryProvider,
    HindsightMemorySpec,
)
from openhands.agent_server.models import StoredConversation
from openhands.sdk import LLM, Agent
from openhands.sdk.context.memory_provider import (
    MemoryRecallRequest,
    MemoryReflectRequest,
    MemoryScope,
)
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.workspace import LocalWorkspace


def test_hindsight_provider_sends_trusted_identity_scope_and_provenance(
    monkeypatch,
) -> None:
    captured: dict = {}

    def post(url, *, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "memories": [
                    {
                        "source_memory_id": "memory-1",
                        "source_event_id": "event-1",
                        "source_conversation_id": "conversation-1",
                        "date": datetime(2026, 11, 17, tzinfo=UTC).isoformat(),
                        "scope": [{"type": "private_user", "id": "user-1"}],
                        "relevance": 0.9,
                        "uncertainty": 0.1,
                        "content": "Use focused tests.",
                    }
                ]
            },
        )

    monkeypatch.setattr("openhands.agent_server.hindsight_memory.httpx.post", post)
    conversation_id = uuid4()
    provider = HindsightBrokerMemoryProvider(
        HindsightMemorySpec(
            broker_url="http://memory-broker:8080",
            identity="identity-1",
            scope=[
                MemoryScope(type="server", id="deployment-1"),
                MemoryScope(type="organization", id="org-halo-studios"),
                MemoryScope(type="repository", id="OpenHands/software-agent-sdk"),
                MemoryScope(type="workspace", id="workspace-1"),
                MemoryScope(type="private_user", id="user-1"),
            ],
        )
    )

    result = provider.recall(
        MemoryRecallRequest(
            conversation_id=conversation_id,
            source_event_id="current-event",
            query="How should this be tested?",
            max_tokens=1024,
            reason="new_task",
        )
    )

    assert result.available
    assert result.memories[0].source_memory_id == "memory-1"
    assert captured["url"] == ("http://memory-broker:8080/api/v1/hindsight/recall")
    assert captured["json"] == {
        "identity": "identity-1",
        "scope": [
            {"type": "server", "id": "deployment-1"},
            {"type": "organization", "id": "org-halo-studios"},
            {"type": "repository", "id": "OpenHands/software-agent-sdk"},
            {"type": "workspace", "id": "workspace-1"},
            {"type": "private_user", "id": "user-1"},
        ],
        "conversation_id": str(conversation_id),
        "source_event_id": "current-event",
        "query": "How should this be tested?",
        "max_tokens": 1024,
        "reason": "new_task",
    }


def test_hindsight_provider_degrades_invalid_response_to_unavailable(
    monkeypatch,
) -> None:
    def post(url, *, json, timeout):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"content": ["not", "a", "string"]},
        )

    monkeypatch.setattr("openhands.agent_server.hindsight_memory.httpx.post", post)
    provider = HindsightBrokerMemoryProvider(
        HindsightMemorySpec(
            broker_url="http://memory-broker:8080",
            identity="identity-1",
        )
    )

    result = provider.reflect(
        MemoryReflectRequest(
            conversation_id=uuid4(),
            query="Reflect on prior decisions.",
            max_tokens=4096,
        )
    )

    assert not result.available
    assert result.content is None


def test_hindsight_spec_exposes_one_trusted_active_organization() -> None:
    spec = HindsightMemorySpec(
        broker_url="http://memory-broker:8080",
        identity="identity-1",
        scope=[
            MemoryScope(type="server", id="deployment-1"),
            MemoryScope(type="organization", id="org-personal-user-1"),
            MemoryScope(type="private_user", id="user-1"),
        ],
    )

    assert spec.organization_id == "org-personal-user-1"

    with pytest.raises(ValueError, match="only one active organization"):
        HindsightMemorySpec(
            broker_url="http://memory-broker:8080",
            identity="identity-1",
            scope=[
                MemoryScope(type="organization", id="org-personal-user-1"),
                MemoryScope(type="organization", id="org-halo-studios"),
            ],
        )


@pytest.mark.asyncio
async def test_event_service_wires_hindsight_provider_to_local_conversation(
    tmp_path,
) -> None:
    spec = HindsightMemorySpec(
        broker_url="http://memory-broker:8080",
        identity="identity-1",
    )
    event_service = EventService(
        stored=StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir=str(tmp_path)),
        ),
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        conversations_dir=tmp_path / "conversations",
        hindsight_memory=spec,
    )

    with patch(
        "openhands.agent_server.event_service.LocalConversation"
    ) as mock_conversation_class:
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.IDLE
        state.events = []
        agent = MagicMock()
        agent.get_all_llms.return_value = []
        conversation._state = state
        conversation.state = state
        conversation.agent = agent
        conversation._on_event = MagicMock()
        mock_conversation_class.return_value = conversation

        await event_service.start()

        provider = mock_conversation_class.call_args.kwargs["memory_provider"]
        assert isinstance(provider, HindsightBrokerMemoryProvider)
