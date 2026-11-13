from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse
from pydantic import ValidationError

from openhands.sdk.llm import LLM
from openhands.sdk.llm.llm import AZURE_OPENAI_SCOPE


def _chat_response() -> ModelResponse:
    return ModelResponse(
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content="ok", role="assistant"),
            )
        ],
        model="azure/deployment",
    )


@patch("openhands.sdk.llm.llm.get_bearer_token_provider")
@patch("openhands.sdk.llm.llm.DefaultAzureCredential")
@patch("openhands.sdk.llm.llm.litellm_completion")
def test_workload_identity_injected_into_chat_completion(
    mock_completion: Mock,
    mock_credential_class: Mock,
    mock_get_provider: Mock,
) -> None:
    credential = Mock()
    token_provider = Mock(return_value="token")
    mock_credential_class.return_value = credential
    mock_get_provider.return_value = token_provider
    mock_completion.return_value = _chat_response()
    llm = LLM(
        model="azure/deployment",
        auth_type="azure_workload_identity",
    )

    llm._transport_call(
        messages=[{"role": "user", "content": "hello"}],
        api_key="caller-api-key",
        azure_ad_token="static-token",
    )

    kwargs = mock_completion.call_args.kwargs
    assert kwargs["azure_ad_token_provider"] is token_provider
    assert "api_key" not in kwargs
    assert "azure_ad_token" not in kwargs
    mock_credential_class.assert_called_once_with()
    mock_get_provider.assert_called_once_with(credential, AZURE_OPENAI_SCOPE)


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.get_bearer_token_provider")
@patch("openhands.sdk.llm.llm.DefaultAzureCredential")
@patch("openhands.sdk.llm.llm.litellm_acompletion", new_callable=AsyncMock)
async def test_workload_identity_injected_into_async_chat_completion(
    mock_completion: AsyncMock,
    mock_credential_class: Mock,
    mock_get_provider: Mock,
) -> None:
    token_provider = Mock(return_value="token")
    mock_get_provider.return_value = token_provider
    mock_completion.return_value = _chat_response()
    llm = LLM(
        model="azure/deployment",
        auth_type="azure_workload_identity",
    )

    await llm._atransport_call(messages=[{"role": "user", "content": "hello"}])

    assert mock_completion.call_args.kwargs["azure_ad_token_provider"] is token_provider
    assert "api_key" not in mock_completion.call_args.kwargs
    mock_credential_class.assert_called_once_with()


@patch("openhands.sdk.llm.llm.get_bearer_token_provider")
@patch("openhands.sdk.llm.llm.DefaultAzureCredential")
def test_workload_identity_injected_into_responses_calls(
    mock_credential_class: Mock,
    mock_get_provider: Mock,
) -> None:
    token_provider = Mock(return_value="token")
    mock_get_provider.return_value = token_provider
    llm = LLM(
        model="azure/deployment",
        auth_type="azure_workload_identity",
    )

    kwargs = llm._build_responses_call_kwargs(
        input_items=[],
        instructions=None,
        resp_tools=None,
        final_kwargs={
            "api_key": "caller-api-key",
            "azure_ad_token": "static-token",
        },
    )
    second_kwargs = llm._build_responses_call_kwargs(
        input_items=[],
        instructions=None,
        resp_tools=None,
        final_kwargs={},
    )

    assert kwargs["azure_ad_token_provider"] is token_provider
    assert second_kwargs["azure_ad_token_provider"] is token_provider
    assert "api_key" not in kwargs
    assert "azure_ad_token" not in kwargs
    mock_credential_class.assert_called_once_with()
    mock_get_provider.assert_called_once()


@patch("openhands.sdk.llm.llm.get_bearer_token_provider")
@patch("openhands.sdk.llm.llm.DefaultAzureCredential")
def test_workload_identity_provider_creation_failure_is_not_cached(
    mock_credential_class: Mock,
    mock_get_provider: Mock,
) -> None:
    error = RuntimeError("workload identity unavailable")
    token_provider = Mock(return_value="token")
    mock_get_provider.side_effect = [error, token_provider]
    llm = LLM(
        model="azure/deployment",
        auth_type="azure_workload_identity",
    )

    with pytest.raises(RuntimeError, match="workload identity unavailable"):
        llm._prepare_transport_kwargs(messages=[], enable_streaming=False)

    kwargs = llm._prepare_transport_kwargs(messages=[], enable_streaming=False)

    assert kwargs["azure_ad_token_provider"] is token_provider
    assert "api_key" not in kwargs
    assert mock_credential_class.call_count == 2
    assert mock_get_provider.call_count == 2


@patch("openhands.sdk.llm.llm.DefaultAzureCredential")
def test_api_key_auth_is_unchanged(mock_credential_class: Mock) -> None:
    llm = LLM(model="azure/deployment", api_key="api-key")

    chat_kwargs = llm._prepare_transport_kwargs(
        messages=[],
        enable_streaming=False,
    )
    responses_kwargs = llm._build_responses_call_kwargs(
        input_items=[],
        instructions=None,
        resp_tools=None,
        final_kwargs={},
    )

    assert chat_kwargs["api_key"] == "api-key"
    assert responses_kwargs["api_key"] == "api-key"
    assert "azure_ad_token_provider" not in chat_kwargs
    assert "azure_ad_token_provider" not in responses_kwargs
    mock_credential_class.assert_not_called()


@pytest.mark.parametrize(
    "config",
    [
        {"model": "openai/gpt-4o"},
        {"model": "azure/deployment", "api_key": "api-key"},
        {"model": "azure/deployment", "provider_connection_id": "connection"},
        {"model": "azure/deployment", "subscription_vendor": "openai"},
        {"model": "azure/deployment", "is_subscription": True},
    ],
)
def test_workload_identity_rejects_incompatible_configuration(
    config: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        LLM(auth_type="azure_workload_identity", **config)


def test_workload_identity_persistence_round_trip() -> None:
    llm = LLM(
        model="azure/deployment",
        auth_type="azure_workload_identity",
        base_url="https://example.openai.azure.com",
    )

    restored = LLM.from_persisted(llm.to_persisted())

    assert restored.model == llm.model
    assert restored.auth_type == "azure_workload_identity"
    assert restored.base_url == llm.base_url
    assert restored.api_key is None


def test_workload_identity_json_schema_and_serialized_validation() -> None:
    auth_schema = LLM.model_json_schema()["properties"]["auth_type"]
    assert "azure_workload_identity" in auth_schema["enum"]

    llm = LLM.model_validate_json(
        """
        {
          "model": "azure/gpt-5.6-sol",
          "base_url": "https://mortmain-openai2.openai.azure.com/",
          "api_version": "2025-03-01-preview",
          "auth_type": "azure_workload_identity"
        }
        """
    )

    assert llm.auth_type == "azure_workload_identity"
    assert llm.api_key is None
