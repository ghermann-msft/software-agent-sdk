from openhands.agent_server.persistence import FileSettingsStore, PersistedSettings
from openhands.sdk.settings import OpenHandsAgentSettings


def _set_azure_llm_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "azure/gpt-5.6-sol")
    monkeypatch.setenv(
        "LLM_BASE_URL",
        "https://mortmain-openai2.openai.azure.com",
    )
    monkeypatch.setenv("LLM_API_VERSION", "2024-12-01-preview")
    monkeypatch.setenv("LLM_AUTH_TYPE", "azure_workload_identity")


def test_fresh_settings_use_deployment_llm_environment(monkeypatch) -> None:
    _set_azure_llm_env(monkeypatch)

    settings = PersistedSettings()

    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    llm = settings.agent_settings.llm
    assert llm.model == "azure/gpt-5.6-sol"
    assert llm.base_url == "https://mortmain-openai2.openai.azure.com"
    assert llm.api_version == "2024-12-01-preview"
    assert llm.auth_type == "azure_workload_identity"
    assert llm.api_key is None


def test_persisted_sdk_defaults_adopt_deployment_llm_environment(
    monkeypatch, tmp_path
) -> None:
    store = FileSettingsStore(tmp_path)
    store.save(PersistedSettings())
    _set_azure_llm_env(monkeypatch)

    settings = store.load()

    assert settings is not None
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    assert settings.agent_settings.llm.model == "azure/gpt-5.6-sol"
    assert settings.agent_settings.llm.auth_type == "azure_workload_identity"


def test_persisted_llm_override_wins_over_deployment_environment(monkeypatch) -> None:
    persisted = PersistedSettings().model_dump(mode="json")
    persisted["agent_settings"]["llm"]["model"] = "anthropic/claude-sonnet-4-5"
    _set_azure_llm_env(monkeypatch)

    settings = PersistedSettings.from_persisted(persisted)

    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    assert settings.agent_settings.llm.model == "anthropic/claude-sonnet-4-5"
    assert settings.agent_settings.llm.auth_type == "api_key"
